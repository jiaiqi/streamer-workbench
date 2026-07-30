"""R2 P3 直播会话 HTTP 路由（/api/live-sessions*）。

端点:
- GET    /api/live-sessions                 列表 (会话摘要)
- POST   /api/live-sessions                 创建会话
- GET    /api/live-sessions/{id}            详情
- POST   /api/live-sessions/{id}/queue       入队
- POST   /api/live-sessions/{id}/record      记录演唱结果
- POST   /api/live-sessions/{id}/close       关闭
- POST   /api/live-sessions/{id}/entitlements 授予权益
"""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request

from server.api.errors import ApiError
from server.api.handlers import api_error_response
from server.api.secondary_models import (
    LiveSessionCreateRequest,
    LiveSessionDetail,
    LiveSessionEntitlementGrantRequest,
    LiveSessionEntitlementResponse,
    LiveSessionQueueRequest,
    LiveSessionQueueResponse,
    LiveSessionRecordRequest,
    LiveSessionRecordResponse,
    LiveSessionSummary,
)
from server.dependencies import get_app_context
from server.services.live import LiveServiceError
from server.services.live_persistence import (
    LiveSessionPersistenceService,
)
from server.services.entitlements import EntitlementServiceError


router = APIRouter()


def _service(req: Request) -> LiveSessionPersistenceService:
    return get_app_context(req).live_persistence_service


def _lives(req: Request):
    """列出 (id, live) 对。"""
    ctx = get_app_context(req)
    persistence = ctx.live_persistence_service
    items = []
    for sid in persistence.list_sessions():
        live = persistence.get_live(sid)
        if live is not None:
            items.append((sid, live))
    return items


@router.get("/api/live-sessions", response_model=list[LiveSessionSummary])
def api_live_sessions_list(req: Request):
    """所有已加载会话摘要。"""
    return [
        LiveSessionSummary(
            id=sid,
            state=live.session.state,
            title=live.session.title,
            rule_version=live.session.rule_version,
            started_at=live.session.started_at,
            closed_at=live.session.closed_at,
            queue_size=live.queue_size,
        )
        for sid, live in _lives(req)
    ]


@router.post("/api/live-sessions", response_model=LiveSessionSummary)
def api_live_sessions_create(payload: LiveSessionCreateRequest, req: Request):
    """创建并立即刷写 repo。"""
    persistence = _service(req)
    live = persistence.create_session(
        rule_version=payload.rule_version,
        title=payload.title,
        poster_id=payload.poster_id,
    )
    return LiveSessionSummary(
        id=live.session.id,
        state=live.session.state,
        title=live.session.title,
        rule_version=live.session.rule_version,
        started_at=live.session.started_at,
        closed_at=live.session.closed_at,
        queue_size=live.queue_size,
    )


@router.get("/api/live-sessions/{session_id}", response_model=LiveSessionDetail)
def api_live_sessions_get(session_id: str, req: Request):
    persistence = _service(req)
    live = persistence.get_live(session_id)
    if live is None:
        return api_error_response(
            req, 404, ApiError("live_session_not_found",
                                 f"会话不存在：{session_id}"),
        )
    return LiveSessionDetail(
        id=live.session.id,
        state=live.session.state,
        title=live.session.title,
        rule_version=live.session.rule_version,
        started_at=live.session.started_at,
        closed_at=live.session.closed_at,
        poster_id=live.session.poster_id,
        notes=live.session.notes,
        queue=[asdict(q) for q in sorted(live._queue, key=lambda q: q.position)],
        performances=[asdict(p) for p in live.performances.values()],
    )


