"""R1a.1 Poster HTTP API 测试——通过 ASGI 直接驱动，记录 happy path 与拒绝路径。"""
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


async def _scenario(coro):
    return await coro


class PosterApiCrudTests(unittest.TestCase):

    def test_post_create_then_list_then_get(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    # 创建
                    status, body, _ = await _request(
                        app, "POST", "/api/posters", _payload("第一张"),
                    )
                    assert status == 200, body
                    assert body["ok"] is True
                    created_id = body["id"]
                    assert created_id.startswith("poster_")

                    # 列表
                    status, body, _ = await _request(app, "GET", "/api/posters")
                    assert status == 200
                    assert any(item["id"] == created_id for item in body)
                    summary = next(item for item in body if item["id"] == created_id)
                    assert summary["name"] == "第一张"
                    assert summary["theme_id"] == "海洋柔光"
                    assert summary["song_count"] == 0

                    # 读取
                    status, body, _ = await _request(
                        app, "GET", f"/api/posters/{created_id}",
                    )
                    assert status == 200
                    assert body["id"] == created_id
                    assert body["layout_id"] == "grid-wrap"
                    assert body["page_policy"]["mode"] == "legacy-fixed-2"
        asyncio.run(scenario())

    def test_post_update_overwrites(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    status, body, _ = await _request(
                        app, "POST", "/api/posters", _payload("原名"),
                    )
                    pid = body["id"]
                    rev = body["revision"]

                    # 用同一 id 改 name
                    p2 = _payload("改名了")
                    p2["id"] = pid
                    status, body, _ = await _request(
                        app, "POST", "/api/posters", p2,
                    )
                    assert status == 200
                    assert body["id"] == pid
                    assert body["revision"] != rev

                    # 读取确认
                    status, body, _ = await _request(
                        app, "GET", f"/api/posters/{pid}",
                    )
                    assert body["name"] == "改名了"
        asyncio.run(scenario())

    def test_delete_marks_soft_deleted(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    status, body, _ = await _request(
                        app, "POST", "/api/posters", _payload(),
                    )
                    pid = body["id"]

                    status, body, _ = await _request(
                        app, "DELETE", f"/api/posters/{pid}",
                    )
                    assert status == 200
                    assert body["ok"] is True

                    # 再读：返回 404
                    status, body, _ = await _request(
                        app, "GET", f"/api/posters/{pid}",
                    )
                    assert status == 404
                    assert body["error"]["code"] == "poster_not_found"
        asyncio.run(scenario())


class PosterApiValidationTests(unittest.TestCase):
    """HTTP 层应将 service 校验翻译为 400 invalid_poster。"""

    def test_empty_name_rejected(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    status, body, _ = await _request(
                        app, "POST", "/api/posters", _payload("   "),
                    )
                    assert status == 400
                    assert body["error"]["code"] == "invalid_poster"
        asyncio.run(scenario())

    def test_non_grid_wrap_layout_rejected(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    p = _payload("bad")
                    p["layout_id"] = "magazine-flow"
                    status, body, _ = await _request(
                        app, "POST", "/api/posters", p,
                    )
                    assert status == 400
                    assert "grid-wrap" in body["error"]["message"]
        asyncio.run(scenario())

    def test_non_legacy_fixed_2_rejected(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    p = _payload("bad page")
                    p["page_policy"] = {"mode": "auto", "min_pages": 1}
                    status, body, _ = await _request(
                        app, "POST", "/api/posters", p,
                    )
                    assert status == 400
                    assert "legacy-fixed-2" in body["error"]["message"]
        asyncio.run(scenario())

    def test_invalid_song_id_rejected(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    p = _payload("bad song id")
                    p["selected_song_ids"] = ["not_a_song_id"]
                    status, body, _ = await _request(
                        app, "POST", "/api/posters", p,
                    )
                    assert status == 400
                    assert "song_id" in body["error"]["message"]
        asyncio.run(scenario())

    def test_pydantic_rejects_unknown_extra_field(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    p = _payload("extra")
                    p["future_field"] = "should be rejected"
                    status, _, _ = await _request(
                        app, "POST", "/api/posters", p,
                    )
                    # PosterRequest 默认 ConfigDict extra="forbid"：未知字段返回 422
                    assert status == 422
        asyncio.run(scenario())


class PosterApiResolveTests(unittest.TestCase):

    def test_resolve_returns_songs_for_artist_source(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    p = _payload("林俊杰")
                    p["song_source"] = {"type": "artist", "artists": ["林俊杰"]}
                    # 库中没有歌曲 → 空快照是预期
                    status, body, _ = await _request(
                        app, "POST", "/api/posters", p,
                    )
                    assert status == 200
                    pid = body["id"]

                    status, body, _ = await _request(
                        app, "POST", f"/api/posters/{pid}/resolve", None,
                    )
                    assert status == 200
                    assert body["poster_id"] == pid
                    assert isinstance(body["songs"], list)
                    assert isinstance(body["missing_song_ids"], list)
        asyncio.run(scenario())

    def test_resolve_unknown_poster_returns_404(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    status, body, _ = await _request(
                        app, "POST", "/api/posters/poster_definitely_not_exists/resolve", None,
                    )
                    assert status == 404
                    assert body["error"]["code"] == "poster_not_found"
        asyncio.run(scenario())


class PosterApiPersistenceTests(unittest.TestCase):

    def test_persists_across_app_restart(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                data_root = Path(raw)
                # 第一次 app：创建
                app1 = _boot_app(data_root)
                async with app1.router.lifespan_context(app1):
                    status, body, _ = await _request(
                        app1, "POST", "/api/posters", _payload("持久的海报"),
                    )
                    assert status == 200
                    pid = body["id"]

                # 第二次 app：必须读得到
                app2 = _boot_app(data_root)
                async with app2.router.lifespan_context(app2):
                    status, body, _ = await _request(
                        app2, "GET", f"/api/posters/{pid}",
                    )
                    assert status == 200
                    assert body["name"] == "持久的海报"
        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
