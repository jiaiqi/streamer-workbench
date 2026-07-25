"""生成可视化证据：修复后成品(与金标准完全一致) + 修复前(错分组)差异热图。"""
import os, sys
from PIL import Image, ImageChops, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core.spec import CanvasSpec
from core.themes.loader import load_theme
from core.layouts import get_layout
from core.data.songs import build_default_library, Song
from core.engine import render_page

FONT = os.path.join(ROOT, "fonts", "MaokenAssortedSans.ttf")
GOLD = os.path.join(ROOT, "..", "歌单-排版一")
OUT = os.path.join(ROOT, "output")
os.makedirs(OUT, exist_ok=True)

t = load_theme(os.path.join(ROOT, "themes", "海洋柔光"))
layout = get_layout("grid-wrap")
spec = CanvasSpec(width=1080, height=2400, avoid_zones=((940, 1080, 1080, 2400),))
gold = Image.open(os.path.join(GOLD, "海洋柔光", f"{t.output_prefix}-糖圆体全屏绕排-1.png")).convert("RGB")

# 修复后（带 section 标记）
fixed = render_page(t, layout, build_default_library(), spec, 1, FONT)
fixed.save(os.path.join(OUT, "ocean_p1_fixed.png"))

# 修复前（去掉 section 标记 -> 回退按字数分组，复现恋爱ing错位bug）
buggy_lib = build_default_library()
for s in buggy_lib.songs:
    s.section = None
buggy = render_page(t, layout, buggy_lib, spec, 1, FONT)

# 差异热图：buggy vs golden，差像素标红
diff = ImageChops.difference(buggy, gold).convert("RGB")
heat = Image.new("RGB", diff.size, (0, 0, 0))
px = heat.load()
dx = diff.load()
for y in range(0, diff.size[1], 1):
    for x in range(0, diff.size[0], 1):
        r, g, b = dx[x, y]
        if r or g or b:
            px[x, y] = (220, 40, 40)
heat.save(os.path.join(OUT, "ocean_p1_diff_before_fix.png"))
print("saved:", os.path.join(OUT, "ocean_p1_fixed.png"),
      os.path.join(OUT, "ocean_p1_diff_before_fix.png"))
print("fixed vs gold diff:", ImageChops.difference(fixed, gold).getbbox())
