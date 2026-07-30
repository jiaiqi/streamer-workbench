"""P4 R2: PracticeApplicationService 测试。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.repositories.events import FileEventStore
from server.services.practice import (
    PracticeApplicationService,
    PracticeValidationFailed,
)


def _build(tmpdir):
    events_path = Path(tmpdir) / "events.jsonl"
    store = FileEventStore(events_path)
    svc = PracticeApplicationService(event_store=store)
    return svc, store


class PracticeLogTests(unittest.TestCase):

    def test_log_returns_practice_log(self):
        with tempfile.TemporaryDirectory() as td:
            svc, _ = _build(td)
            result = svc.log({
                "song_id": "song_x", "title_snapshot": "江南",
                "minutes": 30, "self_rating": 4, "note": "副歌卡壳",
            })
            self.assertFalse(result.already_processed)
            self.assertEqual(result.log.minutes, 30)
            self.assertEqual(result.log.self_rating, 4)

    def test_rejects_zero_minutes(self):
        with tempfile.TemporaryDirectory() as td:
            svc, _ = _build(td)
            with self.assertRaises(PracticeValidationFailed):
                svc.log({"minutes": 0, "note": "x"})

    def test_rejects_rating_out_of_range(self):
        with tempfile.TemporaryDirectory() as td:
            svc, _ = _build(td)
            with self.assertRaises(PracticeValidationFailed):
                svc.log({"minutes": 10, "self_rating": 7, "note": "x"})

    def test_rejects_no_song_no_note(self):
        with tempfile.TemporaryDirectory() as td:
            svc, _ = _build(td)
            with self.assertRaises(PracticeValidationFailed):
                svc.log({"minutes": 10, "note": ""})

    def test_idempotent_duplicate_event_id(self):
        """相同 event_id 重复打卡 → already_processed=True。"""
        with tempfile.TemporaryDirectory() as td:
            svc, _ = _build(td)
            payload = {
                "event_id": "evt_abc123", "minutes": 10, "note": "x",
            }
            r1 = svc.log(payload)
            r2 = svc.log(payload)
            self.assertFalse(r1.already_processed)
            self.assertTrue(r2.already_processed)

    def test_title_snapshot_filled_from_song(self):
        """无 title_snapshot 但提供 song_id → 从 song_repository 补全。"""
        with tempfile.TemporaryDirectory() as td:
            events_path = Path(td) / "events.jsonl"
            store = FileEventStore(events_path)
            # Mock song repo with known song
            from core.data.songs import Song, SongLibrary
            from server.ports.repositories import StoredSnapshot
            from server.repositories.songs import FileSongRepository
            songs_json = Path(td) / "songs.json"
            import json
            songs_json.write_text(json.dumps({
                "version": 5, "songs": [{
                    "title": "江南", "id": "song_x",
                    "artists": ["林俊杰"], "lyricist": "", "composer": "",
                    "key": "", "capo": None, "difficulty": "", "tabs": "",
                    "status": "active", "tags": [], "pinyin": "",
                    "added_at": "", "notes": "", "learned_at": "",
                    "tab_files": [], "section": 3,
                }],
            }, ensure_ascii=False))
            song_repo = FileSongRepository(songs_json, None)
            svc = PracticeApplicationService(
                event_store=store, song_repository=song_repo)
            result = svc.log({
                "song_id": "song_x", "minutes": 10, "note": "",
            })
            self.assertEqual(result.log.title_snapshot, "江南")


class PracticeGetStatsTests(unittest.TestCase):

    def test_stats_empty_library(self):
        with tempfile.TemporaryDirectory() as td:
            svc, _ = _build(td)
            stats = svc.get_stats(today="2026-07-30")
            self.assertEqual(stats.total_minutes, 0)
            self.assertEqual(stats.total_sessions, 0)
            self.assertEqual(stats.current_streak.total_days, 0)

    def test_stats_with_logs(self):
        with tempfile.TemporaryDirectory() as td:
            svc, _ = _build(td)
            svc.log({"minutes": 10, "note": "day1", "occurred_at": "2026-07-29T08:00:00+08:00"})
            svc.log({"minutes": 20, "note": "day2", "occurred_at": "2026-07-30T08:00:00+08:00"})
            stats = svc.get_stats(today="2026-07-30")
            self.assertEqual(stats.total_minutes, 30)
            self.assertEqual(stats.total_sessions, 2)
            self.assertEqual(stats.current_streak.current_streak, 2)

    def test_streak_only(self):
        with tempfile.TemporaryDirectory() as td:
            svc, _ = _build(td)
            svc.log({"minutes": 10, "note": "y", "occurred_at": "2026-07-29T08:00:00+08:00"})
            svc.log({"minutes": 20, "note": "y", "occurred_at": "2026-07-30T08:00:00+08:00"})
            streak = svc.get_streak(today="2026-07-30")
            self.assertEqual(streak.current_streak, 2)
            self.assertEqual(streak.total_days, 2)

    def test_month_summary(self):
        with tempfile.TemporaryDirectory() as td:
            svc, _ = _build(td)
            svc.log({"minutes": 10, "note": "x", "occurred_at": "2026-07-15T08:00:00+08:00"})
            svc.log({"minutes": 20, "note": "x", "occurred_at": "2026-07-20T08:00:00+08:00"})
            ms = svc.get_month_summary("2026-07")
            self.assertEqual(ms.total_minutes, 30)
            self.assertEqual(ms.total_sessions, 2)


if __name__ == "__main__":
    unittest.main()
