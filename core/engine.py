"""合成管线：render_page(theme, layout, library, spec, page, font_path) -> PIL.Image

流程（与旧 compose() 严格同序，保证像素一致）：
1. 读背景 → watermark_fix 则去水印 → 全屏延展（顶部 80px 拉伸 + 模糊接缝）
2. 加载字体（avoid 时歌名降 34）
3. 画柔光层（避让版底边 1498+OFF，否则 1410+OFF）
4. 构造 DrawContext，调 layout.render_page(ctx, page)
5. 返回 RGB 图（保存/预览由调用方决定）
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from .spec import CanvasSpec
from .style import Style
from .watermark import remove_watermark
from .mist import draw_mist
from .context import DrawContext
from .themes.model import Theme
from .layouts.base import LayoutPlugin


def render_page(theme: Theme, layout: LayoutPlugin, library,
                spec: CanvasSpec, page: int, font_path: str) -> Image.Image:
    st: Style = theme.styles[page]
    bg_path = theme.background_path(page)
    AVOID = bool(spec.avoid_zones)
    CH = spec.height
    OFF = (CH - 1920) // 2
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

    font = ImageFont.truetype(font_path, spec.font_song if not AVOID else 34)
    font_label = ImageFont.truetype(font_path, spec.font_label)

    img = draw_mist(img, st, AVOID, OFF, W)

    d = ImageDraw.Draw(img)
    ctx = DrawContext(draw=d, spec=spec, style=st,
                      font_song=font, font_label=font_label)
    layout.render_page(ctx, page, library)
    return img.convert("RGB")
