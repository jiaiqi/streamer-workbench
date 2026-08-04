"""R2 P3 RequestPolicyService——请求资格与插队决策。

决策维度 (v3 §6.4)：
- 高价值礼物 → 解锁「申请插队」，**不是**自动插队
- 主播确认 → 保存 original_position + target_position + reason + confirmed_at
- 插队后保持当前正在演唱的歌曲不动
- 公平保护: 连续插队达到上限后，至少处理一条普通队列；触发时说明「已达插队上限」，允许主播覆盖但需要原因
- 同权益、相同 command_id 不能重复核销

约束：
- rule_version 是**当前**活跃规则快照；修改后不回写历史
- 单次决策返回 PolicyDecision (allowed / requires_broadcaster_confirmation / degraded)
- bump_position(decision): 计算插入位置；保持当前歌曲不动
"""
from __future__ import annotations

from dataclasses import dataclass

from core.data.live import (
    PolicyDecision,
    RequestPolicy,
)


# 哪些权益「解锁插队申请」而非自动插队——可配置列表的简化表达
BUMP_UNLOCK_KINDS = frozenset({"high_value_gift", "manual_bump"})


class RequestPolicyServiceError(Exception):
    """可由 HTTP 适配层稳定映射。"""


class UnknownEntitlementKind(RequestPolicyServiceError):
    pass


@dataclass(frozen=True)
class QueueSnapshot:
    """决策时的队列快照。

    M2.4 新增 3 字段（用于 cooldown / max_queue / per_song / per_user 决策）：
    - cooldown_seconds_remaining: 同用户最近一次入队到现在的秒数，None = 同用户无历史
    - per_user_in_queue: 该用户当前在队列里的条数
    - per_song_in_session: 该歌曲当前在队列 + 已演唱累计数（已唱也计，防止刷榜）
    """

    queue_size: int = 0          # 当前队尾已加入数
    current_song_position: int = 0  # 当前演唱歌曲位置（不可替换）
    recent_bumps_in_a_row: int = 0   # 最近连续插队计数（不含当前/过去插队）
    # M2.4 三个统计字段
    cooldown_seconds_remaining: float | None = None  # 距上次同用户入队秒数；None=无历史
    per_user_in_queue: int = 0                       # 该用户当前在队条数
    per_song_in_session: int = 0                     # 该歌本场累计条数（含已唱）


