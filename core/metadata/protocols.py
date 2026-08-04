"""M2.7 MetadataProvider 协议。

用 typing.Protocol 而非 ABC，原因：
- 第三方实现（如 NeteaseProvider）继承负担最小（duck typing 友好）
- 测试 FakeProvider 不需要继承任何东西
- mypy --strict 能识别（Protocol 类型会传播）

API 表面参考 neteasecloudmusicapienhanced + QQMusicApi 的共同子集：
- search：按关键词搜（type: song/artist/album/playlist）
- get_song / get_artist / get_album / get_playlist：详情
- get_lyric：LRC 歌词（返回 None = 该 provider 无歌词）
- get_charts：官方榜单列表
- get_similar：相似歌曲（仅 song → list[Hit]）

所有方法都可能抛：
- MetadataNotFound：合法请求但无结果
- MetadataUnavailable：网络/5xx/限流
"""
from __future__ import annotations

from typing import Literal, Protocol

from .types import (
    AlbumDetail,
    ArtistDetail,
    Chart,
    Hit,
    LyricContent,
    PlaylistDetail,
    SongDetail,
)


SearchType = Literal["song", "artist", "album", "playlist"]


class MetadataProvider(Protocol):
    """单一在线音乐服务的元数据访问接口。

    M2.7 阶段所有方法都是同步实现（与现有 server 路由一致）。
    异步化在确有性能瓶颈时再做。
    """

    name: str  # "netease" / "qq" / "kugou" / ...

    def search(
        self,
        keyword: str,
        *,
        type: SearchType = "song",
        limit: int = 20,
    ) -> list[Hit]:
        """按关键词搜索。

        Args:
            keyword: 搜索关键词
            type: 搜索类型，默认 song
            limit: 最多返回条数（1-50）

        Returns:
            命中列表。空列表 = 查无结果（合法状态，**不**抛 NotFound）。

        Raises:
            MetadataUnavailable: 网络错误 / 5xx / 限流
        """
        ...

    def get_song(self, song_id: str) -> SongDetail:
        """获取歌曲详情。"""
        ...

    def get_artist(self, artist_id: str) -> ArtistDetail:
        """获取艺人详情（含热门歌曲）。"""
        ...

    def get_album(self, album_id: str) -> AlbumDetail:
        """获取专辑详情（含曲目）。"""
        ...

    def get_playlist(self, playlist_id: str) -> PlaylistDetail:
        """获取歌单详情。"""
        ...

    def get_lyric(self, song_id: str) -> LyricContent | None:
        """获取 LRC 歌词。

        Returns:
            歌词内容；None 表示该 provider 无歌词（**不**抛 NotFound）。
        """
        ...

    def get_charts(self) -> list[Chart]:
        """获取官方榜单列表。"""
        ...

    def get_similar(self, song_id: str) -> list[Hit]:
        """获取相似歌曲。"""
        ...
