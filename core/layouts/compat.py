"""R4 Runtime v2: Theme × Layout 能力矩阵校验。

双向校验：
- layout 声明 compatible_themes() 排除 theme → 不兼容
- theme 声明 compatible_layouts 排除 layout → 不兼容
- 任一未声明 = 全部兼容（v1 兼容）

UI 端：LayoutPicker 用 check_compatibility 在主题下拉里灰显不兼容项。
"""
from __future__ import annotations

from typing import Optional, Tuple

from .base import LayoutPlugin
from ..themes.model import Theme


def check_compatibility(layout: LayoutPlugin, theme: Theme) -> Tuple[bool, str]:
    """R4 Runtime v2: 双向校验 layout × theme 兼容性。

    返回 (compatible, reason)：
    - True, ""：完全兼容
    - False, "reason"：不兼容 + 不兼容原因

    v1 兼容：layout.compatible_themes() 或 theme.compatible_layouts 空 = 全部兼容。
    """
    # 1. layout 自报不兼容的 theme
    layout_themes = layout.compatible_themes()
    if layout_themes and theme.name not in layout_themes:
        return False, f"layout「{layout.id}」声明不兼容 theme「{theme.name}」"
    # 2. theme 自报不兼容的 layout
    if theme.compatible_layouts and layout.id not in theme.compatible_layouts:
        return False, f"theme「{theme.name}」声明不兼容 layout「{layout.id}」"
    return True, ""


def list_compatible_layouts(theme: Theme, all_layouts: dict[str, LayoutPlugin]) -> list[str]:
    """R4 Runtime v2: 列出某 theme 兼容的 layout id 列表。

    给前端 UI 用：先看 theme.compatible_layouts 是否为空，
    否则按 layout 自报 compatible_themes() 二次过滤。
    """
    if theme.compatible_layouts:
        # theme 显式声明只兼容部分 layout → 直接取交集
        return [lid for lid in theme.compatible_layouts if lid in all_layouts]
    # theme 全部兼容 → 按 layout 自报过滤
    return [
        lid for lid, layout in all_layouts.items()
        if not layout.compatible_themes() or theme.name in layout.compatible_themes()
    ]


def list_compatible_themes(layout: LayoutPlugin, all_themes: dict[str, Theme]) -> list[str]:
    """R4 Runtime v2: 列出某 layout 兼容的 theme id 列表。

    给前端 UI 用：按 layout 自报 compatible_themes() 过滤（None = 全部）。
    """
    declared = layout.compatible_themes()
    if not declared:
        return list(all_themes.keys())
    return [tname for tname in all_themes if tname in declared]


def compatibility_matrix(
    all_layouts: dict[str, LayoutPlugin],
    all_themes: dict[str, Theme],
) -> dict[str, dict[str, dict]]:
    """R4 Runtime v2: 完整兼容矩阵（layout × theme）。

    返回结构：
      {
        layout_id: {
          theme_id: {"compatible": bool, "reason": str}
        }
      }

    给前端 UI 用：启动时拉一次缓存，主题/布局切换时实时校验。
    """
    matrix: dict[str, dict[str, dict]] = {}
    for lid, layout in all_layouts.items():
        matrix[lid] = {}
        for tname, theme in all_themes.items():
            ok, reason = check_compatibility(layout, theme)
            matrix[lid][tname] = {"compatible": ok, "reason": reason}
    return matrix


__all__ = [
    "check_compatibility",
    "list_compatible_layouts",
    "list_compatible_themes",
    "compatibility_matrix",
]
