"""Songs v5 schema 校验 (2026-07-30 加固) 测试。

覆盖:
- None section: 合法 (与 Song dataclass 默认一致)
- 整数 1..7: 合法
- 0 / 8+ / 负数 / 字符串 / 浮点: 拒绝 (保护下游分类与分桶)
- 真实 songs.json 通过校验 (regression)
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.data.songs import SongLibrary


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SongsValidationV5Tests(unittest.TestCase):

    def test_real_songs_json_passes_validation(self):
        """默认数据文件仍可通过 v5 校验。"""
        songs_json = PROJECT_ROOT / "data" / "songs.json"
        data = json.loads(songs_json.read_text(encoding="utf-8"))
        SongLibrary._validate_v5(data)

    def test_none_section_is_legal(self):
        """None 是合法值 (与 Song.section: Optional[int] = None 默认)。"""
        data = {
            "version": 5,
            "songs": [
                {"title": "T1", "id": "song_" + "a" * 32,
                  "section": None, "status": "active", "pinyin": "",
                  "artists": [], "lyricist": "", "composer": "",
                  "key": "", "capo": None, "difficulty": "", "tabs": "",
                  "tags": [], "added_at": "", "notes": "", "learned_at": "",
                  "tab_files": []},
            ],
        }
        SongLibrary._validate_v5(data)

    def test_int_1_to_7_legal(self):
        for sec in (1, 2, 3, 4, 5, 6, 7):
            data = self._payload(sec=sec)
            SongLibrary._validate_v5(data)

    def _payload(self, *, sec):
        return {
            "version": 5,
            "songs": [
                {"title": "T1", "id": "song_" + "f" * 32,
                  "section": sec, "status": "active", "pinyin": "",
                  "artists": [], "lyricist": "", "composer": "",
                  "key": "", "capo": None, "difficulty": "", "tabs": "",
                  "tags": [], "added_at": "", "notes": "", "learned_at": "",
                  "tab_files": []},
            ],
        }

    def test_section_zero_rejected(self):
        with self.assertRaises(ValueError):
            SongLibrary._validate_v5(self._payload(sec=0))

    def test_section_eight_rejected(self):
        """section=8 越界 (索引 7 = 长歌名); section 必须 <=7。"""
        with self.assertRaises(ValueError):
            SongLibrary._validate_v5(self._payload(sec=8))

    def test_section_negative_rejected(self):
        with self.assertRaises(ValueError):
            SongLibrary._validate_v5(self._payload(sec=-1))

    def test_section_string_rejected(self):
        with self.assertRaises(ValueError):
            SongLibrary._validate_v5(self._payload(sec="3"))

    def test_section_float_rejected(self):
        """float 不允许 (即使 3.0 是整数值)。"""
        with self.assertRaises(ValueError):
            SongLibrary._validate_v5(self._payload(sec=3.0))


if __name__ == "__main__":
    unittest.main()
