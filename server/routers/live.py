"""R2 P3 直播会话 HTTP 路由（/api/live-sessions*）。

端点:
- GET    /api/live-sessions                 列表 (会话摘要)
- POST   /api/live-sessions                 创建会话
- GET    /api/live-sessions/{id}            详情
- POST   /api/live-sessions/{id}/queue       入队
- POST   /api/live-sessions/{id}/record      记录演唱结果
- POST   /api/live-sessions/{id}/close       关闭
- POST   /api/live-sessions/{id}/entitlements 授予权益
- POST   /api/live-sessions/{id}/poster      R2.5 live-set 直播复盘海报
"""
from __future__ import annotations

import io
import time
import uuid
from dataclasses import asdict, replace
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import Response

from server.api.errors import ApiError
from server.api.handlers import api_error_response
from server.api.secondary_models import (
    LiveSessionCreateRequest,
    LiveSessionDetail,
    LiveSessionEntitlementGrantRequest,
    LiveSessionEntitlementResponse,
    LiveSessionQueueRequest,
    LiveSessionQueueResponse,
    LiveSessionPosterRequest,
    LiveSessionRecordRequest,
    LiveSessionRecordResponse,
    LiveSessionSummary,
    RequestPolicyResponse,
    RequestPolicyUpdateRequest,
)
from server.dependencies import get_app_context
from server.services.live import LiveServiceError
from server.services.live_persistence import (
    LiveSessionPersistenceService,
)
from server.services.live_poster import build_live_session_snapshot
from server.services.entitlements import EntitlementServiceError


def _live_poster_filename(session_id: str, when: datetime) -> str:
    """R4.2.3: 与前端 electron-bridge.livePosterFilename 同规则。"""
    stamp = when.strftime("%Y%m%d")
    return f"复盘海报-{session_id[:8]}-{stamp}.png"


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


# =====================================================================
# M2.4 点歌条件
# =====================================================================

@router.get(
    "/api/live-sessions/{session_id}/policy",
    response_model=RequestPolicyResponse,
)
def api_live_sessions_get_policy(session_id: str, req: Request):
    """M2.4：获取当前会话的 RequestPolicy。"""
    persistence = _service(req)
    policy = persistence.get_policy(session_id)
    if policy is None:
        return api_error_response(
            req, 404, ApiError("live_session_not_found",
                                f"会话不存在：{session_id}"),
        )
    return RequestPolicyResponse(**asdict(policy))


@router.post(
    "/api/live-sessions/{session_id}/policy",
    response_model=RequestPolicyResponse,
)
def api_live_sessions_update_policy(
    session_id: str, payload: RequestPolicyUpdateRequest, req: Request,
):
    """M2.4：主播更新点歌条件（cooldown / max_queue / per_song / per_user）。

    行为：
    - 若新值与当前不同 → 生成新 rule_version，旧 RequestPolicy 保留在 history
    - 若新值与当前相同 → 返回原 policy（不 bump version）
    - 失败 → 400 + ApiError
    """
    persistence = _service(req)
    try:
        # 用现有 policy 作基底，覆盖 4 个新字段
        current = persistence.get_policy(session_id)
        if current is None:
            return api_error_response(
                req, 404, ApiError("live_session_not_found",
                                    f"会话不存在：{session_id}"),
            )
        merged = replace(
            current,
            cooldown_seconds_per_user=payload.cooldown_seconds_per_user,
            max_queue_length=payload.max_queue_length,
            per_song_max_per_session=payload.per_song_max_per_session,
            per_user_max_in_queue=payload.per_user_max_in_queue,
        )
        updated = persistence.update_policy(session_id, new_policy=merged)
    except ValueError as exc:
        return api_error_response(
            req, 400, ApiError("invalid_policy", str(exc)),
        )
    except LiveServiceError as exc:
        return api_error_response(
            req, 400, ApiError("live_service_error", str(exc)),
        )
    return RequestPolicyResponse(**asdict(updated))


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


# ── R2.5 live-set 直播复盘海报 ──

