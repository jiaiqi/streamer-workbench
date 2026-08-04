"""M2.8 在线元数据 HTTP API 端到端测试。

策略：
- 用 mock 替换 NeteaseProvider 的方法，构造确定响应
- 走 ASGI 原始调用（与 test_snapshots.py 一致），手动管理 lifespan
- 覆盖：search / song / lyric / artist / album / playlist / charts / similar
  + 错误路径（404 not_found / 429 rate_limited / 503 unavailable / 422 validation）
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.config import AppConfig


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _boot_app(data_root: Path):
    from server.app import create_app
    return create_app(AppConfig(PROJECT_ROOT, mode="test", data_root=data_root))


async def _raw_request(app, method, path, payload=None, headers=None):
    """绕过 TestClient 的 lifespan 机制，直接 ASGI 调用（与 test_snapshots.py 一致）。"""
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
        await app(
            {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
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
    # 解析响应
    status = 500
    response_body = b""
    for m in messages:
        if m["type"] == "http.response.start":
            status = m["status"]
        elif m["type"] == "http.response.body":
            response_body += m.get("body", b"")
    return status, response_body, messages


def _run(coro):
    return asyncio.run(coro)


class _FakeHit:
    def __init__(self, **kw):
        self.source = kw["source"]
        self.song_id = kw["song_id"]
        self.title = kw["title"]
        self.artist = kw["artist"]
        self.album = kw.get("album")
        self.duration_ms = kw.get("duration_ms")
        self.cover_url = kw.get("cover_url")


class _FakeSongDetail:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class MetadataApiTest(unittest.TestCase):
    """端到端：mock router → 路由 → 响应。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="meta_api_"))
        self.app = _boot_app(self.tmp)
        # 构造 mock router
        self.router_mock = mock.MagicMock()
        self.router_mock.provider_names = ["netease"]
        self.router_mock.cache = None

    def tearDown(self):
        import shutil
        if self.tmp.exists():
            shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_with_mock(self, method, path, payload=None, *, expected_status=200):
        async def scenario():
            async with self.app.router.lifespan_context(self.app):
                # 在 lifespan 内替换 router 为 mock
                self.app.state.context.metadata_router = self.router_mock
                status, body, _ = await _raw_request(self.app, method, path, payload)
                return status, body
        status, body = _run(scenario())
        self.assertEqual(status, expected_status, body.decode("utf-8", errors="replace"))
        return body

    # ── providers ──

    def test_providers_list(self):
        body = self._run_with_mock("GET", "/api/metadata/providers")
        data = json.loads(body)
        self.assertEqual(data["providers"], ["netease"])

    # ── search ──

    def test_search_success(self):
        self.router_mock.search.return_value = [
            _FakeHit(source="netease", song_id="123", title="七里香",
                     artist="周杰伦", album="七里香", duration_ms=234000,
                     cover_url="http://x/cover.jpg"),
        ]
        body = self._run_with_mock("POST", "/api/metadata/search",
                                    {"keyword": "周杰伦", "type": "song", "limit": 20})
        data = json.loads(body)
        self.assertEqual(data["keyword"], "周杰伦")
        self.assertEqual(data["type"], "song")
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["title"], "七里香")
        self.assertEqual(data["items"][0]["song_id"], "123")

    def test_search_empty_keyword(self):
        self.router_mock.search.return_value = []
        body = self._run_with_mock("POST", "/api/metadata/search", {"keyword": ""})
        data = json.loads(body)
        self.assertEqual(data["items"], [])

    def test_search_router_unavailable(self):
        from core.metadata import MetadataUnavailable
        self.router_mock.search.side_effect = MetadataUnavailable([
            ("netease", OSError("net")),
        ])
        self._run_with_mock("POST", "/api/metadata/search",
                            {"keyword": "kw"}, expected_status=503)

    def test_search_rate_limited(self):
        from core.metadata import MetadataRateLimited
        self.router_mock.search.side_effect = MetadataRateLimited("netease", retry_after=30)
        # 429 + Retry-After header；测试只验状态码
        self._run_with_mock("POST", "/api/metadata/search",
                            {"keyword": "kw"}, expected_status=429)

    # ── song ──

    def test_song_success(self):
        self.router_mock.get_song.return_value = _FakeSongDetail(
            source="netease", song_id="123", title="七里香",
            artist="周杰伦", artist_id="1", album="七里香",
            album_id="2", duration_ms=234000,
            cover_url="http://x/cover.jpg", bpm=None,
        )
        body = self._run_with_mock("POST", "/api/metadata/song", {"song_id": "123"})
        data = json.loads(body)
        self.assertEqual(data["title"], "七里香")
        self.assertEqual(data["artist_id"], "1")
        self.assertEqual(data["album_id"], "2")
        self.assertEqual(data["duration_ms"], 234000)

    def test_song_not_found(self):
        from core.metadata import MetadataNotFound
        self.router_mock.get_song.side_effect = MetadataNotFound("没找到")
        self._run_with_mock("POST", "/api/metadata/song", {"song_id": "999"},
                            expected_status=404)

    def test_song_with_preferred_provider(self):
        self.router_mock.get_song.return_value = _FakeSongDetail(
            source="qq", song_id="123", title="七里香", artist="周杰伦",
            artist_id=None, album=None, album_id=None, duration_ms=234000,
            cover_url=None, bpm=None,
        )
        self._run_with_mock("POST", "/api/metadata/song",
                            {"song_id": "123", "preferred_provider": "qq"})
        # router 应被以 preferred_provider="qq" 调用
        self.router_mock.get_song.assert_called_once_with(
            "123", preferred_provider="qq",
        )

    # ── lyric ──

    def test_lyric_success(self):
        from core.metadata import LyricContent
        self.router_mock.get_lyric.return_value = LyricContent(
            source="netease", song_id="123",
            lrc_text="[00:00]hello",
            translated_lrc="[00:00]你好",
        )
        body = self._run_with_mock("POST", "/api/metadata/lyric", {"song_id": "123"})
        data = json.loads(body)
        self.assertIn("hello", data["lrc_text"])
        self.assertIn("你好", data["translated_lrc"])

    def test_lyric_no_lyric(self):
        self.router_mock.get_lyric.return_value = None
        self._run_with_mock("POST", "/api/metadata/lyric", {"song_id": "123"},
                            expected_status=404)

    def test_lyric_unavailable(self):
        from core.metadata import MetadataUnavailable
        self.router_mock.get_lyric.side_effect = MetadataUnavailable([
            ("netease", TimeoutError("net")),
        ])
        self._run_with_mock("POST", "/api/metadata/lyric", {"song_id": "123"},
                            expected_status=503)

    # ── artist ──

    def test_artist_success(self):
        from core.metadata import ArtistDetail
        self.router_mock.get_artist.return_value = ArtistDetail(
            source="netease", artist_id="1", name="周杰伦",
            bio="华语流行", avatar_url="http://x/a.jpg",
            songs=[_FakeHit(source="netease", song_id="11", title="七里香", artist="周杰伦")],
        )
        body = self._run_with_mock("POST", "/api/metadata/artist", {"artist_id": "1"})
        data = json.loads(body)
        self.assertEqual(data["name"], "周杰伦")
        self.assertEqual(data["bio"], "华语流行")
        self.assertEqual(len(data["songs"]), 1)

    # ── album ──

    def test_album_success(self):
        from core.metadata import AlbumDetail
        self.router_mock.get_album.return_value = AlbumDetail(
            source="netease", album_id="2", title="七里香",
            artist="周杰伦", cover_url="http://x/al.jpg",
            release_date="2004-07-31",
            songs=[_FakeHit(source="netease", song_id="11", title="七里香", artist="周杰伦")],
        )
        body = self._run_with_mock("POST", "/api/metadata/album", {"album_id": "2"})
        data = json.loads(body)
        self.assertEqual(data["title"], "七里香")
        self.assertEqual(data["release_date"], "2004-07-31")

    # ── playlist ──

    def test_playlist_success(self):
        from core.metadata import PlaylistDetail
        self.router_mock.get_playlist.return_value = PlaylistDetail(
            source="netease", playlist_id="100", title="我喜欢的",
            creator="主播", cover_url="http://x/p.jpg",
            description="个人精选", play_count=12345,
            songs=[_FakeHit(source="netease", song_id="11", title="七里香", artist="周杰伦")],
        )
        body = self._run_with_mock("POST", "/api/metadata/playlist", {"playlist_id": "100"})
        data = json.loads(body)
        self.assertEqual(data["title"], "我喜欢的")
        self.assertEqual(data["play_count"], 12345)
        self.assertEqual(len(data["songs"]), 1)

    # ── charts ──

    def test_charts_success(self):
        from core.metadata import Chart
        self.router_mock.get_charts.return_value = [
            Chart(source="netease", chart_id="19723756", title="飙升榜",
                  cover_url="http://x/c1.jpg", description="上升最快"),
            Chart(source="netease", chart_id="3779629", title="原创榜"),
        ]
        body = self._run_with_mock("POST", "/api/metadata/charts", {})
        data = json.loads(body)
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["title"], "飙升榜")
        self.assertEqual(data[1]["title"], "原创榜")

    def test_charts_empty(self):
        self.router_mock.get_charts.return_value = []
        body = self._run_with_mock("POST", "/api/metadata/charts", {})
        self.assertEqual(json.loads(body), [])

    # ── similar ──

    def test_similar_success(self):
        self.router_mock.get_similar.return_value = [
            _FakeHit(source="netease", song_id="22", title="晴天", artist="周杰伦"),
            _FakeHit(source="netease", song_id="33", title="夜曲", artist="周杰伦"),
        ]
        body = self._run_with_mock("POST", "/api/metadata/similar", {"song_id": "11"})
        data = json.loads(body)
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["title"], "晴天")

    def test_similar_empty(self):
        self.router_mock.get_similar.return_value = []
        body = self._run_with_mock("POST", "/api/metadata/similar", {"song_id": "11"})
        self.assertEqual(json.loads(body), [])

    # ── Validation ──

    def test_search_validation_missing_keyword(self):
        self._run_with_mock("POST", "/api/metadata/search", {}, expected_status=422)

    def test_song_validation_missing_song_id(self):
        self._run_with_mock("POST", "/api/metadata/song", {}, expected_status=422)


