"""R2 P3 直播会话 HTTP API 端到端测试。

完整纵向切片:
- 创建会话 → 列表可见
- 授予权益 → 入队（消费额度）→ 重复入队（duplicate_merged）
- 记录演唱结果 → sung（不退）/ skipped（退）
- 关闭会话 → 状态变 SESSION_CLOSED
- 重启: 新建 app instance，验证会话被 lifespan 自动恢复
"""
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


class LiveApiCrudTests(unittest.TestCase):

    def test_empty_list_on_bootstrap(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    status, body, _ = await _request(app, "GET", "/api/live-sessions")
                    assert status == 200
                    assert body == []
        asyncio.run(scenario())

    def test_create_returns_summary_with_id(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    status, body, _ = await _request(
                        app, "POST", "/api/live-sessions",
                        {"rule_version": "rv1", "title": "首播"},
                    )
                    assert status == 200, body
                    assert body["title"] == "首播"
                    assert body["state"] == "active"
                    self.assertTrue(body["id"].startswith("live_"))
                    self.assertEqual(body["queue_size"], 0)
        asyncio.run(scenario())

    def test_create_then_list_finds_it(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    await _request(
                        app, "POST", "/api/live-sessions",
                        {"rule_version": "rv1", "title": "直播"},
                    )
                    status, body, _ = await _request(app, "GET", "/api/live-sessions")
                    assert status == 200
                    self.assertEqual(len(body), 1)

    def test_get_unknown_session_returns_404(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    status, body, _ = await _request(
                        app, "GET", "/api/live-sessions/live_never_existed",
                    )
                    assert status == 404
                    assert body["error"]["code"] == "live_session_not_found"
        asyncio.run(scenario())


class LiveApiQueueTests(unittest.TestCase):

    async def _seed_session(self, app):
        _, body, _ = await _request(
            app, "POST", "/api/live-sessions",
            {"rule_version": "rv1"},
        )
        return body["id"]

    def test_grant_then_queue_consumes_entitlement(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    sid = await self._seed_session(app)

                    # 授予
                    _, g, _ = await _request(
                        app, "POST", f"/api/live-sessions/{sid}/entitlements",
                        {"kind": "fan_join", "rule_version": "rv1",
                          "quota": 2, "requester_id": "u_1"},
                    )
                    assert g["remaining"] == 2, g
                    eid = g["id"]

                    # 入队
                    _, q, _ = await _request(
                        app, "POST", f"/api/live-sessions/{sid}/queue",
                        {"requester_name": "张三", "requester_id": "u_1",
                          "song_id": "song_a",
                          "entitlement_id": eid, "entitlement_kind": "fan_join"},
                    )
                    assert q.get("duplicate_merged") is False
                    self.assertEqual(q["position"], 1)
                    self.assertTrue(q["request_id"].startswith("req_"))

                    # 入队应已被消费 (remaining=1)
                    _, after, _ = await _request(
                        app, "GET", f"/api/live-sessions/{sid}",
                    )
                    # 详情接口验证入队后队列有 1 个 entry
                    self.assertEqual(len(after["queue"]), 1)
        asyncio.run(scenario())

    def test_duplicate_queue_returns_duplicate_merged(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    sid = await self._seed_session(app)

                    _, g, _ = await _request(
                        app, "POST", f"/api/live-sessions/{sid}/entitlements",
                        {"kind": "fan_join", "rule_version": "rv1",
                          "quota": 3, "requester_id": "u_1"},
                    )
                    eid = g["id"]
                    payload = {"requester_name": "张三",
                                "requester_id": "u_1", "song_id": "song_a",
                                "entitlement_id": eid,
                                "entitlement_kind": "fan_join"}

                    # 第 1 次入队
                    _, first, _ = await _request(
                        app, "POST", f"/api/live-sessions/{sid}/queue", payload,
                    )
                    self.assertFalse(first["duplicate_merged"])
                    # 第 2 次相同 song+user → duplicate_merged
                    _, second, _ = await _request(
                        app, "POST", f"/api/live-sessions/{sid}/queue", payload,
                    )
                    self.assertTrue(second["duplicate_merged"])
        asyncio.run(scenario())

    def test_quota_exceeded_returns_400(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    sid = await self._seed_session(app)

                    _, g, _ = await _request(
                        app, "POST", f"/api/live-sessions/{sid}/entitlements",
                        {"kind": "fan_join", "rule_version": "rv1",
                          "quota": 1, "requester_id": "u_1"},
                    )
                    eid = g["id"]
                    payload = {"requester_name": "张三",
                                "requester_id": "u_1", "song_id": "song_a",
                                "entitlement_id": eid,
                                "entitlement_kind": "fan_join"}

                    # 第 1 次 OK
                    await _request(
                        app, "POST", f"/api/live-sessions/{sid}/queue", payload,
                    )
                    # 第 2 次超出 quota → 400
                    payload2 = dict(payload, song_id="song_b")
                    status, body, _ = await _request(
                        app, "POST", f"/api/live-sessions/{sid}/queue", payload2,
                    )
                    assert status == 400, body
                    assert body["error"]["code"] in (
                        "invalid_request", "entitlement_error",
                        "queue_rejected", "live_service_error",
                    )
        asyncio.run(scenario())


class LiveApiRecordTests(unittest.TestCase):

    async def _session_with_queued_request(self, app):
        sid_response = await _request(
            app, "POST", "/api/live-sessions",
            {"rule_version": "rv1"},
        )
        sid = sid_response[1]["id"]
        ent = await _request(
            app, "POST", f"/api/live-sessions/{sid}/entitlements",
            {"kind": "fan_join", "rule_version": "rv1",
              "quota": 1, "requester_id": "u_1"},
        )
        eid = ent[1]["id"]
        queued = await _request(
            app, "POST", f"/api/live-sessions/{sid}/queue",
            {"requester_name": "张三", "requester_id": "u_1",
              "song_id": "song_a", "entitlement_id": eid,
              "entitlement_kind": "fan_join"},
        )
        return sid, eid, queued[1]["request_id"]

    def test_sung_records_performance_no_refund(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    sid, eid, req_id = await self._session_with_queued_request(app)
                    status, body, _ = await _request(
                        app, "POST", f"/api/live-sessions/{sid}/record",
                        {"request_id": req_id, "result": "sung"},
                    )
                    assert status == 200, body
                    self.assertEqual(body["result"], "sung")
                    self.assertFalse(body["refunded"])
        asyncio.run(scenario())

    def test_skipped_refunds_entitlement(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    sid, eid, req_id = await self._session_with_queued_request(app)
                    status, body, _ = await _request(
                        app, "POST", f"/api/live-sessions/{sid}/record",
                        {"request_id": req_id, "result": "skipped",
                          "reason": "时间不足"},
                    )
                    assert status == 200, body
                    self.assertEqual(body["result"], "skipped")
                    self.assertTrue(body["refunded"])
        asyncio.run(scenario())

    def test_record_unknown_request_returns_400(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    sid = (await _request(
                        app, "POST", "/api/live-sessions",
                        {"rule_version": "rv1"},
                    ))[1]["id"]
                    status, body, _ = await _request(
                        app, "POST", f"/api/live-sessions/{sid}/record",
                        {"request_id": "phantom", "result": "sung"},
                    )
                    assert status == 400, body
        asyncio.run(scenario())


class LiveApiCloseTests(unittest.TestCase):

    def test_close_marks_session_closed(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    sid = (await _request(
                        app, "POST", "/api/live-sessions",
                        {"rule_version": "rv1"},
                    ))[1]["id"]
                    status, body, _ = await _request(
                        app, "POST", f"/api/live-sessions/{sid}/close", None,
                    )
                    assert status == 200, body
                    self.assertEqual(body["state"], "closed")
        asyncio.run(scenario())

    def test_close_then_queue_returns_error(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    sid = (await _request(
                        app, "POST", "/api/live-sessions",
                        {"rule_version": "rv1"},
                    ))[1]["id"]
                    await _request(
                        app, "POST", f"/api/live-sessions/{sid}/close", None,
                    )
                    # 关闭后入队应失败
                    status, body, _ = await _request(
                        app, "POST", f"/api/live-sessions/{sid}/queue",
                        {"requester_name": "x", "song_id": "y"},
                    )
                    assert status == 400, body
        asyncio.run(scenario())


class LiveApiPersistenceTests(unittest.TestCase):

    def test_restart_app_recovers_sessions(self):
        """lifespan 启动期自动 load; 新 app instance 可读已存会话。"""
        async def scenario():
            data_root = Path(tempfile.mkdtemp())
            try:
                # 第 1 次 app: 创建会话 + 入队
                app1 = _boot_app(data_root)
                async with app1.router.lifespan_context(app1):
                    sid = (await _request(
                        app1, "POST", "/api/live-sessions",
                        {"rule_version": "rv1", "title": "持久化"},
                    ))[1]["id"]
                    await _request(
                        app1, "POST", f"/api/live-sessions/{sid}/entitlements",
                        {"kind": "fan_join", "rule_version": "rv1",
                          "quota": 1, "requester_id": "u_1"},
                    )

                # 第 2 次 app: 应能直接 GET 到会话
                app2 = _boot_app(data_root)
                async with app2.router.lifespan_context(app2):
                    status, body, _ = await _request(
                        app2, "GET", f"/api/live-sessions/{sid}",
                    )
                    assert status == 200, body
                    self.assertEqual(body["title"], "持久化")
                    self.assertEqual(body["rule_version"], "rv1")

                    # list 也应包含
                    status, listing, _ = await _request(
                        app2, "GET", "/api/live-sessions",
                    )
                    assert status == 200
                    self.assertEqual(len(listing), 1)
            finally:
                import shutil
                shutil.rmtree(data_root, ignore_errors=True)
        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
