"""R4 Runtime v2: analyze 统一签名 + render_pages 解耦 测试。

覆盖：
- base.py 默认 analyze(library, ctx) 返 LayoutAnalysis(page_count=plugin.pages or 1)
- 4 套 layout analyze() 统一签名：ctx 既可 LayoutContext 也可 CanvasSpec（v1 兼容）
- grid-wrap: 固定 2 页 + 7 段
- magazine-flow: 1-3 页（按 axis + 歌数）
- live-set: 固定 1 页 + 4 段
- learning-report: 固定 1 页 + 4 段
- engine.render_pages 解耦：自动分页走 layout.analyze() 而非写死 magazine_flow
- base.py 默认 plan(library, ctx) 从 PageSections 派生 LayoutPlan
- 4 套 layout plan() 都能调通
"""
from __future__ import annotations

import pytest

from core.layouts import (
    REGISTRY, get_layout,
    LayoutAnalysis, LayoutPlan, LayoutContext,
)
from core.layouts.base import LayoutPlugin, PageSections
from core.layouts.channel import DataChannel
from core.spec import CanvasSpec
from core.data.songs import Song, SongLibrary
from core.themes.model import Theme


# ── Helpers ──

def _ctx(canvas: CanvasSpec | None = None, **kwargs) -> LayoutContext:
    if canvas is None:
        canvas = CanvasSpec(width=1080, height=1920)
    return LayoutContext(canvas=canvas, **kwargs)


def _song(title: str, section: int | None = None) -> Song:
    return Song(
        id=title, title=title, artists=(), tags=(), section=section,
        status="active",  # SongLibrary.mastered() == active() 走 active
    )


def _small_library() -> SongLibrary:
    """7 首歌，跨 1-7 字 + 1 个英文"""
    return SongLibrary([
        _song("枫"), _song("后来"), _song("恋爱ing"),
        _song("黑色毛衣"), _song("江南"), _song("童年"),
        _song("Take Me Home, Country Roads"),
    ])


def _many_library(n: int = 36) -> SongLibrary:
    """36 首歌（够 magazine-flow 触发 auto 分页）"""
    titles = [f"歌{i}" for i in range(1, n + 1)]
    return SongLibrary([_song(t) for t in titles])


# ── base.py 默认 analyze ──

class TestBaseAnalyze:
    def test_default_analyze_with_pages(self):
        """子类 plugin.pages=2 → LayoutAnalysis(page_count=2)"""
        layout = get_layout("grid-wrap")
        ctx = _ctx()
        result = layout.analyze(_small_library(), ctx)
        assert isinstance(result, LayoutAnalysis)
        assert result.page_count == 2  # grid-wrap.pages = 2

    def test_default_analyze_without_pages(self):
        """子类 plugin.pages=None → LayoutAnalysis(page_count=1)"""
        # 构造一个 pages=None 的 mock layout
        class _MockAutoLayout(LayoutPlugin):
            id = "mock-auto"
            name = "Mock Auto"
            pages = None
            supported_channels = ("song_library",)
            def params(self): return []
            def categorize(self, library): return [PageSections(1, [])]
            def render_page(self, ctx, page, library): return 0
        layout = _MockAutoLayout()
        ctx = _ctx()
        result = layout.analyze(_small_library(), ctx)
        assert isinstance(result, LayoutAnalysis)
        assert result.page_count == 1  # 默认兜底


# ── 4 套 layout 统一签名 ──

class TestGridWrapAnalyze:
    def test_grid_wrap_fixed_2_pages(self):
        """grid-wrap 固定 2 页"""
        layout = get_layout("grid-wrap")
        result = layout.analyze(_small_library(), _ctx())
        assert result.page_count == 2
        assert result.sections_count == 7
        assert result.axes_used == ("chars",)

    def test_grid_wrap_accepts_canvas_spec(self):
        """v1 兼容：ctx 既可 LayoutContext 也可 CanvasSpec"""
        layout = get_layout("grid-wrap")
        canvas = CanvasSpec(width=1080, height=1920)
        result = layout.analyze(_small_library(), canvas)
        assert result.page_count == 2

    def test_grid_wrap_empty_library(self):
        """空 library 不报错"""
        layout = get_layout("grid-wrap")
        result = layout.analyze(SongLibrary([]), _ctx())
        assert result.page_count == 2
        assert result.sections_count == 7


