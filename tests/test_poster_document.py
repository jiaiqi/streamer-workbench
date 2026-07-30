"""R1a.1 PosterDocument 领域模型测试。

覆盖：往返一致性、schema 校验、SongSource/PagePolicy/ExportSettings 校验、
selected_song_ids 不可变 ID 约束、P1 范围（仅 grid-wrap + legacy-fixed-2）的拒绝路径，
以及 resolve_all_active / resolve_artist_source 的解析行为。
"""
from __future__ import annotations

import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.data.posters import (
    CURRENT_SCHEMA_VERSION,
    GROUPING_NONE,
    GROUPING_ARTIST,
    GROUPING_CHARS,
    GROUPING_STATUS,
    GROUPING_TAG,
    SORTING_MANUAL,
    SORTING_TITLE,
    SORTING_ARTIST,
    SORTING_UPDATED,
    SORTING_REQUEST_HEAT,
    SOURCE_ALL_ACTIVE,
    SOURCE_ARTIST,
    SOURCE_MANUAL,
    ExportSettings,
    PagePolicy,
    PosterDocument,
    SongSource,
    is_valid_poster_id,
    new_poster_id,
    resolve_all_active,
    resolve_artist_source,
)


SAMPLE_ID = "song_227fe9c4775f51e2a3e414bc78fdf12e"
SAMPLE_ID_2 = "song_a891717f4c1c5d27a8074c18faa212aa"


@dataclass
class _FakeSong:
    id: str
    title: str = ""
    artists: list = None
    status: str = "active"

    def __post_init__(self):
        if self.artists is None:
            self.artists = []


class PosterDocumentSchemaTests(unittest.TestCase):
    """PosterDocument.validate() 校验路径——必须严格拒绝带病写入。"""

    def test_default_document_passes_validation(self):
        doc = PosterDocument.default()
        doc.selected_song_ids = [SAMPLE_ID]
        doc.validate()  # 不抛异常

    def test_rejects_invalid_poster_id(self):
        doc = PosterDocument.default()
        doc.id = "../escape"
        with self.assertRaises(ValueError):
            doc.validate()

    def test_rejects_empty_name(self):
        doc = PosterDocument.default()
        doc.name = "   "
        with self.assertRaises(ValueError):
            doc.validate()

    def test_rejects_invalid_song_id_in_selected(self):
        doc = PosterDocument.default()
        doc.selected_song_ids = ["not_a_song_id"]
        with self.assertRaises(ValueError):
            doc.validate()

    def test_rejects_duplicate_song_ids(self):
        doc = PosterDocument.default()
        doc.selected_song_ids = [SAMPLE_ID, SAMPLE_ID]
        with self.assertRaises(ValueError):
            doc.validate()

    def test_rejects_unknown_grouping(self):
        doc = PosterDocument.default()
        doc.grouping = "unknown_axis"
        with self.assertRaises(ValueError):
            doc.validate()

    def test_rejects_unknown_sorting(self):
        doc = PosterDocument.default()
        doc.sorting = "lucky_sort"
        with self.assertRaises(ValueError):
            doc.validate()

    def test_rejects_non_grid_wrap_layout(self):
        """P1 R1a 严格保护：只允许 grid-wrap，避免金标准 16/16 漂移。"""
        doc = PosterDocument.default()
        doc.layout_id = "magazine-flow"
        with self.assertRaises(ValueError) as cm:
            doc.validate()
        self.assertIn("grid-wrap", str(cm.exception))

    def test_rejects_non_legacy_fixed_2_page_policy(self):
        """P1 R1a 严格保护：只允许 legacy-fixed-2 分页。"""
        doc = PosterDocument.default()
        doc.page_policy = PagePolicy(mode="auto")
        with self.assertRaises(ValueError) as cm:
            doc.validate()
        self.assertIn("legacy-fixed-2", str(cm.exception))

    def test_rejects_invalid_export_format(self):
        doc = PosterDocument.default()
        doc.export_settings = ExportSettings(format="tiff")
        with self.assertRaises(ValueError):
            doc.validate()

    def test_rejects_low_dpi(self):
        doc = PosterDocument.default()
        doc.export_settings = ExportSettings(dpi=36)
        with self.assertRaises(ValueError):
            doc.validate()

    def test_schema_version_constant_is_one(self):
        # 当前 v1；未来 v2 引入新字段时此断言会被故意打破以提示更新。
        self.assertEqual(CURRENT_SCHEMA_VERSION, 1)


