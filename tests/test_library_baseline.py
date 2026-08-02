"""M0.5 (蓝图 v0.1) 178 首曲库导入验证。

蓝图 §3.5 第 177 首真实样本：
- 一字 2 / 二字 36 / 三字 43 / 四字 41 / 五字 22 / 六字 14 / 长歌名 19
- 总 177（active 子集）

验证：
- data/songs.json 存在
- 总数 ≥ 170（容差 7）
- 字数分组在蓝图容差内（每组 ±3）
- active 子集可被 grid-wrap / magazine-flow / fullscreen-flow 渲染无报错
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


REPO_ROOT = Path(__file__).resolve().parents[1]
SONGS_JSON = REPO_ROOT / "data" / "songs.json"

# 蓝图 v0.1 §3.5 第 177 首真实样本（容差 ±3）
EXPECTED_GROUPS = {
    "一字": 2,
    "二字": 36,
    "三字": 43,
    "四字": 41,
    "五字": 22,
    "六字": 14,
    "长歌名/英文": 19,
}
TOLERANCE = 3  # 每组允许偏差
MIN_TOTAL = 170  # 至少 170 首（蓝图 177 - 7 容差）


def _group(library) -> dict[str, list[str]]:
    """复用 core/layouts/grid_wrap._group 的分组逻辑。"""
    from core.layouts.grid_wrap import _group as gw_group
    return gw_group(library)


class LibraryBaselineTests(unittest.TestCase):
    """M0.5 蓝图 v0.1：178 首曲库验证。"""

    def test_songs_json_exists(self):
        self.assertTrue(SONGS_JSON.exists(),
                        f"曲库 JSON 不存在: {SONGS_JSON}")

    def test_songs_count_meets_minimum(self):
        """总曲数 ≥ 170（蓝图 177 - 7 容差）。"""
        from core.data.songs import SongLibrary
        lib = SongLibrary.load_from_json(str(SONGS_JSON))
        self.assertGreaterEqual(len(lib.songs), MIN_TOTAL,
                                f"曲库 {len(lib.songs)} 首 < {MIN_TOTAL}")

    def test_active_count_meets_minimum(self):
        """active 子集 ≥ 165（蓝图 177 - 12 容差）。"""
        from core.data.songs import SongLibrary
        lib = SongLibrary.load_from_json(str(SONGS_JSON))
        active = lib.mastered()
        self.assertGreaterEqual(len(active), 165,
                                f"active {len(active)} 首 < 165")

    def test_word_count_groups_match_blueprint(self):
        """字数分组在蓝图 §3.5 容差内。"""
        from core.data.songs import SongLibrary
        lib = SongLibrary.load_from_json(str(SONGS_JSON))
        groups = _group(lib)
        label_map = {1: "一字", 2: "二字", 3: "三字", 4: "四字",
                     5: "五字", 6: "六字", 7: "长歌名/英文"}
        for gid, label in label_map.items():
            actual = len(groups[gid])
            expected = EXPECTED_GROUPS[label]
            self.assertLessEqual(
                abs(actual - expected), TOLERANCE,
                f"{label} 分组 {actual} 首，与蓝图 {expected} 偏差 {abs(actual - expected)} > {TOLERANCE}"
            )

    def test_renders_with_all_three_song_library_layouts(self):
        """178 首 active 子集在 3 套 song_library layout 都能渲染（grid-wrap / magazine-flow / fullscreen-flow）。"""
        from core.data.songs import SongLibrary
        from core.engine import render_pages
        from core.layouts import get_layout
        from core.themes.loader import load_theme
        from core.spec import get_canvas_spec
        lib = SongLibrary.load_from_json(str(SONGS_JSON))
        theme = load_theme(str(REPO_ROOT / "themes" / "海洋柔光"))
        font = str(REPO_ROOT / "fonts" / "MaokenAssortedSans.ttf")
        for layout_id, canvas_id in [
            ("grid-wrap", "标准 9:16"),
            ("magazine-flow", "抖音全屏 9:20"),
            ("fullscreen-flow", "抖音全屏 9:20"),
        ]:
            with self.subTest(layout=layout_id):
                spec = get_canvas_spec(canvas_id, avoid=True)
                plugin = get_layout(layout_id)
                images = render_pages(theme, plugin, lib, spec, font)
                self.assertGreaterEqual(len(images), 1, f"{layout_id} 应至少 1 页")
                self.assertEqual(images[0].size[0], spec.width)

    def test_no_duplicate_titles(self):
        """active 子集无重复歌名（蓝图 §3.1 一歌一档）。"""
        from core.data.songs import SongLibrary
        lib = SongLibrary.load_from_json(str(SONGS_JSON))
        active = lib.mastered()
        titles = [s.title for s in active]
        self.assertEqual(len(titles), len(set(titles)),
                         f"active 子集有 {len(titles) - len(set(titles))} 个重复歌名")

    def test_every_active_song_has_id(self):
        """active 子集每首歌有 id（R4 Runtime v1 要求）。"""
        from core.data.songs import SongLibrary
        lib = SongLibrary.load_from_json(str(SONGS_JSON))
        active = lib.mastered()
        missing = [s.title for s in active if not s.id]
        self.assertEqual(missing, [], f"active 中 {len(missing)} 首歌缺 id")


if __name__ == "__main__":
    unittest.main()
