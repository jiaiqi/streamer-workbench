"""金标准测试：新引擎渲染 vs 歌单-排版一 现有成品，逐像素统计差异。

当前对比对象（歌单-排版一下现有成品）：
  - 全屏绕排版：<prefix>-糖圆体全屏绕排-{page}.png  （1080×2400，grid-wrap）
  - 海洋柔光另含标准版：<prefix>-糖圆体-{page}.png     （1080×1920）

运行：python tests/test_golden.py
首轮以「报告差异」为主，不强制 assert，便于观察 Pillow 版本/环境带来的差异量级。
"""
import os
from PIL import Image, ImageChops, ImageStat

from core.spec import CanvasSpec
from core.themes.loader import load_themes
from core.layouts import get_layout
from core.data.songs import build_default_library
from core.engine import render_page

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THEMES_DIR = os.path.join(ROOT, "themes")
GOLDEN_DIR_LOCAL = os.path.join(ROOT, "tests", "golden")
GOLDEN_DIR_UP = os.path.join(ROOT, "..", "歌单-排版一")
# 优先用本地 tests/golden/（从设计仓库复制而来），其次用上级软链
GOLDEN_DIR = GOLDEN_DIR_LOCAL if os.path.isdir(GOLDEN_DIR_LOCAL) and os.listdir(GOLDEN_DIR_LOCAL) else GOLDEN_DIR_UP
FONT = os.path.join(ROOT, "fonts", "MaokenAssortedSans.ttf")


def diff_stats(new: Image.Image, gold: Image.Image):
    if new.size != gold.size:
        return {"size_mismatch": (new.size, gold.size)}
    d = ImageChops.difference(new, gold).convert("RGB")
    bbox = d.getbbox()
    if bbox is None:
        return {"max": 0, "nonzero": 0, "total": 0, "bbox": None}
    stat = ImageStat.Stat(d)
    gray = d.convert("L").point(lambda p: 255 if p > 0 else 0)
    hist = gray.histogram()
    nonzero = sum(hist[1:])
    return {
        "max": max(stat.extrema),
        "nonzero": nonzero,
        "total": sum(stat.sum),
        "bbox": bbox,
    }


def main():
    themes = load_themes(THEMES_DIR)
    # 金标准固定使用内置 178 首全 active 数据集：
    # 与 songs.json 中的学歌 draft 状态解耦，保证基准稳定。
    library = build_default_library()
    layout = get_layout("grid-wrap")
    results = []

    # 全屏绕排版（1080×2400，带 avoid-rail）——金标准成品即 --fullscreen --avoid-rail 版本
    fs_spec = CanvasSpec(width=1080, height=2400,
                         avoid_zones=((940, 1080, 1080, 2400),))
    for name, t in themes.items():
        prefix = t.output_prefix
        for page in (1, 2):
            img = render_page(t, layout, library, fs_spec, page, FONT)
            gold_path = os.path.join(GOLDEN_DIR, name, f"{prefix}-糖圆体全屏绕排-{page}.png")
            # 也尝试扁平命名（tests/golden/ 格式）
            if not os.path.isfile(gold_path):
                flat = os.path.join(GOLDEN_DIR, f"{name}-全屏p{page}.png")
                if os.path.isfile(flat):
                    gold_path = flat
            if not os.path.isfile(gold_path):
                results.append((name, f"全屏p{page}", "SKIP(无金标准)"))
                continue
            gold = Image.open(gold_path).convert("RGB")
            st = diff_stats(img, gold)
            results.append((name, f"全屏p{page}", st))

    # 海洋柔光标准版（1080×1920）
    t0 = themes["海洋柔光"]
    std_spec = CanvasSpec(width=1080, height=1920)
    for page in (1, 2):
        img = render_page(t0, layout, library, std_spec, page, FONT)
        gold_path = os.path.join(GOLDEN_DIR, "海洋柔光", f"{t0.output_prefix}-糖圆体-{page}.png")
        if not os.path.isfile(gold_path):
            results.append(("海洋柔光", f"标准p{page}", "SKIP(无金标准)"))
            continue
        gold = Image.open(gold_path).convert("RGB")
        st = diff_stats(img, gold)
        results.append(("海洋柔光", f"标准p{page}", st))

    print("=" * 70)
    print(f"{'主题':<8}{'页面':<10}{'结果'}")
    print("=" * 70)
    perfect = 0
    checked = 0
    for name, page, st in results:
        if st == "SKIP(无金标准)":
            print(f"{name:<8}{page:<10}SKIP")
            continue
        checked += 1
        if st.get("size_mismatch"):
            print(f"{name:<8}{page:<10}尺寸不一致 {st['size_mismatch']}")
            continue
        if st["nonzero"] == 0:
            perfect += 1
            print(f"{name:<8}{page:<10}✅ 像素完全一致 (diff=0)")
        else:
            print(f"{name:<8}{page:<10}⚠️  diff: nonzero={st['nonzero']} "
                  f"max={st['max']} total={st['total']} bbox={st['bbox']}")
    print("=" * 70)
    print(f"完美对齐 {perfect}/{checked}；像素级一致目标 = 逐像素 diff=0")
    # 金标准是回归死线：任何像素差异都视为失败
    assert perfect == checked, (
        f"金标准测试失败：{perfect}/{checked} 通过。"
        "差异可能来自 Pillow 版本/字体光栅化环境差异，请检查环境后重试。"
    )


if __name__ == "__main__":
    main()
