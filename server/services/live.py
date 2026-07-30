"""R2 P3 LiveService——主直播应用服务。

核心契约 (v3 §6)：
- LiveSession 聚合根：start / close；每次操作写 EventStore
- 入队 / 插队 / 演唱结果：通过 RequestPolicyService 决策 + EntitlementService 核销
- 同 command_id 重复调用幂等；同 song_id + 同 requester_id 触发 duplicate_merged
- 同一 service 调用在锁内串行 (避免竞态生成不一致状态)
- 错误时回退状态 / 退还权益 (compensation event)

不在本服务范围：
- LiveRepository 持久化 (P3.5)，FileEventStore detail (R0 已实现)
- HTTP 模型 (P3.6)
- UI (后续会话)
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Optional

from core.data.live import (
    EntitlementGrant,
    KIND_FAN_JOIN,
    KIND_MEMBER_DAILY,
    KIND_GIFT_EXCHANGE,
    KIND_MANUAL,
    LiveSession,
    PerformanceRecord,
    PolicyDecision,
    QueueEntry,
    RequestPolicy,
    RESULT_CANCELLED,
    RESULT_CURRENT,
    RESULT_DUPLICATE_MERGED,
    RESULT_POSTPONED,
    RESULT_QUEUED,
    RESULT_REQUESTED,
    RESULT_SKIPPED,
    RESULT_SUNG,
    RESULT_UNKNOWN,
    SESSION_ACTIVE,
    SESSION_CLOSED,
    SongRequest,
)
from server.services.entitlements import EntitlementService
from server.services.request_policy import (
    QueueSnapshot,
    RequestPolicyService,
)


# ── 错误映射 ──

class LiveServiceError(Exception):
    pass


class SessionNotFound(LiveServiceError):
    pass


class SessionClosed(LiveServiceError):
    pass


class UnknownRequest(LiveServiceError):
    pass


class BumpRequiresConfirmation(LiveServiceError):
    pass


# ── 命令返回值 ──

@dataclass(frozen=True)
class QueueResult:
    entry: QueueEntry
    request: SongRequest
    decision: PolicyDecision


@dataclass(frozen=True)
class RecordResult:
    performance: PerformanceRecord
    refunded: bool
    refund_reason: str = ""


# ── EventStore 抽象 ──

class _NullEventStore:
    """默认空实现：本地调用不附加事件，由上层接入 FileEventStore。"""
    def append(self, event: dict) -> Any:
        return None


class LiveService:
    """状态机派：start / queue / bump / record / close。

    单实例代表单 LiveSession；多 session 需要多实例。
    """

    def __init__(
        self,
        *,
        session: LiveSession,
        policy_service: RequestPolicyService,
        entitlement_service: EntitlementService,
        event_store: Any | None = None,
        song_repository: Any | None = None,
    ):
        self._session = session
        self._policy = policy_service
        self._entitlements = entitlement_service
        self._events = event_store or _NullEventStore()

        # 内存中映射：测试用；持久化在 P3.5 仓储层
        self._requests: dict[str, SongRequest] = {}
        self._queue: list[QueueEntry] = []
        self._performances: dict[str, PerformanceRecord] = {}  # request_id -> rec
        self._lock = threading.RLock()
        self._consecutive_bumps = 0
        self._request_by_song_requester: dict[tuple[str, str], str] = {}

    @property
    def session(self) -> LiveSession:
        return self._session

    @property
    def queue_size(self) -> int:
        return len(self._queue)

    @property
    def performances(self) -> dict[str, PerformanceRecord]:
        return dict(self._performances)

    # ── 会话生命周期 ──

    def close(self, *, reason: str = "broadcaster") -> None:
        with self._lock:
            if self._session.state == SESSION_CLOSED:
                raise SessionClosed(f"会话已关闭：{self._session.id}")
            now = datetime.now().astimezone().isoformat(timespec="seconds")
            closed = LiveSession(
                id=self._session.id,
                state=SESSION_CLOSED,
                started_at=self._session.started_at,
                closed_at=now,
                rule_version=self._session.rule_version,
                poster_id=self._session.poster_id,
                title=self._session.title,
                notes=self._session.notes,
            )
            closed.validate()
            self._session = closed
            self._events.append({
                "schema_version": 2,
                "event_id": f"evt_{uuid.uuid4().hex}",
                "occurred_at": now,
                "recorded_at": now,
                "type": "session_closed",
                "source": "live-service",
                "session_id": self._session.id,
                "meta": {"reason": reason},
            })

    # ── 请求与入队 ──

    def queue_request(
        self,
        *,
        requester_name: str,
        song_id: str,
        requester_id: str | None = None,
        entitlement_id: str | None = None,
        entitlement_kind: str = "",
        note: str = "",
        command_id: str | None = None,
    ) -> QueueResult:
        """加入队列：触发核销（如果给 entitlement）；写 song_request_added 事件。

        同 (session, song, requester) 第二次加入 → duplicate_merged
        """
        with self._lock:
            if self._session.state == SESSION_CLOSED:
                raise SessionClosed(f"会话已关闭：{self._session.id}")

            # 去重：同行+同 song_id+同 requester_id（若给）
            key = (song_id, requester_id or requester_name)
            if key in self._request_by_song_requester:
                existing_id = self._request_by_song_requester[key]
                existing_req = self._requests[existing_id]
                # 二次视为 duplicate
                req = SongRequest(
                    id=existing_id,
                    requester_name=requester_name,
                    requester_id=requester_id,
                    song_id=song_id,
                    session_id=self._session.id,
                    note=note,
                    entitlement_kind=entitlement_kind or existing_req.entitlement_kind,
                    entitlement_id=entitlement_id or existing_req.entitlement_id,
                )
                req.validate()
                # 仍然 active，没有新增 entry
                self._events.append({
                    "schema_version": 2,
                    "event_id": f"evt_{uuid.uuid4().hex}",
                    "occurred_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "type": "request_duplicate_merged",
                    "source": "live-service",
                    "session_id": self._session.id,
                    "request_id": req.id,
                    "song_id": song_id,
                })
                # queue 不变；返回现有 entry
                existing_entry = next(
                    (e for e in self._queue if e.request_id == req.id), None,
                )
                return QueueResult(
                    entry=existing_entry or self._placeholder_entry(req),
                    request=req,
                    decision=PolicyDecision(
                        allowed=True,
                        rule_version=self._policy.rule_version,
                        reason="duplicate_merged",
                    ),
                )

            # 决策
            snapshot = QueueSnapshot(
                queue_size=len(self._queue),
                current_song_position=self._current_position(),
                recent_bumps_in_a_row=self._consecutive_bumps,
            )
            decision = self._policy.decide_queue(
                entitlement_kind=entitlement_kind, snapshot=snapshot,
            )
            if not decision.allowed:
                raise LiveServiceError(
                    f"queue 决策不允许：{decision.reason}"
                )

            req = SongRequest(
                id=(f"req_{uuid.uuid4().hex[:16]}"
                    if not command_id else f"req_{command_id[:12]}"),
                requester_name=requester_name,
                requester_id=requester_id,
                song_id=song_id,
                session_id=self._session.id,
                note=note,
                entitlement_kind=entitlement_kind,
                entitlement_id=entitlement_id or "",
            )
            req.validate()
            self._requests[req.id] = req
            self._request_by_song_requester[key] = req.id

            entry = QueueEntry(
                request_id=req.id,
                session_id=self._session.id,
                song_id=song_id,
                position=len(self._queue) + 1,
                inserted_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                state=RESULT_QUEUED,
                requester_name=requester_name,
                requester_id=requester_id,
                entitlement_kind=entitlement_kind,
            )
            entry.validate()
            self._queue.append(entry)

            # 核销
            if entitlement_id:
                consume_result = self._entitlements.consume(
                    entitlement_id,
                    command_id=f"queue:{req.id}",
                )
                if not consume_result.recorded and not consume_result.already_processed:
                    # 核销失败：回滚 req 注册
                    self._requests.pop(req.id, None)
                    self._request_by_song_requester.pop(key, None)
                    self._queue.pop()
                    raise LiveServiceError(
                        f"entitlement 核销失败：{consume_result.reason}"
                    )

            # 事件
            self._events.append({
                "schema_version": 2,
                "event_id": f"evt_{uuid.uuid4().hex}",
                "occurred_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "type": "queue_added",
                "source": "live-service",
                "session_id": self._session.id,
                "request_id": req.id,
                "song_id": song_id,
                "requester_id": requester_id,
                "decision": _decision_to_event(decision),
            })
            return QueueResult(entry=entry, request=req, decision=decision)

    # ── 演唱结果 ──

    def record_result(
        self,
        *,
        request_id: str,
        result: str,
        operator: str = "broadcaster",
        reason: str = "",
    ) -> RecordResult:
        """记录请求的最终结果。

        result ∈ RESULT_SUNG / SKIPPED / UNKNOWN / CANCELLED / POSTPONED
        - sung → performed_at = now，记录到 performances
        - 不演唱 (unknown/skipped/cancelled) → 返还 entitlement
        - postponed → 保留 entry 在队列中（保持 state）
        """
        with self._lock:
            if request_id not in self._requests:
                raise UnknownRequest(f"未知 request：{request_id}")
            req = self._requests[request_id]
            now = datetime.now().astimezone().isoformat(timespec="seconds")

            performed_at = now if result == RESULT_SUNG else None
            perf = PerformanceRecord(
                request_id=request_id,
                session_id=self._session.id,
                song_id=req.song_id,
                result=result,
                performed_at=performed_at,
                operator=operator,
                reason=reason,
            )
            perf.validate()
            self._performances[request_id] = perf

            # 更新 QueueEntry 状态 (移除已唱，保留 cancelled/queued/skipped 入队)
            for i, e in enumerate(self._queue):
                if e.request_id == request_id:
                    if result == RESULT_SUNG:
                        self._queue.pop(i)
                        self._consecutive_bumps = 0
                    elif result == RESULT_CANCELLED:
                        self._queue.pop(i)
                    elif result == RESULT_POSTPONED:
                        # 保持 entry 不动
                        pass
                    elif result == RESULT_SKIPPED or result == RESULT_UNKNOWN:
                        # 不唱了；从队列移除
                        self._queue.pop(i)
                    break

            # 事件
            self._events.append({
                "schema_version": 2,
                "event_id": f"evt_{uuid.uuid4().hex}",
                "occurred_at": now,
                "recorded_at": now,
                "type": f"performance_{result}",
                "source": "live-service",
                "session_id": self._session.id,
                "request_id": request_id,
                "song_id": req.song_id,
                "reason": reason,
                "operator": operator,
            })

            # 返还：未演唱 + 已核销 → 返还
            refunded = False
            refund_reason = ""
            if result in (RESULT_CANCELLED, RESULT_SKIPPED, RESULT_UNKNOWN):
                if req.entitlement_id:
                    refund_result = self._entitlements.refund(
                        req.entitlement_id,
                        command_id=f"refund:{request_id}",
                        operator=operator,
                        reason=f"未演唱（{result}）",
                    )
                    refunded = refund_result.recorded
                    refund_reason = refund_result.reason
                    if refunded:
                        self._events.append({
                            "schema_version": 2,
                            "event_id": f"evt_{uuid.uuid4().hex}",
                            "occurred_at": now,
                            "recorded_at": now,
                            "type": "entitlement_refunded",
                            "source": "live-service",
                            "session_id": self._session.id,
                            "request_id": request_id,
                            "entitlement_id": req.entitlement_id,
                            "reason": refund_reason,
                        })

            return RecordResult(
                performance=perf,
                refunded=refunded,
                refund_reason=refund_reason,
            )

    # ── 工具 ──

    def _current_position(self) -> int:
        # 简单版：队尾即当前演唱位置
        return 0 if not self._queue else 1

    def _placeholder_entry(self, req: SongRequest) -> QueueEntry:
        return QueueEntry(
            request_id=req.id,
            session_id=self._session.id,
            song_id=req.song_id,
            position=0,
            state=RESULT_QUEUED,
            requester_name=req.requester_name,
            requester_id=req.requester_id,
            entitlement_kind=req.entitlement_kind,
        )


def _decision_to_event(d: PolicyDecision) -> dict:
    return {
        "allowed": d.allowed,
        "reason": d.reason,
        "requires_broadcaster_confirmation": d.requires_broadcaster_confirmation,
        "degraded": d.degraded,
        "rule_version": d.rule_version,
        "entitlement_id": d.entitlement_id,
    }
