"""M2.10 QQProvider 单元测试。

策略同 NeteaseProvider 测试：mock HttpClient，按 QQ 真实响应结构喂样本。
覆盖：
- search（song 类型 + 其他类型未实现）
- get_song（成功 + 缺字段 + business code != 0）
- get_lyric（带翻译 + 不带翻译 + base64 解码）
- get_similar（search fallback：去掉自己 + top 5）
- 未实现方法：get_artist / get_album / get_playlist 抛 MetadataNotFound；
  get_charts 返回 []
- 公共：name / 满足 MetadataProvider Protocol / 业务码校验
"""
from __future__ import annotations

import base64
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path := __import__("pathlib").Path(__file__).resolve().parents[1]))

from core.metadata import (
    HttpClient,
    MetadataNotFound,
    MetadataUnavailable,
    SongDetail,
    LyricContent,
    Hit,
)
from core.metadata.providers import QQProvider


def _ok(payload):
    return {"code": 0, **(payload or {})}


def _lrc_b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


# ───────────────────── search ─────────────────────


class SearchTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self._payload = _ok({
            "data": {
                "song": {
                    "list": [
                        {
                            "songname": "七里香",
                            "songmid": "001gJR2P0UxWGm",
                            "singer": [{"name": "周杰伦", "mid": "003aQYLo2x8izx"}],
                            "albumname": "七里香",
                            "albummid": "002aQYLo2x8izx",
                            "interval": 234,
                        },
                        {
                            "songname": "晴天",
                            "songmid": "001gJR2P0UxWGN",
                            "singer": [{"name": "周杰伦", "mid": "003aQYLo2x8izx"}],
                            "albumname": "叶惠美",
                            "albummid": "002aQYLo2x8izx2",
                            "interval": 269,
                        },
                    ]
                }
            }
        })

        def _fake(url, *, params=None):
            self.calls.append((url, params))
            return self._payload

        self.http = mock.MagicMock(spec=HttpClient)
        self.http.get_json.side_effect = _fake
        self.provider = QQProvider(self.http)

    def test_search_returns_hits(self):
        hits = self.provider.search("周杰伦", limit=20)
        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0].title, "七里香")
        self.assertEqual(hits[0].artist, "周杰伦")
        self.assertEqual(hits[0].album, "七里香")
        self.assertEqual(hits[0].duration_ms, 234000)
        self.assertEqual(hits[0].source, "qq")
        self.assertEqual(hits[0].song_id, "001gJR2P0UxWGm")

    def test_search_uses_correct_url(self):
        self.provider.search("周杰伦")
        url, params = self.calls[0]
        self.assertIn("client_search_cp", url)
        self.assertEqual(params["w"], "周杰伦")
        self.assertEqual(params["n"], 20)
        self.assertEqual(params["t"], 0)

    def test_search_empty_keyword(self):
        self.assertEqual(self.provider.search(""), [])
        self.assertEqual(self.http.get_json.call_count, 0)

    def test_search_artist_type_not_supported(self):
        with self.assertRaises(MetadataNotFound):
            self.provider.search("周杰伦", type="artist")

    def test_search_business_code_not_0(self):
        self._payload = {"code": 1, "msg": "频率过高"}
        with self.assertRaises(MetadataUnavailable):
            self.provider.search("kw")

    def test_search_no_code_field_ok(self):
        # 部分端点不返回 code，应按成功处理
        self._payload = {
            "data": {"song": {"list": []}},
        }
        # 仍能正常返回空列表
        self.assertEqual(self.provider.search("kw"), [])

    def test_search_skips_song_without_mid(self):
        self._payload = _ok({
            "data": {"song": {"list": [{"songname": "x", "songmid": "", "singer": []}]}},
        })
        self.assertEqual(self.provider.search("kw"), [])

    def test_search_clamps_limit(self):
        self.provider.search("kw", limit=999)
        params = self.calls[0][1]
        self.assertEqual(params["n"], 50)  # clamp 到 50

    def test_search_multiple_singers(self):
        self._payload = _ok({
            "data": {"song": {"list": [{
                "songname": "合唱", "songmid": "x1",
                "singer": [{"name": "A"}, {"name": "B"}, {"name": "C"}],
                "albumname": "x", "interval": 0,
            }]}},
        })
        hits = self.provider.search("kw")
        self.assertEqual(hits[0].artist, "A / B / C")


