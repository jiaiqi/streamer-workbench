"""R2 P3 直播领域层 (v3 §6 LiveSession / SongRequest / QueueEntry /
PerformanceRecord / RequestPolicy / EntitlementGrant / PolicyDecision)。

设计原则：
- dataclass + frozen 保证不可变身份 (与 Song/Poster 同)
- 跨稳定 ID (event_id / request_id / session_id) 全部 sha256-derived 风格 UUID hex
- rule_version 用于 RequestPolicy 修改回溯 (按 v3 §6.2「规则修改后生成新 rule_version，不回写历史」)
- 状态转移：requested → queued → current → sung (及 postponed/unknown/skipped/cancelled/duplicate_merged)
- 权益核销幂等：command_id (请求 ID) 在 EntitlementService 中保证 consumed 单调递增不重复
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# ── 三个核心对象 ──

RESULT_PENDING = "pending"
RESULT_REQUESTED = "requested"
RESULT_QUEUED = "queued"
RESULT_CURRENT = "current"
RESULT_SUNG = "sung"
RESULT_POSTPONED = "postponed"
RESULT_UNKNOWN = "unknown"           # 主播说不会唱 → learning_candidate
RESULT_SKIPPED = "skipped"
RESULT_CANCELLED = "cancelled"
RESULT_DUPLICATE_MERGED = "duplicate_merged"

VALID_RESULT_STATES = frozenset((
    RESULT_PENDING, RESULT_REQUESTED, RESULT_QUEUED, RESULT_CURRENT,
    RESULT_SUNG, RESULT_POSTPONED, RESULT_UNKNOWN, RESULT_SKIPPED,
    RESULT_CANCELLED, RESULT_DUPLICATE_MERGED,
))


@dataclass(frozen=True)
class SongRequest:
    """观众或主播提出「想听某首歌」的请求。"""
    id: str = field(default_factory=lambda: _new_id("req"))
    requester_name: str = ""                    # 显示名（昵称）
    requester_id: Optional[str] = None         # 平台稳定 ID（无值时仅估算）
    song_id: str = ""
    session_id: str = ""
    note: str = ""
    requested_at: str = field(default_factory=_now_iso)
    # 权益快照（创建时授予，可空）
    entitlement_kind: str = ""                # fan_join | member_daily | gift_exchange | campaign | manual
    entitlement_id: str = ""

    def validate(self) -> None:
        if not self.requester_name and not self.requester_id:
            raise ValueError("requester_name / requester_id 必须至少给一个")
        if not self.song_id:
            raise ValueError("song_id 必填")
        if not self.session_id:
            raise ValueError("session_id 必填")
        if not self.requester_id and not self.requester_name.strip():
            raise ValueError("requester_name 不能为纯空白")
        # idempotent: 同一 (session, song, requester_name) + entitlement 不应重复
        if self.entitlement_kind and not self.entitlement_id:
            raise ValueError("entitlement_kind 必须配套 entitlement_id")


@dataclass(frozen=True)
class QueueEntry:
    """某次请求在某场直播队列中的当前投影。"""

    request_id: str = ""
    session_id: str = ""
    song_id: str = ""
    position: int = 0
    inserted_at: str = field(default_factory=_now_iso)
    state: str = RESULT_QUEUED
    # 插队元数据（如果该 entry 是插队过来的）
    is_bumped: bool = False
    original_position: Optional[int] = None
    bump_reason: str = ""
    bumped_at: Optional[str] = None
    requester_name: str = ""
    requester_id: Optional[str] = None
    entitlement_kind: str = ""

    def validate(self) -> None:
        if not self.request_id:
            raise ValueError("request_id 必填")
        if not self.song_id:
            raise ValueError("song_id 必填")
        if self.position < 0:
            raise ValueError("position 必须 >= 0")
        if self.state not in VALID_RESULT_STATES:
            raise ValueError(f"state 非法：{self.state}")
        if self.is_bumped and self.original_position is None:
            raise ValueError("is_bumped 必须配套 original_position")


@dataclass(frozen=True)
class PerformanceRecord:
    """最终是否演唱、何时演唱及结果。每场已唱历史永久可回看。"""

    id: str = field(default_factory=lambda: _new_id("perf"))
    request_id: str = ""
    session_id: str = ""
    song_id: str = ""
    result: str = RESULT_SUNG
    performed_at: Optional[str] = None         # sung 时才有
    recorded_at: str = field(default_factory=_now_iso)
    reason: str = ""                          # skipped/postponed/cancelled 时可选原因
    operator: str = "broadcaster"             # 手工覆盖记录操作者

    def validate(self) -> None:
        if not self.session_id or not self.request_id or not self.song_id:
            raise ValueError("session/request/song 必填")
        if self.result not in VALID_RESULT_STATES:
            raise ValueError(f"result 非法：{self.result}")
        if self.result == RESULT_SUNG and not self.performed_at:
            raise ValueError("sung 必须有 performed_at")


# ── RequestPolicy (v3 §6.2) ──

@dataclass(frozen=True)
class RequestPolicy:
    """主播运营规则。新规则修改 → 新 rule_version，不回写历史。"""

    rule_version: str = field(default_factory=lambda: _new_id("rule"))
    created_at: str = field(default_factory=_now_iso)
    # 每类权益的额度配置
    fan_join_session_quota: int = 1            # 新粉团单场 1 首
    member_daily_quota: int = 1               # 会员每日 1 首
    gift_exchange_quota: int = 1              # 墨镜/等价礼物兑换 1 首
    high_value_gift_names: tuple = ()         # 高价值礼物名（升级插队申请资格）
    # 插队
    bump_default_target: int = 3              # 默认插入位置：当前歌曲后第 3 位
    bump_requires_broadcaster: bool = True    # 必须主播确认
    # 公平保护
    fairness_max_consecutive_bumps: int = 3  # 连续插队上限，超过需主播说明
    # 默认有效期
    entitlement_session_window_hours: int = 4  # 单场权益默认有效期

    def validate(self) -> None:
        if not self.rule_version:
            raise ValueError("rule_version 必填")
        for n in (
            self.fan_join_session_quota, self.member_daily_quota,
            self.gift_exchange_quota,
        ):
            if n < 1:
                raise ValueError("quota 必须 >= 1")
        if self.bump_default_target < 1:
            raise ValueError("bump_default_target 必须 >= 1")
        if self.fairness_max_consecutive_bumps < 1:
            raise ValueError("fairness_max_consecutive_bumps 必须 >= 1")


# ── EntitlementGrant (v3 §6.3) ──

KIND_FAN_JOIN = "fan_join"
KIND_MEMBER_DAILY = "member_daily"
KIND_GIFT_EXCHANGE = "gift_exchange"
KIND_CAMPAIGN = "campaign"
KIND_MANUAL = "manual"
VALID_KINDS = frozenset((
    KIND_FAN_JOIN, KIND_MEMBER_DAILY, KIND_GIFT_EXCHANGE,
    KIND_CAMPAIGN, KIND_MANUAL,
))


@dataclass(frozen=True)
class EntitlementGrant:
    """权益授予。核销必须幂等：consumed 单调递增，重复 command_id 不重复扣。"""

    id: str = field(default_factory=lambda: _new_id("ent"))
    rule_version: str = ""
    requester_id: Optional[str] = None
    kind: str = KIND_FAN_JOIN
    granted_at: str = field(default_factory=_now_iso)
    expires_at: Optional[str] = None
    quota: int = 1
    consumed: int = 0
    evidence_label: str = ""
    evidence_value: Optional[float] = None
    platform_ref: str = ""

    def validate(self) -> None:
        if not self.rule_version:
            raise ValueError("rule_version 必填")
        if self.kind not in VALID_KINDS:
            raise ValueError(f"kind 非法：{self.kind}")
        if self.quota < 1:
            raise ValueError("quota 必须 >= 1")
        if self.consumed < 0 or self.consumed > self.quota:
            raise ValueError("consumed 必须在 [0, quota] 区间")

    def remaining(self) -> int:
        return max(0, self.quota - self.consumed)


# ── PolicyDecision (服务层返回值) ──

@dataclass(frozen=True)
class PolicyDecision:
    """RequestPolicyService 单次决策结果。"""

    allowed: bool
    reason: str = ""
    entitlement_id: str = ""
    rule_version: str = ""
    requires_broadcaster_confirmation: bool = False
    degraded: bool = False                # 已记录降级原因（如公平保护）


# ── LiveSession (顶级聚合根) ──

SESSION_ACTIVE = "active"
SESSION_CLOSED = "closed"
VALID_SESSION_STATES = frozenset((SESSION_ACTIVE, SESSION_CLOSED))


@dataclass(frozen=True)
class LiveSession:
    id: str = field(default_factory=lambda: _new_id("live"))
    state: str = SESSION_ACTIVE
    started_at: str = field(default_factory=_now_iso)
    closed_at: Optional[str] = None
    rule_version: str = ""
    poster_id: Optional[str] = None    # 可选引用海报
    title: str = ""
    notes: str = ""

    def validate(self) -> None:
        if not self.rule_version:
            raise ValueError("LiveSession 必须绑定 rule_version")
        if self.state not in VALID_SESSION_STATES:
            raise ValueError(f"state 非法：{self.state}")
        if self.state == SESSION_CLOSED and not self.closed_at:
            raise ValueError("closed 会话必须有 closed_at")
