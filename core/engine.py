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
# key: (theme_name, page, canvas_width, canvas_height)
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
    key = (theme.name, page, spec.width, spec.height)
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