# ───────────────────── get_song ─────────────────────


class GetSongTest(unittest.TestCase):
    def setUp(self):
        self.http = mock.MagicMock(spec=HttpClient)
        self.http.get_json.return_value = _ok({
            "data": [{
                "mid": "001gJR2P0UxWGm",
                "name": "七里香",
                "singer": [{"name": "周杰伦", "mid": "003aQYLo2x8izx"}],
                "album": {"name": "七里香", "mid": "002aQYLo2x8izx"},
                "interval": 234,
            }],
        })
        self.provider = QQProvider(self.http)

    def test_returns_song_detail(self):
        d = self.provider.get_song("001gJR2P0UxWGm")
        self.assertIsInstance(d, SongDetail)
        self.assertEqual(d.song_id, "001gJR2P0UxWGm")
        self.assertEqual(d.title, "七里香")
        self.assertEqual(d.artist, "周杰伦")
        self.assertEqual(d.artist_id, "003aQYLo2x8izx")
        self.assertEqual(d.album, "七里香")
        self.assertEqual(d.album_id, "002aQYLo2x8izx")
        self.assertEqual(d.duration_ms, 234000)
        self.assertEqual(d.source, "qq")

    def test_uses_correct_url(self):
        self.provider.get_song("001gJR2P0UxWGm")
        url, params = self.http.get_json.call_args.args[0], self.http.get_json.call_args.kwargs.get("params", {})
        self.assertIn("fcg_play_single_song", url)
        self.assertEqual(params["songmid"], "001gJR2P0UxWGm")

    def test_empty_id_raises(self):
        with self.assertRaises(MetadataNotFound):
            self.provider.get_song("")

    def test_no_data_raises(self):
        self.http.get_json.return_value = _ok({"data": []})
        with self.assertRaises(MetadataNotFound):
            self.provider.get_song("001gJR2P0UxWGm")

    def test_parse_failure_raises(self):
        self.http.get_json.return_value = _ok({"data": [{"mid": "", "name": "x"}]})
        with self.assertRaises(MetadataNotFound):
            self.provider.get_song("001gJR2P0UxWGm")

    def test_business_code_not_0(self):
        self.http.get_json.return_value = {"code": 1}
        with self.assertRaises(MetadataUnavailable):
            self.provider.get_song("001gJR2P0UxWGm")

    def test_alt_field_names_songname(self):
        """部分响应可能用 songname/name 任一字段。"""
        self.http.get_json.return_value = _ok({
            "data": [{
                "songmid": "001gJR2P0UxWGm",
                "songname": "七里香",  # 备用字段
                "singer": [{"name": "周杰伦"}],
                "albumname": "七里香",  # 备用字段
                "interval": 234,
            }],
        })
        d = self.provider.get_song("001gJR2P0UxWGm")
        self.assertEqual(d.title, "七里香")
        self.assertEqual(d.album, "七里香")

    def test_no_artist_id_when_singer_has_no_mid(self):
        self.http.get_json.return_value = _ok({
            "data": [{
                "mid": "1", "name": "x",
                "singer": [{"name": "y"}],  # 无 mid
                "album": {}, "interval": 0,
            }],
        })
        d = self.provider.get_song("1")
        self.assertIsNone(d.artist_id)


# ───────────────────── get_lyric ─────────────────────


