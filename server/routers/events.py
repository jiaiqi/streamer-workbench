"""事件流路由（/api/events*）。"""
from fastapi import APIRouter, Request, Response

from datetime import datetime
import uuid
from core.data.events import EVENT_TYPES, _normalize_timestamp
from server.ports.repositories import EventQuery, RepositoryError
from server.dependencies import get_app_context

router = APIRouter()

CLIENT_REPORTABLE = ("queue_added", "song_sung", "practice_logged")


@router.get("/api/events")
def api_events(req: Request,
               type: str = None, since: str = None, limit: int = 50):
    store = get_app_context(req).event_store
    if type and type not in EVENT_TYPES:
        return Response(f"未知事件类型：{type}", status_code=400)
    limit = max(1, min(500, int(limit)))
    if since:
        events = list(store.iter(EventQuery(event_type=type, since=since)))[:500]
    else:
        events = list(store.tail(limit=limit, event_type=type))
    return {"total": len(events), "events": events}


@router.post("/api/events/report")
def api_events_report(req: Request, payload: dict):
    context = get_app_context(req)
    etype = (payload.get("type") or "").strip()
    if etype not in CLIENT_REPORTABLE:
        return Response(f"不可上报的事件类型：{etype}（允许 {CLIENT_REPORTABLE}）", status_code=400)
    library = context.song_repository.load().value
    song_id = str(payload.get("song_id") or "").strip() or None
    title = payload.get("title_snapshot", payload.get("title"))
    title = str(title).strip() if title is not None else None
    if song_id:
        song = library.get_by_id(song_id)
        if song is None:
            return Response(f"未找到歌曲 ID：{song_id}", status_code=404)
        required = {
            "event_id": payload.get("event_id"),
            "title_snapshot": payload.get("title_snapshot"),
            "occurred_at": payload.get("occurred_at"),
            "source": payload.get("source"),
        }
        missing = [key for key, value in required.items()
                   if not str(value or "").strip()]
        if missing:
            return Response(
                f"Event v2 缺少必填字段：{', '.join(missing)}",
                status_code=400,
            )
    else:
        # R0.5 兼容旧 QuickView；新客户端必须直接提交 song_id。
        song = library.get(title) if title else None
        if song is None:
            return Response("事件必须关联有效的 song_id", status_code=400)
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
    except (ValueError, RepositoryError) as e:
        return Response(str(e), status_code=400)
    return {"ok": True, "event": event}
