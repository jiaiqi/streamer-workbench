"""渲染性能基准测试。

用量（项目根目录下）：
    PYTHONPATH=. python tools/benchmark.py

输出：冷/热缓存各组合的渲染耗时（P50/P95/P99），结果可追加到 docs/benchmark.md。
"""
import os
import sys
import time
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.spec import CanvasSpec
from core.engine import render_page, clear_bg_cache, _load_font
from core.themes.loader import load_themes
from core.data.songs import build_default_library
from core.layouts import get_layout


THEMES_DIR = os.path.join(ROOT, "themes")
FONT = os.path.join(ROOT, "fonts", "MaokenAssortedSans.ttf")


def time_one(theme_name, canvas_name, spec, library, layout, page, warm_cache):
    """渲染一张并返回耗时（ms）。"""
    themes = load_themes(THEMES_DIR)
    t = themes[theme_name]
    if not warm_cache:
        clear_bg_cache()
        _load_font.cache_clear()
    t0 = time.perf_counter()
    render_page(t, layout, library, spec, page, FONT)
    return (time.perf_counter() - t0) * 1000


def bench(label, theme, canvas, spec, library, layout, n=7):
    """跑 n 次，前 2 次抛掉（冷缓存），后 5 次统计。返回 (label, times_ms)。"""
    samples = []
    for i in range(n):
        ms = time_one(theme, canvas, spec, library, layout, (i % 2 + 1), warm_cache=(i > 0))
        if i >= 2:
            samples.append(ms)
    return label, samples


def report(results):
    """打印表格报告。"""
    print(f"{'场景':<36} {'P50(ms)':<10} {'P95(ms)':<10} {'P99(ms)':<10} {'样本':<6}")
    print("-" * 72)
    for label, samples in results:
        if not samples:
            continue
        samples.sort()
        p50 = samples[len(samples) // 2]
        p95 = samples[int(len(samples) * 0.95)]
        p99 = samples[int(len(samples) * 0.99)]
        print(f"{label:<36} {p50:<10.1f} {p95:<10.1f} {p99:<10.1f} {len(samples):<6}")


def main():
    library = build_default_library()
    layout = get_layout("grid-wrap")
    themes_list = ["海洋柔光", "梦幻海洋", "青提气泡", "卡通音符", "奶油花园", "奶油玻璃", "轻复古唱片"]
    theme = themes_list[0]

    specs = {
        "标准 9:16":      CanvasSpec(width=1080, height=1920),
        "抖音全屏":       CanvasSpec(width=1080, height=2400, avoid_zones=((940, 1080, 1080, 2400),)),
    }

    results = []

    # === 热缓存（重复渲染同一页）===
    for canvas_name, spec in specs.items():
        ms = []
        for _ in range(10):
            t = load_themes(THEMES_DIR)[theme]
            clear_bg_cache()
            _load_font.cache_clear()
            # 冷加载一次
            render_page(t, layout, library, spec, 1, FONT)
            # 之后走缓存
            t0 = time.perf_counter()
            render_page(t, layout, library, spec, 1, FONT)
            ms.append((time.perf_counter() - t0) * 1000)
        ms.sort()
        results.append((f"热缓存 {theme} {canvas_name} p1", ms[2:7]))

    # === 冷缓存（每张清空背景+字体缓存）===
    for canvas_name, spec in specs.items():
        ms = []
        for _ in range(6):
            ms.append(time_one(theme, canvas_name, spec, library, layout, 1, warm_cache=False))
        ms.sort()
        results.append((f"冷缓存 {theme} {canvas_name} p1", ms[1:5]))

    # === 7 主题 × 避让/标准 热缓存 ===
    for theme_name in themes_list:
        t = load_themes(THEMES_DIR)[theme_name]
        clear_bg_cache()
        _load_font.cache_clear()
        render_page(t, layout, library, specs["抖音全屏"], 1, FONT)
        ms = []
        for _ in range(5):
            t0 = time.perf_counter()
            render_page(t, layout, library, specs["抖音全屏"], 1, FONT)
            ms.append((time.perf_counter() - t0) * 1000)
        ms.sort()
        results.append((f"热缓存 {theme_name} 抖音全屏 p1", ms))

    # === 7 主题冷缓存 ===
    for theme_name in themes_list:
        ms = [time_one(theme_name, "抖音全屏", specs["抖音全屏"], library, layout, 1, warm_cache=False) for _ in range(4)]
        ms.sort()
        results.append((f"冷缓存 {theme_name} 抖音全屏 p1", ms))

    print(f"\n主播工作台 · 渲染性能基准\n{'=' * 60}")
    print(f"字体: {os.path.basename(FONT)}")
    print(f"布局: grid-wrap | 歌曲数: {len(library.active())}")
    print()
    report(results)
    print(f"\n{'=' * 60}")


if __name__ == "__main__":
    main()
