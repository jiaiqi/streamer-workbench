"""M2.7 在线元数据层数据类型。

所有类型 @dataclass(frozen=True) —— 不可变、跨 provider 缓存安全、hashable。
字段名参考 QQMusicApi / api-enhanced / UnblockNeteaseMusic 三个项目的共同子集。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Hit:
    """搜索结果条目（轻量，仅用于浏览/选择）。

    与 SongDetail 的区别：Hit 不包含 artist_id / album_id / bpm 等深链字段。
    用户从 Hit 列表选中某条后，再用 song_id 调 get_song 拿详情。
    """
    source: str           # provider name: "netease" / "qq" / "kugou"
    song_id: str          # provider 内部 id（在该 provider 内唯一）
    title: str
    artist: str
    album: str | None = None
    duration_ms: int | None = None
    cover_url: str | None = None


@dataclass(frozen=True)
class SongDetail:
    """歌曲详情（用于补全本地 Song 字段）。

    字段对齐 Song 模型（M2.9 会做字段映射）：
      - title → Song.title
      - artist → Song.artists[0]
      - album → 暂不入 Song（Song 模型无 album 字段；M2.9+ 可加）
      - duration_ms → 仅展示用（不存 Song，因为 Song 暂未存时长）
      - cover_url → M2.7 不下载；M3+ 视需求
    """
    source: str
    song_id: str
    title: str
    artist: str
    artist_id: str | None = None
    album: str | None = None
    album_id: str | None = None
    duration_ms: int = 0
    cover_url: str | None = None
    bpm: float | None = None


@dataclass(frozen=True)
class LyricContent:
    """LRC 歌词内容。

    一些 provider（如网易云）会同时返回原文 + 翻译歌词，分两个字段存。
    """
    source: str
    song_id: str
    lrc_text: str
    translated_lrc: str | None = None


@dataclass(frozen=True)
class ArtistDetail:
    """艺人详情（含热门歌曲）。"""
    source: str
    artist_id: str
    name: str
    bio: str | None = None
    avatar_url: str | None = None
    songs: list[Hit] = field(default_factory=list)


@dataclass(frozen=True)
class AlbumDetail:
    """专辑详情（含曲目）。"""
    source: str
    album_id: str
    title: str
    artist: str
    cover_url: str | None = None
    release_date: str | None = None
    songs: list[Hit] = field(default_factory=list)


@dataclass(frozen=True)
class PlaylistDetail:
    """歌单详情。"""
    source: str
    playlist_id: str
    title: str
    creator: str | None = None
    cover_url: str | None = None
    description: str | None = None
    play_count: int | None = None
    songs: list[Hit] = field(default_factory=list)


@dataclass(frozen=True)
class Chart:
    """榜单条目（如「网易云热歌榜」）。"""
    source: str
    chart_id: str
    title: str
    cover_url: str | None = None
    description: str | None = None