@router.post(
    "/api/live-sessions/{session_id}/queue",
    response_model=LiveSessionQueueResponse,
)
def api_live_sessions_queue(
    session_id: str, payload: LiveSessionQueueRequest, req: Request,
):
    persistence = _service(req)
    try:
        result = persistence.queue_request(
            session_id,
            requester_name=payload.requester_name,
            requester_id=payload.requester_id,
            song_id=payload.song_id,
            entitlement_id=payload.entitlement_id or None,
            entitlement_kind=payload.entitlement_kind,
            note=payload.note,
            command_id=payload.command_id,
        )
    except KeyError:
        return api_error_response(
            req, 400, ApiError("invalid_request", "Payload 校验失败"),
        )
    except ValueError as exc:
        return api_error_response(
            req, 400, ApiError("invalid_request", str(exc)),
        )
    except EntitlementServiceError as exc:
        return api_error_response(
            req, 400, ApiError("entitlement_error", str(exc)),
        )
    except LiveServiceError as exc:
        return api_error_response(
            req, 400, ApiError("live_service_error", str(exc)),
        )
    # result.decision.allowed == False → 业务不允许
    if not result.decision.allowed:
        return api_error_response(
            req, 400, ApiError("queue_rejected",
                                result.decision.reason or "规则拒绝"),
        )
    duplicate = "duplicate_merged" in (result.decision.reason or "")
    return LiveSessionQueueResponse(
        request_id=result.request.id,
        song_id=result.request.song_id,
        position=result.entry.position,
        decision=asdict(result.decision),
        duplicate_merged=duplicate,
    )


@router.post(
    "/api/live-sessions/{session_id}/record",
    response_model=LiveSessionRecordResponse,
)
def api_live_sessions_record(
    session_id: str, payload: LiveSessionRecordRequest, req: Request,
):
    persistence = _service(req)
    try:
        result = persistence.record_result(
            session_id,
            request_id=payload.request_id,
            result=payload.result,
            operator=payload.operator,
            reason=payload.reason,
        )
    except ValueError as exc:
        return api_error_response(
            req, 400, ApiError("invalid_result", str(exc)),
        )
    except LiveServiceError as exc:
        return api_error_response(
            req, 400, ApiError("live_service_error", str(exc)),
        )
    return LiveSessionRecordResponse(
        request_id=payload.request_id,
        result=result.performance.result,
        refunded=result.refunded,
        refund_reason=result.refund_reason,
    )


@router.post("/api/live-sessions/{session_id}/close", response_model=LiveSessionSummary)
def api_live_sessions_close(session_id: str, req: Request):
    persistence = _service(req)
    try:
        persistence.close_session(session_id)
    except ValueError as exc:
        return api_error_response(
            req, 400, ApiError("invalid_close", str(exc)),
        )
    live = persistence.get_live(session_id)
    if live is None:
        return api_error_response(
            req, 404, ApiError("live_session_not_found",
                                f"会话不存在：{session_id}"),
        )
    return LiveSessionSummary(
        id=live.session.id,
        state=live.session.state,
        title=live.session.title,
        rule_version=live.session.rule_version,
        started_at=live.session.started_at,
        closed_at=live.session.closed_at,
        queue_size=live.queue_size,
    )


@router.post(
    "/api/live-sessions/{session_id}/entitlements",
    response_model=LiveSessionEntitlementResponse,
)
def api_live_sessions_grant(
    session_id: str, payload: LiveSessionEntitlementGrantRequest, req: Request,
):
    persistence = _service(req)
    try:
        grant = persistence.grant_entitlement(
            kind=payload.kind,
            rule_version=payload.rule_version,
            quota=payload.quota,
            requester_id=payload.requester_id,
            expires_at=payload.expires_at,
            evidence_label=payload.evidence_label,
            evidence_value=payload.evidence_value,
            platform_ref=payload.platform_ref,
        )
    except ValueError as exc:
        return api_error_response(
            req, 400, ApiError("invalid_grant", str(exc)),
        )
    return LiveSessionEntitlementResponse(
        id=grant.id,
        kind=grant.kind,
        rule_version=grant.rule_version,
        requester_id=grant.requester_id,
        quota=grant.quota,
        consumed=grant.consumed,
        remaining=grant.remaining(),
        granted_at=grant.granted_at,
        expires_at=grant.expires_at,
    )
