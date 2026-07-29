"""事件流路由（/api/events*）。"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from datetime import datetime
import uuid
from core.data.events import EVENT_TYPES, _normalize_timestamp
from server.api.errors import ApiError, map_repository_error
from server.api.models import EventReportRequest, EventReportResponse, EventsResponse
from server.ports.repositories import EventQuery, RepositoryError
from server.dependencies import get_app_context

router = APIRouter()

CLIENT_REPORTABLE = ("queue_added", "song_sung", "practice_logged")


def _error(status_code: int, code: str, message: str,
           *, recovery: str | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ApiError(code, message, recovery=recovery).envelope(),
    )


@router.get("/api/events", response_model=EventsResponse)
def api_events(req: Request,
               type: str = None, since: str = None, limit: int = 50):
    store = get_app_context(req).event_store
    if type and type not in EVENT_TYPES:
        return _error(400, "invalid_event_type", f"未知事件类型：{type}")
    limit = max(1, min(500, int(limit)))
    if since:
        events = list(store.iter(EventQuery(event_type=type, since=since)))[:500]
    else:
        events = list(store.tail(limit=limit, event_type=type))
    return {"total": len(events), "events": events}


@router.post("/api/events/report", response_model=EventReportResponse)
def api_events_report(req: Request, request: EventReportRequest):
    context = get_app_context(req)
    # 保留单元测试和内部 Python 调用的 dict 兼容；HTTP 边界仍由 Pydantic 校验。
    payload = (request.model_dump(exclude_none=True)
               if isinstance(request, EventReportRequest) else request)
    etype = (payload.get("type") or "").strip()
    if etype not in CLIENT_REPORTABLE:
        return _error(
            400,
            "event_type_not_reportable",
            f"不可上报的事件类型：{etype}（允许 {CLIENT_REPORTABLE}）",
        )
    library = context.song_repository.load().value
    song_id = str(payload.get("song_id") or "").strip() or None
    title = payload.get("title_snapshot", payload.get("title"))
    title = str(title).strip() if title is not None else None
    if song_id:
        song = library.get_by_id(song_id)
        if song is None:
            return _error(404, "song_not_found", f"未找到歌曲 ID：{song_id}")
        required = {
            "event_id": payload.get("event_id"),
            "title_snapshot": payload.get("title_snapshot"),
            "occurred_at": payload.get("occurred_at"),
            "source": payload.get("source"),
        }
        missing = [key for key, value in required.items()
                   if not str(value or "").strip()]
        if missing:
            return _error(
                400,
                "event_v2_missing_fields",
                f"Event v2 缺少必填字段：{', '.join(missing)}",
            )
    else:
        # R0.5 兼容旧 QuickView；新客户端必须直接提交 song_id。
        song = library.get(title) if title else None
        if song is None:
            return _error(
                400,
                "event_song_required",
                "事件必须关联有效的 song_id",
            )
    song_id = song.id
    title = song.title
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else None
    occurred_at = payload.get("occurred_at", payload.get("ts"))
    event_id = str(payload.get("event_id") or "").strip() or None
    source = str(payload.get("source") or "quick-view").strip()
    try:
        event = {
            "schema_version": 2,
            "event_id": event_id or f"evt_{uuid.uuid4().hex}",
            "occurred_at": _normalize_timestamp(occurred_at),
            "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "type": etype, "source": source, "song_id": song_id,
            "title_snapshot": title,
        }
        if meta:
            event["meta"] = meta
        event = context.event_store.append(event).event
    except RepositoryError as error:
        status_code, api_error = map_repository_error(error)
        return JSONResponse(status_code=status_code, content=api_error.envelope())
    except ValueError as error:
        return _error(400, "invalid_event", str(error))
    return {"ok": True, "event": event}
