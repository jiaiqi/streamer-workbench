"""R4 Runtime v2 v2.5: Theme × Layout 能力矩阵测试。

覆盖：
- Theme.compatible_layouts 字段（v1 兼容空 tuple = 全部兼容）
- LayoutPlugin.compatible_themes() 默认空 tuple
- check_compatibility 双向校验
- list_compatible_layouts / list_compatible_themes
- compatibility_matrix 完整矩阵
- 月夜星河 theme.json 加载后 compatible_layouts 字段生效
- grid_wrap.compatible_themes() override 排除「月夜星河」
- 双向校验：theme 排除 grid-wrap + layout 排除月夜星河 → 双重不兼容
- 3 端点集成：/api/compatibility /matrix /layouts /themes
"""
from __future__ import annotations

import pytest

from core.layouts import REGISTRY, get_layout
from core.layouts.compat import (
    check_compatibility,
    compatibility_matrix,
    list_compatible_layouts,
    list_compatible_themes,
)
from core.themes.model import Theme
from core.themes.loader import load_theme


# ── 辅助函数 ──

def _make_theme(name: str, **kwargs) -> Theme:
    """构造 Theme（不依赖目录）"""
    return Theme(
        name=name, dir="", output_prefix=f"prefix-{name}",
        backgrounds={}, watermark_fix=False, styles={}, **kwargs,
    )


# ── Theme.compatible_layouts 字段 ──

class TestThemeCompatibleLayouts:
    def test_default_empty_tuple(self):
        """v1 兼容：不传 compatible_layouts → 空 tuple"""
        t = _make_theme("测试主题")
        assert t.compatible_layouts == ()

    def test_explicit_value(self):
        """显式传 compatible_layouts → 保留"""
        t = _make_theme("测试主题", compatible_layouts=("grid-wrap", "magazine-flow"))
        assert t.compatible_layouts == ("grid-wrap", "magazine-flow")


# ── LayoutPlugin.compatible_themes() 默认 ──

class TestLayoutCompatibleThemes:
    def test_default_empty_tuple(self):
        """默认全兼容（v1 兼容）— 排除 grid-wrap（演示 override）"""
        for layout_id, layout in REGISTRY.items():
            if layout_id == "grid-wrap":
                # grid-wrap 演示 override：排除「月夜星河」
                assert layout.compatible_themes() != ()
                continue
            assert layout.compatible_themes() == ()

    def test_grid_wrap_excludes_yueye(self):
        """grid-wrap 演示 override：排除「月夜星河」"""
        layout = get_layout("grid-wrap")
        themes_declared = layout.compatible_themes()
        assert "月夜星河" not in themes_declared
        assert "海洋柔光" in themes_declared


# ── check_compatibility 双向校验 ──

class TestCheckCompatibility:
    def test_both_default_compatible(self):
        """layout/theme 都没声明 → 全部兼容"""
        layout = get_layout("magazine-flow")
        theme = _make_theme("随便主题")
        ok, reason = check_compatibility(layout, theme)
        assert ok is True
        assert reason == ""

    def test_layout_excludes_theme(self):
        """layout 声明排除 → 不兼容"""
        layout = get_layout("grid-wrap")  # 排除月夜星河
        theme = _make_theme("月夜星河")
        ok, reason = check_compatibility(layout, theme)
        assert ok is False
        assert "grid-wrap" in reason
        assert "月夜星河" in reason

    def test_theme_excludes_layout(self):
        """theme 声明排除 → 不兼容"""
        layout = get_layout("grid-wrap")
        theme = _make_theme("月夜星河", compatible_layouts=("magazine-flow",))
        ok, reason = check_compatibility(layout, theme)
        assert ok is False
        assert "月夜星河" in reason
        assert "grid-wrap" in reason

    def test_both_exclude(self):
        """双向排除（theme + layout 都不兼容）→ 不兼容"""
        layout = get_layout("grid-wrap")  # 排除月夜星河
        theme = _make_theme("月夜星河", compatible_layouts=("magazine-flow",))
        ok, reason = check_compatibility(layout, theme)
        assert ok is False
        # 优先报 layout 端排除
        assert "layout「grid-wrap」" in reason


# ── list_compatible_layouts / list_compatible_themes ──

class TestListCompatible:
    def test_list_compatible_layouts_no_constraint(self):
        """theme 全部兼容 → 返所有 layout（grid-wrap 兼容的主题也算）"""
        # 用 grid-wrap 兼容的 theme 名（演示 override 不影响）
        theme = _make_theme("海洋柔光")
        result = list_compatible_layouts(theme, REGISTRY)
        assert set(result) == set(REGISTRY.keys())

    def test_list_compatible_layouts_with_constraint(self):
        """theme 只兼容部分 layout → 返子集"""
        theme = _make_theme("限制主题", compatible_layouts=("grid-wrap", "magazine-flow"))
        result = list_compatible_layouts(theme, REGISTRY)
        assert set(result) == {"grid-wrap", "magazine-flow"}

    def test_list_compatible_themes_no_constraint(self):
        """layout 不声明 → 返所有 theme"""
        layout = get_layout("magazine-flow")  # 默认全兼容
        themes = {"A": _make_theme("A"), "B": _make_theme("B")}
        result = list_compatible_themes(layout, themes)
        assert set(result) == {"A", "B"}

    def test_list_compatible_themes_with_constraint(self):
        """layout 声明 → 返子集"""
        layout = get_layout("grid-wrap")  # 排除月夜星河
        themes = {
            "海洋柔光": _make_theme("海洋柔光"),
            "月夜星河": _make_theme("月夜星河"),
        }
        result = list_compatible_themes(layout, themes)
        assert result == ["海洋柔光"]


