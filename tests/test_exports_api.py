"""R4.2.3 导出历史（/api/exports/recent）端到端测试。

覆盖：
- 空 events → items=[]
- 3 种 kind（grid-export / live-poster / learning-report）都正确返回
- limit 参数（默认 20、显式、越界 422）
- 兼容 R0-R3 早期事件：缺 kind 字段时按 source 推断
- 兼容未知 source
- 端到端：live.py /poster 和 learning_report.py /poster 写入的事件能被 recent 读到
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
import uuid
from datetime import datetime
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
    """通用 ASGI 请求：返回 (status, body_bytes, headers_dict)。"""
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
        key.decode("ascii"): value.decode("ascii")
        for key, value in response_start.get("headers", [])
    }
    body_chunks = [bytes(message.get("body", b""))
                   for message in messages if message["type"] == "http.response.body"]
    return status, b"".join(body_chunks), response_headers


def _append_event(context, **overrides):
    """直接往 event_store 写一条 poster_exported 事件。"""
    base = {
        "schema_version": 2,
        "event_id": f"evt_{uuid.uuid4().hex}",
        "occurred_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "type": "poster_exported",
        "source": "test-fixture",
        "meta": {"kind": "grid-export", "files": 1, "total_ms": 123.4,
                 "subject": "海洋柔光", "themes": ["海洋柔光"],
                 "output_dir": "/tmp/output"},
    }
    base.update(overrides)
    if "meta" in overrides:
        base["meta"] = {**base["meta"], **overrides["meta"]}
    context.event_store.append(base)
    return base


class ExportsApiTests(unittest.TestCase):

    def test_empty_events_returns_empty_items(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    status, body, _ = await _raw_request(app, "GET", "/api/exports/recent")
                    self.assertEqual(status, 200)
                    payload = json.loads(body)
                    self.assertEqual(payload, {"items": []})
        asyncio.run(scenario())

    def test_three_kinds_are_returned_in_reverse_chronological_order(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    context = app.state.context
                    # 第一条：grid-export
                    _append_event(context, source="export-api",
                                  meta={"kind": "grid-export", "files": 4,
                                        "total_ms": 900.0, "subject": "海洋柔光",
                                        "themes": ["海洋柔光"],
                                        "output_dir": "/tmp/out"})
                    # 第二条：live-poster
                    _append_event(context, source="live-poster-api",
                                  meta={"kind": "live-poster",
                                        "session_id": "live_3e2d21593d914fba",
                                        "title": "周五夜聊",
                                        "filename": "复盘海报-live_3e2d-20260801.png",
                                        "count": 1, "total_ms": 540.0})
                    # 第三条：learning-report
                    _append_event(context, source="learning-report-api",
                                  meta={"kind": "learning-report",
                                        "days": 30, "period_label": "近 30 天",
                                        "filename": "学歌报告-近30天-20260801.png",
                                        "count": 1, "total_ms": 720.0})

                    status, body, _ = await _raw_request(app, "GET", "/api/exports/recent")
                    self.assertEqual(status, 200)
                    items = json.loads(body)["items"]
                    self.assertEqual(len(items), 3)
                    # tail 已按时间倒序（最后写入的在前）
                    self.assertEqual(items[0]["kind"], "learning-report")
                    self.assertEqual(items[1]["kind"], "live-poster")
                    self.assertEqual(items[2]["kind"], "grid-export")
                    # learning-report 字段填充
                    self.assertEqual(items[0]["days"], 30)
                    self.assertEqual(items[0]["period_label"], "近 30 天")
                    self.assertEqual(items[0]["filename"], "学歌报告-近30天-20260801.png")
                    self.assertEqual(items[0]["subject"], "近 30 天")
                    # live-poster 字段填充
                    self.assertEqual(items[1]["session_id"], "live_3e2d21593d914fba")
                    self.assertEqual(items[1]["title"], "周五夜聊")
                    self.assertEqual(items[1]["subject"], "周五夜聊")
                    # grid-export 字段填充
                    self.assertEqual(items[2]["subject"], "海洋柔光")
                    self.assertEqual(items[2]["output_dir"], "/tmp/out")
                    self.assertEqual(items[2]["count"], 4)
        asyncio.run(scenario())

    def test_limit_param_caps_results(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    context = app.state.context
                    for _ in range(7):
                        _append_event(context, source="export-api",
                                      meta={"kind": "grid-export", "files": 1,
                                            "subject": "海洋柔光", "themes": ["海洋柔光"]})
                    status, body, _ = await _raw_request(
                        app, "GET", "/api/exports/recent?limit=3")
                    self.assertEqual(status, 200)
                    items = json.loads(body)["items"]
                    self.assertEqual(len(items), 3)
        asyncio.run(scenario())

    def test_default_limit_is_20(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    context = app.state.context
                    for _ in range(25):
                        _append_event(context, source="export-api",
                                      meta={"kind": "grid-export", "files": 1})
                    status, body, _ = await _raw_request(app, "GET", "/api/exports/recent")
                    self.assertEqual(status, 200)
                    items = json.loads(body)["items"]
                    self.assertEqual(len(items), 20)
        asyncio.run(scenario())

    def test_limit_out_of_range_returns_422(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    # 0 < limit < 1 越界
                    status, _, _ = await _raw_request(
                        app, "GET", "/api/exports/recent?limit=0")
                    self.assertEqual(status, 422)
                    # 100 < limit 越界
                    status, _, _ = await _raw_request(
                        app, "GET", "/api/exports/recent?limit=101")
                    self.assertEqual(status, 422)
        asyncio.run(scenario())

    def test_compat_missing_kind_inferred_from_source(self):
        """R0-R3 早期事件没有 kind 字段；按 source 回退推断。"""
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    context = app.state.context
                    # 写一条没 kind 字段的旧事件
                    _append_event(context, source="export-api", meta={"files": 1})
                    _append_event(context, source="live-poster-api", meta={
                        "session_id": "live_abc", "title": "旧事件", "count": 1})
                    _append_event(context, source="learning-report-api", meta={
                        "days": 7, "period_label": "7天", "count": 1})

                    status, body, _ = await _raw_request(app, "GET", "/api/exports/recent")
                    self.assertEqual(status, 200)
                    items = json.loads(body)["items"]
                    kinds = [item["kind"] for item in items]
                    # 注意：tail 是按时间倒序，所以最后追加的 learning-report 在最前
                    self.assertEqual(kinds, ["learning-report", "live-poster", "grid-export"])
        asyncio.run(scenario())

    def test_compat_unknown_source_marks_kind_unknown(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    context = app.state.context
                    _append_event(context, source="mystery-source", meta={"foo": "bar"})
                    status, body, _ = await _raw_request(app, "GET", "/api/exports/recent")
                    items = json.loads(body)["items"]
                    self.assertEqual(len(items), 1)
                    self.assertEqual(items[0]["kind"], "mystery-source")
        asyncio.run(scenario())

    def test_legacy_grid_event_without_count_uses_files(self):
        """R0-R3 的 grid-export 事件可能没有 count 字段；回退到 files。"""
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    context = app.state.context
                    _append_event(context, source="export-api",
                                  meta={"kind": "grid-export", "files": 9})
                    status, body, _ = await _raw_request(app, "GET", "/api/exports/recent")
                    items = json.loads(body)["items"]
                    self.assertEqual(items[0]["count"], 9)
        asyncio.run(scenario())

    def test_legacy_grid_event_without_themes_falls_back_to_count(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    context = app.state.context
                    _append_event(context, source="export-api",
                                  meta={"kind": "grid-export", "files": 12})
                    status, body, _ = await _raw_request(app, "GET", "/api/exports/recent")
                    items = json.loads(body)["items"]
                    self.assertEqual(items[0]["subject"], "12 张")
        asyncio.run(scenario())

    def test_end_to_end_live_set_poster_writes_event(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    # 创建 session
                    status, body, _ = await _raw_request(
                        app, "POST", "/api/live-sessions",
                        {"rule_version": "rv1", "title": "R4.2.3 端到端"})
                    self.assertEqual(status, 200)
                    sid = json.loads(body)["id"]
                    # 渲染海报
                    status, png, headers = await _raw_request(
                        app, "POST", f"/api/live-sessions/{sid}/poster",
                        {"theme_id": "海洋柔光", "canvas_id": "抖音全屏 9:20"})
                    self.assertEqual(status, 200)
                    self.assertIn("image/png", headers.get("content-type", ""))
                    # recent 端点能读到这条
                    status, body, _ = await _raw_request(app, "GET", "/api/exports/recent")
                    items = json.loads(body)["items"]
                    self.assertEqual(len(items), 1)
                    self.assertEqual(items[0]["kind"], "live-poster")
                    self.assertEqual(items[0]["source"], "live-poster-api")
                    self.assertEqual(items[0]["session_id"], sid)
                    self.assertEqual(items[0]["title"], "R4.2.3 端到端")
                    self.assertEqual(items[0]["count"], 1)
                    self.assertTrue(items[0]["filename"].startswith("复盘海报-"))
                    self.assertTrue(items[0]["filename"].endswith(".png"))
        asyncio.run(scenario())

    def test_end_to_end_learning_report_poster_writes_event(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    # 写一些 practice_logged 事件让 snapshot 有数据
                    context = app.state.context
                    for i in range(3):
                        context.event_store.append({
                            "schema_version": 2,
                            "event_id": f"evt_{uuid.uuid4().hex}",
                            "occurred_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                            "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                            "type": "practice_logged",
                            "source": "test-fixture",
                            "meta": {"minutes": 10 + i},
                        })
                    # 渲染 learning-report 海报
                    status, png, headers = await _raw_request(
                        app, "POST", "/api/learning-report/poster",
                        {"theme_id": "海洋柔光", "canvas_id": "抖音全屏 9:20",
                         "period_label": "近 7 天", "days": 7, "top_n_artists": 5})
                    self.assertEqual(status, 200)
                    self.assertIn("image/png", headers.get("content-type", ""))
                    # recent 端点能读到这条
                    status, body, _ = await _raw_request(app, "GET", "/api/exports/recent")
                    items = json.loads(body)["items"]
                    # 3 条 practice_logged 不会出现在 recent（filter event_type=poster_exported）
                    self.assertEqual(len(items), 1)
                    self.assertEqual(items[0]["kind"], "learning-report")
                    self.assertEqual(items[0]["source"], "learning-report-api")
                    self.assertEqual(items[0]["days"], 7)
                    self.assertEqual(items[0]["period_label"], "近 7 天")
                    self.assertEqual(items[0]["subject"], "近 7 天")
                    self.assertTrue(items[0]["filename"].startswith("学歌报告-"))
        asyncio.run(scenario())