class GetLyricTest(unittest.TestCase):
    def setUp(self):
        self.http = mock.MagicMock(spec=HttpClient)
        self.provider = QQProvider(self.http)

    def test_with_translation(self):
        lrc = "[00:00.00]hello\n[00:01.00]world"
        trans = "[00:00.00]你好\n[00:01.00]世界"
        self.http.get_json.return_value = {
            "code": 0,
            "lyric": _lrc_b64(lrc),
            "trans": _lrc_b64(trans),
        }
        c = self.provider.get_lyric("001gJR2P0UxWGm")
        self.assertIsInstance(c, LyricContent)
        self.assertEqual(c.lrc_text, lrc)
        self.assertEqual(c.translated_lrc, trans)
        self.assertEqual(c.source, "qq")
        self.assertEqual(c.song_id, "001gJR2P0UxWGm")

    def test_without_translation(self):
        lrc = "[00:00]x"
        self.http.get_json.return_value = {
            "code": 0,
            "lyric": _lrc_b64(lrc),
            "trans": "",
        }
        c = self.provider.get_lyric("001gJR2P0UxWGm")
        self.assertIsNotNone(c)
        self.assertIsNone(c.translated_lrc)

    def test_no_lyric_returns_none(self):
        self.http.get_json.return_value = {"code": 0, "lyric": ""}
        self.assertIsNone(self.provider.get_lyric("001gJR2P0UxWGm"))

    def test_empty_id(self):
        self.assertIsNone(self.provider.get_lyric(""))

    def test_uses_lyric_url(self):
        self.http.get_json.return_value = {"code": 0, "lyric": ""}
        self.provider.get_lyric("001gJR2P0UxWGm")
        url, params = self.http.get_json.call_args.args[0], self.http.get_json.call_args.kwargs.get("params", {})
        self.assertIn("fcg_query_lyric_new", url)
        self.assertEqual(params["songmid"], "001gJR2P0UxWGm")
        self.assertEqual(params["nobase64"], 0)

    def test_business_code_not_0(self):
        self.http.get_json.return_value = {"code": 1}
        with self.assertRaises(MetadataUnavailable):
            self.provider.get_lyric("001gJR2P0UxWGm")


# ───────────────────── get_similar ─────────────────────


class GetSimilarTest(unittest.TestCase):
    def setUp(self):
        self.http = mock.MagicMock(spec=HttpClient)

        def _fake(url, *, params=None):
            # 第一次是 get_song，第二次是 search
            if "fcg_play_single_song" in url:
                return _ok({
                    "data": [{
                        "mid": "001gJR2P0UxWGm",
                        "name": "七里香",
                        "singer": [{"name": "周杰伦"}],
                        "album": {}, "interval": 0,
                    }],
                })
            elif "client_search_cp" in url:
                return _ok({
                    "data": {"song": {"list": [
                        {"songname": "七里香", "songmid": "001gJR2P0UxWGm",  # self
                         "singer": [{"name": "周杰伦"}], "albumname": "x", "interval": 0},
                        {"songname": "晴天", "songmid": "001gJR2P0UxWGN",
                         "singer": [{"name": "周杰伦"}], "albumname": "x", "interval": 0},
                        {"songname": "夜曲", "songmid": "001gJR2P0UxWGQ",
                         "singer": [{"name": "周杰伦"}], "albumname": "x", "interval": 0},
                    ]}},
                })
            return {}
        self.http.get_json.side_effect = _fake
        self.provider = QQProvider(self.http)

    def test_returns_similar_excluding_self(self):
        hits = self.provider.get_similar("001gJR2P0UxWGm")
        self.assertEqual(len(hits), 2)
        # 第一个 hit 不应是 self
        for h in hits:
            self.assertNotEqual(h.song_id, "001gJR2P0UxWGm")
        self.assertEqual(hits[0].title, "晴天")
        self.assertEqual(hits[1].title, "夜曲")

    def test_empty_id(self):
        self.assertEqual(self.provider.get_similar(""), [])

    def test_song_not_found(self):
        # get_song 抛 NotFound → get_similar 返回空
        def _raise(url, *, params=None):
            if "fcg_play_single_song" in url:
                raise MetadataNotFound("not found")
            return _ok({"data": {"song": {"list": []}}})
        self.http.get_json.side_effect = _raise
        self.assertEqual(self.provider.get_similar("x"), [])


# ───────────────────── 未实现方法 ─────────────────────


