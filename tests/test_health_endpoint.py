"""P0-4b /api/health 端点回归——单一注册 + 轻量探针载荷。

背景：create_app 曾在 include_router(health.router) 之后又手工定义了一个
@app.get("/api/health")（读盘的旧版实现），导致 OpenAPI 生成时出现
"Duplicate Operation ID health_api_health_get" UserWarning，且手工版是
永远匹配不到的死路由。收口为仅保留 health.router 一处。
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.app import create_app  # noqa: E402
from server.config import AppConfig  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _setup_minimal_data_root(td: Path) -> Path:
    td.mkdir(parents=True, exist_ok=True)
    (td / "events.jsonl").touch()
    (td / "settings.json").write_text(
        '{"output_dir":"/tmp","default_canvas":"9:20","default_theme":"海洋柔光",'
        '"font_path":"/tmp/font.ttf","backup_count":0,"render_threads":1,'
        '"schemaVersion":1}', encoding="utf-8")
    (td / "songs.json").write_text(
        '{"schema_version":5,"songs":[]}', encoding="utf-8")
    return td


async def _request(app, method: str, path: str,
                   client: tuple[str, int] = ("127.0.0.1", 1234)):
    """最小 ASGI 请求（与 test_local_security._request 同构）。"""
    target = urlsplit(path)
    messages: list[dict] = []
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    await app(
        {
            "type": "http", "asgi": {"version": "3.0"},
            "http_version": "1.1", "method": method, "scheme": "http",
            "path": target.path, "raw_path": target.path.encode(),
            "query_string": target.query.encode(), "headers": [],
            "client": client, "server": ("127.0.0.1", 8000),
        },
        receive, send,
    )
    start = next(m for m in messages if m["type"] == "http.response.start")
    raw = b"".join(m.get("body", b"") for m in messages
                   if m["type"] == "http.response.body")
    return start["status"], json.loads(raw)


def _make_app(td: str):
    return create_app(AppConfig(
        PROJECT_ROOT, mode="test",
        data_root=_setup_minimal_data_root(Path(td) / "data")))


class HealthEndpointTests(unittest.TestCase):

    def test_openapi_has_single_health_operation(self):
        """/api/health 只注册一次——OpenAPI 生成不产生重复 operationId。"""
        with tempfile.TemporaryDirectory() as td:
            app = _make_app(td)
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                schema = app.openapi()
            dup = [w for w in caught
                   if "Duplicate Operation ID" in str(w.message)]
            self.assertEqual(dup, [])
            self.assertEqual(list(schema["paths"]["/api/health"].keys()), ["get"])
            # ASGI 路由层也只有一条（死路由已移除）
            health_routes = [r for r in app.routes
                             if getattr(r, "path", "") == "/api/health"]
            self.assertEqual(len(health_routes), 1)

    def test_health_probe_payload(self):
        """探针返回 200 + ok/mode 元信息（不读盘、不依赖 context）。"""
        with tempfile.TemporaryDirectory() as td:
            app = _make_app(td)
            status, body = asyncio.run(_request(app, "GET", "/api/health"))
            self.assertEqual(status, 200)
            self.assertTrue(body["ok"])
            self.assertEqual(
                list(body), ["ok", "mode", "session_required", "request_id"])


if __name__ == "__main__":
    unittest.main()
