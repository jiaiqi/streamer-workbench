"""P4 R3: 学歌练习 HTTP API 端到端测试。"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.config import AppConfig
from tests.test_api_contract import _request


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _boot_app(data_root: Path):
    from server.app import create_app
    return create_app(AppConfig(PROJECT_ROOT, mode="test", data_root=data_root))


class PracticeLogApiTests(unittest.TestCase):

    def test_log_returns_event_id(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    status, body, _ = await _request(
                        app, "POST", "/api/practice/log",
                        {"song_id": "song_x", "title_snapshot": "江南",
                          "minutes": 30, "self_rating": 4, "note": "副歌卡壳"},
                    )
                    assert status == 200, body
                    assert body["ok"] is True
                    assert body["event_id"].startswith("evt_")
                    self.assertEqual(body["minutes"], 30)
                    self.assertFalse(body["already_processed"])
        asyncio.run(scenario())

    def test_log_idempotent_duplicate_event_id(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    payload = {
                        "event_id": "evt_same_1", "minutes": 10, "note": "x",
                    }
                    await _request(app, "POST", "/api/practice/log", payload)
                    status, body, _ = await _request(
                        app, "POST", "/api/practice/log", payload,
                    )
                    assert status == 200
                    assert body["already_processed"] is True
        asyncio.run(scenario())

    def test_log_rejects_zero_minutes(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    status, body, _ = await _request(
                        app, "POST", "/api/practice/log",
                        {"minutes": 0, "note": "x"},
                    )
                    assert status == 400
                    assert body["error"]["code"] == "invalid_practice"
        asyncio.run(scenario())

    def test_log_rejects_no_song_no_note(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    status, body, _ = await _request(
                        app, "POST", "/api/practice/log",
                        {"minutes": 10, "note": ""},
                    )
                    assert status == 400
                    assert body["error"]["code"] == "invalid_practice"
        asyncio.run(scenario())


class PracticeStatsApiTests(unittest.TestCase):

    def test_stats_empty(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    status, body, _ = await _request(
                        app, "GET", "/api/practice/stats", None,
                    )
                    assert status == 200
                    self.assertEqual(body["total_minutes"], 0)
                    self.assertEqual(body["current_streak_days"], 0)
                    self.assertEqual(len(body["months"]), 6)
        asyncio.run(scenario())

    def test_stats_with_logs(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    for minutes in (10, 20, 30):
                        await _request(app, "POST", "/api/practice/log",
                                        {"minutes": minutes, "note": "x"})
                    status, body, _ = await _request(
                        app, "GET", "/api/practice/stats", None,
                    )
                    assert status == 200
                    self.assertEqual(body["total_minutes"], 60)
                    self.assertEqual(body["total_sessions"], 3)
        asyncio.run(scenario())

    def test_streak(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    # 连续 2 天
                    await _request(app, "POST", "/api/practice/log",
                                    {"minutes": 10, "note": "x",
                                      "occurred_at": "2026-07-29T08:00:00+08:00"})
                    await _request(app, "POST", "/api/practice/log",
                                    {"minutes": 20, "note": "x",
                                      "occurred_at": "2026-07-30T08:00:00+08:00"})
                    status, body, _ = await _request(
                        app, "GET", "/api/practice/streak", None,
                    )
                    assert status == 200
                    self.assertEqual(body["current_streak"], 2)
                    self.assertEqual(body["total_days"], 2)
        asyncio.run(scenario())


class PracticeMonthApiTests(unittest.TestCase):

    def test_month_summary(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    await _request(app, "POST", "/api/practice/log",
                                    {"minutes": 10, "note": "x",
                                      "occurred_at": "2026-07-15T08:00:00+08:00"})
                    await _request(app, "POST", "/api/practice/log",
                                    {"minutes": 20, "note": "x",
                                      "occurred_at": "2026-07-20T08:00:00+08:00"})
                    status, body, _ = await _request(
                        app, "GET", "/api/practice/months/2026-07", None,
                    )
                    assert status == 200
                    self.assertEqual(body["month"], "2026-07")
                    self.assertEqual(body["total_minutes"], 30)
                    self.assertEqual(body["total_sessions"], 2)
        asyncio.run(scenario())

    def test_invalid_month_format(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    status, body, _ = await _request(
                        app, "GET", "/api/practice/months/202607", None,
                    )
                    assert status == 400
        asyncio.run(scenario())


class PracticePersistenceTests(unittest.TestCase):

    def test_restart_app_recovers_logs(self):
        """lifespan 启动时 EventStore 自动读取已存 practice_logged。"""
        async def scenario():
            data_root = Path(tempfile.mkdtemp())
            try:
                app1 = _boot_app(data_root)
                async with app1.router.lifespan_context(app1):
                    await _request(app1, "POST", "/api/practice/log",
                                    {"minutes": 30, "note": "x"})

                app2 = _boot_app(data_root)
                async with app2.router.lifespan_context(app2):
                    status, body, _ = await _request(
                        app2, "GET", "/api/practice/stats", None,
                    )
                    assert status == 200
                    self.assertEqual(body["total_minutes"], 30)
            finally:
                import shutil
                shutil.rmtree(data_root, ignore_errors=True)
        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
