"""R3.5 learning-report 海报 HTTP 路由（/api/learning-report*）。

端点:
- GET  /api/learning-report/analyze     元数据（桶摘要）
- POST /api/learning-report/poster      渲染 PNG（image/png）
"""
from __future__ import annotations

import io

from fastapi import APIRouter, Request
from fastapi.responses import Response

from server.api.errors import ApiError
from server.api.handlers import api_error_response
from server.api.secondary_models import LearningReportPosterRequest
from server.dependencies import get_app_context
from server.services.learning_report import build_learning_report_snapshot


router = APIRouter()


@router.post(
    "/api/learning-report/poster",
    responses={200: {"content": {"image/png": {}}}},
)
def api_learning_report_poster(payload: LearningReportPosterRequest, req: Request):
    """R3.5: 渲染 learning-report 学歌报告海报，返回 PNG。

    数据流：StatsApplicationService 事件聚合 → LearningReportSnapshot
    → engine.render_page(layout=learning-report)
    """
    from core.engine import render_page
    from core.layouts import get_layout
    from core.spec import get_canvas_spec
    from core.themes.loader import load_themes

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

    snapshot = build_learning_report_snapshot(
        ctx.stats_service,
        period_label=payload.period_label,
        days=payload.days,
        top_n_artists=payload.top_n_artists,
    )
    plugin = get_layout("learning-report")
    # 严格校验画布
    supported = plugin.capabilities().get("supported_canvas_ids", [])
    if payload.canvas_id not in supported:
        return api_error_response(
            req, 400, ApiError("canvas_not_supported",
                                f"learning-report 不支持画布 {payload.canvas_id}；"
                                f"可选：{supported}"),
        )
    font_path = str(ctx.paths.fonts_dir / "MaokenAssortedSans.ttf")
    img = render_page(theme, plugin, snapshot, spec, 1, font_path)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return Response(buf.getvalue(), media_type="image/png")


@router.get("/api/learning-report/analyze")
def api_learning_report_analyze(
    req: Request,
    days: int = 30,
    period_label: str = "",
    top_n_artists: int = 5,
):
    """R3.5: 报告 learning-report 海报的元数据（桶摘要）。"""
    from core.layouts import get_layout
    from core.spec import CanvasSpec

    ctx = get_app_context(req)
    snapshot = build_learning_report_snapshot(
        ctx.stats_service,
        period_label=period_label,
        days=days,
        top_n_artists=top_n_artists,
    )
    plugin = get_layout("learning-report")
    canvas = CanvasSpec(width=1080, height=2400, margin=58)
    report = plugin.analyze(snapshot, canvas)
    report["period_label"] = snapshot.period_label
    report["period_start"] = snapshot.period_start
    report["period_end"] = snapshot.period_end
    return report
