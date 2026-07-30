"""R2 P3 EntitlementService——权益核销应用服务。

幂等性核心契约 (v3 §6.3)：
- 核销必须幂等：重复提交不能重复扣额度。
- 删除/取消请求是否返还由规则决定 (默认「未演唱取消则返还 / 已开始演唱不返还」)。
- 所有手工覆盖记录操作者、时间和原因。

设计：
- command_id (请求级 ID) 持久化到 EntitlementLedger，重复 command_id 直接返已有结果。
- EntitlementRepository 负责 atomically 增量保存。
- 返还 (refund) 用新 command_id = "refund:<request_id>" 区分。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from core.data.live import (
    EntitlementGrant,
    KIND_FAN_JOIN,
    KIND_MEMBER_DAILY,
    KIND_GIFT_EXCHANGE,
    KIND_CAMPAIGN,
    KIND_MANUAL,
    VALID_KINDS,
)


class EntitlementServiceError(Exception):
    """可由 HTTP 适配层稳定映射。"""


class EntitlementKindUnknown(EntitlementServiceError):
    pass


class EntitlementQuotaExceeded(EntitlementServiceError):
    pass


class EntitlementAlreadyConsumed(EntitlementServiceError):
    """请求级 ID 已经被核销；重复提交不重复扣。"""


@dataclass(frozen=True)
class ConsumptionResult:
    """单次核销结果。

    - recorded: True 表示已落账 (无论是新增消费还是匹配旧记录)
    - entitlement: 核销后的新快照 (consumed += 1)
    - reason: 失败/降级说明
    """
    recorded: bool
    entitlement: EntitlementGrant
    reason: str = ""
    already_processed: bool = False


@dataclass(frozen=True)
class LedgerEntry:
    """核销账目行：command_id 幂等键。"""
    command_id: str
    entitlement_id: str
    delta: int                # +1 = 核销 / -1 = 返还
    occurred_at: str
    operator: str
    reason: str = ""


class InMemoryEntitlementLedger:
    """测试 + 默认实现的轻量核销账目；接口与持久后端一致。"""

    def __init__(self):
        self._entries: dict[str, LedgerEntry] = {}

    def has(self, command_id: str) -> bool:
        return command_id in self._entries

    def add(self, entry: LedgerEntry) -> None:
        # 真实的持久后端由 Repository 实现；这里允许覆盖测试
        self._entries[entry.command_id] = entry

    def all(self) -> list[LedgerEntry]:
        return list(self._entries.values())


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class EntitlementService:
    """权益授予 + 核销应用服务。

    在 R1 阶段保留纯内存储能 (在测试与服务层之间通过构造函数注入);
    R2 仓储 + AtomicJsonWriter 由上层补齐，这里只做业务规则。
    """

    def __init__(self, *, repository=None, ledger=None):
        """repository: 模拟 EntertainmentRepository port; 提供 .get(id)/.save(grant)."""
        self._grants: dict[str, EntitlementGrant] = {}
        self._repo = repository       # 持久化抽象 (R1 未实现，先 None)
        self._ledger = ledger or InMemoryEntitlementLedger()

    # ── 授予 ──

    def grant(
        self,
        *, kind: str, rule_version: str, quota: int,
        requester_id: str | None = None,
        expires_at: str | None = None,
        evidence_label: str = "",
        evidence_value: float | None = None,
        platform_ref: str = "",
        operator: str = "broadcaster",
    ) -> EntitlementGrant:
        if kind not in VALID_KINDS:
            raise EntitlementKindUnknown(f"未知 kind：{kind}")
        if quota < 1:
            raise EntitlementServiceError(f"quota 必须 ≥ 1：quota={quota}")
        grant = EntitlementGrant(
            rule_version=rule_version,
            requester_id=requester_id,
            kind=kind,
            quota=quota,
            expires_at=expires_at,
            evidence_label=evidence_label,
            evidence_value=evidence_value,
            platform_ref=platform_ref,
        )
        grant.validate()
        self._grants[grant.id] = grant
        if self._repo and hasattr(self._repo, "save"):
            self._repo.save(grant, expected_revision=None)
        return grant

    def get(self, entitlement_id: str) -> EntitlementGrant | None:
        if self._repo and hasattr(self._repo, "get"):
            return self._repo.get(entitlement_id)
        return self._grants.get(entitlement_id)

    # ── 核销 ──

    def consume(
        self,
        entitlement_id: str,
        *,
        command_id: str | None = None,
        operator: str = "broadcaster",
        reason: str = "",
    ) -> ConsumptionResult:
        """尝试核销 1 份额度。

        command_id: 幂等键；同 command_id 重复提交 → already_processed=True。
        """
        grant = self.get(entitlement_id)
        if grant is None:
            return ConsumptionResult(
                recorded=False,
                entitlement=EntitlementGrant(rule_version="?"),
                reason=f"entitlement 不存在：{entitlement_id}",
            )

        if not command_id:
            command_id = f"consume:{uuid.uuid4().hex[:16]}"

        # 幂等：账目已存在
        if self._ledger.has(command_id):
            entry = self._ledger.all()
            for ent in entry:
                if ent.command_id == command_id:
                    return ConsumptionResult(
                        recorded=True,
                        entitlement=grant,
                        already_processed=True,
                        reason=f"已处理：command_id={command_id}",
                    )

        if grant.remaining() <= 0:
            return ConsumptionResult(
                recorded=False,
                entitlement=grant,
                reason=f"quota 已用尽：{grant.consumed}/{grant.quota}",
            )

        new_grant = EntitlementGrant(
            id=grant.id,
            rule_version=grant.rule_version,
            requester_id=grant.requester_id,
            kind=grant.kind,
            granted_at=grant.granted_at,
            expires_at=grant.expires_at,
            quota=grant.quota,
            consumed=grant.consumed + 1,
            evidence_label=grant.evidence_label,
            evidence_value=grant.evidence_value,
            platform_ref=grant.platform_ref,
        )
        new_grant.validate()
        self._grants[grant.id] = new_grant
        if self._repo and hasattr(self._repo, "save"):
            self._repo.save(new_grant, expected_revision=None)

        self._ledger.add(LedgerEntry(
            command_id=command_id,
            entitlement_id=entitlement_id,
            delta=+1,
            occurred_at=_now_iso(),
            operator=operator,
            reason=reason,
        ))
        return ConsumptionResult(
            recorded=True,
            entitlement=new_grant,
        )

    # ── 返还 ──

    def refund(
        self,
        entitlement_id: str,
        *, command_id: str,
        operator: str = "broadcaster",
        reason: str = "",
    ) -> ConsumptionResult:
        """返还 1 份额度 (默认「未演唱取消则返还」)。

        command_id 必须是 refund:<original_command_id> 形式，避免与 consume 重复。
        """
        grant = self.get(entitlement_id)
        if grant is None:
            return ConsumptionResult(
                recorded=False,
                entitlement=EntitlementGrant(rule_version="?"),
                reason=f"entitlement 不存在：{entitlement_id}",
            )

        if not command_id.startswith("refund:"):
            raise EntitlementServiceError(
                "refund command_id 必须以 'refund:' 开头"
            )
        if self._ledger.has(command_id):
            return ConsumptionResult(
                recorded=True,
                entitlement=grant,
                already_processed=True,
                reason=f"已返还：command_id={command_id}",
            )
        if grant.consumed <= 0:
            return ConsumptionResult(
                recorded=False,
                entitlement=grant,
                reason="已无额度可返还",
            )

        new_grant = EntitlementGrant(
            id=grant.id,
            rule_version=grant.rule_version,
            requester_id=grant.requester_id,
            kind=grant.kind,
            granted_at=grant.granted_at,
            expires_at=grant.expires_at,
            quota=grant.quota,
            consumed=grant.consumed - 1,
            evidence_label=grant.evidence_label,
            evidence_value=grant.evidence_value,
            platform_ref=grant.platform_ref,
        )
        self._grants[grant.id] = new_grant
        if self._repo and hasattr(self._repo, "save"):
            self._repo.save(new_grant, expected_revision=None)
        self._ledger.add(LedgerEntry(
            command_id=command_id,
            entitlement_id=entitlement_id,
            delta=-1,
            occurred_at=_now_iso(),
            operator=operator,
            reason=reason,
        ))
        return ConsumptionResult(
            recorded=True,
            entitlement=new_grant,
        )

    # ── 账目审计 ──

    def ledger(self) -> list[LedgerEntry]:
        return self._ledger.all()

    def granted(self) -> list[EntitlementGrant]:
        return list(self._grants.values())
