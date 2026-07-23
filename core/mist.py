"""柔光层：无边框、向四周消散的半透明遮罩，压住落在文字区的背景装饰。

移植自 歌单-排版一\build_playlist.py 的 compose() 柔光段。
避让版底边下延 88px（1498+OFF），保证绕排多出的行仍落在柔光上。
"""
from PIL import Image, ImageDraw, ImageFilter

from .style import Style


def draw_mist(img, style: Style, avoid: bool, off: int, width: int):
    mist_bottom = (1498 if avoid else 1410) + off
    mist = Image.new("RGBA", (width, img.size[1]), (0, 0, 0, 0))
    md = ImageDraw.Draw(mist)
    md.rounded_rectangle((-60, -60, width + 60, mist_bottom), radius=80, fill=style.mist)
    mist = mist.filter(ImageFilter.GaussianBlur(34))
    return Image.alpha_composite(img, mist)
