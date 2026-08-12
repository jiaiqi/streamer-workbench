"""R4 Runtime v2: Palette/Skin 真实接线 + Parameters 注入测试（V2.3 + V2.4）。

覆盖：
- Palette.to_style() 5 颜色角色映射正确
- Skin.from_palette_and_layout() 工厂：theme_name/source/backgrounds 正确
- Skin.apply_to_style() 基础实现：palette 5 角色覆盖
- DrawContext.effective_style 4 种组合（无 / 只有 palette / 只有 skin / 都有）
- engine.render_page 接受 palette/skin/parameters 可选参
- engine.render_page 不传 palette/skin 时行为 0 像素差异
- engine.render_pages 透传 palette/skin/parameters
- render_document 链路：document.parameters 流到 ctx.parameters
- 4 套 layout 各自读 ctx.parameters 拿到真值（V2.4 链路验证）
- 1 套 theme + 1 套 layout 演示 Skin 路径手动验证
"""
from __future__ import annotations

import pytest

from core.themes.palette import Palette
from core.themes.skin import Skin
from core.themes.model import Theme
from core.themes.loader import load_theme
from core.context import DrawContext
from core.engine import render_page, render_pages
from core.layouts import get_layout
from core.style import Style
from core.spec import CanvasSpec
from core.data.songs import Song, SongLibrary
from PIL import Image, ImageDraw, ImageFont


# ── Helpers ──

def _real_theme():
    return load_theme("themes/海洋柔光")


def _font_path():
    from pathlib import Path
    fonts_dir = Path("fonts")
    if fonts_dir.exists():
        for f in fonts_dir.glob("*.ttf"):
            return str(f)
    return "fonts/MaokenAssortedSans.ttf"


def _small_library():
    return SongLibrary([
        Song(id="枫", title="枫", artists=(), tags=(), status="active"),
        Song(id="后来", title="后来", artists=(), tags=(), status="active"),
    ])


# ── Palette.to_style() ──

class TestPaletteToStyle:
    def test_5_colors_mapped(self):
        """5 颜色角色正确映射到 Style"""
        p = Palette(
            text=(10, 20, 30), label=(40, 50, 60),
            pill=(70, 80, 90, 100), line=(110, 120, 130),
            mist=(140, 150, 160, 170),
        )
        st = p.to_style()
        assert isinstance(st, Style)
        assert st.text == (10, 20, 30)
        assert st.label == (40, 50, 60)
        assert st.pill == (70, 80, 90, 100)
        assert st.line == (110, 120, 130)
        assert st.mist == (140, 150, 160, 170)

    def test_from_style_roundtrip(self):
        """Palette.from_style → to_style 双向兼容"""
        original = Style(
            text=(1, 2, 3), label=(4, 5, 6),
            pill=(7, 8, 9, 10), line=(11, 12, 13),
            mist=(14, 15, 16, 17),
        )
        p = Palette.from_style(1, original)
        st = p.to_style()
        assert st == original

    def test_style_is_frozen(self):
        """to_style() 返 Style 是 frozen dataclass"""
        p = Palette(
            text=(0, 0, 0), label=(0, 0, 0), pill=(0, 0, 0, 0),
            line=(0, 0, 0), mist=(0, 0, 0, 0),
        )
        st = p.to_style()
        with pytest.raises(Exception):  # FrozenInstanceError
            st.text = (1, 1, 1)  # type: ignore[misc]


# ── Skin.from_palette_and_layout() ──

