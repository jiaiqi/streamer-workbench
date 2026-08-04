"""M2.4 点歌条件 HTTP 端到端测试。

测试场景：
- GET /api/live-sessions/{id}/policy 返回当前 RequestPolicy
- POST /api/live-sessions/{id}/policy 改 cooldown / max_queue / per_song / per_user
- 改后 rule_version bump（如果值变了）
- 改后入队触发 M2.4 拒绝（4xx + queue_rejected）
- 浏览器模式（无 server）：不阻塞本地调用
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.config import AppConfig


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _boot_app(data_root: Path):
    from server.app import create_app
    return create_app(AppConfig(PROJECT_ROOT, mode="test", data_root=data_root))


async def _raw_request(app, method, path, payload=None, headers=None):
    """通用 ASGI 请求：返回 (status, body_bytes, response_headers_dict)。"""
    from starlette.types import Scope  # noqa: F401
    import asyncio
    from urllib.parse import urlsplit
    from io import BytesIO

    url = urlsplit(path)
    raw_body = b"" if payload is None else json.dumps(payload).encode()

    # 找匹配的 route
    scope = {
        "type": "http",
        "method": method,
        "path": url.path,
        "query_string": (url.query or "").encode(),
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
    }
    sent = []
    body_chunks = []

    async def receive():
        if not sent:
            sent.append(True)
            return {"type": "http.request", "body": raw_body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            status["code"] = message["status"]
            status["headers"] = list(message.get("headers", []))
        elif message["type"] == "http.response.body":
            body_chunks.append(message.get("body", b""))

    status = {"code": 0, "headers": []}
    await app(scope, receive, send)
    return status["code"], b"".join(body_chunks), dict(
        (k.decode().lower(), v.decode()) for k, v in status["headers"]
    )


def _parse_json(body: bytes) -> dict:
    return json.loads(body.decode())


class M24PolicyApiTests(unittest.TestCase):
    """用 asyncio.run 包裹，每个测试独立 lifespan。"""

    def _run(self, coro):
        import asyncio
        return asyncio.run(coro)

    def _with_app(self, scenario_coro):
        import asyncio
        async def wrapper():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    # 把 app 注入 self 闭包
                    return await scenario_coro(app)
        return asyncio.run(wrapper())

    async def _create_session(self, app, title: str = "M2.4 测试场") -> str:
        code, body, _ = await _raw_request(
            app, "POST", "/api/live-sessions",
            payload={"title": title, "rule_version": "rv1"},
        )
        self.assertEqual(code, 200, body)
        return _parse_json(body)["id"]

    async def _get_policy(self, app, session_id: str) -> tuple[int, dict]:
        code, body, _ = await _raw_request(
            app, "GET", f"/api/live-sessions/{session_id}/policy",
        )
        return code, _parse_json(body) if code == 200 else {}

    async def _update_policy(self, app, session_id: str, payload: dict) -> tuple[int, dict]:
        code, body, _ = await _raw_request(
            app, "POST", f"/api/live-sessions/{session_id}/policy",
            payload=payload,
        )
        return code, _parse_json(body) if code < 500 else {}

    async def _queue(self, app, session_id: str, requester_name: str, song_id: str,
                    requester_id: str | None = None) -> tuple[int, dict]:
        payload = {"requester_name": requester_name, "song_id": song_id}
        if requester_id:
            payload["requester_id"] = requester_id
        code, body, _ = await _raw_request(
            app, "POST", f"/api/live-sessions/{session_id}/queue",
            payload=payload,
        )
        try:
            return code, _parse_json(body)
        except Exception:
            return code, {"_raw": body[:200].decode(errors="replace")}

    async def _scenario_get_policy_returns_default(self, app):
        sid = await self._create_session(app)
        code, policy = await self._get_policy(app, sid)
        self.assertEqual(code, 200)
        self.assertEqual(policy["cooldown_seconds_per_user"], 0)
        self.assertEqual(policy["max_queue_length"], 0)
        self.assertEqual(policy["per_song_max_per_session"], 0)
        self.assertEqual(policy["per_user_max_in_queue"], 0)
        self.assertIn("rule_version", policy)

    def test_get_policy_returns_default(self):
        self._with_app(self._scenario_get_policy_returns_default)

    async def _scenario_get_policy_404(self, app):
        code, _ = await self._get_policy(app, "no_such_session")
        self.assertEqual(code, 404)

    def test_get_policy_404(self):
        self._with_app(self._scenario_get_policy_404)

    async def _scenario_update_policy_bumps_version(self, app):
        sid = await self._create_session(app)
        _, before = await self._get_policy(app, sid)
        code, after = await self._update_policy(app, sid, {
            "cooldown_seconds_per_user": 30,
            "max_queue_length": 5,
            "per_song_max_per_session": 2,
            "per_user_max_in_queue": 3,
        })
        self.assertEqual(code, 200, after)
        self.assertNotEqual(before["rule_version"], after["rule_version"])
        self.assertEqual(after["cooldown_seconds_per_user"], 30)
        self.assertEqual(after["max_queue_length"], 5)

    def test_update_policy_bumps_version(self):
        self._with_app(self._scenario_update_policy_bumps_version)

    async def _scenario_update_policy_same_no_bump(self, app):
        sid = await self._create_session(app)
        _, before = await self._get_policy(app, sid)
        code, after = await self._update_policy(app, sid, {
            "cooldown_seconds_per_user": 0,
            "max_queue_length": 0,
            "per_song_max_per_session": 0,
            "per_user_max_in_queue": 0,
        })
        self.assertEqual(code, 200)
        self.assertEqual(before["rule_version"], after["rule_version"])

    def test_update_policy_same_no_bump(self):
        self._with_app(self._scenario_update_policy_same_no_bump)

    async def _scenario_update_policy_rejects_negative(self, app):
        sid = await self._create_session(app)
        code, body = await self._update_policy(app, sid, {
            "cooldown_seconds_per_user": -1,
        })
        # Pydantic 自动校验（ge=0）→ 422
        self.assertIn(code, (400, 422))

    def test_update_policy_rejects_negative(self):
        self._with_app(self._scenario_update_policy_rejects_negative)

    async def _scenario_max_queue_length_policy_set(self, app):
        """policy 字段可设置并可被 GET 读回。

        注：4 检查在 queue 决策的 LiveService 内部触发，HTTP 端点无法直接绕过
        R2 的"空 kind=手动加"语义来 e2e 触发；这块覆盖在 test_live_service.M24LiveServiceIntegrationTests。
        """
        sid = await self._create_session(app)
        code, body = await self._update_policy(app, sid, {"max_queue_length": 3})
        self.assertEqual(code, 200)
        self.assertEqual(body["max_queue_length"], 3)
        code2, body2 = await self._get_policy(app, sid)
        self.assertEqual(code2, 200)
        self.assertEqual(body2["max_queue_length"], 3)

    def test_max_queue_length_policy_set(self):
        self._with_app(self._scenario_max_queue_length_policy_set)

    async def _scenario_per_song_max_policy_set(self, app):
        sid = await self._create_session(app)
        code, body = await self._update_policy(app, sid, {"per_song_max_per_session": 2})
        self.assertEqual(code, 200)
        self.assertEqual(body["per_song_max_per_session"], 2)
        code2, body2 = await self._get_policy(app, sid)
        self.assertEqual(code2, 200)
        self.assertEqual(body2["per_song_max_per_session"], 2)

    def test_per_song_max_policy_set(self):
        self._with_app(self._scenario_per_song_max_policy_set)

    async def _scenario_per_user_max_policy_set(self, app):
        sid = await self._create_session(app)
        code, body = await self._update_policy(app, sid, {"per_user_max_in_queue": 3})
        self.assertEqual(code, 200)
        self.assertEqual(body["per_user_max_in_queue"], 3)
        code2, body2 = await self._get_policy(app, sid)
        self.assertEqual(code2, 200)
        self.assertEqual(body2["per_user_max_in_queue"], 3)

    def test_per_user_max_policy_set(self):
        self._with_app(self._scenario_per_user_max_policy_set)


if __name__ == "__main__":
    unittest.main()
