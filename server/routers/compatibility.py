"""R4 Runtime v2 v2.5: Theme × Layout 能力矩阵 端点。

- GET  /api/posters/compatibility?layout_id=&theme_id=  → 单对校验
- GET  /api/posters/compatibility/matrix               → 完整矩阵（启动时拉一次）
- GET  /api/posters/compatibility/layouts?theme_id=     → 某 theme 兼容的 layout 列表
- GET  /api/posters/compatibility/themes?layout_id=     → 某 layout 兼容的 theme 列表

UI 端：LayoutPicker 主题下拉 + 主题下拉用此端点实时灰显不兼容项。
"""
from __future__ import annotations

from fastapi import APIRouter, Query, Request

from server.api.errors import ApiError
from server.api.handlers import api_error_response
from server.api.secondary_models import (
    CompatibilityCheckResponse,
    CompatibilityMatrixResponse,
    CompatibilityListResponse,
)
from core.layouts import REGISTRY, get_layout
from core.layouts.compat import (
    check_compatibility,
    compatibility_matrix,
    list_compatible_layouts,
    list_compatible_themes,
)


router = APIRouter()


def _all_themes(req: Request) -> dict:
    """从 AppContext 拿全部 themes（按 name 索引）。"""
    themes = req.app.state.context.themes
    return {t.name: t for t in themes.values()}


@router.get("/api/compatibility",
            response_model=CompatibilityCheckResponse)
def api_compatibility_check(
    req: Request,
    layout_id: str = Query(..., min_length=1, max_length=64),
    theme_id: str = Query(..., min_length=1, max_length=64),
) -> CompatibilityCheckResponse:
    """R4 Runtime v2 v2.5: 校验 (layout_id, theme_id) 兼容性。"""
    if layout_id not in REGISTRY:
        return api_error_response(
            req, 404, ApiError("layout_not_found", f"未知排版：{layout_id}"),
        )
    layout = get_layout(layout_id)
    themes = _all_themes(req)
    if theme_id not in themes:
        return api_error_response(
            req, 404, ApiError("theme_not_found", f"未知主题：{theme_id}"),
        )
    theme = themes[theme_id]
    ok, reason = check_compatibility(layout, theme)
    return CompatibilityCheckResponse(compatible=ok, reason=reason)


@router.get("/api/compatibility/matrix",
            response_model=CompatibilityMatrixResponse)
def api_compatibility_matrix(req: Request) -> CompatibilityMatrixResponse:
    """R4 Runtime v2 v2.5: 完整 layout × theme 兼容矩阵。

    启动时拉一次缓存；切换 layout/poster 时实时校验。
    """
    themes = _all_themes(req)
    matrix = compatibility_matrix(REGISTRY, themes)
    return CompatibilityMatrixResponse(
        layouts=list(REGISTRY.keys()),
        themes=list(themes.keys()),
        matrix=matrix,
    )


@router.get("/api/compatibility/layouts",
            response_model=CompatibilityListResponse)
def api_compatibility_layouts(
    req: Request,
    theme_id: str = Query(..., min_length=1, max_length=64),
) -> CompatibilityListResponse:
    """R4 Runtime v2 v2.5: 某 theme 兼容的 layout 列表。"""
    themes = _all_themes(req)
    if theme_id not in themes:
        return api_error_response(
            req, 404, ApiError("theme_not_found", f"未知主题：{theme_id}"),
        )
    return CompatibilityListResponse(
        items=list_compatible_layouts(themes[theme_id], REGISTRY),
    )


@router.get("/api/compatibility/themes",
            response_model=CompatibilityListResponse)
def api_compatibility_themes(
    req: Request,
    layout_id: str = Query(..., min_length=1, max_length=64),
) -> CompatibilityListResponse:
    """R4 Runtime v2 v2.5: 某 layout 兼容的 theme 列表。"""
    if layout_id not in REGISTRY:
        return api_error_response(
            req, 404, ApiError("layout_not_found", f"未知排版：{layout_id}"),
        )
    return CompatibilityListResponse(
        items=list_compatible_themes(get_layout(layout_id), _all_themes(req)),
    )