@router.post(
    "/api/live-sessions/{session_id}/poster",
    responses={200: {"content": {"image/png": {}}}},
)
def api_live_sessions_poster(
    session_id: str, payload: LiveSessionPosterRequest, req: Request,
):
    """R2.5: 渲染 live-set 直播复盘海报，返回 PNG。

    数据流：LiveService 状态 → LiveSessionSnapshot → engine.render_page
    R4 Runtime v1：用 get_layout("live-set", channel="live_session") 显式校验
    通道契约；snapshot 是 LiveSessionSnapshot，layout 读其字段。
    """
    from core.engine import render_page
    from core.layouts import get_layout
    from core.spec import get_canvas_spec
    from core.themes.loader import load_themes

    persistence = _service(req)
    live = persistence.get_live(session_id)
    if live is None:
        return api_error_response(
            req, 404, ApiError("live_session_not_found",
                                f"会话不存在：{session_id}"),
        )

    ctx = get_app_context(req)
    themes = load_themes(str(ctx.paths.themes_dir))
    if payload.theme_id not in themes:
        return api_error_response(
            req, 404, ApiError("theme_not_found",
                                f"未知主题：{payload.theme_id}"),
        )
    theme = themes[payload.theme_id]
    try:
        spec = get_canvas_spec(payload.canvas_id, avoid=True)
    except (ValueError, KeyError) as exc:
        return api_error_response(
            req, 404, ApiError("canvas_not_found", str(exc)),
        )

    snapshot = build_live_session_snapshot(
        live, song_repository=ctx.song_repository,
    )
    # R4 Runtime v1: 显式声明 channel，让 capabilities() 校验失败早暴露
    try:
        plugin = get_layout("live-set", channel="live_session")
    except KeyError as exc:
        return api_error_response(
            req, 500, ApiError("layout_channel_mismatch", str(exc)),
        )
    # 严格校验画布（live-set 只支持 9:20/9:16）
    supported = plugin.capabilities().get("supported_canvas_ids", [])
    if payload.canvas_id not in supported:
        return api_error_response(
            req, 400, ApiError("canvas_not_supported",
                                f"live-set 不支持画布 {payload.canvas_id}；"
                                f"可选：{supported}"),
        )
    font_path = str(ctx.paths.fonts_dir / "MaokenAssortedSans.ttf")
    started = time.perf_counter()
    img = render_page(theme, plugin, snapshot, spec, 1, font_path)
    total_ms = round((time.perf_counter() - started) * 1000, 1)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    # R4.2.3: 在 events.jsonl 写 poster_exported 事件，供 GET /api/exports/recent 拉取
    when = datetime.now().astimezone()
    ctx.event_store.append({
        "schema_version": 2,
        "event_id": f"evt_{uuid.uuid4().hex}",
        "occurred_at": when.isoformat(timespec="seconds"),
        "recorded_at": when.isoformat(timespec="seconds"),
        "type": "poster_exported",
        "source": "live-poster-api",
        "meta": {
            "kind": "live-poster",
            "session_id": session_id,
            "title": live.session.title or "",
            "filename": _live_poster_filename(session_id, when),
            "count": 1,
            "total_ms": total_ms,
        },
    })
    return Response(buf.getvalue(), media_type="image/png")


@router.get(
    "/api/live-sessions/{session_id}/poster/analyze",
)
def api_live_sessions_poster_analyze(session_id: str, req: Request):
    """R2.5: 报告 live-set 海报的元数据（页数 / 数量 / 桶分布）。"""
    from core.layouts import get_layout

    persistence = _service(req)
    live = persistence.get_live(session_id)
    if live is None:
        return api_error_response(
            req, 404, ApiError("live_session_not_found",
                                f"会话不存在：{session_id}"),
        )
    ctx = get_app_context(req)
    snapshot = build_live_session_snapshot(
        live, song_repository=ctx.song_repository,
    )
    plugin = get_layout("live-set")
    # 临时 canvas 给 analyze 用
    from core.spec import CanvasSpec
    canvas = CanvasSpec(width=1080, height=2400, margin=58)
    report = plugin.analyze(snapshot, canvas)
    report["session_id"] = session_id
    report["session_title"] = live.session.title
    return report
