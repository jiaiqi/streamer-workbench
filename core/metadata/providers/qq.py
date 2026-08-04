"""M2.10 QQ 音乐 QQProvider。

实现的 API 端点（均无需登录，公开接口）：
- 搜索歌曲：GET https://c.y.qq.com/soso/fcgi-bin/client_search_cp?w=KEYWORD&n=N&t=0&format=json
- 歌曲详情：GET https://c.y.qq.com/v8/fcg-bin/fcg_play_single_song?songmid=MID&format=json
- LRC 歌词：  GET https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new?songmid=MID&format=json
- 相似歌曲：search by title - self（fallback 方式，未对接 QQ 专用相似接口）

不实现（用 search 兜底 或 抛 MetadataNotFound）：
- get_artist：QQ 艺人详情 API 需要额外参数（singermid），未实现 → 抛 NotImplementedError
- get_album：QQ 专辑详情 API 需要 album mid，未实现 → 抛 NotImplementedError
- get_playlist：QQ 歌单 API 需要 playlist id + 复杂参数，未实现 → 抛 NotImplementedError
- get_charts：QQ 榜单需特殊处理，未实现 → 抛 NotImplementedError

注：QQ 公开 API 偶有"业务码 0/非 0"判断，`code` 字段可能缺失。错误处理与 NeteaseProvider 一致。

借鉴 L-1124/QQMusicApi + UnblockNeteaseMusic 的多源回退架构。
"""
from __future__ import annotations

import base64
from typing import Any

from ..errors import MetadataNotFound, MetadataUnavailable
from ..http_client import HttpClient
from ..types import (
    Hit,
    SongDetail,
    LyricContent,
)

API_BASE = "https://c.y.qq.com"
LYRIC_BASE = "https://c.y.qq.com/lyric/fcgi-bin/fcgi-bin/fcg_query_lyric_new"  # placeholder
LYRIC_BASE_CORRECT = "https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new"
DEFAULT_TIMEOUT = 10.0


def _ms(seconds: Any) -> int:
    """QQ 的 interval 字段是秒。"""
    if seconds is None:
        return 0
    try:
        return int(float(seconds) * 1000)
    except (TypeError, ValueError):
        return 0


def _singer_name(singers: list[dict]) -> str:
    """合并 singers 数组为 'a / b' 形式。"""
    names = [s.get("name", "") for s in (singers or []) if s]
    return " / ".join(n for n in names if n)


def _first_singer_mid(singers: list[dict]) -> str | None:
    if not singers:
        return None
    mid = singers[0].get("mid")
    return str(mid) if mid else None


def _hit_from_song(song: dict) -> Hit | None:
    """从 client_search_cp 返回的 songs[].xx 构造 Hit。"""
    if not song:
        return None
    mid = song.get("songmid")
    title = song.get("songname")
    if not mid or not title:
        return None
    singers = song.get("singer") or []
    album_name = song.get("albumname")
    return Hit(
        source="qq",
        song_id=str(mid),  # QQ 用 songmid 作主键
        title=title,
        artist=_singer_name(singers) or "",
        album=album_name,
        duration_ms=_ms(song.get("interval")),
        cover_url=None,  # QQ 搜索结果不直接给封面 URL
    )


def _song_detail_from_track(track: dict) -> SongDetail | None:
    """从 fcg_play_single_song 返回的 data[0] 构造 SongDetail。"""
    if not track:
        return None
    mid = track.get("mid") or track.get("songmid")
    title = track.get("name") or track.get("songname")
    if not mid or not title:
        return None
    singers = track.get("singer") or []
    album = track.get("album") or {}
    # 兼容：部分响应 album 字段为空，但顶层有 albumname / albummid
    album_name = album.get("name") or album.get("albumname") or track.get("albumname")
    album_mid = album.get("mid") or album.get("albummid") or track.get("albummid")
    return SongDetail(
        source="qq",
        song_id=str(mid),
        title=title,
        artist=_singer_name(singers) or "",
        artist_id=_first_singer_mid(singers),
        album=album_name,
        album_id=str(album_mid) if album_mid else None,
        duration_ms=_ms(track.get("interval")),
        cover_url=None,
    )


