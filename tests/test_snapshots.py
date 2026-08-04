"""L2.3 快照（/api/songs/snapshots + /api/songs/snapshots/restore）端到端测试。"""
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


async def _raw_request(app, method, path, payload=None, headers=None):
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
        if not any(m["type"] == "http.response.start" for m in messages):
            raise

    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    response_start = next(m for m in messages if m["type"] == "http.response.start")
    headers_dict = {k.decode("ascii").lower(): v.decode("ascii")
                    for k, v in response_start.get("headers", [])}
    body_chunks = [bytes(m.get("body", b"")) for m in messages if m["type"] == "http.response.body"]
    return status, b"".join(body_chunks), headers_dict


def _write_songs_json(data_root, payload):
    songs_path = data_root / "songs.json"
    songs_path.parent.mkdir(parents=True, exist_ok=True)
    songs_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _song(title, **over):
    base = {"id": "song_" + title, "title": title, "artists": [], "lyricist": "", "composer": "",
            "key": "", "capo": 0, "difficulty": "", "tabs": "", "status": "active",
            "tags": [], "pinyin": "", "added_at": "", "notes": "", "learned_at": "",
            "tab_files": [], "section": 1, "lyrics_lrc": "", "lyrics_plain": "",
            "audio_vocal_path": None, "audio_instrumental_path": None,
            "audio_duration_ms": 0, "deleted_at": None,
            "capo_options": [], "capo_default": 0}
    base.update(over)
    return base


class SnapshotTests(unittest.TestCase):
    def test_list_empty_no_backups(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                _write_songs_json(Path(raw), {"version": 5, "songs": [_song("晴天")]})
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    status, body, _ = await _raw_request(app, "GET", "/api/songs/snapshots")
                    self.assertEqual(status, 200, body)
                    payload = json.loads(body)
                    self.assertEqual(payload["total"], 0)
                    self.assertEqual(payload["items"], [])
        asyncio.run(scenario())

    def test_save_creates_snapshot(self):
        """任何 save 都会自动备份到 backups/songs/<filename>.json。"""
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                data_root = Path(raw)
                _write_songs_json(data_root, {"version": 5, "songs": [_song("晴天")]})
                app = _boot_app(data_root)
                async with app.router.lifespan_context(app):
                    ctx = app.state.context
                    # 触发 save（status 切换）
                    status, _, _ = await _raw_request(
                        app, "POST", "/api/songs/status",
                        {"title": "晴天", "status": "draft"})
                    self.assertEqual(status, 200)
                    # 现在 snapshots 列表应该有一个
                    status, body, _ = await _raw_request(app, "GET", "/api/songs/snapshots")
                    self.assertEqual(status, 200)
                    payload = json.loads(body)
                    self.assertGreaterEqual(payload["total"], 1)
                    item = payload["items"][0]
                    self.assertTrue(item["filename"].startswith("songs-"))
                    self.assertTrue(item["filename"].endswith(".json"))
                    self.assertGreater(item["size_bytes"], 0)
        asyncio.run(scenario())

    def test_restore_overwrites_songs_json(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                data_root = Path(raw)
                _write_songs_json(data_root, {"version": 5, "songs": [_song("晴天")]})
                app = _boot_app(data_root)
                async with app.router.lifespan_context(app):
                    # 先做几次 save 来生成 snapshot
                    await _raw_request(app, "POST", "/api/songs/status",
                                       {"title": "晴天", "status": "draft"})
                    await _raw_request(app, "POST", "/api/songs/status",
                                       {"title": "晴天", "status": "active"})
                    # 取最新 snapshot 文件名
                    status, body, _ = await _raw_request(app, "GET", "/api/songs/snapshots")
                    items = json.loads(body)["items"]
                    self.assertGreater(len(items), 0)
                    target_item = items[0]
                    # 模拟：改 songs.json 内容（模拟意外编辑）
                    songs_json = data_root / "songs.json"
                    self.assertTrue(songs_json.exists())
                    original = songs_json.read_text(encoding="utf-8")
                    songs_json.write_text('{"version": 5, "songs": []}', encoding="utf-8")
                    # 恢复
                    status, body, _ = await _raw_request(
                        app, "POST", "/api/songs/snapshots/restore",
                        {"filename": target_item["filename"]})
                    self.assertEqual(status, 200, body)
                    payload = json.loads(body)
                    self.assertEqual(payload["ok"], True)
                    # songs.json 应该被恢复（不一定 == original 因为中间有 save，
                    # 但应该有一个晴天）
                    restored = json.loads(songs_json.read_text(encoding="utf-8"))
                    titles = {s["title"] for s in restored["songs"]}
                    self.assertIn("晴天", titles)
        asyncio.run(scenario())

    def test_restore_missing_snapshot_returns_404(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                _write_songs_json(Path(raw), {"version": 5, "songs": [_song("晴天")]})
                app = _boot_app(Path(raw))
                async with app.router.lifespan_context(app):
                    status, body, _ = await _raw_request(
                        app, "POST", "/api/songs/snapshots/restore",
                        {"filename": "nonexistent.json"})
                    self.assertEqual(status, 404, body)
                    payload = json.loads(body)
                    self.assertEqual(payload["error"]["code"], "snapshot_not_found")
        asyncio.run(scenario())

    def test_list_sorted_descending(self):
        """多个 snapshot 按时间倒序排列。"""
        async def scenario():
            with tempfile.TemporaryDirectory() as raw:
                data_root = Path(raw)
                _write_songs_json(data_root, {"version": 5, "songs": [_song("晴天")]})
                app = _boot_app(data_root)
                async with app.router.lifespan_context(app):
                    # 3 次 save → 3 个 snapshot
                    for i in range(3):
                        status = "draft" if i % 2 == 0 else "active"
                        await _raw_request(app, "POST", "/api/songs/status",
                                           {"title": "晴天", "status": status})
                    status, body, _ = await _raw_request(app, "GET", "/api/songs/snapshots")
                    items = json.loads(body)["items"]
                    self.assertGreaterEqual(len(items), 3)
                    # modified_at 倒序
                    times = [it["modified_at"] for it in items]
                    self.assertEqual(times, sorted(times, reverse=True))
        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