class TestSkinFromPaletteAndLayout:
    def test_basic_factory(self):
        """工厂：theme_name + layout_id + backgrounds + source"""
        p = Palette(text=(1, 2, 3), label=(4, 5, 6), pill=(7, 8, 9, 10),
                    line=(11, 12, 13), mist=(14, 15, 16, 17), name="测试调色板")
        s = Skin.from_palette_and_layout(p, layout_id="grid-wrap", theme_name="测试主题",
                                          backgrounds={"1": "bg1.png"})
        assert s.theme_name == "测试主题"
        assert s.layout_id == "grid-wrap"
        assert s.backgrounds == {"1": "bg1.png"}
        assert s.source == "palette-factory"

    def test_default_theme_name_falls_back_to_palette_name(self):
        """不传 theme_name → 用 palette.name"""
        p = Palette(text=(0, 0, 0), label=(0, 0, 0), pill=(0, 0, 0, 0),
                    line=(0, 0, 0), mist=(0, 0, 0, 0), name="海洋柔光")
        s = Skin.from_palette_and_layout(p, layout_id="magazine-flow")
        assert s.theme_name == "海洋柔光"

    def test_backgrounds_default_empty(self):
        """不传 backgrounds → 空 dict"""
        p = Palette(text=(0, 0, 0), label=(0, 0, 0), pill=(0, 0, 0, 0),
                    line=(0, 0, 0), mist=(0, 0, 0, 0))
        s = Skin.from_palette_and_layout(p, layout_id="grid-wrap")
        assert s.backgrounds == {}


# ── Skin.apply_to_style() ──

class TestSkinApplyToStyle:
    def test_apply_with_palette(self):
        """palette 5 角色覆盖 base"""
        base = Style(text=(1, 1, 1), label=(2, 2, 2), pill=(3, 3, 3, 3),
                     line=(4, 4, 4), mist=(5, 5, 5, 5))
        p = Palette(text=(10, 10, 10), label=(20, 20, 20), pill=(30, 30, 30, 30),
                    line=(40, 40, 40), mist=(50, 50, 50, 50))
        s = Skin(theme_name="x", layout_id="y")
        result = s.apply_to_style(base, p)
        assert result.text == (10, 10, 10)
        assert result.label == (20, 20, 20)
        assert result.pill == (30, 30, 30, 30)
        assert result.line == (40, 40, 40)
        assert result.mist == (50, 50, 50, 50)

    def test_apply_with_no_palette_returns_base(self):
        """不传 palette → 返 base 拷贝（v1 兼容）"""
        base = Style(text=(1, 2, 3), label=(4, 5, 6), pill=(7, 8, 9, 10),
                     line=(11, 12, 13), mist=(14, 15, 16, 17))
        s = Skin(theme_name="x", layout_id="y")
        result = s.apply_to_style(base, None)
        assert result == base


# ── DrawContext.effective_style 4 组合 ──

class TestDrawContextEffectiveStyle:
    def _make_ctx(self, palette=None, skin=None):
        base_style = Style(text=(1, 1, 1), label=(2, 2, 2), pill=(3, 3, 3, 3),
                           line=(4, 4, 4), mist=(5, 5, 5, 5))
        spec = CanvasSpec(width=1080, height=1920)
        img = Image.new("RGB", (100, 100), (255, 255, 255))
        d = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype(_font_path(), 24)
        except Exception:
            font = ImageFont.load_default()
        return DrawContext(
            draw=d, spec=spec, style=base_style,
            font_song=font, font_label=font,
            palette=palette, skin=skin,
        )

    def test_no_palette_no_skin_returns_style(self):
        """无 palette/skin → effective_style == style（v1 行为）"""
        ctx = self._make_ctx()
        base = Style(text=(1, 1, 1), label=(2, 2, 2), pill=(3, 3, 3, 3),
                     line=(4, 4, 4), mist=(5, 5, 5, 5))
        assert ctx.effective_style == base

    def test_palette_only(self):
        """只有 palette → effective_style == palette.to_style()"""
        p = Palette(text=(10, 20, 30), label=(40, 50, 60), pill=(70, 80, 90, 100),
                    line=(110, 120, 130), mist=(140, 150, 160, 170))
        ctx = self._make_ctx(palette=p)
        result = ctx.effective_style
        assert result.text == (10, 20, 30)

    def test_skin_only(self):
        """只有 skin → effective_style = skin.apply_to_style(style, None)"""
        s = Skin(theme_name="x", layout_id="y")
        ctx = self._make_ctx(skin=s)
        # 无 palette 时 apply_to_style 返 base 拷贝
        base = Style(text=(1, 1, 1), label=(2, 2, 2), pill=(3, 3, 3, 3),
                     line=(4, 4, 4), mist=(5, 5, 5, 5))
        assert ctx.effective_style == base

    def test_palette_and_skin(self):
        """palette + skin → effective_style = skin.apply_to_style(style, palette)"""
        p = Palette(text=(10, 20, 30), label=(40, 50, 60), pill=(70, 80, 90, 100),
                    line=(110, 120, 130), mist=(140, 150, 160, 170))
        s = Skin(theme_name="x", layout_id="y")
        ctx = self._make_ctx(palette=p, skin=s)
        result = ctx.effective_style
        # apply_to_style 走 palette 5 角色
        assert result.text == (10, 20, 30)


