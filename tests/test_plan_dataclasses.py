"""R4 Runtime v2: LayoutPlan / LayoutAnalysis / PagePlan / SectionPlan / LayoutContext 数据结构测试。

覆盖：
- SectionPlan 字段必填 + 不可变 + 序列化
- PagePlan 字段 + tuple 不可变
- LayoutAnalysis 字段默认值
- LayoutPlan 字段 + 嵌套 dataclass
- LayoutContext 字段 + None 默认
- 模块导出（__all__ + 直接 import）
"""
from __future__ import annotations

import pytest

from core.layouts.plan import (
    LayoutAnalysis,
    LayoutPlan,
    PagePlan,
    SectionLayoutKind,
    SectionPlan,
)
from core.layouts.ctx import LayoutContext
from core.layouts import (
    LayoutAnalysis as LayoutAnalysisFromInit,
    LayoutPlan as LayoutPlanFromInit,
    PagePlan as PagePlanFromInit,
    SectionPlan as SectionPlanFromInit,
    LayoutContext as LayoutContextFromInit,
)
from core.spec import CanvasSpec


# ── SectionPlan ──

class TestSectionPlan:
    def test_required_fields(self):
        """label + song_titles 必填"""
        sp = SectionPlan(label="一字", song_titles=("枫", "耿"))
        assert sp.label == "一字"
        assert sp.song_titles == ("枫", "耿")
        assert sp.layout_kind == "flow"
        assert sp.columns == 1
        assert sp.decoration is None
        assert sp.bbox is None

    def test_immutable(self):
        """frozen=True：字段赋值抛 FrozenInstanceError"""
        sp = SectionPlan(label="x", song_titles=("a",))
        with pytest.raises(Exception):  # FrozenInstanceError
            sp.label = "y"  # type: ignore[misc]

    def test_song_titles_accepts_list(self):
        """song_titles 接受 list，自动转 tuple"""
        sp = SectionPlan(label="x", song_titles=["a", "b", "c"])
        assert sp.song_titles == ("a", "b", "c")
        assert isinstance(sp.song_titles, tuple)

    def test_layout_kind_literal(self):
        """layout_kind 限定 3 个 Literal 值"""
        assert SectionPlan(label="x", song_titles=(), layout_kind="flow")
        assert SectionPlan(label="x", song_titles=(), layout_kind="columns")
        assert SectionPlan(label="x", song_titles=(), layout_kind="list")

    def test_bbox_optional(self):
        """bbox 是 0-1 归一化坐标 4-tuple"""
        sp = SectionPlan(label="x", song_titles=(), bbox=(0.0, 0.0, 0.5, 0.5))
        assert sp.bbox == (0.0, 0.0, 0.5, 0.5)


# ── PagePlan ──

class TestPagePlan:
    def test_required_fields(self):
        pp = PagePlan(page=1, sections=(SectionPlan(label="x", song_titles=()),))
        assert pp.page == 1
        assert len(pp.sections) == 1
        assert pp.header is None
        assert pp.footer is None
        assert pp.bg_strategy is None

    def test_multiple_sections(self):
        sections = (
            SectionPlan(label="一字", song_titles=("枫",)),
            SectionPlan(label="二字", song_titles=("后来", "红豆")),
        )
        pp = PagePlan(page=1, sections=sections)
        assert len(pp.sections) == 2
        assert pp.sections[0].label == "一字"
        assert pp.sections[1].song_titles == ("后来", "红豆")

    def test_immutable(self):
        pp = PagePlan(page=1, sections=())
        with pytest.raises(Exception):
            pp.page = 2  # type: ignore[misc]

    def test_sections_is_tuple(self):
        """sections 字段强制 tuple（可哈希 + 不可变）"""
        sections_list = [SectionPlan(label="x", song_titles=())]
        pp = PagePlan(page=1, sections=tuple(sections_list))
        assert isinstance(pp.sections, tuple)


# ── LayoutAnalysis ──

class TestLayoutAnalysis:
    def test_required_field_page_count(self):
        """page_count 是必填（v1 阶段其他字段都给默认）"""
        a = LayoutAnalysis(page_count=2)
        assert a.page_count == 2
        assert a.overflow is False
        assert a.degrade_reason is None
        assert a.sections_count == 0
        assert a.axes_used == ()
        assert a.total_songs == 0
        assert a.max_density == {}

    def test_axes_used_accepts_list(self):
        """axes_used 接受 list，自动转 tuple"""
        a = LayoutAnalysis(page_count=1, axes_used=["chars", "artist"])
        assert a.axes_used == ("chars", "artist")
        assert isinstance(a.axes_used, tuple)

    def test_overflow_flag(self):
        a = LayoutAnalysis(page_count=2, overflow=True, degrade_reason="容量超限")
        assert a.overflow is True
        assert a.degrade_reason == "容量超限"

    def test_immutable(self):
        a = LayoutAnalysis(page_count=1)
        with pytest.raises(Exception):
            a.page_count = 5  # type: ignore[misc]

    def test_max_density_independent(self):
        """max_density 字段独立可变（dict 输入）；不影响 immutable 校验"""
        a = LayoutAnalysis(page_count=1)
        assert dict(a.max_density) == {}
        b = LayoutAnalysis(page_count=1, max_density={"per_page": 36})
        assert dict(b.max_density) == {"per_page": 36}


