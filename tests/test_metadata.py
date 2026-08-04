"""M2.7 在线元数据层单元测试。

覆盖：
- 协议 duck typing（FakeProvider 不继承任何基类也能满足 MetadataProvider）
- types：frozen 不可变
- errors：三种异常的构造、属性
- http_client：成功 / 4xx / 5xx 重试 / 超时 / 429 / 速率限制
- cache：get/put / TTL 过期 / force / 原子写 / key sanitize / clear
- router：首个成功即返回 / 首个失败 → 第二个成功 / 都失败抛 MetadataUnavailable /
  缓存命中不调 provider / use_cache=False 强制刷新 / preferred_provider 排第一
- 公开 API：from core.metadata import ... 全部可用
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
import urllib.error
from email.message import Message
from pathlib import Path
from typing import Any
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.metadata import (
    DEFAULT_TTL_SECONDS,
    AlbumDetail,
    ArtistDetail,
    Chart,
    Hit,
    HttpClient,
    LyricContent,
    MetadataCache,
    MetadataError,
    MetadataNotFound,
    MetadataProvider,
    MetadataRateLimited,
    MetadataRouter,
    MetadataUnavailable,
    PlaylistDetail,
    SearchType,
    SongDetail,
)
from core.metadata import errors as errors_mod
from core.metadata import protocols as protocols_mod


# ───────────────────── 辅助：Fake Provider ─────────────────────


class FakeProvider:
    """不继承任何基类，纯 duck typing 满足 MetadataProvider。"""

    def __init__(self, name: str, *, behavior: dict | None = None):
        self.name = name
        self.behavior = behavior or {}
        self.call_log: list[tuple[str, tuple]] = []

    def search(self, keyword, *, type="song", limit=20):
        self.call_log.append(("search", (keyword, type, limit)))
        if "search" in self.behavior:
            entry = self.behavior["search"]
            if isinstance(entry, Exception):
                raise entry
            return [Hit(**h) for h in entry]
        return []

    def get_song(self, song_id):
        self.call_log.append(("get_song", (song_id,)))
        if "get_song" in self.behavior:
            entry = self.behavior["get_song"]
            if isinstance(entry, Exception):
                raise entry
            return SongDetail(**entry)
        raise MetadataNotFound(f"fake {self.name} 无 song={song_id}")

    def get_artist(self, artist_id):
        self.call_log.append(("get_artist", (artist_id,)))
        if "get_artist" in self.behavior:
            entry = self.behavior["get_artist"]
            if isinstance(entry, Exception):
                raise entry
            return ArtistDetail(**entry)
        raise MetadataNotFound(f"fake {self.name} 无 artist={artist_id}")

    def get_album(self, album_id):
        self.call_log.append(("get_album", (album_id,)))
        if "get_album" in self.behavior:
            entry = self.behavior["get_album"]
            if isinstance(entry, Exception):
                raise entry
            return AlbumDetail(**entry)
        raise MetadataNotFound(f"fake {self.name} 无 album={album_id}")

    def get_playlist(self, playlist_id):
        self.call_log.append(("get_playlist", (playlist_id,)))
        if "get_playlist" in self.behavior:
            entry = self.behavior["get_playlist"]
            if isinstance(entry, Exception):
                raise entry
            return PlaylistDetail(**entry)
        raise MetadataNotFound(f"fake {self.name} 无 playlist={playlist_id}")

    def get_lyric(self, song_id):
        self.call_log.append(("get_lyric", (song_id,)))
        if "get_lyric" in self.behavior:
            entry = self.behavior["get_lyric"]
            if entry is None:
                return None
            if isinstance(entry, Exception):
                raise entry
            return LyricContent(**entry)
        return None

    def get_charts(self):
        self.call_log.append(("get_charts", ()))
        if "get_charts" in self.behavior:
            entry = self.behavior["get_charts"]
            if isinstance(entry, Exception):
                raise entry
            return [Chart(**c) for c in entry]
        return []

    def get_similar(self, song_id):
        self.call_log.append(("get_similar", (song_id,)))
        if "get_similar" in self.behavior:
            entry = self.behavior["get_similar"]
            if isinstance(entry, Exception):
                raise entry
            return [Hit(**h) for h in entry]
        return []


# ───────────────────── 协议 duck typing ─────────────────────


class ProtocolConformanceTest(unittest.TestCase):
    def test_fake_provider_satisfies_protocol(self):
        # mypy 视角下 FakeProvider 满足 MetadataProvider Protocol（duck typing）
        provider: MetadataProvider = FakeProvider("test")
        self.assertEqual(provider.name, "test")

    def test_protocols_module_exports(self):
        # 协议模块确实导出 MetadataProvider 和 SearchType
        self.assertTrue(hasattr(protocols_mod, "MetadataProvider"))
        self.assertTrue(hasattr(protocols_mod, "SearchType"))


# ───────────────────── types 不可变性 ─────────────────────


class TypesFrozenTest(unittest.TestCase):
    def test_hit_frozen(self):
        h = Hit(source="x", song_id="1", title="t", artist="a")
        with self.assertRaises(Exception):
            h.title = "changed"  # type: ignore[misc]

    def test_song_detail_frozen(self):
        s = SongDetail(source="x", song_id="1", title="t", artist="a")
        with self.assertRaises(Exception):
            s.song_id = "2"  # type: ignore[misc]

    def test_hit_to_dict_roundtrip(self):
        original = Hit(
            source="netease", song_id="123", title="七里香",
            artist="周杰伦", album="七里香", duration_ms=234000,
            cover_url="http://example.com/cover.jpg",
        )
        d = {
            "source": original.source, "song_id": original.song_id,
            "title": original.title, "artist": original.artist,
            "album": original.album, "duration_ms": original.duration_ms,
            "cover_url": original.cover_url,
        }
        roundtrip = Hit(**d)
        self.assertEqual(roundtrip, original)


# ───────────────────── errors ─────────────────────


class ErrorsTest(unittest.TestCase):
    def test_metadata_error_base(self):
        exc = MetadataError("boom")
        self.assertIsInstance(exc, Exception)
        self.assertEqual(str(exc), "boom")

    def test_metadata_not_found(self):
        exc = MetadataNotFound("查不到")
        self.assertIsInstance(exc, MetadataError)
        self.assertEqual(str(exc), "查不到")

    def test_metadata_unavailable_with_errors(self):
        n1 = MetadataUnavailable([("netease", TimeoutError("net")), ("qq", OSError("dns"))])
        s = str(n1)
        self.assertIn("netease", s)
        self.assertIn("qq", s)
        self.assertEqual(len(n1.errors), 2)
        self.assertIsInstance(n1.errors[0][1], TimeoutError)

    def test_metadata_unavailable_empty(self):
        n = MetadataUnavailable([])
        s = str(n)
        self.assertIn("no providers", s)

    def test_metadata_rate_limited(self):
        r = MetadataRateLimited("netease", retry_after=30)
        self.assertEqual(r.provider, "netease")
        self.assertEqual(r.retry_after, 30)
        self.assertIn("30", str(r))
        self.assertIn("netease", str(r))

    def test_metadata_rate_limited_no_retry_after(self):
        r = MetadataRateLimited("qq", retry_after=None)
        self.assertIsNone(r.retry_after)
        self.assertIn("qq", str(r))


# ───────────────────── http_client ─────────────────────


class _MockResponse:
    def __init__(self, body: str, code: int = 200, headers: dict | None = None):
        self._body = body.encode("utf-8")
        self.code = code
        self.headers = headers or {}
    def read(self):
        return self._body
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def _make_http_error(code: int, retry_after: int | None = None) -> urllib.error.HTTPError:
    """构造一个真实的 urllib.error.HTTPError 用于 mock。"""
    msg = {404: "Not Found", 429: "Too Many Requests", 503: "Service Unavailable"}.get(code, "Error")
    headers = Message()
    if retry_after is not None:
        headers["Retry-after"] = str(retry_after)
    return urllib.error.HTTPError(
        url="http://example.com/api",
        code=code,
        msg=msg,
        hdrs=headers,
        fp=None,
    )


class HttpClientTest(unittest.TestCase):
    def _make_client(self, **kwargs) -> HttpClient:
        # 用 mock sleep 避免真实等待
        return HttpClient(
            timeout=0.1, max_retries=kwargs.pop("max_retries", 2),
            min_interval=kwargs.pop("min_interval", 0),
            sleep=lambda s: None,
            **kwargs,
        )

    def test_get_json_success(self):
        client = self._make_client()
        with mock.patch("urllib.request.urlopen", return_value=_MockResponse('{"a": 1}')):
            data = client.get_json("https://example.com/api")
        self.assertEqual(data, {"a": 1})

    def test_get_text_success(self):
        client = self._make_client()
        with mock.patch("urllib.request.urlopen", return_value=_MockResponse("hello")):
            text = client.get_text("https://example.com/text")
        self.assertEqual(text, "hello")

    def test_get_json_bad_json_raises_unavailable(self):
        client = self._make_client()
        with mock.patch("urllib.request.urlopen", return_value=_MockResponse("not json")):
            with self.assertRaises(MetadataUnavailable) as ctx:
                client.get_json("https://example.com/api")
        self.assertIn("self", ctx.exception.errors[0][0])

    def test_4xx_no_retry_raises_unavailable(self):
        client = self._make_client(max_retries=3)
        http_err = _make_http_error(404)
        with mock.patch("urllib.request.urlopen", side_effect=http_err):
            with self.assertRaises(MetadataUnavailable):
                client.get_text("https://example.com/api")

    def test_5xx_retries_then_raises(self):
        client = self._make_client(max_retries=2)
        call_count = [0]
        def _always_503(*a, **kw):
            call_count[0] += 1
            raise _make_http_error(503)
        with mock.patch("urllib.request.urlopen", side_effect=_always_503):
            with self.assertRaises(MetadataUnavailable):
                client.get_text("https://example.com/api")
        # 重试 = 1 + 2 = 3 次
        self.assertEqual(call_count[0], 3)

    def test_5xx_eventually_succeeds(self):
        client = self._make_client(max_retries=2)
        # 第一次 5xx，第二次 200
        success = _MockResponse('{"ok": true}')
        with mock.patch("urllib.request.urlopen", side_effect=[
            _make_http_error(503), success,
        ]):
            data = client.get_json("https://example.com/api")
        self.assertEqual(data, {"ok": True})

    def test_429_raises_rate_limited(self):
        client = self._make_client()
        call_count = [0]
        def _always_429(*a, **kw):
            call_count[0] += 1
            raise _make_http_error(429, retry_after=30)
        with mock.patch("urllib.request.urlopen", side_effect=_always_429):
            with self.assertRaises(MetadataRateLimited) as ctx:
                client.get_text("https://example.com/api")
        self.assertEqual(ctx.exception.retry_after, 30)
        # 429 不重试
        self.assertEqual(call_count[0], 1)

    def test_url_building_with_params(self):
        client = self._make_client()
        captured_urls: list[str] = []
        def _capture(req, *a, **kw):
            # urlopen 收到的是 Request 对象，不是 url 字符串
            captured_urls.append(req.full_url)
            return _MockResponse("ok")
        with mock.patch("urllib.request.urlopen", side_effect=_capture):
            client.get_text("https://example.com/api", params={"a": 1, "b": "x y"})
        self.assertEqual(len(captured_urls), 1)
        self.assertIn("a=1", captured_urls[0])
        self.assertIn("b=x+y", captured_urls[0])  # urllib 编码空格为 +

    def test_throttle_enforces_min_interval(self):
        sleeps: list[float] = []
        client = HttpClient(
            timeout=0.1, max_retries=0, min_interval=0.5,
            sleep=lambda s: sleeps.append(s),
        )
        with mock.patch("urllib.request.urlopen", return_value=_MockResponse("ok")):
            client.get_text("https://example.com/a")
            client.get_text("https://example.com/b")
        # 第二次调用应 sleep 约 0.5s
        self.assertEqual(len(sleeps), 1)
        self.assertGreater(sleeps[0], 0)

    def test_user_agent_header_sent(self):
        client = self._make_client()
        captured_req = []
        def _capture(req, *a, **kw):
            captured_req.append(req)
            return _MockResponse("ok")
        with mock.patch("urllib.request.urlopen", side_effect=_capture):
            client.get_text("https://example.com/api")
        self.assertEqual(captured_req[0].headers["User-agent"], client._ua)


# ───────────────────── cache ─────────────────────


class CacheTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="meta_cache_"))

    def tearDown(self):
        import shutil
        if self.tmp.exists():
            shutil.rmtree(self.tmp, ignore_errors=True)

    def test_get_miss(self):
        c = MetadataCache(self.tmp, ttl_seconds=3600)
        self.assertIsNone(c.get("netease", "song_1"))

    def test_put_then_get(self):
        c = MetadataCache(self.tmp, ttl_seconds=3600)
        c.put("netease", "song_1", {"title": "七里香"})
        result = c.get("netease", "song_1")
        self.assertEqual(result, {"title": "七里香"})

    def test_force_bypasses_ttl(self):
        c = MetadataCache(self.tmp, ttl_seconds=1)  # 1 秒 TTL
        c.put("netease", "song_1", {"a": 1})
        # 手动改 fetched_at 到 1970 实现立即过期
        path = c._path("netease", "song_1")
        env = json.loads(path.read_text(encoding="utf-8"))
        env["fetched_at"] = "1970-01-01T00:00:00+00:00"
        path.write_text(json.dumps(env), encoding="utf-8")
        self.assertIsNone(c.get("netease", "song_1"))  # 过期
        self.assertEqual(c.get("netease", "song_1", force=True), {"a": 1})  # force 绕过

    def test_ttl_expiry(self):
        c = MetadataCache(self.tmp, ttl_seconds=1)
        c.put("netease", "song_1", {"a": 1})
        self.assertEqual(c.get("netease", "song_1"), {"a": 1})
        # 手动改 fetched_at 模拟过期
        path = c._path("netease", "song_1")
        env = json.loads(path.read_text(encoding="utf-8"))
        env["fetched_at"] = "2000-01-01T00:00:00+00:00"
        path.write_text(json.dumps(env), encoding="utf-8")
        self.assertIsNone(c.get("netease", "song_1"))

    def test_corrupt_cache_returns_none(self):
        c = MetadataCache(self.tmp, ttl_seconds=3600)
        c.put("netease", "song_1", {"a": 1})
        c._path("netease", "song_1").write_text("not json", encoding="utf-8")
        self.assertIsNone(c.get("netease", "song_1"))

    def test_key_sanitize_prevents_path_traversal(self):
        c = MetadataCache(self.tmp, ttl_seconds=3600)
        # song_id 包含 ../  → sanitize 后变成安全 key
        c.put("netease", "../etc/passwd", {"a": 1})
        # 文件应在 cache base 之下，不应跳出
        self.assertTrue(c._path("netease", "../etc/passwd").is_relative_to(self.tmp))
        result = c.get("netease", "../etc/passwd")
        self.assertEqual(result, {"a": 1})

    def test_clear_specific_provider(self):
        c = MetadataCache(self.tmp, ttl_seconds=3600)
        c.put("netease", "1", {"a": 1})
        c.put("qq", "2", {"b": 2})
        deleted = c.clear("netease")
        self.assertEqual(deleted, 1)
        self.assertIsNone(c.get("netease", "1"))
        self.assertEqual(c.get("qq", "2"), {"b": 2})

    def test_clear_all(self):
        c = MetadataCache(self.tmp, ttl_seconds=3600)
        c.put("netease", "1", {"a": 1})
        c.put("qq", "2", {"b": 2})
        deleted = c.clear()
        self.assertEqual(deleted, 2)
        self.assertIsNone(c.get("netease", "1"))
        self.assertIsNone(c.get("qq", "2"))

    def test_atomic_write_no_partial_file(self):
        """put 失败时不应留下损坏的 tmp。"""
        c = MetadataCache(self.tmp, ttl_seconds=3600)
        # 模拟 json.dump 失败
        with mock.patch("json.dump", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                c.put("netease", "1", {"a": 1})
        # 确认 cache 目录里没有遗留 tmp
        tmp_files = list((self.tmp / "netease").glob("*.tmp")) if (self.tmp / "netease").exists() else []
        self.assertEqual(tmp_files, [])

    def test_invalid_ttl_raises(self):
        with self.assertRaises(ValueError):
            MetadataCache(self.tmp, ttl_seconds=0)

    def test_list_keys(self):
        c = MetadataCache(self.tmp, ttl_seconds=3600)
        c.put("netease", "1", {"a": 1})
        c.put("netease", "2", {"b": 2})
        keys = c.list_keys("netease")
        self.assertEqual(sorted(keys), ["1", "2"])

    def test_default_ttl_is_30_days(self):
        c = MetadataCache(self.tmp)
        self.assertEqual(c.ttl_seconds, DEFAULT_TTL_SECONDS)
        self.assertEqual(c.ttl_seconds, 30 * 24 * 3600)


# ───────────────────── router ─────────────────────


class RouterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="meta_router_"))

    def tearDown(self):
        import shutil
        if self.tmp.exists():
            shutil.rmtree(self.tmp, ignore_errors=True)

    def _make(self, providers: list[FakeProvider], *, with_cache: bool = True):
        cache = MetadataCache(self.tmp, ttl_seconds=3600) if with_cache else None
        return MetadataRouter(providers, cache=cache)

    def test_constructor_requires_providers(self):
        with self.assertRaises(ValueError):
            MetadataRouter([])
        with self.assertRaises(ValueError):
            MetadataRouter([FakeProvider("a"), FakeProvider("a")])

    def test_provider_names_preserves_order(self):
        r = self._make([FakeProvider("c"), FakeProvider("a"), FakeProvider("b")])
        self.assertEqual(r.provider_names, ["c", "a", "b"])

    def test_search_first_with_result_wins(self):
        p1 = FakeProvider("a", behavior={"search": [{"source": "a", "song_id": "1", "title": "t", "artist": "x"}]})
        p2 = FakeProvider("b", behavior={"search": [{"source": "b", "song_id": "2", "title": "u", "artist": "y"}]})
        r = self._make([p1, p2])
        hits = r.search("kw")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].source, "a")
        # p2 不应被调用
        self.assertEqual(len([c for c in p2.call_log if c[0] == "search"]), 0)

    def test_search_empty_falls_through(self):
        p1 = FakeProvider("a", behavior={"search": []})
        p2 = FakeProvider("b", behavior={"search": [{"source": "b", "song_id": "2", "title": "u", "artist": "y"}]})
        r = self._make([p1, p2])
        hits = r.search("kw")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].source, "b")

    def test_search_all_empty_returns_empty(self):
        p1 = FakeProvider("a", behavior={"search": []})
        p2 = FakeProvider("b", behavior={"search": []})
        r = self._make([p1, p2])
        self.assertEqual(r.search("kw"), [])

    def test_search_all_fail_raises_unavailable(self):
        p1 = FakeProvider("a", behavior={"search": OSError("net")})
        p2 = FakeProvider("b", behavior={"search": TimeoutError("timeout")})
        r = self._make([p1, p2])
        with self.assertRaises(MetadataUnavailable) as ctx:
            r.search("kw")
        self.assertEqual(len(ctx.exception.errors), 2)

    def test_get_song_first_success(self):
        p1 = FakeProvider("a", behavior={"get_song": {
            "source": "a", "song_id": "1", "title": "t", "artist": "x", "duration_ms": 100,
        }})
        p2 = FakeProvider("b")
        r = self._make([p1, p2])
        result = r.get_song("1")
        self.assertEqual(result.source, "a")
        self.assertEqual(result.duration_ms, 100)

    def test_get_song_falls_through_on_not_found(self):
        p1 = FakeProvider("a")
        p2 = FakeProvider("b", behavior={"get_song": {
            "source": "b", "song_id": "1", "title": "t", "artist": "x",
        }})
        r = self._make([p1, p2])
        result = r.get_song("1")
        self.assertEqual(result.source, "b")

    def test_get_song_all_fail(self):
        p1 = FakeProvider("a", behavior={"get_song": OSError()})
        p2 = FakeProvider("b", behavior={"get_song": OSError()})
        r = self._make([p1, p2])
        with self.assertRaises(MetadataUnavailable):
            r.get_song("1")

    def test_get_song_all_not_found(self):
        p1 = FakeProvider("a")
        p2 = FakeProvider("b")
        r = self._make([p1, p2])
        with self.assertRaises(MetadataNotFound):
            r.get_song("1")

    def test_cache_hit_skips_provider(self):
        p1 = FakeProvider("a", behavior={"get_song": {
            "source": "a", "song_id": "1", "title": "t", "artist": "x",
        }})
        r = self._make([p1])
        # 第一次：调用 provider + 写 cache
        r.get_song("1")
        self.assertEqual(len(p1.call_log), 1)
        # 第二次：命中 cache，不调 provider
        r.get_song("1")
        self.assertEqual(len(p1.call_log), 1)

    def test_use_cache_false_force_refresh(self):
        p1 = FakeProvider("a", behavior={"get_song": {
            "source": "a", "song_id": "1", "title": "t", "artist": "x",
        }})
        r = self._make([p1])
        r.get_song("1")
        r.get_song("1", use_cache=False)
        # 第二次强制刷新 → 调 provider 两次
        self.assertEqual(len(p1.call_log), 2)

    def test_preferred_provider_first(self):
        p1 = FakeProvider("a", behavior={"get_song": {
            "source": "a", "song_id": "1", "title": "t", "artist": "x",
        }})
        p2 = FakeProvider("b", behavior={"get_song": {
            "source": "b", "song_id": "1", "title": "u", "artist": "y",
        }})
        r = self._make([p1, p2])
        # preferred=b → 优先 p2
        result = r.get_song("1", preferred_provider="b")
        self.assertEqual(result.source, "b")
        self.assertEqual(len(p1.call_log), 0)  # p1 没被调

    def test_preferred_provider_unknown_ignored(self):
        p1 = FakeProvider("a", behavior={"get_song": {
            "source": "a", "song_id": "1", "title": "t", "artist": "x",
        }})
        r = self._make([p1])
        result = r.get_song("1", preferred_provider="zzz")
        self.assertEqual(result.source, "a")  # 用默认顺序

    def test_get_lyric_returns_none(self):
        p1 = FakeProvider("a", behavior={"get_lyric": None})
        p2 = FakeProvider("b", behavior={"get_lyric": None})
        r = self._make([p1, p2])
        self.assertIsNone(r.get_lyric("1"))

    def test_get_lyric_first_with_content(self):
        p1 = FakeProvider("a", behavior={"get_lyric": None})
        p2 = FakeProvider("b", behavior={"get_lyric": {
            "source": "b", "song_id": "1", "lrc_text": "[00:00]hello",
        }})
        r = self._make([p1, p2])
        lyric = r.get_lyric("1")
        self.assertIsNotNone(lyric)
        self.assertEqual(lyric.source, "b")
        self.assertEqual(lyric.lrc_text, "[00:00]hello")

    def test_get_lyric_caches_none(self):
        # 三个 provider 都返回 None → router 应缓存 None 避免重复调用
        p1 = FakeProvider("a", behavior={"get_lyric": None})
        r = self._make([p1])
        self.assertIsNone(r.get_lyric("1"))
        self.assertIsNone(r.get_lyric("1"))
        # 第二次命中 None cache，不再调 provider
        self.assertEqual(len(p1.call_log), 1)

    def test_search_no_cache(self):
        # 无 cache 时不应崩溃
        p1 = FakeProvider("a", behavior={"search": [{"source": "a", "song_id": "1", "title": "t", "artist": "x"}]})
        r = self._make([p1], with_cache=False)
        hits = r.search("kw")
        self.assertEqual(len(hits), 1)

    def test_search_empty_keyword(self):
        p1 = FakeProvider("a")
        r = self._make([p1])
        self.assertEqual(r.search(""), [])
        self.assertEqual(r.search("   "), [])
        # 不应调用 provider
        self.assertEqual(len(p1.call_log), 0)

    def test_search_limit_clamp(self):
        p1 = FakeProvider("a")
        r = self._make([p1])
        r.search("kw", limit=999)  # 超过 50 应 clamp
        # 看 call_log 的 limit 参数
        for method, args in p1.call_log:
            if method == "search":
                self.assertEqual(args[2], 50)

    def test_get_charts(self):
        p1 = FakeProvider("a", behavior={"get_charts": [
            {"source": "a", "chart_id": "hot", "title": "热歌榜"},
        ]})
        p2 = FakeProvider("b")
        r = self._make([p1, p2])
        charts = r.get_charts()
        self.assertEqual(len(charts), 1)
        self.assertEqual(charts[0].title, "热歌榜")

    def test_get_similar(self):
        p1 = FakeProvider("a", behavior={"get_similar": [
            {"source": "a", "song_id": "2", "title": "u", "artist": "y"},
        ]})
        r = self._make([p1])
        hits = r.get_similar("1")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].song_id, "2")

    def test_get_playlist(self):
        p1 = FakeProvider("a", behavior={"get_playlist": {
            "source": "a", "playlist_id": "p1", "title": "我喜欢的",
            "songs": [{"source": "a", "song_id": "1", "title": "t", "artist": "x"}],
        }})
        r = self._make([p1])
        pl = r.get_playlist("p1")
        self.assertEqual(pl.title, "我喜欢的")
        self.assertEqual(len(pl.songs), 1)

    def test_get_album(self):
        p1 = FakeProvider("a", behavior={"get_album": {
            "source": "a", "album_id": "al1", "title": "七里香", "artist": "周杰伦",
            "songs": [{"source": "a", "song_id": "1", "title": "七里香", "artist": "周杰伦"}],
        }})
        r = self._make([p1])
        al = r.get_album("al1")
        self.assertEqual(al.title, "七里香")
        self.assertEqual(len(al.songs), 1)

    def test_get_artist(self):
        p1 = FakeProvider("a", behavior={"get_artist": {
            "source": "a", "artist_id": "ar1", "name": "周杰伦", "bio": "华语流行男歌手",
            "songs": [{"source": "a", "song_id": "1", "title": "七里香", "artist": "周杰伦"}],
        }})
        r = self._make([p1])
        ar = r.get_artist("ar1")
        self.assertEqual(ar.name, "周杰伦")
        self.assertEqual(ar.bio, "华语流行男歌手")
        self.assertEqual(len(ar.songs), 1)

    def test_attach_cache_runtime(self):
        p1 = FakeProvider("a", behavior={"get_song": {
            "source": "a", "song_id": "1", "title": "t", "artist": "x",
        }})
        r = self._make([p1], with_cache=False)
        r.get_song("1")  # 无 cache
        self.assertEqual(len(p1.call_log), 1)
        # 运行时挂 cache
        cache = MetadataCache(self.tmp, ttl_seconds=3600)
        r.attach_cache(cache)
        r.get_song("1")  # 这次写 cache
        self.assertEqual(len(p1.call_log), 2)
        r.get_song("1")  # 命中 cache
        self.assertEqual(len(p1.call_log), 2)


# ───────────────────── 公开 API 完整性 ─────────────────────


class PublicApiTest(unittest.TestCase):
    def test_imports_all(self):
        from core.metadata import (
            AlbumDetail, ArtistDetail, Chart, Hit, HttpClient, LyricContent,
            MetadataCache, MetadataError, MetadataNotFound, MetadataProvider,
            MetadataRateLimited, MetadataRouter, MetadataUnavailable,
            PlaylistDetail, SearchType, SongDetail, DEFAULT_TTL_SECONDS,
        )
        # 全部可用即可
        self.assertTrue(callable(MetadataRouter))
        self.assertTrue(callable(MetadataCache))

    def test_errors_module_exports(self):
        for name in ("MetadataError", "MetadataNotFound", "MetadataUnavailable", "MetadataRateLimited"):
            self.assertTrue(hasattr(errors_mod, name))


if __name__ == "__main__":
    unittest.main()