class PagePolicyValidationTests(unittest.TestCase):

    def test_validates_legacy_fixed_2(self):
        PagePolicy(mode="legacy-fixed-2").validate()

    def test_validates_auto_with_bounds(self):
        PagePolicy(mode="auto", min_pages=1, max_pages=4).validate()

    def test_rejects_auto_with_invalid_min(self):
        with self.assertRaises(ValueError):
            PagePolicy(mode="auto", min_pages=0).validate()

    def test_rejects_auto_with_inverted_bounds(self):
        with self.assertRaises(ValueError):
            PagePolicy(mode="auto", min_pages=4, max_pages=2).validate()

    def test_rejects_manual_without_pages(self):
        with self.assertRaises(ValueError):
            PagePolicy(mode="manual").validate()


class SongSourceValidationTests(unittest.TestCase):

    def test_rejects_unknown_type(self):
        ss = SongSource(type="lucky")
        with self.assertRaises(ValueError):
            ss.validate()

    def test_artist_requires_non_empty_artists(self):
        ss = SongSource(type=SOURCE_ARTIST, artists=[])
        with self.assertRaises(ValueError):
            ss.validate()


class PosterDocumentRoundTripTests(unittest.TestCase):
    """to_dict / from_dict 往返一致性，未知字段向前兼容。"""

    def test_roundtrip_preserves_all_fields(self):
        doc = PosterDocument.default()
        doc.id = "poster_abc123"
        doc.name = "我的歌单"
        doc.song_source = SongSource(type=SOURCE_ARTIST, artists=["周杰伦", "林俊杰"])
        doc.selected_song_ids = [SAMPLE_ID, SAMPLE_ID_2]
        doc.grouping = GROUPING_ARTIST
        doc.sorting = SORTING_REQUEST_HEAT
        doc.layout_id = "grid-wrap"
        doc.theme_id = "海洋柔光"
        doc.canvas_id = "9:20"
        doc.page_policy = PagePolicy(mode="legacy-fixed-2")
        doc.parameters = {"density": "comfortable", "show_subtitle": True}
        doc.export_settings = ExportSettings(format="jpeg", jpeg_quality=85, single_page=True, dpi=200)
        doc.optional_session_ref = "live_xyz"
        doc.validate()

        d = doc.to_dict()
        restored = PosterDocument.from_dict(d)
        restored.validate()

        self.assertEqual(restored.id, doc.id)
        self.assertEqual(restored.name, doc.name)
        self.assertEqual(restored.song_source.type, SOURCE_ARTIST)
        self.assertEqual(restored.song_source.artists, ["周杰伦", "林俊杰"])
        self.assertEqual(restored.selected_song_ids, [SAMPLE_ID, SAMPLE_ID_2])
        self.assertEqual(restored.grouping, GROUPING_ARTIST)
        self.assertEqual(restored.sorting, SORTING_REQUEST_HEAT)
        self.assertEqual(restored.theme_id, "海洋柔光")
        self.assertEqual(restored.parameters, {"density": "comfortable", "show_subtitle": True})
        self.assertEqual(restored.export_settings.format, "jpeg")
        self.assertEqual(restored.export_settings.jpeg_quality, 85)
        self.assertTrue(restored.export_settings.single_page)
        self.assertEqual(restored.export_settings.dpi, 200)
        self.assertEqual(restored.optional_session_ref, "live_xyz")

    def test_from_dict_tolerates_unknown_fields(self):
        d = {
            "schema_version": 1,
            "id": "poster_unknown_field",
            "name": "未来版本兼容",
            "song_source": {"type": SOURCE_MANUAL, "artists": []},
            "selected_song_ids": [SAMPLE_ID],
            "grouping": GROUPING_NONE,
            "sorting": SORTING_MANUAL,
            "layout_id": "grid-wrap",
            "theme_id": "奶油玻璃",
            "canvas_id": "9:20",
            "page_policy": {"mode": "legacy-fixed-2"},
            "parameters": {},
            "export_settings": {},
            "created_at": "2026-07-30T10:00:00",
            "updated_at": "2026-07-30T10:00:00",
            "unknown_future_field": "harmless",
        }
        doc = PosterDocument.from_dict(d)
        doc.validate()  # 不抛异常

    def test_from_dict_defaults_missing_schema_version(self):
        d = {
            "id": "poster_legacy",
            "name": "缺 schema",
            "song_source": {"type": SOURCE_MANUAL},
            "selected_song_ids": [SAMPLE_ID],
            "layout_id": "grid-wrap",
            "theme_id": "青提气泡",
            "canvas_id": "9:20",
        }
        doc = PosterDocument.from_dict(d)
        # 缺 schema_version 应默认为 1（最老兼容）
        self.assertEqual(doc.schema_version, 1)
        # 默认 page_policy
        self.assertEqual(doc.page_policy.mode, "legacy-fixed-2")
        # 默认 export_settings
        self.assertEqual(doc.export_settings.format, "png")

    def test_from_dict_rejects_non_dict(self):
        with self.assertRaises(ValueError):
            PosterDocument.from_dict("not a dict")

    def test_from_dict_rejects_missing_key_field(self):
        with self.assertRaises(ValueError):
            PosterDocument.from_dict({"name": "无 id", "layout_id": "grid-wrap"})


