"""M0.3 (蓝图 v0.1) 月夜星河主题 smoke 测试。

不维护完整金标准（避免主题调整后反复重新生成），仅做：
- 主题加载 + 字段一致性
- 8 套主题被 themes/loader 全部识别
- 月夜星河配色与设计理念.md 一致
- 用 grid-wrap 渲染 1 张 PNG 不报错 + 主色调验证
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image
from core.themes.loader import load_themes
from core.engine import render_page
from core.layouts import get_layout
from core.data.songs import SongLibrary
from core.themes.loader import load_theme
from core.spec import get_canvas_spec


THEMES_ROOT = Path("themes")
MOON_THEME_DIR = THEMES_ROOT / "月夜星河"


class MoonThemeTests(unittest.TestCase):

    def test_eight_themes_loaded(self):
        """蓝图 v0.1 M0.3：8 套主题全部被 themes/loader 识别。"""
        themes = load_themes(str(THEMES_ROOT))
        expected = {"海洋柔光", "梦幻海洋", "奶油花园", "青提气泡",
                   "卡通音符", "奶油玻璃", "轻复古唱片", "月夜星河"}
        self.assertEqual(set(themes.keys()), expected)

    def test_moon_theme_metadata(self):
        theme = load_theme(str(MOON_THEME_DIR))
        self.assertEqual(theme.name, "月夜星河")
        self.assertEqual(theme.backgrounds["1"], "bg1.png")
        self.assertEqual(theme.backgrounds["2"], "bg2.png")
        # 蓝图 v0.1 M0.3：text 暖白 / label 琥珀 / pill 半透明深底
        st = theme.styles[1]
        self.assertEqual(tuple(st.text), (245, 240, 225))     # 暖白 #F5F0E1
        self.assertEqual(tuple(st.label), (255, 184, 77))     # 琥珀 #FFB84D
        self.assertEqual(tuple(st.pill), (20, 30, 60, 180))   # 半透明深底
        self.assertEqual(tuple(st.line), (255, 165, 0))      # 琥珀细线
        # mist 星云柔光（前 3 通道）
        self.assertEqual(tuple(st.mist[:3]), (180, 200, 255))

    def test_moon_background_files_exist(self):
        for bg in ("bg1.png", "bg2.png"):
            self.assertTrue((MOON_THEME_DIR / bg).exists(),
                            f"缺失背景图 {bg}")
        # 验证尺寸
        with Image.open(MOON_THEME_DIR / "bg1.png") as img:
            self.assertEqual(img.size, (1080, 1920))
        with Image.open(MOON_THEME_DIR / "bg2.png") as img:
            self.assertEqual(img.size, (1080, 2400))

    def test_moon_renders_with_grid_wrap(self):
        """月夜星河 + grid-wrap 9:16 渲染 smoke 测试。"""
        lib = SongLibrary.load_from_json("data/songs.json")
        spec = get_canvas_spec("标准 9:16", avoid=True)
        theme = load_theme(str(MOON_THEME_DIR))
        plugin = get_layout("grid-wrap")
        font = "fonts/MaokenAssortedSans.ttf"
        img = render_page(theme, plugin, lib, spec, 1, font)
        self.assertEqual(img.size, (1080, 1920))
        # 验证主色调：月夜星河背景应深蓝紫黑（顶部 RGB 应接近 10/14/42）
        # 采样顶部中间像素
        rgb = img.getpixel((540, 100))
        # 顶部 0-200 像素在深蓝紫范围（不是纯白，不是纯黑）
        self.assertLess(rgb[0], 80, f"顶部 R 应偏深，实际 {rgb}")
        self.assertLess(rgb[1], 80, f"顶部 G 应偏深，实际 {rgb}")
        self.assertGreater(rgb[2], 30, f"顶部 B 应偏深蓝，实际 {rgb}")
        # 文字颜色：抽样网格中间区域（应有暖白文字）
        # 抽样 (200, 250) 应该是暖白/深底文字行
        sample = img.getpixel((100, 250))
        # 验证至少有一个浅色像素（暖白文字）
        self.assertGreater(sample[0] + sample[1] + sample[2], 100,
                           f"抽样位置应有文字，实际 RGB={sample}")


if __name__ == "__main__":
    unittest.main()
