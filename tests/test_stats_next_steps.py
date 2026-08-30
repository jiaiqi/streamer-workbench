"""P1-A3 行动型统计洞察（下一步建议）测试。

覆盖：
- StatsApplicationService.next_steps() 3 类建议 + 冷启动
- GET /api/stats/next-steps 端点（参数边界 + 数据驱动）
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.config import AppConfig  # noqa: E402


def _boot_app(td: Path):
    from server.app import create_app
    return create_app(AppConfig(Path(__file__).resolve().parents[1],
                                mode="test", data_root=td))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _iso_days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat(timespec="seconds")


def _setup_data(td: Path, *, include_songs=True, include_events=True):
    """写 songs.json + events.jsonl 标准化测试数据。

    默认覆盖 3 类建议各 1 个触发条件。
    """
    if include_songs:
        songs = {
            "schema_version": 5,
            "songs": [
                # 歌 A: hard + 后续 events 写 2 次 unknown
                {"title": "难歌A", "id": "song_a", "artists": ["A"],
                 "difficulty": "hard", "key": "C", "capo": 0,
                 "status": "active", "tags": [], "pinyin": "", "notes": "",
                 "added_at": _now_iso(), "learned_at": _iso_days_ago(60),
                 "tab_files": [], "section": None,
                 "lyrics_lrc": "", "lyrics_plain": "",
                 "audio_vocal_path": "", "audio_instrumental_path": "",
                 "audio_duration_ms": 0},
                # 歌 B: 45 天前学会, 无 practice_logged
                {"title": "旧歌B", "id": "song_b", "artists": ["B"],
                 "difficulty": "medium", "key": "G", "capo": 0,
                 "status": "active", "tags": [], "pinyin": "", "notes": "",
                 "added_at": _now_iso(), "learned_at": _iso_days_ago(45),
                 "tab_files": [], "section": None,
                 "lyrics_lrc": "", "lyrics_plain": "",
                 "audio_vocal_path": "", "audio_instrumental_path": "",
                 "audio_duration_ms": 0},
                # 歌 C: 点歌 3 次但 30 天前才唱
                {"title": "热歌C", "id": "song_c", "artists": ["C"],
                 "difficulty": "medium", "key": "D", "capo": 2,
                 "status": "active", "tags": [], "pinyin": "", "notes": "",
                 "added_at": _now_iso(), "learned_at": _iso_days_ago(60),
                 "tab_files": [], "section": None,
                 "lyrics_lrc": "", "lyrics_plain": "",
                 "audio_vocal_path": "", "audio_instrumental_path": "",
                 "audio_duration_ms": 0},
            ],
        }
        (td / "songs.json").write_text(
            json.dumps(songs, ensure_ascii=False), encoding="utf-8")
    if include_events:
        events = [
            # song_a: 2 次 performance_unknown（difficult 触发）
            {"schema_version": 2, "source": "test", "event_id": "evt_a1",
             "occurred_at": _iso_days_ago(1), "recorded_at": _iso_days_ago(1),
             "type": "performance_unknown", "song_id": "song_a",
             "title_snapshot": "难歌A"},
            {"schema_version": 2, "source": "test", "event_id": "evt_a2",
             "occurred_at": _iso_days_ago(1), "recorded_at": _iso_days_ago(1),
             "type": "performance_unknown", "song_id": "song_a",
             "title_snapshot": "难歌A"},
            # song_c: 3 次点歌 + 30 天前 1 次 sung（restage 触发）
            {"schema_version": 2, "source": "test", "event_id": "evt_c1",
             "occurred_at": _iso_days_ago(2), "recorded_at": _iso_days_ago(2),
             "type": "queue_added", "song_id": "song_c",
             "title_snapshot": "热歌C"},
            {"schema_version": 2, "source": "test", "event_id": "evt_c2",
             "occurred_at": _iso_days_ago(2), "recorded_at": _iso_days_ago(2),
             "type": "queue_added", "song_id": "song_c",
             "title_snapshot": "热歌C"},
            {"schema_version": 2, "source": "test", "event_id": "evt_c3",
             "occurred_at": _iso_days_ago(2), "recorded_at": _iso_days_ago(2),
             "type": "queue_added", "song_id": "song_c",
             "title_snapshot": "热歌C"},
            {"schema_version": 2, "source": "test", "event_id": "evt_c_sung",
             "occurred_at": _iso_days_ago(30), "recorded_at": _iso_days_ago(30),
             "type": "performance_sung", "song_id": "song_c",
             "title_snapshot": "热歌C"},
        ]
        with (td / "events.jsonl").open("w", encoding="utf-8") as f:
            for e in events:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")


# ── 1) StatsApplicationService.next_steps 单元测试 ──


class NextStepsUnitTests(unittest.TestCase):

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.td = Path(self._td.name) / "data"
        self.td.mkdir(parents=True, exist_ok=True)
        _setup_data(self.td)
        # 启动 app 让 lifespan 装配 service
        from server.app import create_app
        self.app = create_app(AppConfig(Path(__file__).resolve().parents[1],
                                        mode="test", data_root=self.td))

    def tearDown(self):
        self._td.cleanup()

    def _service(self):
        # lifespan 未启动时 service 不在 ctx；用 ApplicationService 直接 new
        from server.services.stats import StatsApplicationService
        from server.repositories.events import FileEventStore
        from server.repositories.songs import FileSongRepository
        from server.ports.repositories import BackupPolicy as BP
        ev = FileEventStore(self.td / "events.jsonl")
        sr = FileSongRepository(self.td / "songs.json",
                                BP(self.td / "backups"))
        svc = StatsApplicationService(event_store=ev, song_repository=sr)
        # 注意：不要 close ev（test 还要用）；tearDown 时 GC 清理
        return svc, ev, sr

    def test_review_appears_for_45d_ago_unpracticed(self):
        svc, ev, sr = self._service()
        try:
            r = svc.next_steps()
            review = [i for i in r.items if i.kind == "review"]
            b = next((i for i in review if i.song_id == "song_b"), None)
            self.assertIsNotNone(b, f"review 应包含 song_b；got {review}")
            self.assertIn("45", b.reason)
        finally:
            ev.close()

    def test_difficult_appears_for_hard_with_2_unknown(self):
        svc, ev, sr = self._service()
        try:
            r = svc.next_steps()
            diff = [i for i in r.items if i.kind == "difficult"]
            a = next((i for i in diff if i.song_id == "song_a"), None)
            self.assertIsNotNone(a, f"difficult 应包含 song_a；got {diff}")
            self.assertGreaterEqual(a.metric, 2)
        finally:
            ev.close()

    def test_restage_appears_for_top_song_30d_ago(self):
        svc, ev, sr = self._service()
        try:
            r = svc.next_steps()
            rest = [i for i in r.items if i.kind == "restage"]
            c = next((i for i in rest if i.song_id == "song_c"), None)
            self.assertIsNotNone(c, f"restage 应包含 song_c；got {rest}")
            self.assertEqual(c.metric, 3)
            self.assertGreaterEqual(c.days_since, 7)
        finally:
            ev.close()

    def test_all_three_kinds_appear(self):
        svc, ev, sr = self._service()
        try:
            r = svc.next_steps()
            kinds = {i.kind for i in r.items}
            self.assertEqual(kinds, {"review", "difficult", "restage"})
        finally:
            ev.close()

    def test_review_skipped_for_recently_practiced(self):
        # 加一个 song_b 本周 practice_logged
        with (self.td / "events.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "schema_version": 2, "source": "test", "event_id": "evt_p1",
                "occurred_at": _iso_days_ago(3), "recorded_at": _iso_days_ago(3),
                "type": "practice_logged", "song_id": "song_b",
                "title_snapshot": "旧歌B"}, ensure_ascii=False) + "\n")
        svc, ev, sr = self._service()
        try:
            r = svc.next_steps(practice_window_days=7)
            b = next((i for i in r.items
                      if i.song_id == "song_b" and i.kind == "review"), None)
            self.assertIsNone(b)
        finally:
            ev.close()

    def test_difficult_skipped_for_only_one_unknown(self):
        # 把 song_a 的 1 个 unknown 删掉（重写 events.jsonl 只保留 1 个）
        events = [
            {"schema_version": 2, "source": "test", "event_id": "evt_a1",
             "occurred_at": _iso_days_ago(1), "recorded_at": _iso_days_ago(1),
             "type": "performance_unknown", "song_id": "song_a",
             "title_snapshot": "难歌A"},
            # song_c events（保留让 restage 仍工作）
            {"schema_version": 2, "source": "test", "event_id": "evt_c1",
             "occurred_at": _iso_days_ago(2), "recorded_at": _iso_days_ago(2),
             "type": "queue_added", "song_id": "song_c",
             "title_snapshot": "热歌C"},
            {"schema_version": 2, "source": "test", "event_id": "evt_c2",
             "occurred_at": _iso_days_ago(2), "recorded_at": _iso_days_ago(2),
             "type": "queue_added", "song_id": "song_c",
             "title_snapshot": "热歌C"},
            {"schema_version": 2, "source": "test", "event_id": "evt_c3",
             "occurred_at": _iso_days_ago(2), "recorded_at": _iso_days_ago(2),
             "type": "queue_added", "song_id": "song_c",
             "title_snapshot": "热歌C"},
            {"schema_version": 2, "source": "test", "event_id": "evt_c_sung",
             "occurred_at": _iso_days_ago(30), "recorded_at": _iso_days_ago(30),
             "type": "performance_sung", "song_id": "song_c",
             "title_snapshot": "热歌C"},
        ]
        with (self.td / "events.jsonl").open("w", encoding="utf-8") as f:
            for e in events:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        svc, ev, sr = self._service()
        try:
            r = svc.next_steps(difficult_recent_n=5)
            diff = [i for i in r.items
                    if i.song_id == "song_a" and i.kind == "difficult"]
            self.assertEqual(len(diff), 0)
        finally:
            ev.close()

    def test_restage_skipped_below_min_requests(self):
        # song_c 只 2 次点歌
        with (self.td / "events.jsonl").open("w", encoding="utf-8") as f:
            for e in [
                {"schema_version": 2, "source": "test", "event_id": "evt_c1",
                 "occurred_at": _iso_days_ago(2), "recorded_at": _iso_days_ago(2),
                 "type": "queue_added", "song_id": "song_c",
                 "title_snapshot": "热歌C"},
                {"schema_version": 2, "source": "test", "event_id": "evt_c2",
                 "occurred_at": _iso_days_ago(2), "recorded_at": _iso_days_ago(2),
                 "type": "queue_added", "song_id": "song_c",
                 "title_snapshot": "热歌C"},
            ]:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        svc, ev, sr = self._service()
        try:
            r = svc.next_steps(restage_window_days=7)
            rest = [i for i in r.items
                    if i.song_id == "song_c" and i.kind == "restage"]
            self.assertEqual(len(rest), 0)
        finally:
            ev.close()

    def test_max_per_kind_limit(self):
        svc, ev, sr = self._service()
        try:
            r = svc.next_steps(max_per_kind=1)
            kinds_count: dict = {}
            for i in r.items:
                kinds_count.setdefault(i.kind, 0)
                kinds_count[i.kind] += 1
            for k, n in kinds_count.items():
                self.assertLessEqual(n, 1, f"{k} 超过 max_per_kind=1")
        finally:
            ev.close()

    def test_empty_library_returns_empty_with_note(self):
        # 清空数据
        (self.td / "songs.json").write_text(
            json.dumps({"schema_version": 5, "songs": []}, ensure_ascii=False),
            encoding="utf-8")
        (self.td / "events.jsonl").write_text("", encoding="utf-8")
        svc, ev, sr = self._service()
        try:
            r = svc.next_steps()
            self.assertEqual(r.items, [])
            self.assertIn("曲库为空", r.note)
        finally:
            ev.close()


# ── 2) HTTP 端点测试 ──


class NextStepsHttpTests(unittest.TestCase):

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.td = Path(self._td.name) / "data"
        self.td.mkdir(parents=True, exist_ok=True)
        _setup_data(self.td)
        self.app = _boot_app(self.td)

    def tearDown(self):
        self._td.cleanup()

    def test_endpoint_returns_200_with_3_kinds(self):
        import asyncio
        from tests.test_api_contract import _request
        async def run():
            async with self.app.router.lifespan_context(self.app):
                status, body, _ = await _request(
                    self.app, "GET", "/api/stats/next-steps")
                self.assertEqual(status, 200, body)
                self.assertIn("items", body)
                self.assertIn("note", body)
                kinds = {i["kind"] for i in body["items"]}
                self.assertIn("review", kinds)
                self.assertIn("difficult", kinds)
                self.assertIn("restage", kinds)
        asyncio.run(run())

    def test_endpoint_param_bounds(self):
        import asyncio
        from tests.test_api_contract import _request
        async def run():
            async with self.app.router.lifespan_context(self.app):
                # 非法值钳到合法范围
                for q in ("?review_window_days=99999",
                          "?restage_window_days=99999",
                          "?max_per_kind=999",
                          "?practice_window_days=99999",
                          "?difficult_recent_n=99999"):
                    status, body, _ = await _request(
                        self.app, "GET", f"/api/stats/next-steps{q}")
                    self.assertEqual(status, 200, f"{q} 失败: {body}")
        asyncio.run(run())

    def test_endpoint_zero_songs_note(self):
        import asyncio
        from tests.test_api_contract import _request
        # 清空数据
        (self.td / "songs.json").write_text(
            json.dumps({"schema_version": 5, "songs": []}, ensure_ascii=False),
            encoding="utf-8")
        (self.td / "events.jsonl").write_text("", encoding="utf-8")
        async def run():
            async with self.app.router.lifespan_context(self.app):
                status, body, _ = await _request(
                    self.app, "GET", "/api/stats/next-steps")
                self.assertEqual(status, 200)
                self.assertEqual(body["items"], [])
                self.assertIn("曲库为空", body["note"])
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
