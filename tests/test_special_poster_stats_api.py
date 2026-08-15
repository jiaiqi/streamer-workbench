"""R4 退出条件 #3: GET /api/posters/special-stats 端点测试。

覆盖：
- 空 events → totals 全 0
- 仅 live-poster 事件 → totals.live_poster = N
- 仅 learning-report 事件 → totals.learning_report = M
- 混合事件 + grid-export 不计入
- 时间窗口过滤（旧事件 since 之外不计入）
- days 参数校验（0/366 → 422；默认值 30）
- by_day 按日分桶正确
- recent 最多 5 条
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.config import AppConfig


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _boot_app(data_root: Path):
    from server.app import create_app
    return create_app(AppConfig(PROJECT_ROOT, mode="test", data_root=data_root))  # noqa: E501


async def _raw_request(app, method: str, path: str):
    """通用 ASGI 请求。"""
    target = urlsplit(path)
    sent = False
    messages = []

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    try:
        await app(
            {
                "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                "method": method, "scheme": "http", "path": target.path,
                "raw_path": target.path.encode(),
                "query_string": target.query.encode(),
                "headers": [
                    (key.lower().encode(), value.encode())
                    for key, value in {"content-type": "application/json"}.items()
                ],
                "client": ("test", 1), "server": ("test", 80),
            },
            receive, send,
        )
    except Exception:
        if not any(message["type"] == "http.response.start" for message in messages):
            raise

    status = next(message["status"] for message in messages
                  if message["type"] == "http.response.start")
    body = b"".join(bytes(message.get("body", b""))
                    for message in messages if message["type"] == "http.response.body")
    return status, body


def _append_event(context, *, occurred_at: datetime | None = None,
                  meta: dict | None = None, source: str = "test-fixture"):
    """往 event_store 写一条 poster_exported 事件。"""
    when = occurred_at or datetime.now().astimezone()
    event = {
        "schema_version": 2,
        "event_id": f"evt_{uuid.uuid4().hex}",
        "occurred_at": when.isoformat(timespec="seconds"),
        "recorded_at": when.isoformat(timespec="seconds"),
        "type": "poster_exported",
        "source": source,
        "meta": meta or {"kind": "grid-export"},
    }
    context.event_store.append(event)
    return event


class SpecialPosterStatsApiTests(unittest.TestCase):

    def test_empty_events_returns_zero_totals(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    status, body = await _raw_request(
                        app, "GET", "/api/posters/special-stats?days=30"
                    )
                    self.assertEqual(status, 200)
                    payload = json.loads(body)
                    self.assertEqual(payload["days"], 30)
                    self.assertEqual(payload["totals"],
                                     {"live_poster": 0, "learning_report": 0})
                    self.assertEqual(payload["by_day"], {})
                    self.assertEqual(payload["recent"], [])
                    # since 应是 30 天前
                    since_dt = datetime.fromisoformat(payload["since"])
                    delta = datetime.now().astimezone() - since_dt
                    self.assertAlmostEqual(delta.total_seconds(), 30 * 86400,
                                           delta=60)
        asyncio.run(scenario())

    def test_live_poster_events_count(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    ctx = app.state.context
                    for i in range(3):
                        _append_event(ctx, source="live-poster-api",
                                      meta={"kind": "live-poster",
                                            "session_id": f"s{i}",
                                            "title": f"直播 {i}"})
                    status, body = await _raw_request(
                        app, "GET", "/api/posters/special-stats?days=30"
                    )
                    self.assertEqual(status, 200)
                    payload = json.loads(body)
                    self.assertEqual(payload["totals"]["live_poster"], 3)
                    self.assertEqual(payload["totals"]["learning_report"], 0)
                    self.assertEqual(len(payload["recent"]), 3)
        asyncio.run(scenario())

    def test_learning_report_events_count(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    ctx = app.state.context
                    for i in range(2):
                        _append_event(ctx, source="learning-report-api",
                                      meta={"kind": "learning-report",
                                            "days": 7 + i,
                                            "period_label": f"近 {7+i} 天"})
                    status, body = await _raw_request(
                        app, "GET", "/api/posters/special-stats?days=30"
                    )
                    payload = json.loads(body)
                    self.assertEqual(payload["totals"]["live_poster"], 0)
                    self.assertEqual(payload["totals"]["learning_report"], 2)
        asyncio.run(scenario())

    def test_grid_export_events_excluded(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    ctx = app.state.context
                    # 5 个 grid-export + 2 个 live-poster
                    for _ in range(5):
                        _append_event(ctx,
                                      meta={"kind": "grid-export", "files": 1})
                    for i in range(2):
                        _append_event(ctx, source="live-poster-api",
                                      meta={"kind": "live-poster",
                                            "session_id": f"s{i}", "title": "x"})
                    status, body = await _raw_request(
                        app, "GET", "/api/posters/special-stats?days=30"
                    )
                    payload = json.loads(body)
                    # grid-export 不应计入
                    self.assertEqual(payload["totals"]["live_poster"], 2)
                    self.assertEqual(payload["totals"]["learning_report"], 0)
        asyncio.run(scenario())

    def test_time_window_filters_old_events(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    ctx = app.state.context
                    now = datetime.now().astimezone()
                    # 100 天前 live-poster（应被过滤）
                    _append_event(ctx,
                                  occurred_at=now - timedelta(days=100),
                                  source="live-poster-api",
                                  meta={"kind": "live-poster", "session_id": "old",
                                        "title": "old"})
                    # 5 天前 live-poster（应保留）
                    _append_event(ctx,
                                  occurred_at=now - timedelta(days=5),
                                  source="live-poster-api",
                                  meta={"kind": "live-poster", "session_id": "recent",
                                        "title": "recent"})
                    status, body = await _raw_request(
                        app, "GET", "/api/posters/special-stats?days=30"
                    )
                    payload = json.loads(body)
                    self.assertEqual(payload["totals"]["live_poster"], 1)
        asyncio.run(scenario())

    def test_by_day_buckets(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    ctx = app.state.context
                    now = datetime.now().astimezone()
                    today = now.replace(hour=10, minute=0, second=0, microsecond=0)
                    yesterday = today - timedelta(days=1)
                    # 今天 2 个 live + 1 个 report
                    for _ in range(2):
                        _append_event(ctx, occurred_at=today,
                                      source="live-poster-api",
                                      meta={"kind": "live-poster", "session_id": "x", "title": "t"})
                    _append_event(ctx, occurred_at=today,
                                  source="learning-report-api",
                                  meta={"kind": "learning-report", "days": 7, "period_label": "近 7 天"})
                    # 昨天 1 个 live
                    _append_event(ctx, occurred_at=yesterday,
                                  source="live-poster-api",
                                  meta={"kind": "live-poster", "session_id": "y", "title": "y"})
                    status, body = await _raw_request(
                        app, "GET", "/api/posters/special-stats?days=30"
                    )
                    payload = json.loads(body)
                    today_key = today.date().isoformat()
                    yesterday_key = yesterday.date().isoformat()
                    self.assertEqual(payload["by_day"][today_key]["live_poster"], 2)
                    self.assertEqual(payload["by_day"][today_key]["learning_report"], 1)
                    self.assertEqual(payload["by_day"][yesterday_key]["live_poster"], 1)
                    self.assertEqual(payload["by_day"][yesterday_key]["learning_report"], 0)
        asyncio.run(scenario())

    def test_recent_max_5(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    ctx = app.state.context
                    for _ in range(8):
                        _append_event(ctx, source="live-poster-api",
                                      meta={"kind": "live-poster", "session_id": "x", "title": "x"})
                    status, body = await _raw_request(
                        app, "GET", "/api/posters/special-stats?days=30"
                    )
                    payload = json.loads(body)
                    self.assertEqual(len(payload["recent"]), 5)
                    self.assertEqual(payload["totals"]["live_poster"], 8)
        asyncio.run(scenario())

    def test_invalid_days_422(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    # days=0 越界
                    status, _ = await _raw_request(
                        app, "GET", "/api/posters/special-stats?days=0"
                    )
                    self.assertEqual(status, 422)
                    # days=400 越界
                    status, _ = await _raw_request(
                        app, "GET", "/api/posters/special-stats?days=400"
                    )
                    self.assertEqual(status, 422)
        asyncio.run(scenario())

    def test_default_days_is_30(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    status, body = await _raw_request(
                        app, "GET", "/api/posters/special-stats"
                    )
                    self.assertEqual(status, 200)
                    payload = json.loads(body)
                    self.assertEqual(payload["days"], 30)
        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