# ── LayoutPlan ──

class TestLayoutPlan:
    def test_required_field_layout_id(self):
        p = LayoutPlan(layout_id="grid-wrap")
        assert p.layout_id == "grid-wrap"
        assert p.layout_version == "1"
        assert p.pages == ()
        assert p.effective_palette_name == ""
        assert p.param_overrides == {}
        # analysis 默认值
        assert p.analysis.page_count == 1

    def test_full_construction(self):
        analysis = LayoutAnalysis(page_count=3, sections_count=8, total_songs=36)
        pages = (
            PagePlan(page=1, sections=(
                SectionPlan(label="一字", song_titles=("枫", "耿")),
            )),
            PagePlan(page=2, sections=()),
            PagePlan(page=3, sections=()),
        )
        p = LayoutPlan(
            layout_id="magazine-flow",
            layout_version="1",
            analysis=analysis,
            pages=pages,
            effective_palette_name="海洋柔光",
            param_overrides={"columns": 2},
        )
        assert p.layout_id == "magazine-flow"
        assert p.analysis.page_count == 3
        assert len(p.pages) == 3
        assert p.pages[0].sections[0].label == "一字"
        assert p.effective_palette_name == "海洋柔光"
        assert p.param_overrides == {"columns": 2}

    def test_immutable(self):
        p = LayoutPlan(layout_id="x")
        with pytest.raises(Exception):
            p.layout_id = "y"  # type: ignore[misc]

    def test_hashable(self):
        """frozen=True → 可哈希"""
        a = LayoutPlan(layout_id="x")
        b = LayoutPlan(layout_id="x")
        assert hash(a) == hash(b)
        # 放 set 不报错
        s = {a, b}
        assert len(s) == 1

    def test_pages_is_tuple(self):
        """pages 字段强制 tuple"""
        pages_list = [PagePlan(page=1, sections=())]
        p = LayoutPlan(layout_id="x", pages=tuple(pages_list))
        assert isinstance(p.pages, tuple)


# ── LayoutContext ──

class TestLayoutContext:
    def test_required_field_canvas(self):
        spec = CanvasSpec(width=1080, height=1920)
        ctx = LayoutContext(canvas=spec)
        assert ctx.canvas is spec
        assert ctx.parameters == {}
        assert ctx.theme_capabilities == ()
        assert ctx.palette is None
        assert ctx.skin is None

    def test_with_parameters(self):
        spec = CanvasSpec(width=1080, height=1920)
        ctx = LayoutContext(
            canvas=spec,
            parameters={"columns": 2, "margin": 50},
            theme_capabilities=("warm", "soft"),
        )
        assert ctx.parameters == {"columns": 2, "margin": 50}
        assert ctx.theme_capabilities == ("warm", "soft")

    def test_immutable(self):
        spec = CanvasSpec(width=1080, height=1920)
        ctx = LayoutContext(canvas=spec)
        with pytest.raises(Exception):
            ctx.parameters = {"x": 1}  # type: ignore[misc]


# ── 模块导出 ──

class TestModuleExports:
    def test_from_init(self):
        """core.layouts 顶层导出 5 个新 dataclass"""
        assert LayoutAnalysisFromInit is LayoutAnalysis
        assert LayoutPlanFromInit is LayoutPlan
        assert PagePlanFromInit is PagePlan
        assert SectionPlanFromInit is SectionPlan
        assert LayoutContextFromInit is LayoutContext

    def test_init_all_includes_v2(self):
        """core.layouts.__all__ 包含 v2 导出"""
        from core.layouts import __all__
        for name in ("LayoutAnalysis", "LayoutPlan", "PagePlan", "SectionPlan",
                     "SectionLayoutKind", "LayoutContext"):
            assert name in __all__, f"{name} 应在 __all__ 里"

    def test_plan_module_all(self):
        from core.layouts.plan import __all__
        for name in ("SectionPlan", "PagePlan", "LayoutAnalysis", "LayoutPlan", "SectionLayoutKind"):
            assert name in __all__