class TestMagazineFlowAnalyze:
    def test_magazine_axis_none_1_page(self):
        """axis=none + 7 首歌 → 1 页"""
        layout = get_layout("magazine-flow")
        result = layout.analyze(_small_library(), _ctx(), axis="none")
        assert result.page_count >= 1
        assert "none" in result.axes_used or result.axes_used == ()

    def test_magazine_axis_chars_with_many_songs(self):
        """axis=chars + 36 首歌 → 2-3 页（auto 分页）"""
        layout = get_layout("magazine-flow")
        result = layout.analyze(_many_library(36), _ctx(), axis="chars")
        assert result.page_count >= 2  # 36 首歌应该 multi-page

    def test_magazine_axis_from_ctx_parameters(self):
        """ctx.parameters.get('axis', ...) 覆盖默认 axis"""
        layout = get_layout("magazine-flow")
        ctx = _ctx(parameters={"axis": "chars"})
        result = layout.analyze(_many_library(36), ctx, axis="none")
        # 实际应走 chars 而非 none → 至少 2 页
        assert result.page_count >= 2

    def test_magazine_accepts_canvas_spec(self):
        """v1 兼容：ctx 接受 CanvasSpec"""
        layout = get_layout("magazine-flow")
        canvas = CanvasSpec(width=1080, height=1920)
        result = layout.analyze(_small_library(), canvas, axis="none")
        assert result.page_count >= 1


class TestLiveSetAnalyze:
    def test_live_set_fixed_1_page(self):
        """live-set 固定 1 页"""
        from core.layouts.live_set import LiveSessionSnapshot
        snap = LiveSessionSnapshot(
            session_id="s1", session_title="测试直播",
            session_state="closed",
            started_at="2026-08-12T20:00:00", closed_at="2026-08-12T22:00:00",
            rule_version="v1", requests=(), performances=(),
        )
        layout = get_layout("live-set")
        result = layout.analyze(snap, _ctx())
        assert result.page_count == 1
        assert result.sections_count == 4

    def test_live_set_wrong_library_degrades(self):
        """非 LiveSessionSnapshot → degrade_reason"""
        from core.layouts.live_set import LiveSessionSnapshot
        layout = get_layout("live-set")
        result = layout.analyze(_small_library(), _ctx())
        assert result.page_count == 1
        assert result.degrade_reason is not None
        assert "LiveSessionSnapshot" in result.degrade_reason

    def test_live_set_accepts_canvas_spec(self):
        """v1 兼容"""
        from core.layouts.live_set import LiveSessionSnapshot
        snap = LiveSessionSnapshot(
            session_id="s1", session_title="测试直播",
            session_state="closed",
            started_at="2026-08-12T20:00:00", closed_at="2026-08-12T22:00:00",
            rule_version="v1", requests=(), performances=(),
        )
        layout = get_layout("live-set")
        canvas = CanvasSpec(width=1080, height=1920)
        result = layout.analyze(snap, canvas)
        assert result.page_count == 1


class TestLearningReportAnalyze:
    def test_learning_report_fixed_1_page(self):
        """learning-report 固定 1 页"""
        from core.layouts.learning_report import LearningReportSnapshot
        snap = LearningReportSnapshot(
            report_title="7 天学歌",
            period_label="近 7 天", period_start="2026-08-05", period_end="2026-08-12",
            total_practice_minutes=120, total_practice_sessions=5,
            current_streak_days=3, longest_streak_days=7,
            songs_learned=(), recent_practice=(), top_artists=(),
        )
        layout = get_layout("learning-report")
        result = layout.analyze(snap, _ctx())
        assert result.page_count == 1
        assert result.sections_count == 4

    def test_learning_report_wrong_library_degrades(self):
        """非 LearningReportSnapshot → degrade_reason"""
        layout = get_layout("learning-report")
        result = layout.analyze(_small_library(), _ctx())
        assert result.page_count == 1
        assert result.degrade_reason is not None
        assert "LearningReportSnapshot" in result.degrade_reason

    def test_learning_report_accepts_canvas_spec(self):
        """v1 兼容"""
        from core.layouts.learning_report import LearningReportSnapshot
        snap = LearningReportSnapshot(
            report_title="7 天学歌",
            period_label="近 7 天", period_start="2026-08-05", period_end="2026-08-12",
            total_practice_minutes=120, total_practice_sessions=5,
        )
        layout = get_layout("learning-report")
        canvas = CanvasSpec(width=1080, height=1920)
        result = layout.analyze(snap, canvas)
        assert result.page_count == 1


# ── render_pages 解耦 ──

