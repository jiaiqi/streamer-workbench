"""P1 R1a.4 RenderDocument API 测试——海报驱动渲染预览。"""
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


def _poster_payload(name="测试", source_type="all_active", song_ids=None):
    return {
        "name": name,
        "song_source": {"type": source_type, "artists": []},
        "selected_song_ids": song_ids or [],
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


class RenderDocumentApiTests(unittest.TestCase):
    """纯线性 async 测试，不嵌套 asyncio.run。"""

    def test_render_document_with_all_active_yields_document_id(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    status, body, _ = await _request(
                        app, "POST", "/api/songs/seed-sample", None,
                    )
                    assert status == 200
                    assert body["active"] >= 10

                    status, body, _ = await _request(
                        app, "POST", "/api/posters", _poster_payload(),
                    )
                    assert status == 200
                    pid = body["id"]

                    payload = {"poster_id": pid, "layout_id": "grid-wrap",
                               "theme_id": "海洋柔光", "canvas_id": "9:20",
                               "page": 1, "parameters": {}}
                    status, body, _ = await _request(
                        app, "POST", "/api/render/document", payload,
                    )
                    assert status == 200, body
                    assert len(body["document_id"]) == 64
                    assert body["poster_id"] == pid
                    assert body["layout_id"] == "grid-wrap"
                    assert body["page_policy_mode"] == "legacy-fixed-2"
                    assert body["song_count"] == 14
                    assert body["pages_total"] == 2
                    assert body["missing_song_ids"] == []
        asyncio.run(scenario())

    def test_document_id_is_stable_for_same_inputs(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    await _request(app, "POST", "/api/songs/seed-sample", None)
                    status, body, _ = await _request(
                        app, "POST", "/api/posters", _poster_payload(),
                    )
                    pid = body["id"]
                    payload = {"poster_id": pid, "layout_id": "grid-wrap",
                               "theme_id": "海洋柔光", "canvas_id": "9:20",
                               "page": 1, "parameters": {}}
                    _, body1, _ = await _request(
                        app, "POST", "/api/render/document", payload,
                    )
                    _, body2, _ = await _request(
                        app, "POST", "/api/render/document", payload,
                    )
                    assert body1["document_id"] == body2["document_id"]
        asyncio.run(scenario())

    def test_unknown_poster_returns_404(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    payload = {"poster_id": "poster_never_existed",
                               "layout_id": "grid-wrap",
                               "theme_id": "海洋柔光", "canvas_id": "9:20",
                               "page": 1, "parameters": {}}
                    status, body, _ = await _request(
                        app, "POST", "/api/render/document", payload,
                    )
                    assert status == 404
                    assert body["error"]["code"] == "poster_not_found"
        asyncio.run(scenario())

    def test_overflow_returns_400(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    # 直接写库注入 60 首 section=1（一字）
                    from core.data.songs import Song, SongLibrary, legacy_song_id
                    songs_json = Path(raw) / "songs.json"
                    lib = SongLibrary()
                    for i in range(60):
                        lib.songs.append(
                            Song(title=f"字{i}", id=legacy_song_id(f"字{i}"),
                                 status="active", section=1),
                        )
                    payload_songs = {
                        "version": 5,
                        "songs": [
                            {"title": s.title, "id": s.id, "artists": [],
                             "lyricist": "", "composer": "", "key": "",
                             "capo": None, "difficulty": "", "tabs": "",
                             "status": s.status, "tags": [], "pinyin": "",
                             "added_at": "", "notes": "", "learned_at": "",
                             "tab_files": [], "section": s.section}
                            for s in lib.songs
                        ],
                    }
                    songs_json.write_text(json.dumps(payload_songs, ensure_ascii=False))
                    status, body, _ = await _request(
                        app, "POST", "/api/posters", _poster_payload(),
                    )
                    pid = body["id"]
                    payload = {"poster_id": pid, "layout_id": "grid-wrap",
                               "theme_id": "海洋柔光", "canvas_id": "9:20",
                               "page": 1, "parameters": {}}
                    status, body, _ = await _request(
                        app, "POST", "/api/render/document", payload,
                    )
                    assert status == 400, body
                    assert body["error"]["code"] == "layout_overflow"
        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