class UnimplementedTest(unittest.TestCase):
    def setUp(self):
        self.http = mock.MagicMock(spec=HttpClient)
        self.provider = QQProvider(self.http)

    def test_get_artist_raises_not_found(self):
        with self.assertRaises(MetadataNotFound):
            self.provider.get_artist("1")
        # 不应调 API
        self.assertEqual(self.http.get_json.call_count, 0)

    def test_get_album_raises_not_found(self):
        with self.assertRaises(MetadataNotFound):
            self.provider.get_album("1")
        self.assertEqual(self.http.get_json.call_count, 0)

    def test_get_playlist_raises_not_found(self):
        with self.assertRaises(MetadataNotFound):
            self.provider.get_playlist("1")
        self.assertEqual(self.http.get_json.call_count, 0)

    def test_get_charts_returns_empty(self):
        # 返回空列表（不抛错，让 Router 跳下一个）
        self.assertEqual(self.provider.get_charts(), [])
        self.assertEqual(self.http.get_json.call_count, 0)


# ───────────────────── 公共 ─────────────────────


class CommonTest(unittest.TestCase):
    def test_name(self):
        self.assertEqual(QQProvider.name, "qq")

    def test_custom_base(self):
        http = mock.MagicMock(spec=HttpClient)
        http.get_json.return_value = _ok({"data": {"song": {"list": []}}})
        p = QQProvider(http, base="https://example.com/")
        p.search("kw")
        url = http.get_json.call_args.args[0]
        self.assertTrue(url.startswith("https://example.com/soso/"))

    def test_default_http_client(self):
        p = QQProvider()
        self.assertIsNotNone(p._http)

    def test_satisfies_metadata_provider_protocol(self):
        from core.metadata import MetadataProvider
        p: MetadataProvider = QQProvider()
        for method in ("search", "get_song", "get_artist", "get_album",
                       "get_playlist", "get_lyric", "get_charts", "get_similar"):
            self.assertTrue(hasattr(p, method))
            self.assertTrue(callable(getattr(p, method)))

    def test_unavailable_propagation(self):
        from core.metadata import MetadataUnavailable
        http = mock.MagicMock(spec=HttpClient)
        http.get_json.side_effect = MetadataUnavailable([("upstream", OSError())])
        p = QQProvider(http)
        with self.assertRaises(MetadataUnavailable):
            p.search("kw")


# ───────────────────── Router 集成：QQ + Netease 回退 ─────────────────────


class RouterIntegrationTest(unittest.TestCase):
    """QQ 作为 Netease 失败时的回退。"""

    def test_netease_fails_qq_takes_over(self):
        from core.metadata import (
            MetadataCache, MetadataRouter, NeteaseProvider, QQProvider,
            MetadataUnavailable,
        )
        import tempfile
        from pathlib import Path

        cache_dir = Path(tempfile.mkdtemp(prefix="qq_router_"))
        cache = MetadataCache(cache_dir)
        # 构造两个 provider，QQ 是 fake
        netease = mock.MagicMock()
        netease.name = "netease"
        netease.search.side_effect = MetadataUnavailable([("netease", OSError())])
        qq = QQProvider()
        # Mock QQ 的 http
        qq_http = mock.MagicMock(spec=HttpClient)
        qq_http.get_json.return_value = _ok({
            "data": {"song": {"list": [{
                "songname": "七里香", "songmid": "001gJR2P0UxWGm",
                "singer": [{"name": "周杰伦"}], "albumname": "七里香", "interval": 234,
            }]}},
        })
        qq._http = qq_http
        router = MetadataRouter([netease, qq], cache=cache)
        hits = router.search("周杰伦")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].source, "qq")
        # netease 应被调过
        netease.search.assert_called_once()
        # qq 也应被调过
        qq_http.get_json.assert_called()

    def test_netease_success_qq_not_called(self):
        from core.metadata import (
            MetadataCache, MetadataRouter, NeteaseProvider, QQProvider,
        )
        from core.metadata import Hit
        from pathlib import Path
        import tempfile

        cache_dir = Path(tempfile.mkdtemp(prefix="qq_router2_"))
        cache = MetadataCache(cache_dir)
        netease_hit = Hit(source="netease", song_id="1", title="t", artist="x")
        netease = mock.MagicMock()
        netease.name = "netease"
        netease.search.return_value = [netease_hit]
        qq = QQProvider()
        qq_http = mock.MagicMock(spec=HttpClient)
        qq._http = qq_http
        router = MetadataRouter([netease, qq], cache=cache)
        hits = router.search("x")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].source, "netease")
        # qq 不应被调
        qq_http.get_json.assert_not_called()


if __name__ == "__main__":
    unittest.main()
