"""生成金标准参照图（178 首全 active 版），放入 tests/golden/。

用法（在 歌单海报生成器 目录下）：
    PYTHONPATH=. python tools/regenerate_golden.py

策略（2026-07-25 修订）：
    引擎自举生成 —— 用当前引擎 + 内置 178 首全 active 数据集渲染 14 张。
    引擎本身已经过「与 178 首旧参照图 diff=0」验证，是正确的预言机。
    金标准与 songs.json 的学歌 draft 状态解耦，保证基准稳定。

历史背景：
    旧策略是从设计仓库 歌单-排版一/ 复制成品图，但该目录的成品图是
    177 首时代生成（缺「奇妙能力歌」），与 178 首引擎输出必然有 7 张
    第二页像素差异（nonzero=3116，位置全在五字歌区），已废弃。

产物：tests/golden/<主题>-全屏p{1,2}.png（扁平命名，便于 CI 引用）
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.spec import CanvasSpec
from core.themes.loader import load_themes
from core.layouts import get_layout
from core.data.songs import build_default_library
from core.engine import render_page, clear_bg_cache

THEMES_DIR = os.path.join(ROOT, "themes")
GOLDEN_DST = os.path.join(ROOT, "tests", "golden")
FONT = os.path.join(ROOT, "fonts", "MaokenAssortedSans.ttf")


def main():
    os.makedirs(GOLDEN_DST, exist_ok=True)
    clear_bg_cache()
    themes = load_themes(THEMES_DIR)
    # 内置 178 首全 active 数据集（与学歌 draft 解耦）
    library = build_default_library()
    layout = get_layout("grid-wrap")
    spec = CanvasSpec(width=1080, height=2400,
                      avoid_zones=((940, 1080, 1080, 2400),))

    count = 0
    for name, t in themes.items():
        for page in (1, 2):
            img = render_page(t, layout, library, spec, page, FONT)
            path = os.path.join(GOLDEN_DST, f"{name}-全屏p{page}.png")
            img.save(path)
            count += 1
            print(f"  ✅ {name} p{page}")
    print(f"\n生成完成: {count}/14 张金标准参照图（178 首全 active 版）→ {GOLDEN_DST}")


if __name__ == "__main__":
    main()
