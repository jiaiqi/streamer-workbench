"""R3.5 learning-report 海报 API 端到端测试。

测试场景：
- 空报告（无事件）→ 海报 PNG 200 + analyze empty=true
- 有事件（practice + song_learned）→ 海报 PNG 200 + analyze 桶摘要正确
- 错误 theme / canvas → 400/404
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.config import AppConfig


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _boot_app(data_root: Path):
    from server.app import create_app
    return create_app(AppConfig(PROJECT_ROOT, mode="test", data_root=data_root))  # noqa: E501


async def _raw_request(app, method: str, path: str, payload: dict | None = None,
                       headers: dict | None = None):
    target = urlsplit(path)
    body = (json.dumps(payload, ensure_ascii=False).encode("utf-8")
            if payload is not None else b"")
    sent = False
    messages = []

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
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
                    for key, value in ({"content-type": "application/json"} | (headers or {})).items()
                ],
                "client": ("test", 1), "server": ("test", 80),
            },
            receive,
            send,
        )
    except Exception:
        if not any(message["type"] == "http.response.start" for message in messages):
            raise
    status = next(message["status"] for message in messages
                  if message["type"] == "http.response.start")
    response_start = next(message for message in messages
                          if message["type"] == "http.response.start")
    response_headers = {
        key.decode().lower(): value.decode()
        for key, value in response_start.get("headers", [])
    }
    response_body = b"".join(message.get("body", b"") for message in messages
                             if message["type"] == "http.response.body")
    return status, response_body, response_headers


class LearningReportApiTests(unittest.TestCase):

    async def _add_song(self, app, title: str = "测试曲") -> str:
        """添加一首 active 歌，返回 song_id。"""
        st, body, _ = await _raw_request(
            app, "POST", "/api/songs/add",
            {"title": title, "artists": ["测试歌手"], "status": "active"},
        )
        self.assertEqual(st, 200, body)
        return json.loads(body)["song"]["id"]

    async def _log_practice(self, app, song_id: str, minutes: int = 15,
                            rating: int = 4) -> None:
        st, body, _ = await _raw_request(
            app, "POST", "/api/practice/log",
            {"song_id": song_id, "minutes": minutes, "self_rating": rating},
        )
        self.assertEqual(st, 200, body)

    def test_poster_empty_returns_png(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    st, png_bytes, headers = await _raw_request(
                        app, "POST", "/api/learning-report/poster",
                        {"theme_id": "海洋柔光", "canvas_id": "抖音全屏 9:20",
                         "days": 30, "period_label": "测试报告"},
                    )
                    self.assertEqual(st, 200)
                    self.assertIn("image/png", headers.get("content-type", ""))
                    self.assertGreater(len(png_bytes), 1024)
                    self.assertEqual(png_bytes[:8], b"\x89PNG\r\n\x1a\n")
        asyncio.run(scenario())

    def test_poster_with_practice(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    sid = await self._add_song(app, "练习曲 A")
                    await self._log_practice(app, sid, 25, 4)
                    st, png_bytes, headers = await _raw_request(
                        app, "POST", "/api/learning-report/poster",
                        {"theme_id": "海洋柔光", "canvas_id": "抖音全屏 9:20",
                         "days": 30},
                    )
                    self.assertEqual(st, 200)
                    self.assertGreater(len(png_bytes), 1024)
        asyncio.run(scenario())

    def test_poster_unknown_theme_returns_404(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    st, body, _ = await _raw_request(
                        app, "POST", "/api/learning-report/poster",
                        {"theme_id": "不存在的主题"},
                    )
                    self.assertEqual(st, 404)
                    err = json.loads(body)["error"]
                    self.assertEqual(err["code"], "theme_not_found")
        asyncio.run(scenario())

    def test_poster_unsupported_canvas_returns_400(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    st, body, _ = await _raw_request(
                        app, "POST", "/api/learning-report/poster",
                        {"theme_id": "海洋柔光", "canvas_id": "9:99"},
                    )
                    self.assertEqual(st, 400)
                    err = json.loads(body)["error"]
                    self.assertEqual(err["code"], "canvas_not_supported")
        asyncio.run(scenario())

    def test_analyze_empty(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    st, body, _ = await _raw_request(
                        app, "GET", "/api/learning-report/analyze?days=30",
                    )
                    self.assertEqual(st, 200)
                    data = json.loads(body)
                    self.assertEqual(data["empty"], True)
                    self.assertEqual(data["total_practice_sessions"], 0)
                    self.assertEqual(data["page_count"], 1)
        asyncio.run(scenario())

    def test_analyze_with_data(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    sid = await self._add_song(app, "练习曲 B")
                    await self._log_practice(app, sid, 30, 5)
                    st, body, _ = await _raw_request(
                        app, "GET", "/api/learning-report/analyze?days=30",
                    )
                    self.assertEqual(st, 200)
                    data = json.loads(body)
                    self.assertEqual(data["empty"], False)
                    self.assertGreaterEqual(data["total_practice_sessions"], 1)
                    self.assertGreaterEqual(data["total_practice_minutes"], 30)
        asyncio.run(scenario())

    # ── R4.0: days / top_n_artists 范围校验 ──

    def test_analyze_days_out_of_range_rejected(self):
        """R4.0: days=0/366/1000 必须被 FastAPI Query 校验为 422。"""
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    for bad in (0, -1, 366, 1000):
                        st, _, _ = await _raw_request(
                            app, "GET", f"/api/learning-report/analyze?days={bad}",
                        )
                        self.assertEqual(
                            st, 422,
                            f"days={bad} 应被 422 拒绝，实际 {st}",
                        )
        asyncio.run(scenario())

    def test_analyze_top_n_out_of_range_rejected(self):
        """R4.0: top_n_artists=0/21 必须被 FastAPI Query 校验为 422。"""
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    for bad in (0, -3, 21, 999):
                        st, _, _ = await _raw_request(
                            app, "GET",
                            f"/api/learning-report/analyze?top_n_artists={bad}",
                        )
                        self.assertEqual(
                            st, 422,
                            f"top_n_artists={bad} 应被 422 拒绝，实际 {st}",
                        )
        asyncio.run(scenario())

    def test_poster_days_out_of_range_rejected(self):
        """R4.0: POST 端点 days=0/366 由 Pydantic 422 拒绝。"""
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    for bad in (0, 400):
                        st, _, _ = await _raw_request(
                            app, "POST", "/api/learning-report/poster",
                            {"theme_id": "海洋柔光", "canvas_id": "抖音全屏 9:20",
                             "days": bad},
                        )
                        self.assertEqual(
                            st, 422,
                            f"days={bad} 应被 422 拒绝，实际 {st}",
                        )
        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
