"""M2.8 NeteaseProvider 单元测试。

策略：用 mock 替换 HttpClient 的 get_json，按网易云真实响应结构喂样本。
覆盖：
- 全部 8 个方法（search/get_song/get_lyric/get_artist/get_album/get_playlist/get_charts/get_similar）
- 正常 + 边界（空 / 缺字段 / 业务码非 200）
- 元数据字段映射正确
- 元数据 NotFound / Unavailable 上抛
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.metadata import (
    Hit,
    HttpClient,
    MetadataNotFound,
    MetadataUnavailable,
    SongDetail,
    LyricContent,
    ArtistDetail,
    AlbumDetail,
    PlaylistDetail,
    Chart,
)
from core.metadata.providers import NeteaseProvider


def _ok(payload):
    """构造 code=200 的网易云响应。"""
    return {"code": 200, **(payload or {})}


# ───────────────────── search ─────────────────────


class SearchTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        # 用 mutable payload 让 test 可以重写响应
        self._payload = _ok({
            "result": {
                "songs": [
                    {
                        "id": 123,
                        "name": "七里香",
                        "artists": [{"id": 1, "name": "周杰伦"}],
                        "album": {"id": 2, "name": "七里香", "picUrl": "http://x/cover.jpg"},
                        "duration": 234000,
                    },
                    {
                        "id": 456,
                        "name": "晴天",
                        "artists": [{"id": 1, "name": "周杰伦"}],
                        "album": {"id": 3, "name": "叶惠美", "picUrl": "http://x/cover2.jpg"},
                        "duration": 269000,
                    },
                ]
            }
        })

        def _fake_get_json(url, *, params=None):
            self.calls.append((url, params))
            return self._payload

        self.http = mock.MagicMock(spec=HttpClient)
        self.http.get_json.side_effect = _fake_get_json
        self.provider = NeteaseProvider(self.http)

    def test_search_returns_hits(self):
        hits = self.provider.search("周杰伦", limit=20)
        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0].title, "七里香")
        self.assertEqual(hits[0].artist, "周杰伦")
        self.assertEqual(hits[0].album, "七里香")
        self.assertEqual(hits[0].duration_ms, 234000)
        self.assertEqual(hits[0].cover_url, "http://x/cover.jpg")
        self.assertEqual(hits[0].source, "netease")
        self.assertEqual(hits[0].song_id, "123")

    def test_search_uses_correct_url(self):
        self.provider.search("周杰伦")
        url, params = self.calls[0]
        self.assertIn("music.163.com/api/search/get", url)
        self.assertEqual(params["s"], "周杰伦")
        self.assertEqual(params["type"], 1)  # song
        self.assertEqual(params["limit"], 20)

    def test_search_empty_keyword_returns_empty(self):
        self.assertEqual(self.provider.search(""), [])
        self.assertEqual(self.provider.search("   "), [])
        # 不应调 API
        self.assertEqual(self.http.get_json.call_count, 0)

    def test_search_no_results(self):
        self._payload = _ok({"result": {"songs": []}})
        self.assertEqual(self.provider.search("不存在的歌xyz"), [])

    def test_search_skips_song_without_id(self):
        self._payload = _ok({
            "result": {"songs": [{"id": None, "name": "no id"}]},
        })
        self.assertEqual(self.provider.search("kw"), [])

    def test_search_clamps_limit(self):
        self.provider.search("kw", limit=999)
        params = self.calls[0][1]
        self.assertEqual(params["limit"], 100)  # clamp 到 100

    def test_search_business_code_not_200_raises(self):
        self._payload = {"code": 301, "msg": "需要登录"}
        with self.assertRaises(MetadataUnavailable):
            self.provider.search("kw")

    def test_search_type_artist(self):
        self.provider.search("周杰伦", type="artist")
        params = self.calls[0][1]
        self.assertEqual(params["type"], 100)

    def test_search_type_album(self):
        self.provider.search("kw", type="album")
        self.assertEqual(self.calls[0][1]["type"], 10)

    def test_search_type_playlist(self):
        self.provider.search("kw", type="playlist")
        self.assertEqual(self.calls[0][1]["type"], 1000)

    def test_search_multiple_artists_joined(self):
        self._payload = _ok({
            "result": {"songs": [{
                "id": 1, "name": "合唱",
                "artists": [{"name": "A"}, {"name": "B"}, {"name": "C"}],
                "album": {}, "duration": 0,
            }]},
        })
        hits = self.provider.search("kw")
        self.assertEqual(hits[0].artist, "A / B / C")


# ───────────────────── get_song ─────────────────────


class GetSongTest(unittest.TestCase):
    def setUp(self):
        self.http = mock.MagicMock(spec=HttpClient)
        self.http.get_json.return_value = _ok({
            "songs": [{
                "id": 123,
                "name": "七里香",
                "artists": [{"id": 1, "name": "周杰伦"}],
                "album": {"id": 2, "name": "七里香", "picUrl": "http://x/cover.jpg"},
                "duration": 234000,
            }],
        })
        self.provider = NeteaseProvider(self.http)

    def test_returns_song_detail(self):
        d = self.provider.get_song("123")
        self.assertIsInstance(d, SongDetail)
        self.assertEqual(d.song_id, "123")
        self.assertEqual(d.title, "七里香")
        self.assertEqual(d.artist, "周杰伦")
        self.assertEqual(d.artist_id, "1")
        self.assertEqual(d.album, "七里香")
        self.assertEqual(d.album_id, "2")
        self.assertEqual(d.duration_ms, 234000)
        self.assertEqual(d.cover_url, "http://x/cover.jpg")
        self.assertEqual(d.source, "netease")

    def test_uses_song_detail_url(self):
        self.provider.get_song("123")
        url, params = self.http.get_json.call_args.args[0], self.http.get_json.call_args.kwargs.get("params", {})
        self.assertIn("music.163.com/api/song/detail", url)
        self.assertEqual(params["ids"], "[123]")

    def test_empty_id_raises_not_found(self):
        with self.assertRaises(MetadataNotFound):
            self.provider.get_song("")

    def test_response_song_id_mismatch_raises_not_found(self):
        # API 返回的 song_id 跟请求不一致
        self.http.get_json.return_value = _ok({
            "songs": [{"id": 999, "name": "x", "artists": [], "album": {}}],
        })
        with self.assertRaises(MetadataNotFound):
            self.provider.get_song("123")

    def test_empty_songs_list_raises_not_found(self):
        self.http.get_json.return_value = _ok({"songs": []})
        with self.assertRaises(MetadataNotFound):
            self.provider.get_song("123")

    def test_song_without_duration_returns_zero(self):
        self.http.get_json.return_value = _ok({
            "songs": [{"id": 1, "name": "x", "artists": [], "album": {}, "duration": None}],
        })
        d = self.provider.get_song("1")
        self.assertEqual(d.duration_ms, 0)


# ───────────────────── get_lyric ─────────────────────


class GetLyricTest(unittest.TestCase):
    def setUp(self):
        self.http = mock.MagicMock(spec=HttpClient)
        self.provider = NeteaseProvider(self.http)

    def test_with_translation(self):
        self.http.get_json.return_value = _ok({
            "lrc": {"lyric": "[00:00.00]hello\n[00:01.00]world"},
            "tlyric": {"lyric": "[00:00.00]你好\n[00:01.00]世界"},
        })
        c = self.provider.get_lyric("123")
        self.assertIsInstance(c, LyricContent)
        self.assertIn("hello", c.lrc_text)
        self.assertIn("你好", c.translated_lrc or "")
        self.assertEqual(c.source, "netease")
        self.assertEqual(c.song_id, "123")

    def test_without_translation(self):
        self.http.get_json.return_value = _ok({
            "lrc": {"lyric": "[00:00.00]hello"},
            "tlyric": {"lyric": ""},  # 网易云偶有 lyric="" 的情况
        })
        c = self.provider.get_lyric("123")
        self.assertIsNotNone(c)
        self.assertIsNone(c.translated_lrc)

    def test_no_lyric_returns_none(self):
        self.http.get_json.return_value = _ok({
            "lrc": {"lyric": ""},
        })
        self.assertIsNone(self.provider.get_lyric("123"))

    def test_empty_lrc_object_returns_none(self):
        self.http.get_json.return_value = _ok({"lrc": {}})
        self.assertIsNone(self.provider.get_lyric("123"))

    def test_empty_id_returns_none(self):
        self.assertIsNone(self.provider.get_lyric(""))

    def test_uses_lyric_url(self):
        self.http.get_json.return_value = _ok({"lrc": {"lyric": "[00:00]x"}})
        self.provider.get_lyric("123")
        url, params = self.http.get_json.call_args.args[0], self.http.get_json.call_args.kwargs.get("params", {})
        self.assertIn("music.163.com/api/song/lyric", url)
        self.assertEqual(params["id"], "123")
        self.assertEqual(params["lv"], 1)
        self.assertEqual(params["kv"], 1)
        self.assertEqual(params["tv"], -1)


# ───────────────────── get_artist ─────────────────────


class GetArtistTest(unittest.TestCase):
    def setUp(self):
        self.http = mock.MagicMock(spec=HttpClient)
        self.http.get_json.return_value = _ok({
            "artist": {
                "id": 1,
                "name": "周杰伦",
                "briefDesc": "华语流行男歌手",
                "img1v1Url": "http://x/avatar.jpg",
            },
            "hotSongs": [
                {"id": 11, "name": "七里香", "artists": [{"name": "周杰伦"}], "album": {}, "duration": 0},
                {"id": 12, "name": "晴天", "artists": [{"name": "周杰伦"}], "album": {}, "duration": 0},
            ],
        })
        self.provider = NeteaseProvider(self.http)

    def test_returns_artist_detail(self):
        a = self.provider.get_artist("1")
        self.assertIsInstance(a, ArtistDetail)
        self.assertEqual(a.artist_id, "1")
        self.assertEqual(a.name, "周杰伦")
        self.assertEqual(a.bio, "华语流行男歌手")
        self.assertEqual(a.avatar_url, "http://x/avatar.jpg")
        self.assertEqual(len(a.songs), 2)

    def test_empty_artist_name_raises_not_found(self):
        self.http.get_json.return_value = _ok({
            "artist": {"id": 999, "name": ""},
        })
        with self.assertRaises(MetadataNotFound):
            self.provider.get_artist("999")

    def test_no_hot_songs(self):
        self.http.get_json.return_value = _ok({
            "artist": {"id": 1, "name": "x", "img1v1Url": "..."},
        })
        a = self.provider.get_artist("1")
        self.assertEqual(a.songs, [])

    def test_uses_artist_url(self):
        self.provider.get_artist("1")
        url = self.http.get_json.call_args[0][0]
        self.assertIn("music.163.com/api/v1/artist/1", url)


# ───────────────────── get_album ─────────────────────


class GetAlbumTest(unittest.TestCase):
    def setUp(self):
        self.http = mock.MagicMock(spec=HttpClient)
        self.http.get_json.return_value = _ok({
            "album": {
                "id": 2,
                "name": "七里香",
                "artists": [{"name": "周杰伦"}],
                "picUrl": "http://x/album.jpg",
                "publishTime": 1091308800000,  # 2004-08-01 ms
            },
            "songs": [
                {"id": 11, "name": "七里香", "artists": [{"name": "周杰伦"}], "album": {}, "duration": 0},
            ],
        })
        self.provider = NeteaseProvider(self.http)

    def test_returns_album_detail(self):
        a = self.provider.get_album("2")
        self.assertIsInstance(a, AlbumDetail)
        self.assertEqual(a.album_id, "2")
        self.assertEqual(a.title, "七里香")
        self.assertEqual(a.artist, "周杰伦")
        self.assertEqual(a.cover_url, "http://x/album.jpg")
        self.assertEqual(a.release_date, "2004-07-31")  # UTC 8月1日 0点 = UTC 7月31日 16点
        self.assertEqual(len(a.songs), 1)

    def test_no_publish_time(self):
        self.http.get_json.return_value = _ok({
            "album": {"id": 2, "name": "x", "artists": []},
            "songs": [],
        })
        a = self.provider.get_album("2")
        self.assertIsNone(a.release_date)

    def test_empty_id_raises_not_found(self):
        with self.assertRaises(MetadataNotFound):
            self.provider.get_album("")


# ───────────────────── get_playlist ─────────────────────


class GetPlaylistTest(unittest.TestCase):
    def setUp(self):
        self.http = mock.MagicMock(spec=HttpClient)
        self.http.get_json.return_value = _ok({
            "playlist": {
                "id": 100,
                "name": "我喜欢的音乐",
                "creator": {"nickname": "主播小王"},
                "coverImgUrl": "http://x/pl.jpg",
                "description": "个人精选",
                "playCount": 12345,
                "tracks": [
                    {"id": 11, "name": "七里香", "artists": [{"name": "周杰伦"}], "album": {}, "duration": 0},
                ],
            },
        })
        self.provider = NeteaseProvider(self.http)

    def test_returns_playlist_detail(self):
        p = self.provider.get_playlist("100")
        self.assertIsInstance(p, PlaylistDetail)
        self.assertEqual(p.playlist_id, "100")
        self.assertEqual(p.title, "我喜欢的音乐")
        self.assertEqual(p.creator, "主播小王")
        self.assertEqual(p.cover_url, "http://x/pl.jpg")
        self.assertEqual(p.description, "个人精选")
        self.assertEqual(p.play_count, 12345)
        self.assertEqual(len(p.songs), 1)

    def test_no_creator(self):
        self.http.get_json.return_value = _ok({
            "playlist": {
                "id": 100, "name": "x",
                "creator": None, "tracks": [],
            },
        })
        p = self.provider.get_playlist("100")
        self.assertIsNone(p.creator)

    def test_uses_v6_playlist_url(self):
        self.provider.get_playlist("100")
        url, params = self.http.get_json.call_args.args[0], self.http.get_json.call_args.kwargs.get("params", {})
        self.assertIn("music.163.com/api/v6/playlist/detail", url)
        self.assertEqual(params["id"], "100")
        self.assertEqual(params["n"], 1000)


# ───────────────────── get_charts ─────────────────────


class GetChartsTest(unittest.TestCase):
    def setUp(self):
        self.http = mock.MagicMock(spec=HttpClient)
        self.http.get_json.return_value = _ok({
            "list": [
                {"id": 19723756, "name": "飙升榜", "coverImgUrl": "http://x/c1.jpg", "description": "上升最快"},
                {"id": 3779629, "name": "原创榜", "coverImgUrl": "http://x/c2.jpg"},
                {"id": 2884035, "name": "热歌榜", "description": "最热"},
            ],
        })
        self.provider = NeteaseProvider(self.http)

    def test_returns_charts(self):
        charts = self.provider.get_charts()
        self.assertEqual(len(charts), 3)
        self.assertEqual(charts[0].title, "飙升榜")
        self.assertEqual(charts[0].chart_id, "19723756")
        self.assertEqual(charts[0].cover_url, "http://x/c1.jpg")
        self.assertEqual(charts[0].description, "上升最快")

    def test_charts_without_optional_fields(self):
        self.http.get_json.return_value = _ok({
            "list": [{"id": 1, "name": "x"}],
        })
        charts = self.provider.get_charts()
        self.assertEqual(len(charts), 1)
        self.assertIsNone(charts[0].cover_url)
        self.assertIsNone(charts[0].description)

    def test_empty_list(self):
        self.http.get_json.return_value = _ok({"list": []})
        self.assertEqual(self.provider.get_charts(), [])

    def test_uses_toplist_url(self):
        self.provider.get_charts()
        url = self.http.get_json.call_args[0][0]
        self.assertIn("music.163.com/api/toplist", url)


# ───────────────────── get_similar ─────────────────────


class GetSimilarTest(unittest.TestCase):
    def setUp(self):
        self.http = mock.MagicMock(spec=HttpClient)
        self.http.get_json.return_value = _ok({
            "songs": [
                {"id": 22, "name": "晴天", "artists": [{"name": "周杰伦"}], "album": {}, "duration": 0},
                {"id": 33, "name": "夜曲", "artists": [{"name": "周杰伦"}], "album": {}, "duration": 0},
            ],
        })
        self.provider = NeteaseProvider(self.http)

    def test_returns_similar(self):
        hits = self.provider.get_similar("11")
        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0].title, "晴天")

    def test_empty_id(self):
        self.assertEqual(self.provider.get_similar(""), [])

    def test_uses_simi_url(self):
        self.provider.get_similar("11")
        url, params = self.http.get_json.call_args.args[0], self.http.get_json.call_args.kwargs.get("params", {})
        self.assertIn("music.163.com/api/v1/discovery/simiSong", url)
        self.assertEqual(params["id"], "11")


# ───────────────────── 公共 ─────────────────────


class ProviderCommonTest(unittest.TestCase):
    def test_name(self):
        self.assertEqual(NeteaseProvider.name, "netease")

    def test_custom_base(self):
        http = mock.MagicMock(spec=HttpClient)
        http.get_json.return_value = _ok({"result": {"songs": []}})
        p = NeteaseProvider(http, base="https://example.com/")
        p.search("kw")
        url = http.get_json.call_args[0][0]
        self.assertTrue(url.startswith("https://example.com/api/"))

    def test_default_http_client(self):
        # 不传 http 应自动建一个
        p = NeteaseProvider()
        self.assertIsNotNone(p._http)

    def test_satisfies_metadata_provider_protocol(self):
        """NeteaseProvider 应满足 MetadataProvider Protocol。"""
        from core.metadata import MetadataProvider
        p: MetadataProvider = NeteaseProvider()
        # 全部 8 个方法存在
        for method in ("search", "get_song", "get_artist", "get_album",
                       "get_playlist", "get_lyric", "get_charts", "get_similar"):
            self.assertTrue(hasattr(p, method))
            self.assertTrue(callable(getattr(p, method)))

    def test_unavailable_propagation(self):
        """HttpClient 抛 MetadataUnavailable 应直接传播。"""
        from core.metadata import MetadataUnavailable
        http = mock.MagicMock(spec=HttpClient)
        http.get_json.side_effect = MetadataUnavailable([("upstream", OSError())])
        p = NeteaseProvider(http)
        with self.assertRaises(MetadataUnavailable):
            p.search("kw")


if __name__ == "__main__":
    unittest.main()
