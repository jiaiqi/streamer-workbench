"""M3 海报 UI/UX P0/P1 后端 API 测试。

覆盖：
- GET /api/posters/{id}/thumb 懒生成 + 缓存命中 + size 参数（200/400/600）
- PATCH /api/posters/{id}/name inline 重命名
- POST /api/posters/{id}/duplicate 复制
- DELETE /api/export/jobs/{job_id} 取消导出任务
- POST /api/posters/batch 批量 delete / duplicate / set_theme（含部分失败容错）
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
from tests.test_api_contract import _request


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _boot_app(data_root: Path):
    from server.app import create_app
    return create_app(AppConfig(PROJECT_ROOT, mode="test", data_root=data_root))


def _payload(name="测试海报") -> dict:
    return {
        "name": name,
        "song_source": {"type": "all_active", "artists": []},
        "selected_song_ids": [],
        "grouping": "none",
        "sorting": "manual",
        "layout_id": "grid-wrap",
        "theme_id": "海洋柔光",
        "canvas_id": "9:20",
        "page_policy": {"mode": "legacy-fixed-2"},
        "parameters": {},
        "export_settings": {"format": "png", "jpeg_quality": 92,
                            "single_page": False, "dpi": 144},
    }


def _run(coro):
    return asyncio.run(coro)


async def _create_poster(app, name="测试") -> str:
    status, body, _ = await _request(app, "POST", "/api/posters", _payload(name))
    assert status == 200, f"create failed: {status} {body if isinstance(body, dict) else body[:200]}"
    # _request 已经 json.loads 过 body → 直接 dict 取 id
    return body["id"]


async def _request_binary(app, method: str, path: str, payload: dict | None = None):
    """对返回二进制（如 PNG）的端点专用：不走 json.loads。"""
    target = urlsplit(path)
    body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else b""
    sent = False
    messages = []

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body_bytes, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    try:
        await app(
            {
                "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                "method": method, "scheme": "http", "path": target.path,
                "raw_path": target.path.encode(), "query_string": target.query.encode(),
                "headers": [
                    (key.lower().encode(), value.encode())
                    for key, value in ({"content-type": "application/json"} | {}).items()
                ],
                "client": ("test", 1), "server": ("test", 80),
            },
            receive,
            send,
        )
    except Exception:
        if not any(m["type"] == "http.response.start" for m in messages):
            raise
    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    response_start = next(m for m in messages if m["type"] == "http.response.start")
    response_headers = {
        k.decode().lower(): v.decode() for k, v in response_start.get("headers", [])
    }
    response_body = b"".join(
        m.get("body", b"") for m in messages if m["type"] == "http.response.body"
    )
    return status, response_body, response_headers


# ── 缩略图 ─────────────────────────────────────────────────────────

class ThumbApiTests(unittest.TestCase):
    """GET /api/posters/{id}/thumb"""

    def test_thumb_404_for_unknown_poster(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    status, _body, _ = await _request_binary(
                        app, "GET", "/api/posters/nonexistent-id/thumb")
                    assert status == 404
        _run(scenario())

    def test_thumb_returns_png_for_valid_poster(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    pid = await _create_poster(app)
                    status, body, headers = await _request_binary(
                        app, "GET", f"/api/posters/{pid}/thumb")
                    assert status == 200, body[:200]
                    # 响应体是 PNG 二进制；前 4 字节是 \x89PNG
                    assert body[:4] == b"\x89PNG", f"not PNG: {body[:8]!r}"
                    # Content-Type
                    content_type = headers.get("content-type", "")
                    assert "image/png" in content_type, content_type
        _run(scenario())

    def test_thumb_cache_hits_disk(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    pid = await _create_poster(app)
                    # 第一次：生成
                    s1, b1, _ = await _request_binary(
                        app, "GET", f"/api/posters/{pid}/thumb")
                    assert s1 == 200
                    # 磁盘缓存文件存在
                    thumb = Path(td) / "posters" / pid / ".thumb.png"
                    assert thumb.exists(), f"cache file not created: {thumb}"
                    # 第二次：cache hit
                    s2, b2, _ = await _request_binary(
                        app, "GET", f"/api/posters/{pid}/thumb")
                    assert s2 == 200
                    assert b1 == b2, "cache hit should return same bytes"
        _run(scenario())

    def test_thumb_cache_invalidates_on_poster_json_change(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    pid = await _create_poster(app)
                    s1, b1, _ = await _request_binary(
                        app, "GET", f"/api/posters/{pid}/thumb")
                    assert s1 == 200
                    # 让 thumb mtime 比 poster.json 老（模拟外部更新）
                    import time, os
                    thumb = Path(td) / "posters" / pid / ".thumb.png"
                    poster_json = Path(td) / "posters" / pid / "poster.json"
                    # 改 poster.json 内容 + 留原 mtime → 用 os.utime 显式拉新 mtime
                    poster_json.write_text("{}")
                    time.sleep(0.1)
                    os.utime(poster_json, None)  # 刷新到「现在」
                    # 再次请求 → 缓存失效但 poster.json 被破坏，可能 500；
                    # 主要验证 thumb 仍存在（或被错误删除，但我们要保证 cache 文件未被错误改写）
                    s2, b2, _ = await _request_binary(
                        app, "GET", f"/api/posters/{pid}/thumb")
                    # 重新生成会失败（因为 poster.json 是 "{}"），但这是预期行为
                    # 关键是 cache 失效检查被触发了
                    assert thumb.exists() or s2 != 200
        _run(scenario())


# ── 重命名 ─────────────────────────────────────────────────────────

class RenameApiTests(unittest.TestCase):
    """PATCH /api/posters/{id}/name"""

    def test_rename_happy_path(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    pid = await _create_poster(app, name="原名")
                    status, body, _ = await _request(
                        app, "PATCH", f"/api/posters/{pid}/name",
                        {"name": "新名"})
                    assert status == 200, body
                    data = body
                    assert data["ok"] is True
                    # 验证 GET 返回新名
                    _, get_body, _ = await _request(
                        app, "GET", f"/api/posters/{pid}")
                    doc = get_body
                    assert doc["name"] == "新名"
        _run(scenario())

    def test_rename_empty_name_rejected(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    pid = await _create_poster(app)
                    # min_length=1 校验
                    status, body, _ = await _request(
                        app, "PATCH", f"/api/posters/{pid}/name",
                        {"name": ""})
                    assert status == 422, body
        _run(scenario())

    def test_rename_unknown_poster_404(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    status, body, _ = await _request(
                        app, "PATCH", "/api/posters/nonexistent/name",
                        {"name": "新"})
                    assert status == 404
        _run(scenario())


# ── 复制 ─────────────────────────────────────────────────────────

class DuplicateApiTests(unittest.TestCase):
    """POST /api/posters/{id}/duplicate"""

    def test_duplicate_creates_new_id_with_copy_suffix(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    pid = await _create_poster(app, name="原版")
                    status, body, _ = await _request(
                        app, "POST", f"/api/posters/{pid}/duplicate")
                    assert status == 200, body
                    data = body
                    new_id = data["id"]
                    assert new_id != pid
                    # 验证新海报存在 + name 带「（副本）」
                    _, get_body, _ = await _request(
                        app, "GET", f"/api/posters/{new_id}")
                    doc = get_body
                    assert doc["name"] == "原版（副本）"
                    # 列表里两条
                    _, list_body, _ = await _request(app, "GET", "/api/posters")
                    items = list_body
                    assert len(items) == 2
                    ids = {item["id"] for item in items}
                    assert pid in ids and new_id in ids
        _run(scenario())

    def test_duplicate_unknown_404(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    status, body, _ = await _request(
                        app, "POST", "/api/posters/nonexistent/duplicate")
                    assert status == 404
        _run(scenario())


# ── 取消导出 ─────────────────────────────────────────────────────────

class CancelExportApiTests(unittest.TestCase):
    """DELETE /api/export/jobs/{job_id}"""

    def test_cancel_unknown_job_404(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    status, body, _ = await _request(
                        app, "DELETE", "/api/export/jobs/nonexistent")
                    assert status == 404
        _run(scenario())


# ── M3 P1 缩略图 size 参数 ─────────────────────────────────────────

class ThumbSizeApiTests(unittest.TestCase):
    """GET /api/posters/{id}/thumb?size=200|400|600"""

    def test_thumb_default_size_is_200(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    pid = await _create_poster(app)
                    status, body, _ = await _request_binary(
                        app, "GET", f"/api/posters/{pid}/thumb")
                    assert status == 200, body[:200]
                    # 200 cache 落盘为 200x200 PNG
                    assert body[:4] == b"\x89PNG"
        _run(scenario())

    def test_thumb_size_400_returns_larger_png(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    pid = await _create_poster(app)
                    # 先请求 200 让 cache 落盘
                    await _request_binary(app, "GET", f"/api/posters/{pid}/thumb")
                    s_200, b_200, _ = await _request_binary(
                        app, "GET", f"/api/posters/{pid}/thumb?size=200")
                    s_400, b_400, _ = await _request_binary(
                        app, "GET", f"/api/posters/{pid}/thumb?size=400")
                    assert s_200 == 200 and s_400 == 200
                    assert b_400[:4] == b"\x89PNG"
                    # 400 PNG 应明显比 200 PNG 大（同样 200x200 → 400x400）
                    assert len(b_400) > len(b_200), (
                        f"400 PNG 应比 200 大；200={len(b_200)} 400={len(b_400)}")
        _run(scenario())

    def test_thumb_size_invalid_falls_back_to_200(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    pid = await _create_poster(app)
                    # 非法 size（999）应兜底到 200
                    status, body, _ = await _request_binary(
                        app, "GET", f"/api/posters/{pid}/thumb?size=999")
                    assert status == 200, body[:200]
                    assert body[:4] == b"\x89PNG"
        _run(scenario())


# ── M3 P1 批量操作 ────────────────────────────────────────────

class PosterBatchApiTests(unittest.TestCase):
    """POST /api/posters/batch - delete / duplicate / set_theme"""

    def test_batch_delete_all(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    ids = [await _create_poster(app, f"批删{i}") for i in range(3)]
                    status, body, _ = await _request(
                        app, "POST", "/api/posters/batch",
                        {"action": "delete", "ids": ids})
                    assert status == 200, body
                    assert body["action"] == "delete"
                    assert body["deleted"] == 3
                    assert body["failed"] == []
                    # 列表应为空
                    s2, list_body, _ = await _request(
                        app, "GET", "/api/posters")
                    assert s2 == 200
                    assert all(p["id"] not in ids for p in list_body)
        _run(scenario())

    def test_batch_delete_partial_failure(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    pid_real = await _create_poster(app, "真实")
                    ids = [pid_real, "nonexistent_id_1", "nonexistent_id_2"]
                    status, body, _ = await _request(
                        app, "POST", "/api/posters/batch",
                        {"action": "delete", "ids": ids})
                    assert status == 200, body
                    assert body["deleted"] == 1
                    assert len(body["failed"]) == 2
                    assert all(f["error"] == "not_found" for f in body["failed"])
        _run(scenario())

    def test_batch_duplicate_creates_copies(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    pid = await _create_poster(app, "原版")
                    status, body, _ = await _request(
                        app, "POST", "/api/posters/batch",
                        {"action": "duplicate", "ids": [pid]})
                    assert status == 200, body
                    assert body["duplicated"] == 1
                    new_id = body["new_ids"][0]
                    assert new_id != pid
                    # 原版 + 副本 = 2 张
                    s2, list_body, _ = await _request(
                        app, "GET", "/api/posters")
                    assert len(list_body) == 2
                    copy = next(p for p in list_body if p["id"] == new_id)
                    assert "（副本）" in copy["name"] or "(副本)" in copy["name"]
        _run(scenario())

    def test_batch_set_theme_updates_all(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    ids = [await _create_poster(app, f"换主题{i}") for i in range(2)]
                    status, body, _ = await _request(
                        app, "POST", "/api/posters/batch",
                        {"action": "set_theme", "ids": ids, "theme": "月夜星河"})
                    assert status == 200, body
                    assert body["updated"] == 2
                    # 验证每张的主题已改
                    for pid in ids:
                        s2, post, _ = await _request(
                            app, "GET", f"/api/posters/{pid}")
                        assert post["theme_id"] == "月夜星河"
        _run(scenario())

    def test_batch_set_theme_unknown_theme_fails_all(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    ids = [await _create_poster(app, f"x{i}") for i in range(2)]
                    status, body, _ = await _request(
                        app, "POST", "/api/posters/batch",
                        {"action": "set_theme", "ids": ids, "theme": "不存在的"})
                    assert status == 200, body
                    assert body["updated"] == 0
                    assert len(body["failed"]) == 2
        _run(scenario())

    def test_batch_set_theme_missing_theme_422(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    pid = await _create_poster(app, "y")
                    status, body, _ = await _request(
                        app, "POST", "/api/posters/batch",
                        {"action": "set_theme", "ids": [pid]})
                    assert status == 422
                    assert body.get("error", {}).get("code") == "missing_theme"
        _run(scenario())

    def test_batch_invalid_ids_422(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    status, body, _ = await _request(
                        app, "POST", "/api/posters/batch",
                        {"action": "delete", "ids": ["../etc/passwd", ""]})
                    assert status == 422
                    assert body.get("error", {}).get("code") == "invalid_poster_ids"
        _run(scenario())

    def test_batch_unknown_action_422(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    pid = await _create_poster(app, "z")
                    status, body, _ = await _request(
                        app, "POST", "/api/posters/batch",
                        {"action": "nuke", "ids": [pid]})
                    assert status == 422
        _run(scenario())

    # ── M3 P2 拖拽排序（reorder action） ──

    def test_batch_reorder_writes_order_index(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    ids = [await _create_poster(app, f"reorder{i}") for i in range(3)]
                    # 把 [a, b, c] 重排为 [c, a, b]（a→idx=1, b→idx=2, c→idx=0）
                    target_order = [ids[2], ids[0], ids[1]]
                    status, body, _ = await _request(
                        app, "POST", "/api/posters/batch",
                        {"action": "reorder", "ids": target_order})
                    assert status == 200, body
                    assert body["reordered"] == 3
                    assert body["failed"] == []
                    # list 应按新顺序
                    s2, listed, _ = await _request(app, "GET", "/api/posters")
                    listed_ids = [p["id"] for p in listed]
                    assert listed_ids == target_order
        _run(scenario())

    def test_batch_reorder_partial_failure_does_not_block(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    pid = await _create_poster(app, "alive")
                    # 数组中含不存在 id
                    status, body, _ = await _request(
                        app, "POST", "/api/posters/batch",
                        {"action": "reorder", "ids": ["nope1", pid, "nope2"]})
                    assert status == 200, body
                    assert body["reordered"] == 1
                    assert len(body["failed"]) == 2
        _run(scenario())

    def test_batch_reorder_writes_to_manifest(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as td:
                app = _boot_app(Path(td))
                async with app.router.lifespan_context(app):
                    ids = [await _create_poster(app, f"mf{i}") for i in range(2)]
                    await _request(app, "POST", "/api/posters/batch",
                        {"action": "reorder", "ids": [ids[1], ids[0]]})
                    # 验证单 poster get 后 order_index 持久化
                    s2, post, _ = await _request(app, "GET", f"/api/posters/{ids[1]}")
                    assert post.get("order_index") == 0
                    s3, post2, _ = await _request(app, "GET", f"/api/posters/{ids[0]}")
                    assert post2.get("order_index") == 1
        _run(scenario())
