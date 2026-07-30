"""R1b magazine-flow 布局 + 分类 + analyze 测试。

P2 范围测试集：
- 分类 6 种 axes (chars/artist/genre/language/initial/status)
- analyze: per_page/page_count/overflow/degrade_reason
- capabilities: auto/manual 支持 + 7 种 axes
- 旧 grid-wrap 行为不变（隔离）
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.layouts import REGISTRY, get_layout
from core.layouts.magazine_flow import (
    AXIS_ARTIST,
    AXIS_CHARS,
    AXIS_INITIAL,
    AXIS_NONE,
    VALID_AXES,
    analyze,
    categorize_by_axis,
)
from core.data.songs import Song, SongLibrary, legacy_song_id


class _FakeCanvas:
    height = 2400
    width = 1080
    margin = 58


def _lib(*items):
    """items: list of (title, section, [artists])"""
    lib = SongLibrary()
    for i, (t, sec, artists) in enumerate(items):
        lib.songs.append(Song(
            title=t, id=legacy_song_id(t), status="active",
            section=sec, artists=artists or [],
        ))
    return lib


class MagazineFlowRegistrationTests(unittest.TestCase):

    def test_registered_in_layout_registry(self):
        self.assertIn("magazine-flow", REGISTRY)
        plugin = get_layout("magazine-flow")
        self.assertEqual(plugin.id, "magazine-flow")
        self.assertIsNone(plugin.pages)  # auto

    def test_old_grid_wrap_still_registered(self):
        """R1b 不能破坏 P1 grid-wrap。"""
        self.assertIn("grid-wrap", REGISTRY)

    def test_capabilities_advertise_auto_and_axes(self):
        plugin = get_layout("magazine-flow")
        caps = plugin.capabilities()
        self.assertTrue(caps["supports_auto_pagination"])
        self.assertTrue(caps["supports_manual_pages"])
        self.assertEqual(caps["page_policy_mode"], "auto")
        for axis in ("none", "chars", "artist"):
            self.assertIn(axis, caps["supports_grouping"])


class MagazineFlowCategorizeTests(unittest.TestCase):

    def test_chars_axis_groups_by_section(self):
        lib = _lib(
            ("枫", 1, []),
            ("江南", 2, []),
            ("七里香", 3, []),
            ("十年", 2, []),
            ("突然好想你", 5, []),
        )
        groups = dict(categorize_by_axis(lib, AXIS_CHARS))
        self.assertEqual(set(groups.keys()), {"一字", "二字", "三字", "五字"})
        self.assertEqual(groups["一字"], ["枫"])
        self.assertEqual(groups["二字"], ["江南", "十年"])
        self.assertEqual(groups["三字"], ["七里香"])

    def test_artist_axis_groups_by_first_artist(self):
        lib = _lib(
            ("江南", 2, ["林俊杰"]),
            ("枫", 1, ["周杰伦"]),
            ("小情歌", 3, ["苏打绿"]),
        )
        groups = dict(categorize_by_axis(lib, AXIS_ARTIST))
        self.assertEqual(set(groups.keys()), {"林俊杰", "周杰伦", "苏打绿"})
        self.assertEqual(groups["林俊杰"], ["江南"])

    def test_artist_axis_collapses_no_artist_into_other(self):
        lib = _lib(
            ("枫", 1, []),  # 无歌手
            ("江南", 2, ["林俊杰"]),
        )
        groups = dict(categorize_by_axis(lib, AXIS_ARTIST))
        self.assertIn("其他", groups)
        self.assertIn("林俊杰", groups)

    def test_none_axis_flattens_to_total(self):
        lib = _lib(("枫", 1, []), ("江南", 2, []))
        groups = dict(categorize_by_axis(lib, AXIS_NONE))
        self.assertEqual(list(groups.keys()), ["全部"])
        self.assertEqual(groups["全部"], ["枫", "江南"])

    def test_initial_axis_groups_by_pinyin_first(self):
        # 用 SongLibrary 默认 pinyin = ""——空 pinyin 落到 "#" 桶；这是规格约定
        lib = _lib(
            ("情书", None, []),
            ("分手", None, []),
            ("枫", None, []),
        )
        groups = dict(categorize_by_axis(lib, AXIS_INITIAL))
        # 空 pinyin 全部落到 "#" 桶
        self.assertIn("#", groups)
        self.assertEqual(groups["#"], ["情书", "分手", "枫"])


class MagazineFlowAnalyzeTests(unittest.TestCase):

    def test_analyze_six_songs_single_page(self):
        lib = _lib(*[("歌" + str(i), 2, []) for i in range(6)])
        rep = analyze(lib, axis=AXIS_CHARS, canvas=_FakeCanvas())
        self.assertEqual(rep["total_songs"], 6)
        self.assertGreaterEqual(rep["per_page_max"], 30)
        self.assertEqual(rep["page_count"], 1)
        self.assertEqual(rep["overflow"], [])

    def test_analyze_overflow_detects_large_section(self):
        lib = _lib(*[("枫" + str(i), 1, []) for i in range(70)])  # 70 首一字
        rep = analyze(lib, axis=AXIS_CHARS, canvas=_FakeCanvas())
        self.assertEqual(rep["total_songs"], 70)
        self.assertEqual(rep["page_count"], 3)  # ceil(70/33)
        self.assertGreater(len(rep["overflow"]), 0)
        self.assertEqual(rep["degrade_reason"], "single-section-overflow")

    def test_analyze_zero_songs_no_overflow(self):
        lib = SongLibrary()  # 空
        rep = analyze(lib, axis=AXIS_CHARS, canvas=_FakeCanvas())
        self.assertEqual(rep["total_songs"], 0)
        self.assertEqual(rep["page_count"], 1)
        self.assertEqual(rep["overflow"], [])


class MagazineFlowCategorizePagesTests(unittest.TestCase):

    def test_categorize_returns_pages_with_sections(self):
        lib = _lib(*[("T" + str(i), 2, []) for i in range(50)])
        plugin = get_layout("magazine-flow")
        pages = plugin.categorize(lib, AXIS_CHARS)
        self.assertGreater(len(pages), 0)
        # 每页 sections 至少 1 个；总和歌曲等于 50
        total = sum(
            sum(len(sec["songs"]) for sec in p.sections)
            for p in pages
        )
        self.assertEqual(total, 50)


if __name__ == "__main__":
    unittest.main()
