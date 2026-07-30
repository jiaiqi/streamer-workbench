"""R2 P3 LiveSessionPersistenceService——LiveService ⇄ Repository 桥接。

职责：
- 启动时从 Repository 读 state.json → 重建 LiveService (entitlements/queue/perfs 全恢复)
- 每次操作后把 LiveService 内部状态刷写到 Repository (写穿模式)
- 代替 LiveService._NullEventStore, 接入 FileEventStore 持久事件

revision CAS 协议:
- save_state(expected_revision) 把当前 LiveService 状态序列化, 用 expected_revision 校验
- LiveService 不维护 revision, 由 PersistenceService 调用 repo.get().revision 取得
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any, List, Optional

from core.data.live import (
    EntitlementGrant,
    LiveSession,
    PerformanceRecord,
    QueueEntry,
    SESSION_ACTIVE,
    SESSION_CLOSED,
    SongRequest,
)
from server.ports.repositories import (
    MISSING_REVISION,
    RepositoryConflict,
    RepositoryUnavailable,
)
from server.repositories.live import CURRENT_STATE_SCHEMA
from server.services.entitlements import (
    EntitlementService,
    InMemoryEntitlementLedger,
    LedgerEntry,
)
from server.services.live import LiveService
from server.services.request_policy import RequestPolicyService


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _session_to_dict(s: LiveSession) -> dict:
    return asdict(s)


def _request_to_dict(r: SongRequest) -> dict:
    return asdict(r)


def _queue_to_dict(q: QueueEntry) -> dict:
    return asdict(q)


def _perf_to_dict(p: PerformanceRecord) -> dict:
    return asdict(p)


def _entitlement_to_dict(e: EntitlementGrant) -> dict:
    return asdict(e)


def _from_dict_request(d: dict) -> SongRequest:
    return SongRequest(**d)


def _from_dict_queue(d: dict) -> QueueEntry:
    return QueueEntry(**d)


def _from_dict_perf(d: dict) -> PerformanceRecord:
    return PerformanceRecord(**d)


def _from_dict_entitlement(d: dict) -> EntitlementGrant:
    return EntitlementGrant(**d)


class LiveSessionPersistenceService:
    """桥接 LiveService ⇄ Repository。"""

    def __init__(
        self,
        *,
        live_repository,
        policy_factory,       # callable(rule_version) -> RequestPolicyService
        entitlement_service: Optional[EntitlementService] = None,
        event_store: Any | None = None,
    ):
        self._repo = live_repository
        self._policy_factory = policy_factory
        self._events = event_store  # FileEventStore via DI
        # 内存中: live_id -> LiveService
        self._live_services: dict[str, LiveService] = {}
        # entitlements 是 shared (跨 sessions)
        self._entitlements = entitlement_service or EntitlementService()
        # 重建 ledger (consume / refund 幂等记录持久化在内存)
        self._ledger = self._entitlements._ledger

    # ── 启动恢复 ──

    def load_session(self, session_id: str) -> LiveService | None:
        """从 repo 读取 state.json 重建 LiveService。"""
        snapshot = self._repo.get(session_id)
        if snapshot is None:
            return None
        try:
            return self._restore_from_state(snapshot.value, snapshot.revision)
        except Exception as exc:
            # recovery 失败不阻断整体恢复, 调用方可选
            raise RepositoryUnavailable(f"恢复失败 {session_id}：{exc}") from exc

    def _restore_from_state(self, state: dict, revision: str) -> LiveService:
        if state.get("schema_version") != CURRENT_STATE_SCHEMA:
            raise RepositoryUnavailable("schema_version 不匹配")
        session_dict = state["session"]
        session = LiveSession(**session_dict)

        policy = self._policy_factory(session.rule_version)
        # 先创建 LiveService
        live = LiveService(
            session=session,
            policy_service=policy,
            entitlement_service=self._entitlements,
            event_store=self._events,
        )

        # 恢复 requests / queue / performances / entitlements
        for r_d in state.get("requests", {}).values():
            live._requests[r_d["id"]] = _from_dict_request(r_d)
        for q_d in state.get("queue", []):
            entry = _from_dict_queue(q_d)
            live._queue.append(entry)
        # 重建 request_by_song_requester 索引
        for r in live._requests.values():
            key = (r.song_id, r.requester_id or r.requester_name)
            live._request_by_song_requester[key] = r.id
        for pid, p_d in state.get("performances", {}).items():
            live._performances[pid] = _from_dict_perf(p_d)
        for e_d in state.get("entitlements", {}).values():
            grant = _from_dict_entitlement(e_d)
            live._entitlements._grants[grant.id] = grant
        live._consecutive_bumps = state.get("consecutive_bumps", 0)
        # 恢复 ledger 行 (consume/refund 幂等记录)
        ledger_entries = state.get("ledger", [])
        for le_d in ledger_entries:
            self._ledger.add(LedgerEntry(**le_d))

        self._live_services[session.id] = live
        # 记录当前 revision 供后续 save_state 使用
        self._current_revision[session.id] = revision
        return live

    _current_revision: dict[str, str] = {}

    def list_sessions(self) -> list[str]:
        snap = self._repo.list_sessions()
        return list(snap.value)

    def get_revision(self, session_id: str) -> str | None:
        return self._current_revision.get(session_id)

    # ── 创建 + 命令 ──

    def create_session(self, *, rule_version: str, title: str = "",
                       poster_id: str | None = None) -> LiveService:
        """创建会话, 立即刷写 repo, 返回 live service。"""
        session = LiveSession(
            rule_version=rule_version, title=title, poster_id=poster_id,
        )
        session.validate()
        policy = self._policy_factory(rule_version)
        live = LiveService(
            session=session,
            policy_service=policy,
            entitlement_service=self._entitlements,
            event_store=self._events,
        )
        self._live_services[session.id] = live
        # 立即保存占位 state
        self._save_state(live, expected_revision=MISSING_REVISION)
        return live

    def get_live(self, session_id: str) -> LiveService | None:
        return self._live_services.get(session_id)

    # ── 写穿: 所有命令调用 → LiveService 命令 → 刷写 repo ──

    def queue_request(self, session_id: str, **kwargs) -> Any:
        live = self._require_live(session_id)
        result = live.queue_request(**kwargs)
        self._save_state(live, expected_revision=self._current_revision[session_id])
        return result

    def record_result(self, session_id: str, **kwargs) -> Any:
        live = self._require_live(session_id)
        result = live.record_result(**kwargs)
        self._save_state(live, expected_revision=self._current_revision[session_id])
        return result

    def close_session(self, session_id: str, **kwargs) -> None:
        live = self._require_live(session_id)
        live.close(**kwargs)
        self._save_state(live, expected_revision=self._current_revision[session_id])

    def grant_entitlement(self, *, kind: str, rule_version: str, quota: int,
                          requester_id: str | None = None,
                          expires_at: str | None = None,
                          evidence_label: str = "",
                          evidence_value: float | None = None,
                          platform_ref: str = "") -> EntitlementGrant:
        grant = self._entitlements.grant(
            kind=kind, rule_version=rule_version, quota=quota,
            requester_id=requester_id, expires_at=expires_at,
            evidence_label=evidence_label, evidence_value=evidence_value,
            platform_ref=platform_ref,
        )
        # 找到所有 live services, 写穿
        for live in set(self._live_services.values()):
            # 只有当这条 grant 的 rule_version 与该 session 匹配时刷写
            if live.session.rule_version == rule_version:
                self._save_state(live, expected_revision=self._current_revision[live.session.id])
        return grant

    # ── 保存 ──

    def _require_live(self, session_id: str) -> LiveService:
        live = self._live_services.get(session_id)
        if live is None:
            raise RepositoryUnavailable(
                f"未找到 live session（先 load/create）：{session_id}"
            )
        return live

    def _save_state(self, live: LiveService, *, expected_revision: str):
        # 序列化 LiveService 内部状态
        # 重建 ledger 行（从 InMemoryEntitlementLedger）
        ledger_serialized = [
            {"command_id": e.command_id, "entitlement_id": e.entitlement_id,
             "delta": e.delta, "occurred_at": e.occurred_at,
             "operator": e.operator, "reason": e.reason}
            for e in self._ledger.all()
        ]
        state = {
            "schema_version": CURRENT_STATE_SCHEMA,
            "session": _session_to_dict(live.session),
            "requests": {
                rid: _request_to_dict(r) for rid, r in live._requests.items()
            },
            "queue": [
                # 按 position 排序序列化
                _queue_to_dict(q) for q in sorted(live._queue, key=lambda x: x.position)
            ],
            "performances": {
                pid: _perf_to_dict(p) for pid, p in live._performances.items()
            },
            "entitlements": {
                eid: _entitlement_to_dict(e)
                for eid, e in self._entitlements._grants.items()
            },
            "consecutive_bumps": live._consecutive_bumps,
            "ledger": ledger_serialized,
        }
        snap = self._repo.save(
            live.session.id, state, expected_revision=expected_revision,
        )
        self._current_revision[live.session.id] = snap.revision

    def close_repo(self) -> None:
        self._repo.close()

    def entitlements(self) -> EntitlementService:
        return self._entitlements