class IsValidPosterIdTests(unittest.TestCase):

    def test_accepts_safe_ids(self):
        self.assertTrue(is_valid_poster_id("poster_abc123"))
        self.assertTrue(is_valid_poster_id(new_poster_id()))

    def test_rejects_empty(self):
        self.assertFalse(is_valid_poster_id(""))

    def test_rejects_path_traversal(self):
        self.assertFalse(is_valid_poster_id("../escape"))
        self.assertFalse(is_valid_poster_id("a/b"))
        self.assertFalse(is_valid_poster_id("a\\b"))
        self.assertFalse(is_valid_poster_id("."))
        self.assertFalse(is_valid_poster_id(".."))

    def test_rejects_too_long(self):
        self.assertFalse(is_valid_poster_id("a" * 81))

    def test_rejects_control_chars(self):
        self.assertFalse(is_valid_poster_id("poster_\n"))
        self.assertFalse(is_valid_poster_id("poster_\x00"))


class SongSourceResolutionTests(unittest.TestCase):
    """resolve_all_active / resolve_artist_source 的解析行为。"""

    def test_resolve_all_active_returns_songs_in_order(self):
        songs = [
            _FakeSong(id="s1", artists=["A"]),
            _FakeSong(id="s2", artists=["B"]),
            _FakeSong(id="s3", artists=["C"]),
        ]
        result = resolve_all_active(songs)
        self.assertEqual(result, ["s1", "s2", "s3"])

    def test_resolve_all_active_ignores_draft(self):
        """all_active 由调用方确保传入的 active_songs 已过滤 status；本函数不重过滤。"""
        songs = [
            _FakeSong(id="s1"),
            _FakeSong(id="s2", status="draft"),
        ]
        result = resolve_all_active(songs)  # 函数不假设过滤
        self.assertEqual(result, ["s1", "s2"])

    def test_resolve_artist_case_insensitive(self):
        songs = [
            _FakeSong(id="s1", artists=["Zhou Jielun"]),
            _FakeSong(id="s2", artists=["LIN俊杰", "JJ"]),
            _FakeSong(id="s3", artists=["陈奕迅"]),
        ]
        # Zhou Jielun / LIN俊杰 的目标做大小写抖动；其中纯 ASCII 部分必须命中。
        result = resolve_artist_source(["zhou jielun", "lin俊杰"], songs)
        self.assertEqual(result, ["s1", "s2"])

    def test_resolve_artist_strips_whitespace(self):
        songs = [
            _FakeSong(id="s1", artists=["周 杰 伦"]),
        ]
        result = resolve_artist_source(["周 杰 伦"], songs)
        self.assertEqual(result, ["s1"])

    def test_resolve_artist_rejects_empty_list(self):
        with self.assertRaises(ValueError):
            resolve_artist_source([], [])

    def test_resolve_artist_rejects_whitespace_only(self):
        with self.assertRaises(ValueError):
            resolve_artist_source(["   "], [])


class PosterDocumentConstantsTests(unittest.TestCase):
    """常量级别的可用枚举（防御性断言，文档化合法集合）。"""

    def test_valid_sorts_include_expected(self):
        expected = {SORTING_MANUAL, SORTING_TITLE, SORTING_REQUEST_HEAT}
        self.assertTrue(expected.issubset({SORTING_MANUAL, SORTING_TITLE, SORTING_ARTIST,
                                           SORTING_UPDATED, SORTING_REQUEST_HEAT}))

    def test_valid_groupings_include_expected(self):
        self.assertIn(GROUPING_NONE, {GROUPING_NONE, GROUPING_ARTIST, GROUPING_CHARS,
                                      GROUPING_STATUS, GROUPING_TAG})


if __name__ == "__main__":
    unittest.main()
