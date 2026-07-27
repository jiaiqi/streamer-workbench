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
    etype = (payload.get("type") or "").strip()
    if etype not in CLIENT_REPORTABLE:
        return Response(f"不可上报的事件类型：{etype}（允许 {CLIENT_REPORTABLE}）", status_code=400)
    title = payload.get("title")
    if title is not None:
        title = str(title).strip() or None
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else None
    ts = payload.get("ts")
    ts = str(ts)[:19] if ts else None
    event = append_event(EVENTS_JSONL, etype, title=title, meta=meta, ts=ts)
    return {"ok": True, "event": event}