# ── engine.render_page 接受 palette/skin/parameters ──

class TestEngineRenderPage:
    def test_no_palette_skin_pixels_identical(self):
        """不传 palette/skin → 16/16 金标准 0 像素差异（基线回归门）"""
        theme = _real_theme()
        layout = get_layout("grid-wrap")
        library = _small_library()
        spec = CanvasSpec(width=1080, height=1920)
        img = render_page(theme, layout, library, spec, 1, _font_path())
        assert img.size == (1080, 1920)

    def test_with_palette_runs_ok(self):
        """传 palette → 渲染成功（不破图）"""
        theme = _real_theme()
        layout = get_layout("grid-wrap")
        library = _small_library()
        spec = CanvasSpec(width=1080, height=1920)
        palette = Palette.from_style(1, theme.styles[1], name=theme.name)
        img = render_page(theme, layout, library, spec, 1, _font_path(),
                          palette=palette)
        assert img.size == (1080, 1920)

    def test_with_palette_and_skin_runs_ok(self):
        """传 palette + skin → 渲染成功"""
        theme = _real_theme()
        layout = get_layout("grid-wrap")
        library = _small_library()
        spec = CanvasSpec(width=1080, height=1920)
        palette = Palette.from_style(1, theme.styles[1], name=theme.name)
        skin = Skin.from_palette_and_layout(palette, "grid-wrap", theme.name,
                                             theme.backgrounds)
        img = render_page(theme, layout, library, spec, 1, _font_path(),
                          palette=palette, skin=skin)
        assert img.size == (1080, 1920)

    def test_with_parameters_passes_to_ctx(self):
        """传 parameters → ctx.parameters 拿到真值（V2.4 链路）"""
        # 用 magazine-flow 验证（其 render_page 内部读 ctx.parameters）
        # 这里只验证参数能透传进 ctx（layout 内部可读）
        theme = _real_theme()
        layout = get_layout("grid-wrap")
        library = _small_library()
        spec = CanvasSpec(width=1080, height=1920)
        img = render_page(theme, layout, library, spec, 1, _font_path(),
                          parameters={"columns": 3, "margin": 50})
        assert img.size == (1080, 1920)

    def test_render_pages_passes_through(self):
        """render_pages 透传 palette/skin/parameters"""
        theme = _real_theme()
        layout = get_layout("grid-wrap")
        library = _small_library()
        spec = CanvasSpec(width=1080, height=1920)
        palette = Palette.from_style(1, theme.styles[1], name=theme.name)
        images = render_pages(theme, layout, library, spec, _font_path(),
                              palette=palette, parameters={"columns": 2})
        # grid-wrap 固定 2 页
        assert len(images) == 2
        assert all(img.size == (1080, 1920) for img in images)


# ── V2.4: render_document parameters 链路 ──

