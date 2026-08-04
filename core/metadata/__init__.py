"""M2.7 在线元数据层公开 API。

用法：
    from core.metadata import (
        MetadataProvider, MetadataRouter, MetadataCache, HttpClient,
        Hit, SongDetail, LyricContent, ArtistDetail, AlbumDetail,
        PlaylistDetail, Chart, SearchType,
        MetadataError, MetadataNotFound, MetadataUnavailable, MetadataRateLimited,
    )

设计原则：
- 核心数据 100% 离线
- 辅助元数据（cover/lrc/duration/artist bio）在线可选
- 不锁单一 provider：Router 默认按优先级依次尝试
- 数据落本地缓存：data/metadata/<provider>/<key>.json
- 零凭证：只用公开 API
- 零新增依赖：stdlib urllib.request
"""
from .cache import DEFAULT_TTL_SECONDS, MetadataCache
from .errors import (
    MetadataError,
    MetadataNotFound,
    MetadataRateLimited,
    MetadataUnavailable,
)
from .http_client import HttpClient
from .protocols import MetadataProvider, SearchType
from .router import MetadataRouter
from .types import (
    AlbumDetail,
    ArtistDetail,
    Chart,
    Hit,
    LyricContent,
    PlaylistDetail,
    SongDetail,
)

# M2.8+ providers（具体实现）
from .providers import NeteaseProvider, QQProvider

__all__ = [
    # types
    "AlbumDetail",
    "ArtistDetail",
    "Chart",
    "Hit",
    "LyricContent",
    "PlaylistDetail",
    "SongDetail",
    # errors
    "MetadataError",
    "MetadataNotFound",
    "MetadataRateLimited",
    "MetadataUnavailable",
    # protocols
    "MetadataProvider",
    "SearchType",
    # infra
    "HttpClient",
    "MetadataCache",
    "MetadataRouter",
    "DEFAULT_TTL_SECONDS",
    # providers
    "NeteaseProvider",
    "QQProvider",
]
