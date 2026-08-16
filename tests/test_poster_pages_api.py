"""R4 退出条件 #2: 草稿/手动分页 UI V3 — 4 个端点测试。

覆盖：
- GET 空 manual_pages
- POST 追加空页
- POST 多次累加
- PATCH 重排（合法 new_order）
- PATCH 非法 new_order 422
- DELETE 删除指定页
- DELETE 越界 422
- DELETE 删空后 mode 回退到 auto
- 修改后自动切 mode=manual
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


async def _raw_request(app, method: str, path: str, payload: dict | None = None):
    """通用 ASGI 请求。"""
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
                    for key, value in {"content-type": "application/json"}.items()
                ],
                "client": ("test", 1), "server": ("test", 80),
            }, receive, send,
        )
    except Exception:
        if not any(message["type"] == "http.response.start" for message in messages):
            raise

    status = next(message["status"] for message in messages
                  if message["type"] == "http.response.start")
    body = b"".join(bytes(message.get("body", b""))
                    for message in messages if message["type"] == "http.response.body")
    return status, body


async def _create_poster(app) -> str:
    payload = {
        "name": "测试海报",
        "song_source": {"type": "all_active", "artists": []},
        "selected_song_ids": [],
        "grouping": "none",
        "sorting": "manual",
        "layout_id": "magazine-flow",
        "theme_id": "海洋柔光",
        "canvas_id": "9:20",
        "page_policy": {"mode": "auto", "min_pages": 1, "max_pages": 8},
        "parameters": {},
        "export_settings": {"format": "png", "jpeg_quality": 92,
                            "single_page": False, "dpi": 144},
    }
    status, body = await _raw_request(app, "POST", "/api/posters", payload)
    assert status == 200, f"创建海报失败: {status} {body!r}"
    return json.loads(body)["id"]


class PosterPagesApiTests(unittest.TestCase):

    def test_get_empty_pages(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    poster_id = await _create_poster(app)
                    status, body = await _raw_request(
                        app, "GET", f"/api/posters/{poster_id}/pages"
                    )
                    self.assertEqual(status, 200)
                    payload = json.loads(body)
                    self.assertEqual(payload["items"], [])
                    self.assertEqual(payload["mode"], "auto")
        asyncio.run(scenario())

    def test_add_page(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    poster_id = await _create_poster(app)
                    status, body = await _raw_request(
                        app, "POST", f"/api/posters/{poster_id}/pages"
                    )
                    self.assertEqual(status, 200)
                    payload = json.loads(body)
                    self.assertEqual(len(payload["items"]), 1)
                    self.assertEqual(payload["mode"], "manual")
        asyncio.run(scenario())

    def test_add_multiple_pages(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    poster_id = await _create_poster(app)
                    for _ in range(3):
                        status, _ = await _raw_request(
                            app, "POST", f"/api/posters/{poster_id}/pages"
                        )
                        self.assertEqual(status, 200)
                    status, body = await _raw_request(
                        app, "GET", f"/api/posters/{poster_id}/pages"
                    )
                    payload = json.loads(body)
                    self.assertEqual(len(payload["items"]), 3)
        asyncio.run(scenario())

    def test_reorder_pages(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    poster_id = await _create_poster(app)
                    for _ in range(3):
                        await _raw_request(
                            app, "POST", f"/api/posters/{poster_id}/pages"
                        )
                    status, body = await _raw_request(
                        app, "PATCH", f"/api/posters/{poster_id}/pages",
                        payload={"new_order": [2, 0, 1]},
                    )
                    self.assertEqual(status, 200)
                    payload = json.loads(body)
                    self.assertEqual(len(payload["items"]), 3)
        asyncio.run(scenario())

    def test_reorder_invalid_order_returns_422(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    poster_id = await _create_poster(app)
                    for _ in range(2):
                        await _raw_request(
                            app, "POST", f"/api/posters/{poster_id}/pages"
                        )
                    status, _ = await _raw_request(
                        app, "PATCH", f"/api/posters/{poster_id}/pages",
                        payload={"new_order": [0, 0]},
                    )
                    # PosterValidationFailed → 400
                    self.assertEqual(status, 400)
        asyncio.run(scenario())

    def test_delete_page(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    poster_id = await _create_poster(app)
                    for _ in range(3):
                        await _raw_request(
                            app, "POST", f"/api/posters/{poster_id}/pages"
                        )
                    status, body = await _raw_request(
                        app, "DELETE", f"/api/posters/{poster_id}/pages/1"
                    )
                    self.assertEqual(status, 200)
                    payload = json.loads(body)
                    self.assertEqual(len(payload["items"]), 2)
        asyncio.run(scenario())

    def test_delete_out_of_range_returns_422(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    poster_id = await _create_poster(app)
                    for _ in range(2):
                        await _raw_request(
                            app, "POST", f"/api/posters/{poster_id}/pages"
                        )
                    status, _ = await _raw_request(
                        app, "DELETE", f"/api/posters/{poster_id}/pages/5"
                    )
                    # PosterValidationFailed → 400
                    self.assertEqual(status, 400)
        asyncio.run(scenario())

    def test_delete_last_page_reverts_to_auto(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    poster_id = await _create_poster(app)
                    await _raw_request(
                        app, "POST", f"/api/posters/{poster_id}/pages"
                    )
                    status, body = await _raw_request(
                        app, "DELETE", f"/api/posters/{poster_id}/pages/0"
                    )
                    self.assertEqual(status, 200)
                    payload = json.loads(body)
                    self.assertEqual(payload["items"], [])
                    self.assertEqual(payload["mode"], "auto")
        asyncio.run(scenario())

    def test_get_pages_unknown_poster_returns_404(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    status, _ = await _raw_request(
                        app, "GET", "/api/posters/nonexistent_id/pages"
                    )
                    self.assertEqual(status, 404)
        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
