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
BUMP_UNLOCK_KINDS = frozenset({"high_value_gift", "manual"})


class RequestPolicyServiceError(Exception):
    """可由 HTTP 适配层稳定映射。"""


class UnknownEntitlementKind(RequestPolicyServiceError):
    pass


@dataclass(frozen=True)
class QueueSnapshot:
    """决策时的队列快照。"""

    queue_size: int = 0          # 当前队尾已加入数
    current_song_position: int = 0  # 当前演唱歌曲位置（不可替换）
    recent_bumps_in_a_row: int = 0   # 最近连续插队计数（不含当前/过去插队）


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
            entitlement_kind: 权益类型 (fan_join/member_daily/gift_exchange/campaign/manual)
            snapshot: 当前队尾/正在演唱/连续插队计数

        Returns:
            PolicyDecision (allowed, requires_broadcaster_confirmation, degraded, reason)
        """
        if entitlement_kind == "":
            return PolicyDecision(
                allowed=False,
                reason="缺少 entitlement kind",
                rule_version=self._policy.rule_version,
            )

        # 普通权益 (队尾入队)
        if entitlement_kind in {"fan_join", "member_daily", "gift_exchange", "campaign"}:
            return PolicyDecision(
                allowed=True,
                requires_broadcaster_confirmation=False,
                rule_version=self._policy.rule_version,
            )

        # 插队权益 (申请资格，非自动)
        if entitlement_kind in BUMP_UNLOCK_KINDS:
            # 公平保护：连续插队达到上限 → degraded
            if snapshot.recent_bumps_in_a_row >= self._policy.fairness_max_consecutive_bumps:
                return PolicyDecision(
                    allowed=True,     # 仍允许，但需要原因
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
        )