class MetadataRouterDisabledTest(unittest.TestCase):
    """metadata_router 为 None 时（未启用）的端点应返回 503。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="meta_api_disabled_"))
        self.app = _boot_app(self.tmp)

    def tearDown(self):
        import shutil
        if self.tmp.exists():
            shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, method, path, payload=None, *, expected_status=200):
        async def scenario():
            async with self.app.router.lifespan_context(self.app):
                self.app.state.context.metadata_router = None
                status, body, _ = await _raw_request(self.app, method, path, payload)
                return status, body
        status, body = _run(scenario())
        self.assertEqual(status, expected_status, body.decode("utf-8", errors="replace"))
        return body

    def test_providers_empty(self):
        body = self._run("GET", "/api/metadata/providers")
        data = json.loads(body)
        self.assertEqual(data["providers"], [])

    def test_search_no_router(self):
        self._run("POST", "/api/metadata/search", {"keyword": "kw"},
                  expected_status=503)

    def test_song_no_router(self):
        self._run("POST", "/api/metadata/song", {"song_id": "1"},
                  expected_status=503)


class MetadataRouterIntegrationTest(unittest.TestCase):
    """NeteaseProvider 真用 + cache 真用：走完整路径（HttpClient mock）。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="meta_api_int_"))
        self.app = _boot_app(self.tmp)

    def tearDown(self):
        import shutil
        if self.tmp.exists():
            shutil.rmtree(self.tmp, ignore_errors=True)

    def test_full_path_with_mock_http(self):
        """替换 HttpClient，验证 search → provider → cache → router 整条链路。"""
        from core.metadata import HttpClient, NeteaseProvider
        from core.metadata import MetadataCache, MetadataRouter

        # 构造替换：HttpClient.get_json 返回固定 search 响应
        fake_http = mock.MagicMock(spec=HttpClient)
        fake_http.get_json.return_value = {
            "code": 200,
            "result": {
                "songs": [{
                    "id": 99, "name": "集成测试歌曲",
                    "artists": [{"name": "测试歌手"}],
                    "album": {"picUrl": "http://x/c.jpg"},
                    "duration": 180000,
                }],
            },
        }

        cache = MetadataCache(self.tmp / "metadata")
        provider = NeteaseProvider(fake_http)
        router = MetadataRouter([provider], cache=cache)
        service_mock = mock.MagicMock()
        service_mock.router = router

        async def scenario():
            async with self.app.router.lifespan_context(self.app):
                # 替换为真 router（带 mock http + cache）
                self.app.state.context.metadata_router = router
                self.app.state.context.metadata_service = service_mock
                status, body, _ = await _raw_request(
                    self.app, "POST", "/api/metadata/search",
                    {"keyword": "集成", "type": "song", "limit": 5},
                )
                # 第二次调用应命中 cache，不再调 http
                status2, body2, _ = await _raw_request(
                    self.app, "POST", "/api/metadata/search",
                    {"keyword": "集成", "type": "song", "limit": 5},
                )
                return status, body, status2, body2

        status, body, status2, body2 = _run(scenario())
        self.assertEqual(status, 200)
        data1 = json.loads(body)
        data2 = json.loads(body2)
        self.assertEqual(len(data1["items"]), 1)
        self.assertEqual(data1["items"][0]["title"], "集成测试歌曲")
        self.assertEqual(data2, data1)
        # 第二次应不调 http（cache hit）
        self.assertEqual(fake_http.get_json.call_count, 1)


if __name__ == "__main__":
    unittest.main()
