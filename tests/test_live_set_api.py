"""R2.5 live-set 海报 API 端到端测试。

测试场景：
- 空场会话 → 海报 PNG 200 + analyze empty=true
- 入队 1 首 → analyze queued_count=1
- 入队 + 演唱结果 → analyze sung_count=1 / queued_count=1
- 错误 session_id → 404

本测试用 _raw_request 而不是 test_api_contract._request，
因为后者会强制把 response body 当 JSON 解码，不适用于 PNG 二进制。
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
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
    """通用 ASGI 请求：返回 (status, body_bytes, response_headers_dict)。

    - body 总是 bytes（不解析 JSON）
    - 调用方按 content-type 自取
    """
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


class LiveSetApiTests(unittest.TestCase):

    async def _create_session(self, app, title: str = "测试直播"):
        status, body, _ = await _raw_request(
            app, "POST", "/api/live-sessions",
            {"rule_version": "rv1", "title": title},
        )
        assert status == 200, body
        return json.loads(body)["id"]

    def test_poster_empty_session_returns_png(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    sid = await self._create_session(app, "空场")
                    status, png_bytes, headers = await _raw_request(
                        app, "POST", f"/api/live-sessions/{sid}/poster",
                        {"theme_id": "海洋柔光", "canvas_id": "抖音全屏 9:20"},
                    )
                    self.assertEqual(status, 200)
                    self.assertIn("image/png", headers.get("content-type", ""))
                    # 至少 1KB（空场也有底版）
                    self.assertGreater(len(png_bytes), 1024)
                    # PNG magic number
                    self.assertEqual(png_bytes[:8], b"\x89PNG\r\n\x1a\n")
        asyncio.run(scenario())

    def test_poster_unknown_session_returns_404(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    status, body, _ = await _raw_request(
                        app, "POST",
                        "/api/live-sessions/live_nonexistent/poster",
                        {"theme_id": "海洋柔光"},
                    )
                    self.assertEqual(status, 404)
                    err = json.loads(body)["error"]
                    self.assertEqual(err["code"], "live_session_not_found")
        asyncio.run(scenario())

    def test_poster_unknown_theme_returns_404(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    sid = await self._create_session(app, "测试")
                    status, body, _ = await _raw_request(
                        app, "POST", f"/api/live-sessions/{sid}/poster",
                        {"theme_id": "不存在的主题"},
                    )
                    self.assertEqual(status, 404)
                    err = json.loads(body)["error"]
                    self.assertEqual(err["code"], "theme_not_found")
        asyncio.run(scenario())

    def test_poster_unknown_canvas_returns_400(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    sid = await self._create_session(app, "测试")
                    status, body, _ = await _raw_request(
                        app, "POST", f"/api/live-sessions/{sid}/poster",
                        {"theme_id": "海洋柔光", "canvas_id": "9:99"},
                    )
                    self.assertEqual(status, 400)
                    err = json.loads(body)["error"]
                    self.assertEqual(err["code"], "canvas_not_supported")
        asyncio.run(scenario())

    def test_analyze_empty_session(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    sid = await self._create_session(app, "空场")
                    status, body, _ = await _raw_request(
                        app, "GET", f"/api/live-sessions/{sid}/poster/analyze",
                    )
                    self.assertEqual(status, 200)
                    data = json.loads(body)
                    self.assertEqual(data["empty"], True)
                    self.assertEqual(data["total_songs"], 0)
                    self.assertEqual(data["sung_count"], 0)
                    self.assertEqual(data["queued_count"], 0)
                    self.assertEqual(data["page_count"], 1)
        asyncio.run(scenario())

    def test_analyze_with_queue_and_sung(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    sid = await self._create_session(app, "完整场次")
                    # 拿一首 active 歌
                    st, body, _ = await _raw_request(
                        app, "GET", "/api/songs/list?status=active",
                    )
                    self.assertEqual(st, 200)
                    data = json.loads(body)
                    songs = data.get("songs", [])
                    if not songs:
                        self.skipTest("没有 active 歌曲；先 seed-sample")
                    song_id = songs[0]["id"]
                    # 入队 1
                    st, body, _ = await _raw_request(
                        app, "POST", f"/api/live-sessions/{sid}/queue",
                        {"song_id": song_id, "requester_name": "粉A",
                         "command_id": "cmd-1"},
                    )
                    self.assertEqual(st, 200, body)
                    req_id = json.loads(body)["request_id"]
                    # 入队 2
                    st, body, _ = await _raw_request(
                        app, "POST", f"/api/live-sessions/{sid}/queue",
                        {"song_id": song_id, "requester_name": "粉B",
                         "command_id": "cmd-2"},
                    )
                    self.assertEqual(st, 200, body)
                    # 标记第 1 首 sung
                    st, body, _ = await _raw_request(
                        app, "POST", f"/api/live-sessions/{sid}/record",
                        {"request_id": req_id, "result": "sung"},
                    )
                    self.assertEqual(st, 200, body)
                    # analyze
                    st, body, _ = await _raw_request(
                        app, "GET", f"/api/live-sessions/{sid}/poster/analyze",
                    )
                    self.assertEqual(st, 200)
                    data = json.loads(body)
                    self.assertEqual(data["sung_count"], 1)
                    self.assertEqual(data["queued_count"], 1)
                    self.assertEqual(data["total_songs"], 2)
        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
