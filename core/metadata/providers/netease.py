"""M2.8 网易云音乐 NeteaseProvider。

实现的 API 端点（均无需登录，公开接口）：
- 搜索歌曲：GET https://music.163.com/api/search/get?s=KEYWORD&type=1&limit=N
- 歌曲详情：GET https://music.163.com/api/song/detail?ids=[ID1,ID2]
- LRC 歌词：  GET https://music.163.com/api/song/lyric?id=ID&lv=1&kv=1&tv=-1
- 艺人详情：GET https://music.163.com/api/v1/artist/{id}
- 专辑详情：GET https://music.163.com/api/v1/album/{id}
- 歌单详情：GET https://music.163.com/api/v6/playlist/detail?id=ID&n=1000&s=0
- 官方榜单：GET https://music.163.com/api/toplist
- 相似歌曲：GET https://music.163.com/api/v1/discovery/simiSong?id=ID

限制：
- 全部用 stdlib urllib.request + 默认 User-Agent
- 只用未加密的 /api/... 端点；weapi 加密端点（M2.x 后续如需再做）
- 部分歌单/榜单的 chart_id 用稳定 ID（与社区一致）

错误处理：
- HTTP 5xx / 网络错误 → MetadataUnavailable（由 HttpClient 处理 + 重试）
- HTTP 429 → MetadataRateLimited
- 业务码 != 200（网易云偶有 code != 200）→ 当作 unavailable
- 找不到字段 → 跳过该条（容错优先）
"""
from __future__ import annotations

from typing import Any

from ..errors import MetadataNotFound, MetadataUnavailable
from ..http_client import HttpClient
from ..types import (
    AlbumDetail,
    ArtistDetail,
    Chart,
    Hit,
    LyricContent,
    PlaylistDetail,
    SongDetail,
)

API_BASE = "https://music.163.com"
DEFAULT_TIMEOUT = 10.0


def _ms(duration: Any) -> int:
    """网易云 duration 字段是毫秒 int；有时返回 None。"""
    if duration is None:
        return 0
    try:
        return int(duration)
    except (TypeError, ValueError):
        return 0


def _artist_name(artists: list[dict]) -> str:
    """合并 artists 数组为 'a / b' 形式。"""
    names = [a.get("name", "") for a in (artists or []) if a]
    return " / ".join(n for n in names if n)


def _first_artist_id(artists: list[dict]) -> str | None:
    if not artists:
        return None
    aid = artists[0].get("id")
    return str(aid) if aid is not None else None


def _hit_from_song(song: dict) -> Hit | None:
    """从搜索结果 songs[].xx 构造 Hit。"""
    if not song:
        return None
    sid = song.get("id")
    title = song.get("name")
    if sid is None or not title:
        return None
    artists = song.get("artists") or []
    album_obj = song.get("album") or {}
    return Hit(
        source="netease",
        song_id=str(sid),
        title=title,
        artist=_artist_name(artists) or "",
        album=album_obj.get("name"),
        duration_ms=_ms(song.get("duration")),
        cover_url=album_obj.get("picUrl"),
    )


def _song_detail_from_song(song: dict) -> SongDetail | None:
    """从 /song/detail 返回的 songs[] 构造 SongDetail。"""
    if not song:
        return None
    sid = song.get("id")
    title = song.get("name")
    if sid is None or not title:
        return None
    artists = song.get("artists") or []
    album_obj = song.get("album") or {}
    return SongDetail(
        source="netease",
        song_id=str(sid),
        title=title,
        artist=_artist_name(artists) or "",
        artist_id=_first_artist_id(artists),
        album=album_obj.get("name"),
        album_id=str(album_obj["id"]) if album_obj.get("id") is not None else None,
        duration_ms=_ms(song.get("duration")),
        cover_url=album_obj.get("picUrl"),
    )


