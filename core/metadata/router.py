"""M2.7 多 provider 路由器。

按 provider 顺序依次调用；任一成功即返回。
全部失败抛 MetadataUnavailable（带每个 provider 的错误列表）。

缓存策略：
- read 路径：先查 cache（key = "search:<type>:<keyword>" / "song:<id>" 等）
- write 路径：自动写 cache
- use_cache=False：绕过 cache（强制刷新）
- preferred_provider：把上次成功的 provider 排第一
"""
from __future__ import annotations

import logging
from typing import Callable

from .cache import MetadataCache
from .errors import MetadataNotFound, MetadataUnavailable
from .protocols import MetadataProvider, SearchType
from .types import (
    AlbumDetail,
    ArtistDetail,
    Chart,
    Hit,
    LyricContent,
    PlaylistDetail,
    SongDetail,
)


_log = logging.getLogger(__name__)


# 缓存"该 song 无歌词"的 sentinel
LYRIC_NONE_SENTINEL = {"__lyric_none__": True}


def _cache_key(method: str, *parts: str) -> str:
    """生成 cache key。parts 不能包含 ':'，否则会混淆。"""
    safe = ":".join(p.replace(":", "_") for p in parts)
    return f"{method}:{safe}"


class MetadataRouter:
    """多 provider 路由器。

    构造时按传入顺序保存；调用时 preferred_provider 可以临时调整优先级。
    """

    def __init__(
        self,
        providers: list[MetadataProvider],
        cache: MetadataCache | None = None,
    ):
        if not providers:
            raise ValueError("router 至少需要 1 个 provider")
        # 校验 name 不重复
        names = [p.name for p in providers]
        if len(set(names)) != len(names):
            raise ValueError(f"provider name 重复：{names}")
        self._providers = list(providers)
        self._cache = cache

    @property
    def provider_names(self) -> list[str]:
        return [p.name for p in self._providers]

    @property
    def cache(self) -> MetadataCache | None:
        return self._cache

    def attach_cache(self, cache: MetadataCache) -> None:
        """运行时挂载 cache（用于先建 router 再建 cache 的场景）。"""
        self._cache = cache

    # ── 公共方法 ──

    def search(
        self,
        keyword: str,
        *,
        type: SearchType = "song",
        limit: int = 20,
        use_cache: bool = True,
        preferred_provider: str | None = None,
    ) -> list[Hit]:
        """依次调 provider 搜索；首个有结果即返回。

        search 不抛 NotFound：返回 [] 即可（合法状态）。
        """
        if not keyword or not keyword.strip():
            return []
        keyword = keyword.strip()
        limit = max(1, min(limit, 50))
        ckey = _cache_key("search", type, keyword, str(limit))

        if use_cache and self._cache is not None:
            cached = self._cache.get("router", ckey)
            if cached:
                return [Hit(**h) for h in cached]

        ordered = self._order(preferred_provider)
        errors: list[tuple[str, Exception]] = []
        for provider in ordered:
            try:
                hits = provider.search(keyword, type=type, limit=limit)
                if not hits:
                    # 该 provider 无结果不算错误，继续下一个
                    continue
                if self._cache is not None:
                    self._cache.put(
                        "router", ckey,
                        [self._hit_to_dict(h) for h in hits],
                    )
                return hits
            except MetadataNotFound:
                continue
            except Exception as exc:  # noqa: BLE001 — 收集后一并抛
                _log.warning("provider %s search failed: %s", provider.name, exc)
                errors.append((provider.name, exc))
                continue

        # 全部无结果
        if errors:
            # 至少有一个 provider 报错了 → 整体不可用
            raise MetadataUnavailable(errors)
        return []

    def get_song(
        self,
        song_id: str,
        *,
        use_cache: bool = True,
        preferred_provider: str | None = None,
    ) -> SongDetail:
        return self._detail(
            "song", song_id, use_cache, preferred_provider,
            lambda p, i: p.get_song(i), SongDetail,
        )

    def get_artist(
        self,
        artist_id: str,
        *,
        use_cache: bool = True,
        preferred_provider: str | None = None,
    ) -> ArtistDetail:
        return self._detail(
            "artist", artist_id, use_cache, preferred_provider,
            lambda p, i: p.get_artist(i), ArtistDetail,
        )

    def get_album(
        self,
        album_id: str,
        *,
        use_cache: bool = True,
        preferred_provider: str | None = None,
    ) -> AlbumDetail:
        return self._detail(
            "album", album_id, use_cache, preferred_provider,
            lambda p, i: p.get_album(i), AlbumDetail,
        )

    def get_playlist(
        self,
        playlist_id: str,
        *,
        use_cache: bool = True,
        preferred_provider: str | None = None,
    ) -> PlaylistDetail:
        return self._detail(
            "playlist", playlist_id, use_cache, preferred_provider,
            lambda p, i: p.get_playlist(i), PlaylistDetail,
        )

    def get_lyric(
        self,
        song_id: str,
        *,
        use_cache: bool = True,
        preferred_provider: str | None = None,
    ) -> LyricContent | None:
        """LRC 歌词：返回 None = 该 song 三个 provider 都无歌词。"""
        ckey = _cache_key("lyric", song_id)
        if use_cache and self._cache is not None:
            cached = self._cache.get("router", ckey)
            if cached is not None:
                if cached == LYRIC_NONE_SENTINEL:
                    return None
                return LyricContent(**cached)

        ordered = self._order(preferred_provider)
        errors: list[tuple[str, Exception]] = []
        for provider in ordered:
            try:
                content = provider.get_lyric(song_id)
                if content is None:
                    continue
                if self._cache is not None:
                    self._cache.put("router", ckey, {
                        "source": content.source,
                        "song_id": content.song_id,
                        "lrc_text": content.lrc_text,
                        "translated_lrc": content.translated_lrc,
                    })
                return content
            except MetadataNotFound:
                continue
            except Exception as exc:  # noqa: BLE001
                _log.warning("provider %s get_lyric failed: %s", provider.name, exc)
                errors.append((provider.name, exc))
                continue
        # 都拿不到：标 None 缓存，避免重复打
        if self._cache is not None and not errors:
            self._cache.put("router", ckey, LYRIC_NONE_SENTINEL)
        if errors:
            raise MetadataUnavailable(errors)
        return None

    def get_charts(
        self,
        *,
        use_cache: bool = True,
        preferred_provider: str | None = None,
    ) -> list[Chart]:
        """榜单列表。"""
        ckey = _cache_key("charts", "all")
        if use_cache and self._cache is not None:
            cached = self._cache.get("router", ckey)
            if cached:
                return [Chart(**c) for c in cached]

        ordered = self._order(preferred_provider)
        errors: list[tuple[str, Exception]] = []
        for provider in ordered:
            try:
                charts = provider.get_charts()
                if not charts:
                    continue
                if self._cache is not None:
                    self._cache.put(
                        "router", ckey,
                        [self._chart_to_dict(c) for c in charts],
                    )
                return charts
            except MetadataNotFound:
                continue
            except Exception as exc:  # noqa: BLE001
                _log.warning("provider %s get_charts failed: %s", provider.name, exc)
                errors.append((provider.name, exc))
                continue
        if errors:
            raise MetadataUnavailable(errors)
        return []

    def get_similar(
        self,
        song_id: str,
        *,
        use_cache: bool = True,
        preferred_provider: str | None = None,
    ) -> list[Hit]:
        """相似歌曲。"""
        ckey = _cache_key("similar", song_id)
        if use_cache and self._cache is not None:
            cached = self._cache.get("router", ckey)
            if cached:
                return [Hit(**h) for h in cached]

        ordered = self._order(preferred_provider)
        errors: list[tuple[str, Exception]] = []
        for provider in ordered:
            try:
                hits = provider.get_similar(song_id)
                if not hits:
                    continue
                if self._cache is not None:
                    self._cache.put(
                        "router", ckey,
                        [self._hit_to_dict(h) for h in hits],
                    )
                return hits
            except MetadataNotFound:
                continue
            except Exception as exc:  # noqa: BLE001
                _log.warning("provider %s get_similar failed: %s", provider.name, exc)
                errors.append((provider.name, exc))
                continue
        if errors:
            raise MetadataUnavailable(errors)
        return []

    # ── 内部辅助 ──

    def _order(self, preferred: str | None) -> list[MetadataProvider]:
        if not preferred:
            return list(self._providers)
        for p in self._providers:
            if p.name == preferred:
                rest = [x for x in self._providers if x.name != preferred]
                return [p, *rest]
        # preferred 不在列表里 → 忽略
        return list(self._providers)

    def _detail(
        self,
        method: str,
        item_id: str,
        use_cache: bool,
        preferred_provider: str | None,
        fetcher: Callable[[MetadataProvider, str], Any],
        cls: type,
    ) -> Any:
        ckey = _cache_key(method, item_id)
        if use_cache and self._cache is not None:
            cached = self._cache.get("router", ckey)
            if cached:
                return cls(**cached)

        ordered = self._order(preferred_provider)
        errors: list[tuple[str, Exception]] = []
        for provider in ordered:
            try:
                result = fetcher(provider, item_id)
                if self._cache is not None:
                    self._cache.put("router", ckey, self._detail_to_dict(result))
                return result
            except MetadataNotFound:
                continue
            except Exception as exc:  # noqa: BLE001
                _log.warning("provider %s %s failed: %s", provider.name, method, exc)
                errors.append((provider.name, exc))
                continue
        if errors:
            raise MetadataUnavailable(errors)
        raise MetadataNotFound(f"所有 provider 都查不到 {method}={item_id}")

    @staticmethod
    def _hit_to_dict(h: Hit) -> dict:
        return {
            "source": h.source, "song_id": h.song_id, "title": h.title,
            "artist": h.artist, "album": h.album,
            "duration_ms": h.duration_ms, "cover_url": h.cover_url,
        }

    @staticmethod
    def _chart_to_dict(c: Chart) -> dict:
        return {
            "source": c.source, "chart_id": c.chart_id, "title": c.title,
            "cover_url": c.cover_url, "description": c.description,
        }

    @staticmethod
    def _detail_to_dict(d: Any) -> dict:
        # dataclass → dict (用 asdict 行为；frozen dataclass 同样支持)
        from dataclasses import asdict
        return asdict(d)
