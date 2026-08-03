"""L2.2 批量按 ID 导出（/api/export/by-ids）端到端测试。

覆盖：
- 成功：N 首 active 歌曲 → N 张 PNG 文件落盘，文件名含 title slug
- song_ids 顺序保留（按 song_ids 列表顺序，不是按曲库顺序）
- 找不到的 song_id 静默跳过（不报错）
- 主题不存在 → 404 theme_not_found
- 输出目录不存在时自动创建
- 响应结构：total / total_ms / files[]
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
    return create_app(AppConfig(PROJECT_ROOT, mode="test", data_root=data_root))


async def _raw_request(app, method: str, path: str, payload: dict | None = None,
                       headers: dict | None = None):
    target = urlsplit(path)
    body = (json.dumps(payload, ensure_ascii=False).encode("utf-8")
            if payload is not None else b"")
    sent = False
    messages: list = []

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    try:
        await app({
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": method, "scheme": "http", "path": target.path,
            "raw_path": target.path.encode(),
            "query_string": target.query.encode(),
            "headers": [
                (key.lower().encode(), value.encode())
                for key, value in ({"content-type": "application/json"} | (headers or {})).items()
            ],
            "client": ("test", 1), "server": ("test", 80),
        }, receive, send)
    except Exception:
        if not any(message["type"] == "http.response.start" for message in messages):
            raise

    status = next(message["status"] for message in messages
                  if message["type"] == "http.response.start")
    response_start = next(message for message in messages
                          if message["type"] == "http.response.start")
    headers_dict = {k.decode("ascii").lower(): v.decode("ascii")
                    for k, v in response_start.get("headers", [])}
    body_chunks = [bytes(message.get("body", b""))
                   for message in messages if message["type"] == "http.response.body"]
    return status, b"".join(body_chunks), headers_dict


def _seed_library(context) -> None:
    """注入 3 首 active 歌曲 + 1 首 draft（draft 不参与按 ID 导出）。"""
    import json as _json
    songs_path = context.paths.songs_json
    payload = {
        "version": 8,  # CURRENT_VERSION
        "songs": [
            {"id": "song_a", "title": "晴天", "artists": ["周杰伦"], "lyricist": "",
             "composer": "", "key": "C", "capo": 0, "difficulty": "中等", "tabs": "",
             "status": "active", "tags": [], "pinyin": "qing tian", "added_at": "",
             "notes": "", "learned_at": "", "tab_files": [], "section": 1,
             "lyrics_lrc": "", "lyrics_plain": "",
             "audio_vocal_path": None, "audio_instrumental_path": None,
             "audio_duration_ms": 0, "deleted_at": None,
             "capo_options": [], "capo_default": 0},
            {"id": "song_b", "title": "夜曲", "artists": ["周杰伦"], "lyricist": "",
             "composer": "", "key": "G", "capo": 0, "difficulty": "中等", "tabs": "",
             "status": "active", "tags": [], "pinyin": "ye qu", "added_at": "",
             "notes": "", "learned_at": "", "tab_files": [], "section": 1,
             "lyrics_lrc": "", "lyrics_plain": "",
             "audio_vocal_path": None, "audio_instrumental_path": None,
             "audio_duration_ms": 0, "deleted_at": None,
             "capo_options": [], "capo_default": 0},
            {"id": "song_c", "title": "稻香", "artists": ["周杰伦"], "lyricist": "",
             "composer": "", "key": "D", "capo": 0, "difficulty": "简单", "tabs": "",
             "status": "active", "tags": [], "pinyin": "dao xiang", "added_at": "",
             "notes": "", "learned_at": "", "tab_files": [], "section": 1,
             "lyrics_lrc": "", "lyrics_plain": "",
             "audio_vocal_path": None, "audio_instrumental_path": None,
             "audio_duration_ms": 0, "deleted_at": None,
             "capo_options": [], "capo_default": 0},
            {"id": "song_draft", "title": "未发布的歌", "artists": [], "lyricist": "",
             "composer": "", "key": "", "capo": 0, "difficulty": "", "tabs": "",
             "status": "draft", "tags": [], "pinyin": "", "added_at": "",
             "notes": "", "learned_at": "", "tab_files": [], "section": 1,
             "lyrics_lrc": "", "lyrics_plain": "",
             "audio_vocal_path": None, "audio_instrumental_path": None,
             "audio_duration_ms": 0, "deleted_at": None,
             "capo_options": [], "capo_default": 0},
        ],
    }
    context.paths.songs_json.parent.mkdir(parents=True, exist_ok=True)
    context.paths.songs_json.write_text(_json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _set_output_dir(context, output_dir: Path) -> None:
    settings = context.settings_repository.load()
    new_value = {**settings.value, "output_dir": str(output_dir)}
    context.settings_repository.save(new_value, expected_revision=settings.revision)


class ExportByIdsTests(unittest.TestCase):
    def test_basic_three_songs(self):
        """3 首 active 歌曲：导出 3 张 PNG，文件名含 title slug + song_id。"""
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    context = app.state.context
                    _seed_library(context)
                    output_dir = Path(raw) / "out"
                    _set_output_dir(context, output_dir)
                    status, body, _ = await _raw_request(
                        app, "POST", "/api/export/by-ids",
                        {"theme": "海洋柔光", "song_ids": ["song_a", "song_b", "song_c"],
                         "layout": "grid-wrap", "canvas": "标准 9:16", "avoid": True},
                    )
                    self.assertEqual(status, 200, body)
                    payload = json.loads(body)
                    self.assertEqual(payload["ok"], True)
                    self.assertEqual(payload["total"], 3)
                    self.assertEqual(len(payload["files"]), 3)
                    # 顺序按 song_ids 列表
                    self.assertEqual(payload["files"][0]["song_id"], "song_a")
                    self.assertEqual(payload["files"][1]["song_id"], "song_b")
                    self.assertEqual(payload["files"][2]["song_id"], "song_c")
                    # 文件实际写盘
                    for f in payload["files"]:
                        p = Path(f["path"])
                        self.assertTrue(p.exists(), f"missing: {p}")
                        self.assertGreater(p.stat().st_size, 100)  # PNG 不是空
                    # 文件名规范
                    self.assertIn("晴天", payload["files"][0]["filename"])
                    self.assertTrue(payload["files"][0]["filename"].endswith("song_a.png"))
        asyncio.run(scenario())

    def test_unknown_song_id_silently_skipped(self):
        """不存在的 song_id 静默跳过（不报错，total 减少）。"""
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    context = app.state.context
                    _seed_library(context)
                    output_dir = Path(raw) / "out"
                    _set_output_dir(context, output_dir)
                    status, body, _ = await _raw_request(
                        app, "POST", "/api/export/by-ids",
                        {"theme": "海洋柔光",
                         "song_ids": ["song_a", "song_does_not_exist", "song_b"]},
                    )
                    self.assertEqual(status, 200, body)
                    payload = json.loads(body)
                    self.assertEqual(payload["total"], 2)
                    ids = {f["song_id"] for f in payload["files"]}
                    self.assertEqual(ids, {"song_a", "song_b"})
        asyncio.run(scenario())

    def test_draft_song_excluded(self):
        """draft 歌曲不在按 ID 导出范围（只能导 active）。"""
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    context = app.state.context
                    _seed_library(context)
                    output_dir = Path(raw) / "out"
                    _set_output_dir(context, output_dir)
                    status, body, _ = await _raw_request(
                        app, "POST", "/api/export/by-ids",
                        {"theme": "海洋柔光", "song_ids": ["song_draft"]},
                    )
                    self.assertEqual(status, 200, body)
                    payload = json.loads(body)
                    self.assertEqual(payload["total"], 0)
                    self.assertEqual(payload["files"], [])
        asyncio.run(scenario())

    def test_theme_not_found_returns_404(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    context = app.state.context
                    _seed_library(context)
                    output_dir = Path(raw) / "out"
                    _set_output_dir(context, output_dir)
                    status, body, _ = await _raw_request(
                        app, "POST", "/api/export/by-ids",
                        {"theme": "不存在的题材", "song_ids": ["song_a"]},
                    )
                    self.assertEqual(status, 404)
                    payload = json.loads(body)
                    self.assertEqual(payload["error"]["code"], "theme_not_found")
        asyncio.run(scenario())

    def test_empty_song_ids_rejected(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    status, body, _ = await _raw_request(
                        app, "POST", "/api/export/by-ids",
                        {"theme": "海洋柔光", "song_ids": []},
                    )
                    self.assertEqual(status, 422)
        asyncio.run(scenario())

    def test_output_dir_created_automatically(self):
        """output_dir 不存在时自动创建（不会因为缺目录失败）。"""
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    context = app.state.context
                    _seed_library(context)
                    output_dir = Path(raw) / "nested" / "deeper" / "out"
                    _set_output_dir(context, output_dir)
                    status, body, _ = await _raw_request(
                        app, "POST", "/api/export/by-ids",
                        {"theme": "海洋柔光", "song_ids": ["song_a"]},
                    )
                    self.assertEqual(status, 200, body)
                    self.assertTrue(output_dir.exists())
                    payload = json.loads(body)
                    self.assertEqual(payload["total"], 1)
        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