class NeteaseProvider:
    """网易云音乐元数据 provider。

    M2.8 阶段实现 search / get_song / get_artist / get_album / get_playlist /
    get_lyric / get_charts / get_similar 全套。
    """

    name = "netease"

    def __init__(self, http: HttpClient | None = None, *, base: str = API_BASE):
        self._http = http or HttpClient(timeout=DEFAULT_TIMEOUT)
        self._base = base.rstrip("/")

    # ── search ──

    def search(
        self,
        keyword: str,
        *,
        type: str = "song",
        limit: int = 20,
    ) -> list[Hit]:
        if not keyword or not keyword.strip():
            return []
        # 网易云 type: 1=song, 100=artist, 10=album, 1000=playlist
        type_map = {"song": 1, "artist": 100, "album": 10, "playlist": 1000}
        ne_type = type_map.get(type, 1)
        url = f"{self._base}/api/search/get"
        data = self._http.get_json(url, params={
            "s": keyword.strip(), "type": ne_type, "limit": max(1, min(limit, 100)),
        })
        self._check_business_code(data)
        result = data.get("result") or {}
        songs = result.get("songs") or []
        hits = []
        for s in songs:
            h = _hit_from_song(s)
            if h is not None:
                hits.append(h)
        return hits

    # ── get_song ──

    def get_song(self, song_id: str) -> SongDetail:
        if not song_id:
            raise MetadataNotFound("empty song_id")
        url = f"{self._base}/api/song/detail"
        data = self._http.get_json(url, params={"ids": f"[{song_id}]"})
        self._check_business_code(data)
        songs = data.get("songs") or []
        for s in songs:
            d = _song_detail_from_song(s)
            if d is not None and d.song_id == song_id:
                return d
        raise MetadataNotFound(f"netease: song {song_id} not found")

    # ── get_lyric ──

    def get_lyric(self, song_id: str) -> LyricContent | None:
        if not song_id:
            return None
        url = f"{self._base}/api/song/lyric"
        data = self._http.get_json(url, params={
            "id": song_id, "lv": 1, "kv": 1, "tv": -1,
        })
        self._check_business_code(data)
        lrc_obj = data.get("lrc") or {}
        lrc_text = lrc_obj.get("lyric") or ""
        if not lrc_text:
            return None
        tlyric_obj = data.get("tlyric") or {}
        tlyric_text = tlyric_obj.get("lyric") or ""
        return LyricContent(
            source="netease",
            song_id=str(song_id),
            lrc_text=lrc_text,
            translated_lrc=tlyric_text or None,
        )

    # ── get_artist ──

    def get_artist(self, artist_id: str) -> ArtistDetail:
        if not artist_id:
            raise MetadataNotFound("empty artist_id")
        url = f"{self._base}/api/v1/artist/{artist_id}"
        data = self._http.get_json(url)
        self._check_business_code(data)
        artist = data.get("artist") or {}
        hot = data.get("hotSongs") or []
        songs = []
        for s in hot:
            h = _hit_from_song(s)
            if h is not None:
                songs.append(h)
        name = artist.get("name")
        if not name:
            raise MetadataNotFound(f"netease: artist {artist_id} not found")
        return ArtistDetail(
            source="netease",
            artist_id=str(artist_id),
            name=name,
            bio=artist.get("briefDesc") or artist.get("trans") or None,
            avatar_url=artist.get("img1v1Url") or artist.get("picUrl") or None,
            songs=songs,
        )

    # ── get_album ──

    def get_album(self, album_id: str) -> AlbumDetail:
        if not album_id:
            raise MetadataNotFound("empty album_id")
        url = f"{self._base}/api/v1/album/{album_id}"
        data = self._http.get_json(url)
        self._check_business_code(data)
        album = data.get("album") or {}
        songs_raw = data.get("songs") or []
        songs = []
        for s in songs_raw:
            h = _hit_from_song(s)
            if h is not None:
                songs.append(h)
        title = album.get("name")
        if not title:
            raise MetadataNotFound(f"netease: album {album_id} not found")
        artists = album.get("artists") or []
        return AlbumDetail(
            source="netease",
            album_id=str(album_id),
            title=title,
            artist=_artist_name(artists) or "",
            cover_url=album.get("picUrl"),
            release_date=album.get("publishTime") and self._format_date(
                album.get("publishTime")),
            songs=songs,
        )

    # ── get_playlist ──

    def get_playlist(self, playlist_id: str) -> PlaylistDetail:
        if not playlist_id:
            raise MetadataNotFound("empty playlist_id")
        url = f"{self._base}/api/v6/playlist/detail"
        data = self._http.get_json(url, params={"id": playlist_id, "n": 1000, "s": 0})
        self._check_business_code(data)
        pl = data.get("playlist") or {}
        title = pl.get("name")
        if not title:
            raise MetadataNotFound(f"netease: playlist {playlist_id} not found")
        creator = pl.get("creator") or {}
        tracks = pl.get("tracks") or []
        songs = []
        for s in tracks:
            h = _hit_from_song(s)
            if h is not None:
                songs.append(h)
        return PlaylistDetail(
            source="netease",
            playlist_id=str(playlist_id),
            title=title,
            creator=creator.get("nickname"),
            cover_url=pl.get("coverImgUrl"),
            description=pl.get("description"),
            play_count=pl.get("playCount"),
            songs=songs,
        )

    # ── get_charts ──

    def get_charts(self) -> list[Chart]:
        url = f"{self._base}/api/toplist"
        data = self._http.get_json(url)
        self._check_business_code(data)
        lst = data.get("list") or []
        charts = []
        for c in lst:
            cid = c.get("id")
            name = c.get("name")
            if cid is None or not name:
                continue
            charts.append(Chart(
                source="netease",
                chart_id=str(cid),
                title=name,
                cover_url=c.get("coverImgUrl"),
                description=c.get("description"),
            ))
        return charts

    # ── get_similar ──

    def get_similar(self, song_id: str) -> list[Hit]:
        if not song_id:
            return []
        url = f"{self._base}/api/v1/discovery/simiSong"
        data = self._http.get_json(url, params={"id": song_id})
        self._check_business_code(data)
        songs = data.get("songs") or []
        hits = []
        for s in songs:
            h = _hit_from_song(s)
            if h is not None:
                hits.append(h)
        return hits

    # ── 内部 ──

    @staticmethod
    def _check_business_code(data: dict) -> None:
        """网易云偶有业务 code != 200；视为不可用。"""
        code = data.get("code")
        if code is not None and code != 200:
            raise MetadataUnavailable([("netease", ValueError(f"code={code}"))])

    @staticmethod
    def _format_date(ms_ts: Any) -> str | None:
        """网易云 publishTime 是 ms 时间戳。"""
        if not ms_ts:
            return None
        try:
            from datetime import datetime, timezone
            dt = datetime.fromtimestamp(int(ms_ts) / 1000, tz=timezone.utc)
            return dt.date().isoformat()
        except (TypeError, ValueError, OSError):
            return None