class TestRenderPagesDecoupling:
    """V2.2: engine.render_pages 不再写死 magazine_flow."""

    def test_render_pages_uses_layout_analyze(self, monkeypatch):
        """render_pages 的 page_count 来自 layout.analyze() 而非写死 import"""
        from core import engine

        # 准备真实 theme（grid-wrap 用 2 页）
        theme = _real_theme()
        font_path = _font_path()
        layout = get_layout("grid-wrap")
        library = _small_library()

        # 不显式传 page_count → 走 layout.analyze() 自动
        images = engine.render_pages(theme, layout, library,
                                     CanvasSpec(width=1080, height=1920),
                                     font_path)
        assert len(images) == 2  # grid-wrap 固定 2 页

    def test_render_pages_explicit_page_count_wins(self):
        """显式 page_count 覆盖 analyze()"""
        from core import engine

        theme = _real_theme()
        font_path = _font_path()
        layout = get_layout("grid-wrap")
        library = _small_library()

        # 显式 page_count=1 → 走 1 页
        images = engine.render_pages(theme, layout, library,
                                     CanvasSpec(width=1080, height=1920),
                                     font_path, page_count=1)
        assert len(images) == 1

    def test_engine_no_longer_imports_magazine_flow(self):
        """R4 v2: engine.render_pages 不写死 magazine_flow import"""
        from core import engine
        # 读 source 确认
        import inspect
        src = inspect.getsource(engine.render_pages)
        assert "from .layouts.magazine_flow import analyze" not in src
        assert "layout.analyze" in src


# ── base.py 默认 plan ──

class TestBasePlan:
    def test_plan_derives_from_page_sections(self):
        """base.plan() 把 PageSections 转成 PagePlan + SectionPlan"""
        layout = get_layout("grid-wrap")
        ctx = _ctx()
        result = layout.plan(_small_library(), ctx)
        assert isinstance(result, LayoutPlan)
        assert result.layout_id == "grid-wrap"
        assert result.layout_version == "1"
        # 7 段（4 + 3）
        total_sections = sum(len(p.sections) for p in result.pages)
        assert total_sections == 7
        # 2 页
        assert len(result.pages) == 2
        # 第一页 4 段
        assert len(result.pages[0].sections) == 4
        # 第二页 3 段
        assert len(result.pages[1].sections) == 3

    def test_plan_param_overrides_from_ctx(self):
        """plan().param_overrides 来自 ctx.parameters"""
        layout = get_layout("grid-wrap")
        ctx = _ctx(parameters={"columns": 3, "margin": 50})
        result = layout.plan(_small_library(), ctx)
        assert dict(result.param_overrides) == {"columns": 3, "margin": 50}

    def test_plan_empty_parameters_default(self):
        """ctx.parameters 缺省 → param_overrides 空"""
        layout = get_layout("grid-wrap")
        ctx = _ctx()
        result = layout.plan(_small_library(), ctx)
        assert dict(result.param_overrides) == {}


# ── 4 套 layout plan() ──

class TestLayoutPlan:
    @pytest.mark.parametrize("layout_id", [
        "grid-wrap", "magazine-flow", "fullscreen-flow",
    ])
    def test_song_library_layouts_plan_ok(self, layout_id):
        """3 套 song_library layout 都能 plan()"""
        layout = get_layout(layout_id)
        plan = layout.plan(_small_library(), _ctx())
        assert isinstance(plan, LayoutPlan)
        assert plan.layout_id == layout_id
        assert len(plan.pages) >= 1

    def test_live_set_plan_ok(self):
        """live-set plan() — 固定 1 页"""
        from core.layouts.live_set import LiveSessionSnapshot
        snap = LiveSessionSnapshot(
            session_id="s1", session_title="测试直播",
            session_state="closed",
            started_at="2026-08-12T20:00:00", closed_at="2026-08-12T22:00:00",
            rule_version="v1", requests=(), performances=(),
        )
        layout = get_layout("live-set")
        plan = layout.plan(snap, _ctx())
        assert plan.layout_id == "live-set"
        assert len(plan.pages) == 1

    def test_learning_report_plan_ok(self):
        """learning-report plan() — 固定 1 页"""
        from core.layouts.learning_report import LearningReportSnapshot
        snap = LearningReportSnapshot(
            report_title="7 天学歌",
            period_label="近 7 天", period_start="2026-08-05", period_end="2026-08-12",
            total_practice_minutes=120, total_practice_sessions=5,
            current_streak_days=3, longest_streak_days=7,
        )
        layout = get_layout("learning-report")
        plan = layout.plan(snap, _ctx())
        assert plan.layout_id == "learning-report"
        assert len(plan.pages) == 1


# ── 辅助函数 ──

def _real_theme():
    """加载真实主题（海洋柔光）"""
    from core.themes.loader import load_theme
    return load_theme("themes/海洋柔光")


def _font_path():
    """真实字体路径"""
    from pathlib import Path
    for p in ("fonts/MaokenAssortedSans.ttf", "fonts/cat-crack.ttf",
              "fonts/default.ttf"):
        if Path(p).exists():
            return p
    # 兜底：返回 fonts/ 目录下第一个 .ttf
    fonts_dir = Path("fonts")
    if fonts_dir.exists():
        for f in fonts_dir.glob("*.ttf"):
            return str(f)
    return "fonts/MaokenAssortedSans.ttf"  # 期望路径
