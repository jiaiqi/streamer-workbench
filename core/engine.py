"""合成管线：render_page(theme, layout, library, spec, page, font_path) -> PIL.Image

流程（与旧 compose() 严格同序，保证像素一致）：
1. 读背景 → watermark_fix 则去水印 → 全屏延展（顶部 80px 拉伸 + 模糊接缝）
2. 加载字体（avoid 时歌名降 34）
3. 画柔光层（避让版底边 1498+OFF，否则 1410+OFF）
4. 构造 DrawContext，调 layout.render_page(ctx, page)
5. 返回 RGB 图（保存/预览由调用方决定）
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from functools import lru_cache

from .spec import CanvasSpec
from .style import Style
from .watermark import remove_watermark
from .mist import draw_mist
from .context import DrawContext
from .themes.model import Theme
from .layouts.base import LayoutPlugin


# ---- 背景预处理缓存 ----
# key: 所有影响背景合成的输入签名
# value: 合成后的 RGBA 底版（背景+水印+延展+柔光）
# 参数调整（字号/边距/栏数）时底版完全不变，只重排文字层。
_BG_CACHE: dict = {}


@lru_cache(maxsize=32)
def _load_font(font_path: str, size: int) -> ImageFont.FreeTypeFont:
    """字体实例缓存（LRU，32 个活跃条目）。ImageFont.truetype 是 I/O 密集型操作。"""
    return ImageFont.truetype(font_path, size)


def _compose_base(theme: Theme, page: int, spec: CanvasSpec) -> Image.Image:
    """合成背景底版：读图→去水印→全屏延展→柔光。返回 RGBA。"""
    bg_path = theme.background_path(page)
    AVOID = bool(spec.avoid_zones)
    CH = spec.height
    OFF = spec.content_offset
    FULL = spec.is_fullscreen
    W = spec.width

    img = Image.open(bg_path).convert("RGB")
    if theme.watermark_fix:
        img = remove_watermark(img)

    if FULL:
        img = img.resize((W, round(img.size[1] * W / img.size[0])), Image.LANCZOS)
        bh = img.size[1]
        canvas = Image.new("RGB", (W, CH), (255, 255, 255))
        strip = img.crop((0, 0, W, 80)).resize((W, CH - bh + 4), Image.BICUBIC)
        strip = strip.filter(ImageFilter.GaussianBlur(6))
        canvas.paste(strip, (0, 0))
        canvas.paste(img, (0, CH - bh))
        img = canvas.convert("RGBA")
    else:
        img = img.resize((W, CH), Image.LANCZOS).convert("RGBA")

    st: Style = theme.styles[page]
    img = draw_mist(img, st, AVOID, OFF, W)
    return img


def _get_base(theme: Theme, page: int, spec: CanvasSpec) -> Image.Image:
    """获取缓存底版，未命中则合成并缓存。"""
    st = theme.styles[page]
    key = (
        theme.background_path(page),
        theme.watermark_fix,
        page,
        spec.width,
        spec.height,
        spec.baseline_height,
        tuple(spec.avoid_zones),
        tuple(st.mist),
    )
    if key not in _BG_CACHE:
        _BG_CACHE[key] = _compose_base(theme, page, spec)
    return _BG_CACHE[key].copy()  # 返回副本，避免污染缓存


def clear_bg_cache():
    """清空缓存（主题文件变更后调用）。"""
    _BG_CACHE.clear()


def render_page(theme: Theme, layout: LayoutPlugin, library,
                spec: CanvasSpec, page: int, font_path: str,
                skip_text: bool = False) -> Image.Image:
    st: Style = theme.styles[page]
    AVOID = bool(spec.avoid_zones)

    img = _get_base(theme, page, spec)

    font = _load_font(font_path, spec.font_song if not AVOID else spec.font_song_avoid)
    font_label = _load_font(font_path, spec.font_label)

    d = ImageDraw.Draw(img)
    ctx = DrawContext(draw=d, spec=spec, style=st,
                      font_song=font, font_label=font_label)
    if not skip_text:
        layout.render_page(ctx, page, library)
    return img.convert("RGB")


def render_pages(theme: Theme, layout: LayoutPlugin, library,
                 spec: CanvasSpec, font_path: str, *,
                 page_count: int | None = None) -> list[Image.Image]:
    """R1b: 渲染多页并按序号返回 Image 列表。

    page_count: 可显式指定；不指定则按 layout.pages（None = 自动）或 1 取。
    主要给 magazine-flow 自动分页使用——调用方需先用 layout.analyze()
    拿到真实 pages，再调用 render_pages()。

    旧 layout（grid-wrap）固定 2 页，按 plugin.pages 渲染。
    新 layout（magazine-flow）以 page_count 覆盖。

    上限：当 page_count > theme.styles 提供的样式数时，截断到样式数；
    主流 7 套主题仅支持 2 个 style（兼容 grid-wrap），Magazine-flow
    自动截断防止 KeyError——调用方应据此裁剪 page_count。
    """
    fixed = layout.pages
    if page_count is None:
        if fixed:
            page_count = fixed
        else:
            # 兜底：自动分页由 layout.analyze 决定；若 layout 没实现则用 1
            from .layouts.magazine_flow import analyze as _mf_analyze
            try:
                page_count = _mf_analyze(library, axis="none", canvas=spec)["page_count"]
            except Exception:
                page_count = 1
    # 上限=theme.styles 支持的页数
    max_style_pages = max(theme.styles.keys()) if theme.styles else 2
    page_count = max(1, min(page_count, max_style_pages))
    images = []
    for page in range(1, page_count + 1):
        images.append(render_page(theme, layout, library, spec, page, font_path))
    return images
