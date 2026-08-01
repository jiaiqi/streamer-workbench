"""R4.2.3 导出历史路由（/api/exports*）。

端点:
- GET /api/exports/recent   最近 N 条导出记录（按时间倒序）

事件源: events.jsonl 中 type=poster_exported 的事件。
涵盖三种 kind：
  - grid-export     工作台 ExportDialog（单页/批量）
  - live-poster     直播复盘海报（live.py /poster）
  - learning-report 学歌报告海报（learning_report.py /poster）
"""
from __future__ import annotations

from typing import Any, Annotated

from fastapi import APIRouter, Query, Request

from server.api.secondary_models import (
    ExportLogEntryResponse,
    ExportLogRecentResponse,
)
from server.dependencies import get_app_context


router = APIRouter()


_GRID_THEMES_KEY = "themes"
_GRID_OUTPUT_DIR_KEY = "output_dir"
_GRID_SUBJECT_KEY = "subject"
_GRID_KIND = "grid-export"
_LIVE_KIND = "live-poster"
_LEARNING_KIND = "learning-report"


def _coerce_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _to_entry(event: dict) -> ExportLogEntryResponse:
    """将 events.jsonl 的一条 poster_exported 事件转成 ExportLogEntryResponse。

    兼容性：
    - R0-R3 早期版本的事件可能缺 kind / subject（写于 R4.2.3 之前），
      按 source 字段回退推断 kind；按 files 字段回填 subject。
    """
    meta = event.get("meta") or {}
    kind = meta.get("kind")
    if not kind:
        source = event.get("source") or ""
        if source == "export-api":
            kind = _GRID_KIND
        elif source == "live-poster-api":
            kind = _LIVE_KIND
        elif source == "learning-report-api":
            kind = _LEARNING_KIND
        else:
            kind = source or "unknown"

    subject = meta.get(_GRID_SUBJECT_KEY) or ""
    if not subject:
        if kind == _GRID_KIND:
            themes = meta.get(_GRID_THEMES_KEY) or []
            files = _coerce_int(meta.get("files"), 1)
            if len(themes) == 1:
                subject = themes[0]
            else:
                subject = f"{len(themes)} 个主题" if themes else f"{files} 张"
        elif kind == _LIVE_KIND:
            title = meta.get("title") or ""
            session_id = meta.get("session_id") or ""
            subject = title or (session_id[:8] if session_id else "复盘海报")
        elif kind == _LEARNING_KIND:
            label = meta.get("period_label") or ""
            subject = label or "学歌报告"

    count = _coerce_int(meta.get("count"), 0)
    if count == 0:
        # 兼容 R4.2.3 之前的 grid-export 事件：files 即 count
        count = _coerce_int(meta.get("files"), 1)

    return ExportLogEntryResponse(
        event_id=event.get("event_id") or "",
        occurred_at=event.get("occurred_at") or event.get("recorded_at") or "",
        source=event.get("source") or "",
        kind=kind,
        subject=subject,
        count=count,
        total_ms=_coerce_float(meta.get("total_ms")),
        filename=meta.get("filename") or "",
        output_dir=meta.get(_GRID_OUTPUT_DIR_KEY) or "",
        session_id=meta.get("session_id") or "",
        title=meta.get("title") or "",
        days=_coerce_int(meta.get("days"), 0),
        period_label=meta.get("period_label") or "",
    )


@router.get("/api/exports/recent", response_model=ExportLogRecentResponse)
def api_exports_recent(
    req: Request,
    limit: Annotated[int, Query(ge=1, le=100, description="返回条数，1 ~ 100")] = 20,
):
    """R4.2.3: 读取最近 N 条导出历史（按时间倒序）。

    数据源: events.jsonl 的 type=poster_exported 事件。
    EventStore.tail 已按时间倒序返回，无需再排序。
    """
    ctx = get_app_context(req)
    events = ctx.event_store.tail(limit=limit, event_type="poster_exported")
    return ExportLogRecentResponse(items=[_to_entry(event) for event in events])