class RequestPolicyService:
    """决策应用服务。"""

    def __init__(self, *, policy: RequestPolicy):
        self._policy = policy

    @property
    def rule_version(self) -> str:
        return self._policy.rule_version

    @property
    def policy(self) -> RequestPolicy:
        return self._policy

    # ── 主决策入口 ──

    def decide_queue(
        self,
        *,
        entitlement_kind: str,
        snapshot: QueueSnapshot,
        operator: str = "broadcaster",
    ) -> PolicyDecision:
        """为一次入队请求做决策。

        Args:
            entitlement_kind: 权益类型
              - "fan_join" / "member_daily" / "gift_exchange" / "campaign": 普通权益入队尾
              - "manual_add": 主播直接加歌（不核销）
              - "manual_bump" / "high_value_gift": 申请插队（主播确认）
            snapshot: 当前队尾/正在演唱/连续插队计数

        Returns:
            PolicyDecision (allowed, requires_broadcaster_confirmation, degraded, reason)
        """
        # 空 kind 视为主播手动加歌 — 不消耗额度（也不走点歌条件冷却/上限）
        kind = entitlement_kind or "manual_add"

        # M2.4 点歌条件：4 检查（0=不限；主播手动加跳过）
        if kind != "manual_add":
            m2_4 = self._check_m2_4_conditions(kind=kind, snapshot=snapshot)
            if m2_4 is not None:
                return m2_4

        # 普通手动加：不需要确认
        if kind in {"manual_add"}:
            return PolicyDecision(
                allowed=True,
                requires_broadcaster_confirmation=False,
                rule_version=self._policy.rule_version,
            )

        # 普通权益（队尾入队）
        if kind in {"fan_join", "member_daily", "gift_exchange", "campaign"}:
            return PolicyDecision(
                allowed=True,
                requires_broadcaster_confirmation=False,
                rule_version=self._policy.rule_version,
            )

        # 插队权益（需主播确认）
        if kind in BUMP_UNLOCK_KINDS:
            # 公平保护触发
            if snapshot.recent_bumps_in_a_row >= self._policy.fairness_max_consecutive_bumps:
                return PolicyDecision(
                    allowed=True,
                    requires_broadcaster_confirmation=True,
                    rule_version=self._policy.rule_version,
                    degraded=True,
                    reason=(
                        f"已达连续插队上限 {self._policy.fairness_max_consecutive_bumps}；"
                        "需要主播提供原因"
                    ),
                )
            return PolicyDecision(
                allowed=True,
                requires_broadcaster_confirmation=True,
                rule_version=self._policy.rule_version,
            )

        raise UnknownEntitlementKind(f"未知 entitlement_kind：{entitlement_kind}")

    def _check_m2_4_conditions(
        self, *, kind: str, snapshot: QueueSnapshot,
    ) -> PolicyDecision | None:
        """M2.4 点歌条件检查。返回 None 表示通过；返回 PolicyDecision(allowed=False) 表示拒绝。

        检查顺序（按「业务严重度」从高到低）：
        1. max_queue_length — 队列满
        2. per_song_max_per_session — 单歌被点超限
        3. per_user_max_in_queue — 单用户霸屏
        4. cooldown_seconds_per_user — 冷却中
        """
        p = self._policy

        # 1) 队列总长上限
        if p.max_queue_length > 0 and snapshot.queue_size >= p.max_queue_length:
            return PolicyDecision(
                allowed=False,
                reason=f"队列已满（{snapshot.queue_size}/{p.max_queue_length}）",
                rule_version=p.rule_version,
            )

        # 2) 单歌累计上限
        if p.per_song_max_per_session > 0 and snapshot.per_song_in_session >= p.per_song_max_per_session:
            return PolicyDecision(
                allowed=False,
                reason=f"本场这首歌已被点 {snapshot.per_song_in_session} 次，达到上限 {p.per_song_max_per_session}",
                rule_version=p.rule_version,
            )

        # 3) 单用户已点上限
        if p.per_user_max_in_queue > 0 and snapshot.per_user_in_queue >= p.per_user_max_in_queue:
            return PolicyDecision(
                allowed=False,
                reason=f"你已在队列里有 {snapshot.per_user_in_queue} 首，达到上限 {p.per_user_max_in_queue}",
                rule_version=p.rule_version,
            )

        # 4) 冷却（仅对非主播手动加）
        if (p.cooldown_seconds_per_user > 0
                and snapshot.cooldown_seconds_remaining is not None
                and snapshot.cooldown_seconds_remaining < p.cooldown_seconds_per_user):
            wait = p.cooldown_seconds_per_user - snapshot.cooldown_seconds_remaining
            return PolicyDecision(
                allowed=False,
                reason=f"冷却中：还需 {int(wait)} 秒后才能再点",
                rule_version=p.rule_version,
            )

        return None

    def decide_bump_position(self, snapshot: QueueSnapshot) -> int:
        """根据 policy 与队列快照，给出「插队目标位置」。

        协议：
        - 默认位置 = current_song_position + bump_default_target
        - 永远不超过 current_song_position + bump_default_target（更近可能盖过当前歌曲）

        注：未启用公平保护时 caller 不需要此 API；
        公平保护触发后，主播手选目标位置覆盖。
        """
        return snapshot.current_song_position + self._policy.bump_default_target

    def rule_differs(self, new_policy: RequestPolicy) -> bool:
        """新规则是否变化足以升级 rule_version。

        实际规则版本化通常由 R3 仓储层处理（upsert 时生成 rule_<uuid>）；
        这里只暴露比较运算。
        """
        return (
            self._policy.fan_join_session_quota != new_policy.fan_join_session_quota
            or self._policy.member_daily_quota != new_policy.member_daily_quota
            or self._policy.gift_exchange_quota != new_policy.gift_exchange_quota
            or self._policy.bump_default_target != new_policy.bump_default_target
            or self._policy.fairness_max_consecutive_bumps
                != new_policy.fairness_max_consecutive_bumps
            or self._policy.bump_requires_broadcaster
                != new_policy.bump_requires_broadcaster
            # M2.4 点歌条件
            or self._policy.cooldown_seconds_per_user
                != new_policy.cooldown_seconds_per_user
            or self._policy.max_queue_length != new_policy.max_queue_length
            or self._policy.per_song_max_per_session
                != new_policy.per_song_max_per_session
            or self._policy.per_user_max_in_queue
                != new_policy.per_user_max_in_queue
        )
