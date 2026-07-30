"""R1b render_pages 多页渲染测试。

覆盖：
- grid-wrap 仍固定 2 页（旧契约不动）
- magazine-flow pages=None 自动分析
- page_count 显式传入覆盖
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.engine import render_pages, render_page
from core.layouts import get_layout
from core.spec import get_canvas_spec
from core.themes.loader import load_themes
from core.data.songs import Song, SongLibrary, legacy_song_id


PROJECT = Path(__file__).resolve().parents[1]
THEMES_DIR = PROJECT / "themes"
FONT_PATH = str(PROJECT / "fonts" / "MaokenAssortedSans.ttf")


def _lib_with(n: int) -> SongLibrary:
    lib = SongLibrary()
    for i in range(n):
        lib.songs.append(Song(
            title=f"歌{i:02d}",
            id=legacy_song_id(f"歌{i:02d}"),
            status="active",
            section=(i % 7) + 1,
        ))
    return lib


class RenderPagesTests(unittest.TestCase):

    def setUp(self):
        self.themes = load_themes(str(THEMES_DIR))
        if not self.themes:
            self.skipTest("未找到主题目录")
        self.theme = self.themes["海洋柔光"]
        self.spec = get_canvas_spec("9:20", avoid=True)

    def test_grid_wrap_still_two_pages(self):
        lib = _lib_with(30)
        plugin = get_layout("grid-wrap")
        images = render_pages(self.theme, plugin, lib, self.spec, FONT_PATH)
        # grid-wrap 仍固定 2 页
        self.assertEqual(len(images), 2)
        for img in images:
            self.assertEqual(img.size[0], 1080)
            self.assertEqual(img.size[1], 1920)

    def test_magazine_flow_with_few_songs_single_page(self):
        lib = _lib_with(10)
        plugin = get_layout("magazine-flow")
        images = render_pages(self.theme, plugin, lib, self.spec, FONT_PATH)
        # 10 首 < per_page_max → 1 页
        self.assertEqual(len(images), 1)

    def test_magazine_flow_with_explicit_page_count_truncated(self):
        """R1b: 调用方要求 3 页，但当前 7 套主题仅 2 个 styles。
        render_pages 会截断到 max(theme.styles) = 2 而非抛出 KeyError。"""
        lib = _lib_with(10)
        plugin = get_layout("magazine-flow")
        images = render_pages(self.theme, plugin, lib, self.spec, FONT_PATH,
                              page_count=3)
        # styles 截断后 = 2
        self.assertEqual(len(images), 2)
        # 调用方判断：若 page_count 截断，应警告「主题只支持 N 页」——R1b 余项实现

    def test_magazine_flow_pagination_forces_more_pages(self):
        # 70 首一字 → magazine-flow 自动分析分桶 → 多页 + overflow
        lib = _lib_with(70)
        # 设置所有歌曲 section=1 (一字)，以便分组足够多
        for s in lib.songs:
            s.section = 1
        plugin = get_layout("magazine-flow")
        images = render_pages(self.theme, plugin, lib, self.spec, FONT_PATH)
        # 应 ≥ 2 页
        self.assertGreaterEqual(len(images), 2)

    def test_render_page_legacy_signature_still_works(self):
        """旧单一 render_page 调用仍可用，layout=grid-wrap page=1。"""
        lib = _lib_with(10)
        plugin = get_layout("grid-wrap")
        img = render_page(self.theme, plugin, lib, self.spec, 1, FONT_PATH)
        self.assertEqual(img.size[0], 1080)


if __name__ == "__main__":
    unittest.main()
