"""R8.1 弹唱：音频 HTTP API 端到端测试。

覆盖：
- POST /api/songs/{id}/audio 上传（vocal / instrumental）
- GET /api/songs/{id}/audio/list 列出
- GET /api/songs/{id}/audio/{role} 元信息
- GET /api/songs/{id}/audio/{role}/file 流式
- DELETE /api/songs/{id}/audio 删除
- POST /api/playback/events 事件上报
- 错误路径：超大文件 / 不支持扩展名 / 不存在 song / 非法 role / 非法事件类型
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.config import AppConfig


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _boot_app(data_root: Path):
    from server.app import create_app
    return create_app(AppConfig(PROJECT_ROOT, mode="test", data_root=data_root))


async def _request(app, method: str, path: str, payload: dict | None = None,
                   headers: dict | None = None, files: dict | None = None):
    """通用 ASGI 请求：返回 (status, body_bytes, response_headers_dict)。"""
    target = urlsplit(path)
    # multipart vs json
    if files is not None:
        # 简易 multipart/form-data 构造
        boundary = "----test" + uuid.uuid4().hex
        body = b""
        for key, (filename, data, content_type) in files.items():
            body += f"--{boundary}\r\n".encode()
            body += f'Content-Disposition: form-data; name="{key}"; filename="{filename}"\r\n'.encode()
            body += f"Content-Type: {content_type}\r\n\r\n".encode()
            body += data
            body += b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        body_bytes = body
        ct_header = f"multipart/form-data; boundary={boundary}"
    else:
        body_bytes = (json.dumps(payload, ensure_ascii=False).encode("utf-8")
                      if payload is not None else b"")
        ct_header = "application/json"

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

    request_headers = {"content-type": ct_header}
    if headers:
        request_headers.update(headers)
    try:
        await app(
            {
                "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                "method": method, "scheme": "http", "path": target.path,
                "raw_path": target.path.encode(),
                "query_string": target.query.encode(),
                "headers": [
                    (key.lower().encode(), value.encode())
                    for key, value in request_headers.items()
                ],
                "client": ("test", 1), "server": ("test", 80),
            },
            receive, send,
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


# ── 测试 ──


class AudioApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_root = Path(self.tmp.name) / "data"
        self.addCleanup(self.tmp.cleanup)
        self.app = _boot_app(self.data_root)

    def _seed_song(self, title: str = "测试歌") -> str:
        """在 lifespan 内创建一首种子歌曲，返回 song_id。"""
        async def scenario():
            async with self.app.router.lifespan_context(self.app):
                # POST /api/songs/add 创建歌曲
                status, body, _ = await _request(
                    self.app, "POST", "/api/songs/add",
                    {"title": title, "status": "active",
                     "artists": ["测试"], "key": "C", "capo": 0,
                     "lyrics_lrc": "[00:00.00]前奏\n[00:10.00]第一句"},
                )
                self.assertEqual(status, 200)
                payload = json.loads(body)
                # SongMutationResponse 含 song 字段
                return payload["song"]["id"]
        return asyncio.run(scenario())

    def test_upload_vocal_mp3(self):
        song_id = self._seed_song()
        async def scenario():
            async with self.app.router.lifespan_context(self.app):
                files = {"file": ("vocal.mp3", b"fake-mp3-bytes" * 100, "audio/mpeg")}
                status, body, _ = await _request(
                    self.app, "POST", f"/api/songs/{song_id}/audio?role=vocal",
                    files=files)
                self.assertEqual(status, 200)
                payload = json.loads(body)
                self.assertTrue(payload["ok"])
                self.assertEqual(payload["role"], "vocal")
                self.assertTrue(payload["path"].endswith("vocal.mp3"))
                self.assertIn(song_id, payload["path"])
        asyncio.run(scenario())

    def test_upload_instrumental_m4a(self):
        song_id = self._seed_song()
        async def scenario():
            async with self.app.router.lifespan_context(self.app):
                files = {"file": ("song.m4a", b"fake-m4a", "audio/mp4")}
                status, body, _ = await _request(
                    self.app, "POST", f"/api/songs/{song_id}/audio?role=instrumental",
                    files=files)
                self.assertEqual(status, 200)
                payload = json.loads(body)
                self.assertEqual(payload["role"], "instrumental")
                self.assertTrue(payload["path"].endswith("instrumental.m4a"))
        asyncio.run(scenario())

    def test_upload_writes_song_field(self):
        """上传后 Song.audio_vocal_path 应被回写。"""
        song_id = self._seed_song()
        async def scenario():
            async with self.app.router.lifespan_context(self.app):
                files = {"file": ("v.mp3", b"data", "audio/mpeg")}
                await _request(
                    self.app, "POST",
                    f"/api/songs/{song_id}/audio?role=vocal", files=files)
                # 重新 GET 歌曲（通过 /api/songs/list）
                status, body, _ = await _request(
                    self.app, "GET", "/api/songs/list")
                items = json.loads(body)["songs"]
                song = next(s for s in items if s["id"] == song_id)
                self.assertTrue(song["audio_vocal_path"].endswith("vocal.mp3"))
        asyncio.run(scenario())

    def test_upload_rejects_oversize(self):
        song_id = self._seed_song()
        async def scenario():
            async with self.app.router.lifespan_context(self.app):
                huge = b"x" * (50 * 1024 * 1024 + 1)
                files = {"file": ("v.mp3", huge, "audio/mpeg")}
                status, body, _ = await _request(
                    self.app, "POST", f"/api/songs/{song_id}/audio?role=vocal",
                    files=files)
                self.assertEqual(status, 413)
        asyncio.run(scenario())

    def test_upload_rejects_invalid_role(self):
        song_id = self._seed_song()
        async def scenario():
            async with self.app.router.lifespan_context(self.app):
                files = {"file": ("v.mp3", b"data", "audio/mpeg")}
                status, body, _ = await _request(
                    self.app, "POST",
                    f"/api/songs/{song_id}/audio?role=backing", files=files)
                self.assertEqual(status, 400)
                self.assertEqual(json.loads(body)["error"]["code"],
                                 "invalid_audio_role")
        asyncio.run(scenario())

    def test_upload_rejects_unsupported_ext(self):
        song_id = self._seed_song()
        async def scenario():
            async with self.app.router.lifespan_context(self.app):
                files = {"file": ("v.exe", b"data", "application/exe")}
                status, body, _ = await _request(
                    self.app, "POST", f"/api/songs/{song_id}/audio?role=vocal",
                    files=files)
                self.assertEqual(status, 400)
        asyncio.run(scenario())

    def test_upload_nonexistent_song_returns_404(self):
        async def scenario():
            async with self.app.router.lifespan_context(self.app):
                files = {"file": ("v.mp3", b"data", "audio/mpeg")}
                status, body, _ = await _request(
                    self.app, "POST",
                    f"/api/songs/song_{'a' * 32}/audio?role=vocal",
                    files=files)
                self.assertEqual(status, 404)
        asyncio.run(scenario())

    def test_list_empty(self):
        song_id = self._seed_song()
        async def scenario():
            async with self.app.router.lifespan_context(self.app):
                status, body, _ = await _request(
                    self.app, "GET", f"/api/songs/{song_id}/audio/list")
                self.assertEqual(status, 200)
                payload = json.loads(body)
                self.assertEqual(payload["items"], [])
                self.assertEqual(payload["song_id"], song_id)
        asyncio.run(scenario())

    def test_list_after_upload(self):
        song_id = self._seed_song()
        async def scenario():
            async with self.app.router.lifespan_context(self.app):
                files1 = {"file": ("v.mp3", b"v-data", "audio/mpeg")}
                await _request(
                    self.app, "POST", f"/api/songs/{song_id}/audio?role=vocal",
                    files=files1)
                files2 = {"file": ("i.m4a", b"i-data", "audio/mp4")}
                await _request(
                    self.app, "POST", f"/api/songs/{song_id}/audio?role=instrumental",
                    files=files2)
                # 列出
                status, body, _ = await _request(
                    self.app, "GET", f"/api/songs/{song_id}/audio/list")
                payload = json.loads(body)
                self.assertEqual(len(payload["items"]), 2)
                roles = {item["role"] for item in payload["items"]}
                self.assertEqual(roles, {"vocal", "instrumental"})
                for item in payload["items"]:
                    self.assertIn(item["filename"], {"vocal.mp3", "instrumental.m4a"})
        asyncio.run(scenario())

    def test_audio_info(self):
        song_id = self._seed_song()
        async def scenario():
            async with self.app.router.lifespan_context(self.app):
                files = {"file": ("v.mp3", b"x" * 1024, "audio/mpeg")}
                await _request(
                    self.app, "POST", f"/api/songs/{song_id}/audio?role=vocal",
                    files=files)
                status, body, _ = await _request(
                    self.app, "GET", f"/api/songs/{song_id}/audio/vocal")
                payload = json.loads(body)
                self.assertEqual(payload["role"], "vocal")
                self.assertEqual(payload["size"], 1024)
                self.assertEqual(payload["mime"], "audio/mpeg")
        asyncio.run(scenario())

    def test_audio_info_404_when_no_audio(self):
        song_id = self._seed_song()
        async def scenario():
            async with self.app.router.lifespan_context(self.app):
                status, body, _ = await _request(
                    self.app, "GET", f"/api/songs/{song_id}/audio/vocal")
                self.assertEqual(status, 404)
        asyncio.run(scenario())

    def test_audio_stream_returns_file(self):
        song_id = self._seed_song()
        data = b"this-is-fake-audio-data"
        async def scenario():
            async with self.app.router.lifespan_context(self.app):
                files = {"file": ("v.mp3", data, "audio/mpeg")}
                await _request(
                    self.app, "POST", f"/api/songs/{song_id}/audio?role=vocal",
                    files=files)
                status, body, headers = await _request(
                    self.app, "GET", f"/api/songs/{song_id}/audio/vocal/file")
                self.assertEqual(status, 200)
                self.assertEqual(body, data)
                self.assertIn("audio/", headers.get("content-type", ""))
        asyncio.run(scenario())

    def test_delete_audio(self):
        song_id = self._seed_song()
        async def scenario():
            async with self.app.router.lifespan_context(self.app):
                files = {"file": ("v.mp3", b"x", "audio/mpeg")}
                await _request(
                    self.app, "POST", f"/api/songs/{song_id}/audio?role=vocal",
                    files=files)
                # 删除
                status, body, _ = await _request(
                    self.app, "DELETE",
                    f"/api/songs/{song_id}/audio?role=vocal")
                self.assertEqual(status, 200)
                payload = json.loads(body)
                self.assertEqual(payload["items"], [])
                # Song.audio_vocal_path 应被清空
                status2, body2, _ = await _request(
                    self.app, "GET", "/api/songs/list")
                items = json.loads(body2)["songs"]
                song = next(s for s in items if s["id"] == song_id)
                self.assertEqual(song["audio_vocal_path"], "")
        asyncio.run(scenario())

    def test_delete_preserves_other_role(self):
        song_id = self._seed_song()
        async def scenario():
            async with self.app.router.lifespan_context(self.app):
                files1 = {"file": ("v.mp3", b"v", "audio/mpeg")}
                files2 = {"file": ("i.m4a", b"i", "audio/mp4")}
                await _request(
                    self.app, "POST", f"/api/songs/{song_id}/audio?role=vocal",
                    files=files1)
                await _request(
                    self.app, "POST", f"/api/songs/{song_id}/audio?role=instrumental",
                    files=files2)
                # 删除 vocal
                await _request(
                    self.app, "DELETE",
                    f"/api/songs/{song_id}/audio?role=vocal")
                # 列表应只剩 instrumental
                status, body, _ = await _request(
                    self.app, "GET", f"/api/songs/{song_id}/audio/list")
                items = json.loads(body)["items"]
                self.assertEqual(len(items), 1)
                self.assertEqual(items[0]["role"], "instrumental")
        asyncio.run(scenario())

    def test_delete_nonexistent_audio_no_error(self):
        song_id = self._seed_song()
        async def scenario():
            async with self.app.router.lifespan_context(self.app):
                # 没上传就删，不抛错
                status, body, _ = await _request(
                    self.app, "DELETE",
                    f"/api/songs/{song_id}/audio?role=vocal")
                self.assertEqual(status, 200)
        asyncio.run(scenario())


class PlaybackEventTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_root = Path(self.tmp.name) / "data"
        self.addCleanup(self.tmp.cleanup)
        self.app = _boot_app(self.data_root)

    def _seed_song_id(self) -> str:
        async def scenario():
            async with self.app.router.lifespan_context(self.app):
                status, body, _ = await _request(
                    self.app, "POST", "/api/songs/add",
                    {"title": "测试", "status": "active",
                     "lyrics_lrc": "[00:00.00]x"})
                return json.loads(body)["song"]["id"]
        return asyncio.run(scenario())

    def test_playback_started(self):
        song_id = self._seed_song_id()
        async def scenario():
            async with self.app.router.lifespan_context(self.app):
                status, body, _ = await _request(
                    self.app, "POST", "/api/playback/events",
                    {"type": "playback_started", "song_id": song_id,
                     "source": "vocal", "position_ms": 0})
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body)["type"], "playback_started")
        asyncio.run(scenario())

    def test_playback_paused(self):
        song_id = self._seed_song_id()
        async def scenario():
            async with self.app.router.lifespan_context(self.app):
                status, body, _ = await _request(
                    self.app, "POST", "/api/playback/events",
                    {"type": "playback_paused", "song_id": song_id,
                     "source": "instrumental", "position_ms": 30000})
                self.assertEqual(status, 200)
        asyncio.run(scenario())

    def test_playback_completed(self):
        song_id = self._seed_song_id()
        async def scenario():
            async with self.app.router.lifespan_context(self.app):
                status, body, _ = await _request(
                    self.app, "POST", "/api/playback/events",
                    {"type": "playback_completed", "song_id": song_id,
                     "duration_ms": 180000})
                self.assertEqual(status, 200)
        asyncio.run(scenario())

    def test_playback_invalid_type_400(self):
        async def scenario():
            async with self.app.router.lifespan_context(self.app):
                status, body, _ = await _request(
                    self.app, "POST", "/api/playback/events",
                    {"type": "playback_bogus", "song_id": "x"})
                self.assertEqual(status, 400)
                self.assertEqual(json.loads(body)["error"]["code"],
                                 "invalid_playback_event")
        asyncio.run(scenario())

    def test_playback_event_written_to_events_jsonl(self):
        song_id = self._seed_song_id()
        async def scenario():
            async with self.app.router.lifespan_context(self.app):
                await _request(
                    self.app, "POST", "/api/playback/events",
                    {"type": "playback_started", "song_id": song_id,
                     "source": "vocal"})
                # 验证 events.jsonl 有这条
                events_file = self.data_root / "events.jsonl"
                self.assertTrue(events_file.is_file())
                lines = events_file.read_text(encoding="utf-8").strip().split("\n")
                playback = [json.loads(line) for line in lines
                            if json.loads(line).get("type", "").startswith("playback_")]
                self.assertEqual(len(playback), 1)
                self.assertEqual(playback[0]["meta"]["song_id"], song_id)
                self.assertEqual(playback[0]["meta"]["source"], "vocal")
                self.assertEqual(playback[0]["meta"]["kind"], "playback_started")
        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
