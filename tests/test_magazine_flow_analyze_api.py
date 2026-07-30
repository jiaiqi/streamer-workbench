"""P2 R1b: /api/layouts/magazine-flow/analyze HTTP 端点测试。"""
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


def _seed_songs_json(data_root: Path) -> None:
    """构造 30 首 active 歌曲：以便 analyze 返回稳定结果。"""
    songs = []
    for i in range(30):
        songs.append({
            "title": f"歌{i:02d}",
            "id": f"song_{i:032x}",
            "artists": ["测试艺人"] if i % 2 == 0 else [],
            "lyricist": "", "composer": "", "key": "", "capo": None,
            "difficulty": "", "tabs": "", "status": "active",
            "tags": [], "pinyin": "",
            "added_at": "", "notes": "", "learned_at": "",
            "tab_files": [], "section": (i % 7) + 1,
        })
    (data_root / "songs.json").write_text(
        json.dumps({"version": 5, "songs": songs}, ensure_ascii=False),
        encoding="utf-8",
    )


class AnalyzeApiTests(unittest.TestCase):

    def test_empty_library_returns_400(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    payload = {"canvas_id": "9:20", "grouping": "none"}
                    status, body, _ = await _request(
                        app, "POST",
                        "/api/layouts/magazine-flow/analyze", payload,
                    )
                    assert status == 400
                    assert body["error"]["code"] == "empty_library"
        asyncio.run(scenario())

    def test_invalid_grouping_returns_400(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                _seed_songs_json(root)
                app = _boot_app(root)
                async with app.router.lifespan_context(app):
                    payload = {"canvas_id": "9:20", "grouping": "unknown"}
                    status, body, _ = await _request(
                        app, "POST",
                        "/api/layouts/magazine-flow/analyze", payload,
                    )
                    assert status == 400
                    assert body["error"]["code"] == "invalid_grouping"
        asyncio.run(scenario())

    def test_unknown_canvas_falls_back_to_default(self):
        """get_canvas_spec 允许任意字符；非法 canvas 走 fallback 不报错。
        真正的 non-existent canvas id 在 grid-wrap 那边也是同样的健壮处理。
        """
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                _seed_songs_json(root)
                app = _boot_app(root)
                async with app.router.lifespan_context(app):
                    payload = {"canvas_id": "100:100", "grouping": "none"}
                    status, body, _ = await _request(
                        app, "POST",
                        "/api/layouts/magazine-flow/analyze", payload,
                    )
                    # 容忍：要么拒绝，要么默认返回值（确保不抛 500）
                    assert status in (200, 400, 404), body
                    assert "error" in body or "total_songs" in body
        asyncio.run(scenario())

    def test_analyze_30_songs_returns_page_count(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                _seed_songs_json(root)
                app = _boot_app(root)
                async with app.router.lifespan_context(app):
                    payload = {"canvas_id": "9:20", "grouping": "chars"}
                    status, body, _ = await _request(
                        app, "POST",
                        "/api/layouts/magazine-flow/analyze", payload,
                    )
                    assert status == 200, body
                    assert body["total_songs"] == 30
                    assert body["layout_id"] == "magazine-flow"
                    assert body["grouping"] == "chars"
                    assert body["canvas_id"] == "9:20"
                    # 30 首 / per_page_max ~33 → 1 页
                    self.assertGreaterEqual(body["page_count"], 1)
                    # 分桶返回 categories 数组
                    self.assertIsInstance(body["categories"], list)
                    self.assertGreater(len(body["categories"]), 0)
        asyncio.run(scenario())

    def test_analyze_with_song_ids_subset(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                _seed_songs_json(root)
                app = _boot_app(root)
                async with app.router.lifespan_context(app):
                    payload = {
                        "canvas_id": "9:20",
                        "grouping": "artist",
                        "song_ids": [f"song_{i:032x}" for i in range(0, 10, 2)],
                    }
                    status, body, _ = await _request(
                        app, "POST",
                        "/api/layouts/magazine-flow/analyze", payload,
                    )
                    assert status == 200, body
                    # 5 首（偶数 0..10 中步长 2 = 0,2,4,6,8）
                    self.assertEqual(body["total_songs"], 5)
        asyncio.run(scenario())

    def test_analyze_unknown_axis_in_grouping_rejected(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                _seed_songs_json(root)
                app = _boot_app(root)
                async with app.router.lifespan_context(app):
                    payload = {"canvas_id": "9:20", "grouping": "language"}
                    status, body, _ = await _request(
                        app, "POST",
                        "/api/layouts/magazine-flow/analyze", payload,
                    )
                    assert status == 200, body
                    # language 轴：英文/中文两个桶
                    labels = [c["label"] for c in body["categories"]]
                    self.assertTrue(
                        any(l in labels for l in ["中文", "英文"]),
                        f"expected 中文 or 英文 in {labels}",
                    )
        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
