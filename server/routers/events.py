"""事件流路由（/api/events*）。"""
from fastapi import APIRouter, Request, Response

from core.data.events import EVENT_TYPES, append_event, iter_events, tail as events_tail
from server.dependencies import get_app_context

router = APIRouter()

CLIENT_REPORTABLE = ("queue_added", "song_sung", "practice_logged")


@router.get("/api/events")
def api_events(req: Request,
               type: str = None, since: str = None, limit: int = 50):
    events_path = str(get_app_context(req).paths.events_jsonl)
    if type and type not in EVENT_TYPES:
        return Response(f"未知事件类型：{type}", status_code=400)
    limit = max(1, min(500, int(limit)))
    if since:
        events = list(iter_events(events_path, type=type, since=since))[:500]
    else:
        events = events_tail(events_path, n=limit, type=type)
    return {"total": len(events), "events": events}


@router.post("/api/events/report")
def api_events_report(req: Request, payload: dict):
    context = get_app_context(req)
    etype = (payload.get("type") or "").strip()
    if etype not in CLIENT_REPORTABLE:
        return Response(f"不可上报的事件类型：{etype}（允许 {CLIENT_REPORTABLE}）", status_code=400)
    library = context.song_repository
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
        event = append_event(
            str(context.paths.events_jsonl), etype, song_id=song_id, title_snapshot=title,
            meta=meta, occurred_at=occurred_at, event_id=event_id, source=source,
        )
    except ValueError as e:
        return Response(str(e), status_code=400)
    return {"ok": True, "event": event}