def _decode_lyric_field(value: Any) -> str:
    """QQ 歌词字段是 base64 编码；空或缺失返回 ''。"""
    if not value:
        return ""
    if not isinstance(value, str):
        return ""
    try:
        return base64.b64decode(value).decode("utf-8", errors="replace")
    except Exception:
        # 退路：尝试直接当 utf-8
        try:
            return value.encode("latin-1").decode("utf-8", errors="replace")
        except Exception:
            return ""


class QQProvider:
    """QQ 音乐元数据 provider。

    M2.10 阶段实现 search / get_song / get_lyric / get_similar 4 个方法。
    其他 4 个方法（artist / album / playlist / charts）抛 MetadataNotFound，
    让 Router 自动跳下一个 provider（NeteaseProvider 等）。
    """

    name = "qq"

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
        if type != "song":
            # QQ 公开 search 接口只支持 song（type 0）；其他类型下个版本
            raise MetadataNotFound(f"qq: search type {type} not supported")
        url = f"{self._base}/soso/fcgi-bin/client_search_cp"
        data = self._http.get_json(url, params={
            "w": keyword.strip(), "n": max(1, min(limit, 50)),
            "t": 0, "format": "json",
        })
        self._check_business_code(data)
        # 响应结构: {"code": 0, "data": {"song": {"list": [...]}}}
        songs = (
            (data.get("data") or {}).get("song") or {}
        ).get("list") or []
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
        url = f"{self._base}/v8/fcg-bin/fcg_play_single_song"
        data = self._http.get_json(url, params={"songmid": song_id, "format": "json"})
        self._check_business_code(data)
        # 响应: {"code": 0, "data": [track_info, ...]}
        tracks = data.get("data") or []
        if not tracks:
            raise MetadataNotFound(f"qq: song {song_id} not found")
        d = _song_detail_from_track(tracks[0])
        if d is None:
            raise MetadataNotFound(f"qq: song {song_id} parse failed")
        return d

    # ── get_lyric ──

    def get_lyric(self, song_id: str) -> LyricContent | None:
        if not song_id:
            return None
        url = LYRIC_BASE_CORRECT
        data = self._http.get_json(url, params={
            "songmid": song_id, "format": "json", "nobase64": 0,
        })
        self._check_business_code(data)
        lyric = _decode_lyric_field(data.get("lyric"))
        if not lyric:
            return None
        trans = _decode_lyric_field(data.get("trans"))
        return LyricContent(
            source="qq",
            song_id=str(song_id),
            lrc_text=lyric,
            translated_lrc=trans or None,
        )

    # ── get_similar ──

    def get_similar(self, song_id: str) -> list[Hit]:
        """用 search 找相似：拿不到原 title 时退化为空。"""
        if not song_id:
            return []
        # 先查原 song 拿 title
        try:
            detail = self.get_song(song_id)
        except MetadataNotFound:
            return []
        # 简化：用 song.title 搜（不含 artist 避免过于严格）
        try:
            hits = self.search(detail.title, limit=10)
        except MetadataNotFound:
            return []
        # 去掉自己
        return [h for h in hits if h.song_id != song_id][:5]

    # ── 未实现的方法：让 Router 跳下一个 provider ──

    def get_artist(self, artist_id: str):
        raise MetadataNotFound(f"qq: get_artist({artist_id}) not implemented")

    def get_album(self, album_id: str):
        raise MetadataNotFound(f"qq: get_album({album_id}) not implemented")

    def get_playlist(self, playlist_id: str):
        raise MetadataNotFound(f"qq: get_playlist({playlist_id}) not implemented")

    def get_charts(self):
        # 返回空列表（让 Router 跳下一个；不抛错避免污染 errors）
        return []

    # ── 内部 ──

    @staticmethod
    def _check_business_code(data: dict) -> None:
        """QQ 偶有 code 字段。code != 0 当作不可用。"""
        if not isinstance(data, dict):
            raise MetadataUnavailable([("qq", ValueError("non-dict response"))])
        code = data.get("code")
        if code is None:
            return  # 部分端点不返回 code，按成功处理
        if code != 0:
            raise MetadataUnavailable([("qq", ValueError(f"code={code}"))])
