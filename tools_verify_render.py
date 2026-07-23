"""临时验证脚本：渲染标准版 + 抖音全屏避让版，存到 output/ 供肉眼核对。"""
from core.spec import CanvasSpec, CANVAS_PRESETS
from core.themes.loader import load_themes
from core.layouts import get_layout
from core.data.songs import build_default_library
from core.engine import render_page

themes = load_themes("themes")
library = build_default_library()
print("loaded themes:", list(themes))
print("mastered songs:", len(library.mastered()))

t = themes["海洋柔光"]
layout = get_layout("grid-wrap")
font = "fonts/MaokenAssortedSans.ttf"

for page in (1, 2):
    spec = CANVAS_PRESETS["标准 9:16"]
    img = render_page(t, layout, library, spec, page, font)
    out = f"output/verify_标准9x16_p{page}.png"
    img.save(out)
    print(f"saved {out} size={img.size}")

spec2 = CanvasSpec(width=1080, height=2400, avoid_zones=((940, 1080, 1080, 2400),))
img2 = render_page(t, layout, library, spec2, 2, font)
img2.save("output/verify_抖音全屏_避让_p2.png")
print("saved output/verify_抖音全屏_避让_p2.png size=", img2.size)
print("RENDER OK")
