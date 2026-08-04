"""M2.7/M2.8 在线元数据 ApplicationService。

职责：
- 构造 MetadataRouter（多 provider 路由 + Cache）
- 暴露简单方法：search / get_song / get_artist / get_album / get_playlist /
  get_lyric / get_charts / get_similar
- 错误：把 core.metadata 的 MetadataError 透传（路由层决定如何转 HTTP）

设计原则：
- 不在 service 层做额外校验（路由层管）
- 不缓存结果（router 自带 cache，service 只是薄包装）
- 不并发（单线程同步；并发性能需要时再异步化）
"""
from __future__ import annotations

from typing import Any

from core.metadata import (
    MetadataCache,
    MetadataRouter,
    NeteaseProvider,
    QQProvider,
)


class MetadataApplicationService:
    """在线元数据服务（包装 MetadataRouter + Cache）。"""

    def __init__(self, router: MetadataRouter, cache: MetadataCache | None = None):
        self._router = router
        # cache 已挂在 router 上，service 保留引用便于管理（clear / stats）
        self._cache = cache or router.cache

    @property
    def router(self) -> MetadataRouter:
        return self._router

    @property
    def cache(self) -> MetadataCache | None:
        return self._cache

    @property
    def provider_names(self) -> list[str]:
        return self._router.provider_names

    # ── 业务方法（透传 router，错误透传） ──

    def search(self, keyword: str, *, type: str = "song", limit: int = 20,
               preferred_provider: str | None = None) -> list:
        return self._router.search(
            keyword, type=type, limit=limit,
            preferred_provider=preferred_provider,
        )

    def get_song(self, song_id: str, *, preferred_provider: str | None = None) -> Any:
        return self._router.get_song(song_id, preferred_provider=preferred_provider)

    def get_artist(self, artist_id: str, *, preferred_provider: str | None = None) -> Any:
        return self._router.get_artist(artist_id, preferred_provider=preferred_provider)

    def get_album(self, album_id: str, *, preferred_provider: str | None = None) -> Any:
        return self._router.get_album(album_id, preferred_provider=preferred_provider)

    def get_playlist(self, playlist_id: str, *, preferred_provider: str | None = None) -> Any:
        return self._router.get_playlist(playlist_id, preferred_provider=preferred_provider)

    def get_lyric(self, song_id: str, *, preferred_provider: str | None = None) -> Any:
        return self._router.get_lyric(song_id, preferred_provider=preferred_provider)

    def get_charts(self, *, preferred_provider: str | None = None) -> list:
        return self._router.get_charts(preferred_provider=preferred_provider)

    def get_similar(self, song_id: str, *, preferred_provider: str | None = None) -> list:
        return self._router.get_similar(song_id, preferred_provider=preferred_provider)


def build_default_router(cache_dir, *, providers: list | None = None) -> tuple[MetadataRouter, MetadataCache]:
    """构造默认的 MetadataRouter + Cache。

    providers 为空时自动注入 [NeteaseProvider(), QQProvider()]（M2.10 多源回退）。
    调用方可传入自定义 providers 列表覆盖默认。
    """
    cache = MetadataCache(cache_dir)
    if not providers:
        # M2.10 默认装两个 provider，Router 自动回退
        providers = [NeteaseProvider(), QQProvider()]
    router = MetadataRouter(providers, cache=cache)
    return router, cache