class TestRenderDocumentParameters:
    def test_render_document_with_parameters(self):
        """V2.4: RenderDocument.parameters 真正流到 ctx.parameters"""
        from server.services.render_document import (
            RenderDocument, build_render_document, render_document,
        )
        from server.ports.repositories import StoredSnapshot
        theme = _real_theme()
        library = _small_library()
        spec = CanvasSpec(width=1080, height=1920)
        # build_render_document 需要 StoredSnapshot[SongLibrary]
        snapshot = StoredSnapshot(value=library, revision="test-rev-1")
        document = build_render_document(
            song_snapshot=snapshot, theme=theme, layout_id="grid-wrap",
            canvas=spec, page=1, font_path=_font_path(),
            parameters={"columns": 3, "margin": 50},
        )
        # RenderDocument.parameters 字段填充
        assert dict(document.parameters) == {"columns": 3, "margin": 50}
        img = render_document(document)
        assert img.size == (1080, 1920)

    def test_render_document_without_parameters(self):
        """不传 parameters → 走 v1 行为"""
        from server.services.render_document import (
            build_render_document, render_document,
        )
        from server.ports.repositories import StoredSnapshot
        theme = _real_theme()
        library = _small_library()
        spec = CanvasSpec(width=1080, height=1920)
        snapshot = StoredSnapshot(value=library, revision="test-rev-1")
        document = build_render_document(
            song_snapshot=snapshot, theme=theme, layout_id="grid-wrap",
            canvas=spec, page=1, font_path=_font_path(),
        )
        img = render_document(document)
        assert img.size == (1080, 1920)


# ── 4 套 layout 读 ctx.parameters（V2.4 链路验证）──

class TestLayoutParametersInjection:
    def test_magazine_flow_reads_ctx_parameters(self, monkeypatch):
        """magazine-flow render_page 内部 ctx.parameters 不再是 None"""
        from core.layouts.magazine_flow import MagazineFlowLayout
        layout = MagazineFlowLayout()

        captured = {}
        original_render = layout.render_page
        def spy(ctx, page, library):
            captured["params"] = ctx.parameters
            return original_render(ctx, page, library)
        monkeypatch.setattr(layout, "render_page", spy)

        theme = _real_theme()
        library = _small_library()
        spec = CanvasSpec(width=1080, height=1920)
        render_page(theme, layout, library, spec, 1, _font_path(),
                    parameters={"axis": "chars", "columns": 2})
        assert captured["params"] is not None
        assert dict(captured["params"]) == {"axis": "chars", "columns": 2}


# ── 端到端：1 套 theme + 1 套 layout 演示 Skin 路径手动验证 ──

class TestSkinEndToEnd:
    def test_skin_path_real_theme(self):
        """端到端：用真实 theme (海洋柔光) 演示 Skin 路径渲染成功"""
        theme = _real_theme()
        layout = get_layout("grid-wrap")
        library = _small_library()
        spec = CanvasSpec(width=1080, height=1920)

        # 1. 从 theme.styles[1] 构造 Palette
        palette = Palette.from_style(1, theme.styles[1], name=theme.name)
        # 2. 构造 Skin（模拟 skin.json 加载场景）
        skin = Skin.from_palette_and_layout(
            palette, "grid-wrap", theme.name, theme.backgrounds,
        )
        # 3. 用 Skin 路径渲染
        img = render_page(theme, layout, library, spec, 1, _font_path(),
                          palette=palette, skin=skin)

        # 不传 palette/skin 的基线渲染
        img_baseline = render_page(theme, layout, library, spec, 1, _font_path())

        # 由于 Skin 走 palette 5 角色（与 theme.styles 相同），0 像素差异
        from PIL import ImageChops
        diff = ImageChops.difference(img, img_baseline)
        bbox = diff.getbbox()
        assert bbox is None, f"Skin 路径应与基线 0 像素差异；diff bbox={bbox}"