# ── compatibility_matrix 完整矩阵 ──

class TestCompatibilityMatrix:
    def test_matrix_shape(self):
        """matrix 形状：每个 layout × 每个 theme 一格"""
        themes = {
            "A": _make_theme("A"),
            "B": _make_theme("B"),
        }
        matrix = compatibility_matrix(REGISTRY, themes)
        # 5 套 layout × 2 主题 = 10 格
        assert set(matrix.keys()) == set(REGISTRY.keys())
        for lid in matrix:
            assert set(matrix[lid].keys()) == {"A", "B"}
            for tname in matrix[lid]:
                assert "compatible" in matrix[lid][tname]
                assert "reason" in matrix[lid][tname]

    def test_matrix_compatible_result(self):
        """matrix 中各格兼容性正确"""
        themes = {
            "海洋柔光": _make_theme("海洋柔光"),
            "月夜星河": _make_theme("月夜星河", compatible_layouts=("magazine-flow",)),
        }
        matrix = compatibility_matrix(REGISTRY, themes)
        # grid-wrap + 月夜星河 = 不兼容
        assert matrix["grid-wrap"]["月夜星河"]["compatible"] is False
        # grid-wrap + 海洋柔光 = 兼容
        assert matrix["grid-wrap"]["海洋柔光"]["compatible"] is True
        # magazine-flow + 月夜星河 = 兼容（theme 显式声明 + magazine-flow 默认全兼容）
        assert matrix["magazine-flow"]["月夜星河"]["compatible"] is True


# ── theme.json 加载后字段生效 ──

class TestThemeJsonCompatibility:
    def test_yueye_xinghe_json_loads(self):
        """themes/月夜星河/theme.json 加载后 compatible_layouts 字段生效"""
        theme = load_theme("themes/月夜星河")
        # 演示字段：月夜星河兼容 4 套 layout（不含 grid-wrap）
        assert "magazine-flow" in theme.compatible_layouts
        assert "fullscreen-flow" in theme.compatible_layouts
        assert "live-set" in theme.compatible_layouts
        assert "learning-report" in theme.compatible_layouts
        assert "grid-wrap" not in theme.compatible_layouts

    def test_haiyang_rouguang_json_no_constraint(self):
        """themes/海洋柔光/theme.json 不含 compatible_layouts → 全部兼容"""
        theme = load_theme("themes/海洋柔光")
        assert theme.compatible_layouts == ()


# ── 端点集成测试 ──

class TestCompatibilityEndpoints:
    def _make_app(self, tmp: str):
        from pathlib import Path
        from server.app import create_app
        from server.config import AppConfig
        config = AppConfig(
            project_root=Path(".").resolve(),
            mode="test",
            data_root=Path(tmp),
            host="127.0.0.1",
            allowed_origins=("http://localhost", "http://127.0.0.1"),
        )
        return create_app(config)

    def test_endpoint_check_compatible(self):
        """GET /api/compatibility?layout_id=&theme_id= 端点集成"""
        from fastapi.testclient import TestClient
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            app = self._make_app(tmp)
            with TestClient(app) as client:
                # 兼容
                r = client.get("/api/compatibility?layout_id=magazine-flow&theme_id=月夜星河")
                assert r.status_code == 200
                data = r.json()
                assert data["compatible"] is True
                # 不兼容（grid-wrap 排除月夜星河）
                r = client.get("/api/compatibility?layout_id=grid-wrap&theme_id=月夜星河")
                assert r.status_code == 200
                data = r.json()
                assert data["compatible"] is False
                assert "月夜星河" in data["reason"]

    def test_endpoint_matrix(self):
        """GET /api/compatibility/matrix 端点"""
        from fastapi.testclient import TestClient
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            app = self._make_app(tmp)
            with TestClient(app) as client:
                r = client.get("/api/compatibility/matrix")
                assert r.status_code == 200
                data = r.json()
                assert "matrix" in data
                assert "layouts" in data
                assert "themes" in data
                # 5 套 layout
                assert set(data["layouts"]) == set(REGISTRY.keys())
                # 至少 1 套 theme（默认海洋柔光）
                assert len(data["themes"]) >= 1

    def test_endpoint_layouts_for_theme(self):
        """GET /api/compatibility/layouts?theme_id= 端点"""
        from fastapi.testclient import TestClient
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            app = self._make_app(tmp)
            with TestClient(app) as client:
                # 月夜星河只兼容 4 套
                r = client.get("/api/compatibility/layouts?theme_id=月夜星河")
                assert r.status_code == 200
                data = r.json()
                assert "grid-wrap" not in data["items"]
                assert "magazine-flow" in data["items"]

    def test_endpoint_themes_for_layout(self):
        """GET /api/compatibility/themes?layout_id= 端点"""
        from fastapi.testclient import TestClient
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            app = self._make_app(tmp)
            with TestClient(app) as client:
                # grid-wrap 排除月夜星河
                r = client.get("/api/compatibility/themes?layout_id=grid-wrap")
                assert r.status_code == 200
                data = r.json()
                assert "月夜星河" not in data["items"]

    def test_endpoint_404_unknown_layout(self):
        """未知 layout_id → 404"""
        from fastapi.testclient import TestClient
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            app = self._make_app(tmp)
            with TestClient(app) as client:
                r = client.get("/api/compatibility?layout_id=unknown&theme_id=海洋柔光")
                assert r.status_code == 404

    def test_endpoint_404_unknown_theme(self):
        """未知 theme_id → 404"""
        from fastapi.testclient import TestClient
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            app = self._make_app(tmp)
            with TestClient(app) as client:
                r = client.get("/api/compatibility?layout_id=grid-wrap&theme_id=unknown")
                assert r.status_code == 404
