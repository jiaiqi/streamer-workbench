"""事件流路由（/api/events*）。"""
from fastapi import APIRouter, Request, Response

from core.data.events import EVENT_TYPES, append_event, iter_events, tail as events_tail

router = APIRouter()

CLIENT_REPORTABLE = ("queue_added", "song_sung", "practice_logged")


@router.get("/api/events")
def api_events(req: Request,
               type: str = None, since: str = None, limit: int = 50):
    from server.deps import EVENTS_JSONL
    if type and type not in EVENT_TYPES:
        return Response(f"未知事件类型：{type}", status_code=400)
    limit = max(1, min(500, int(limit)))
    if since:
        events = list(iter_events(EVENTS_JSONL, type=type, since=since))[:500]
    else:
        events = events_tail(EVENTS_JSONL, n=limit, type=type)
    return {"total": len(events), "events": events}


@router.post("/api/events/report")
def api_events_report(req: Request, payload: dict):
    from server.deps import EVENTS_JSONL
    from server.deps import get_library
    etype = (payload.get("type") or "").strip()
    if etype not in CLIENT_REPORTABLE:
        return Response(f"不可上报的事件类型：{etype}（允许 {CLIENT_REPORTABLE}）", status_code=400)
    library = get_library(req.app.state)
    song_id = str(payload.get("song_id") or "").strip() or None
    title = payload.get("title_snapshot", payload.get("title"))
    title = str(title).strip() if title is not None else None
    song = library.get_by_id(song_id) if song_id else (library.get(title) if title else None)
    if song is not None:
        song_id = song.id
        title = song.title
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else None
    occurred_at = payload.get("occurred_at", payload.get("ts"))
    event_id = str(payload.get("event_id") or "").strip() or None
    source = str(payload.get("source") or "quick-view").strip()
    try:
        event = append_event(
            EVENTS_JSONL, etype, song_id=song_id, title_snapshot=title,
            meta=meta, occurred_at=occurred_at, event_id=event_id, source=source,
        )
    except ValueError as e:
        return Response(str(e), status_code=400)
    return {"ok": True, "event": event}
