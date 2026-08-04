"""M2.7/M2.8 在线元数据 HTTP 路由。

端点：
- GET  /api/metadata/providers                  当前 router 注册的 provider 列表
- POST /api/metadata/search                     body { keyword, type?, limit? } → 搜索
- POST /api/metadata/song                       body { song_id, preferred_provider? } → 歌曲详情
- POST /api/metadata/lyric                      body { song_id, preferred_provider? } → LRC 歌词
- POST /api/metadata/artist                     body { artist_id, preferred_provider? } → 艺人详情
- POST /api/metadata/album                      body { album_id, preferred_provider? } → 专辑详情
- POST /api/metadata/playlist                   body { playlist_id, preferred_provider? } → 歌单详情
- POST /api/metadata/charts                     body {} → 官方榜单列表
- POST /api/metadata/similar                    body { song_id } → 相似歌曲

错误处理：
- MetadataNotFound → 404
- MetadataRateLimited → 429（带 retry_after）
- MetadataUnavailable → 503（带 errors 明细）
- ValidationError → 400
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from core.metadata import (
    Hit,
    SongDetail,
    LyricContent,
    ArtistDetail,
    AlbumDetail,
    PlaylistDetail,
    Chart,
    MetadataNotFound,
    MetadataRateLimited,
    MetadataUnavailable,
)
from server.api.secondary_models import (
    MetadataAlbumResponse,
    MetadataArtistResponse,
    MetadataChartResponse,
    MetadataHitResponse,
    MetadataLyricResponse,
    MetadataPlaylistResponse,
    MetadataProviderListResponse,
    MetadataSearchResponse,
    MetadataSongDetailResponse,
    StrictRequest,
)
from server.dependencies import get_app_context


logger = logging.getLogger(__name__)
router = APIRouter()


# ── 请求模型 ──


class SearchRequest(StrictRequest):
    keyword: str
    type: str = "song"
    limit: int = 20


class SongRequest(StrictRequest):
    song_id: str
    preferred_provider: str | None = None


class LyricRequest(StrictRequest):
    song_id: str
    preferred_provider: str | None = None


class ArtistRequest(StrictRequest):
    artist_id: str
    preferred_provider: str | None = None


class AlbumRequest(StrictRequest):
    album_id: str
    preferred_provider: str | None = None


class PlaylistRequest(StrictRequest):
    playlist_id: str
    preferred_provider: str | None = None


class ChartsRequest(StrictRequest):
    preferred_provider: str | None = None


class SimilarRequest(StrictRequest):
    song_id: str
    preferred_provider: str | None = None


# ── 转换 helper ──


def _hit_to_response(h: Hit) -> MetadataHitResponse:
    return MetadataHitResponse(
        source=h.source, song_id=h.song_id, title=h.title, artist=h.artist,
        album=h.album, duration_ms=h.duration_ms, cover_url=h.cover_url,
    )


def _song_to_response(d: SongDetail) -> MetadataSongDetailResponse:
    return MetadataSongDetailResponse(
        source=d.source, song_id=d.song_id, title=d.title, artist=d.artist,
        artist_id=d.artist_id, album=d.album, album_id=d.album_id,
        duration_ms=d.duration_ms, cover_url=d.cover_url, bpm=d.bpm,
    )


def _lyric_to_response(c: LyricContent) -> MetadataLyricResponse:
    return MetadataLyricResponse(
        source=c.source, song_id=c.song_id,
        lrc_text=c.lrc_text, translated_lrc=c.translated_lrc,
    )


def _artist_to_response(a: ArtistDetail) -> MetadataArtistResponse:
    return MetadataArtistResponse(
        source=a.source, artist_id=a.artist_id, name=a.name,
        bio=a.bio, avatar_url=a.avatar_url,
        songs=[_hit_to_response(h) for h in a.songs],
    )


def _album_to_response(a: AlbumDetail) -> MetadataAlbumResponse:
    return MetadataAlbumResponse(
        source=a.source, album_id=a.album_id, title=a.title, artist=a.artist,
        cover_url=a.cover_url, release_date=a.release_date,
        songs=[_hit_to_response(h) for h in a.songs],
    )


def _playlist_to_response(p: PlaylistDetail) -> MetadataPlaylistResponse:
    return MetadataPlaylistResponse(
        source=p.source, playlist_id=p.playlist_id, title=p.title,
        creator=p.creator, cover_url=p.cover_url, description=p.description,
        play_count=p.play_count,
        songs=[_hit_to_response(h) for h in p.songs],
    )


def _chart_to_response(c: Chart) -> MetadataChartResponse:
    return MetadataChartResponse(
        source=c.source, chart_id=c.chart_id, title=c.title,
        cover_url=c.cover_url, description=c.description,
    )


def _handle_metadata_error(exc: Exception) -> None:
    """统一错误转 HTTP。"""
    if isinstance(exc, MetadataNotFound):
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": str(exc)})
    if isinstance(exc, MetadataRateLimited):
        detail = {
            "code": "rate_limited",
            "message": str(exc),
            "provider": exc.provider,
            "retry_after": exc.retry_after,
        }
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
        raise HTTPException(status_code=429, detail=detail, headers=headers)
    if isinstance(exc, MetadataUnavailable):
        detail = {
            "code": "unavailable",
            "message": str(exc),
            "errors": [
                {"provider": n, "type": type(e).__name__, "message": str(e)}
                for n, e in exc.errors
            ],
        }
        raise HTTPException(status_code=503, detail=detail)
    raise exc


# ── 端点 ──


@router.get("/api/metadata/providers", response_model=MetadataProviderListResponse)
def api_metadata_providers(req: Request):
    """列出当前 router 注册的 providers。"""
    ctx = get_app_context(req)
    if ctx.metadata_router is None:
        return MetadataProviderListResponse(providers=[])
    return MetadataProviderListResponse(providers=ctx.metadata_router.provider_names)


@router.post("/api/metadata/search", response_model=MetadataSearchResponse)
def api_metadata_search(req: Request, body: SearchRequest):
    """按关键词搜索。"""
    ctx = get_app_context(req)
    if ctx.metadata_router is None:
        raise HTTPException(status_code=503, detail={"code": "no_router", "message": "metadata router 未启用"})
    try:
        hits = ctx.metadata_router.search(
            body.keyword, type=body.type, limit=body.limit,
        )
    except MetadataNotFound:
        hits = []
    except (MetadataUnavailable, MetadataRateLimited) as exc:
        _handle_metadata_error(exc)
    return MetadataSearchResponse(
        keyword=body.keyword, type=body.type,
        provider=ctx.metadata_router.provider_names[0] if ctx.metadata_router.provider_names else None,
        items=[_hit_to_response(h) for h in hits],
    )


@router.post("/api/metadata/song", response_model=MetadataSongDetailResponse)
def api_metadata_song(req: Request, body: SongRequest):
    ctx = get_app_context(req)
    if ctx.metadata_router is None:
        raise HTTPException(status_code=503, detail={"code": "no_router", "message": "metadata router 未启用"})
    try:
        d = ctx.metadata_router.get_song(
            body.song_id, preferred_provider=body.preferred_provider,
        )
    except (MetadataNotFound, MetadataUnavailable, MetadataRateLimited) as exc:
        _handle_metadata_error(exc)
    return _song_to_response(d)


@router.post("/api/metadata/lyric", response_model=MetadataLyricResponse)
def api_metadata_lyric(req: Request, body: LyricRequest):
    ctx = get_app_context(req)
    if ctx.metadata_router is None:
        raise HTTPException(status_code=503, detail={"code": "no_router", "message": "metadata router 未启用"})
    try:
        c = ctx.metadata_router.get_lyric(
            body.song_id, preferred_provider=body.preferred_provider,
        )
    except (MetadataUnavailable, MetadataRateLimited) as exc:
        _handle_metadata_error(exc)
    if c is None:
        raise HTTPException(status_code=404, detail={"code": "no_lyric", "message": "无歌词"})
    return _lyric_to_response(c)


@router.post("/api/metadata/artist", response_model=MetadataArtistResponse)
def api_metadata_artist(req: Request, body: ArtistRequest):
    ctx = get_app_context(req)
    if ctx.metadata_router is None:
        raise HTTPException(status_code=503, detail={"code": "no_router", "message": "metadata router 未启用"})
    try:
        a = ctx.metadata_router.get_artist(
            body.artist_id, preferred_provider=body.preferred_provider,
        )
    except (MetadataNotFound, MetadataUnavailable, MetadataRateLimited) as exc:
        _handle_metadata_error(exc)
    return _artist_to_response(a)


@router.post("/api/metadata/album", response_model=MetadataAlbumResponse)
def api_metadata_album(req: Request, body: AlbumRequest):
    ctx = get_app_context(req)
    if ctx.metadata_router is None:
        raise HTTPException(status_code=503, detail={"code": "no_router", "message": "metadata router 未启用"})
    try:
        a = ctx.metadata_router.get_album(
            body.album_id, preferred_provider=body.preferred_provider,
        )
    except (MetadataNotFound, MetadataUnavailable, MetadataRateLimited) as exc:
        _handle_metadata_error(exc)
    return _album_to_response(a)


@router.post("/api/metadata/playlist", response_model=MetadataPlaylistResponse)
def api_metadata_playlist(req: Request, body: PlaylistRequest):
    ctx = get_app_context(req)
    if ctx.metadata_router is None:
        raise HTTPException(status_code=503, detail={"code": "no_router", "message": "metadata router 未启用"})
    try:
        p = ctx.metadata_router.get_playlist(
            body.playlist_id, preferred_provider=body.preferred_provider,
        )
    except (MetadataNotFound, MetadataUnavailable, MetadataRateLimited) as exc:
        _handle_metadata_error(exc)
    return _playlist_to_response(p)


@router.post("/api/metadata/charts", response_model=list[MetadataChartResponse])
def api_metadata_charts(req: Request, body: ChartsRequest):
    ctx = get_app_context(req)
    if ctx.metadata_router is None:
        raise HTTPException(status_code=503, detail={"code": "no_router", "message": "metadata router 未启用"})
    try:
        charts = ctx.metadata_router.get_charts(
            preferred_provider=body.preferred_provider,
        )
    except (MetadataUnavailable, MetadataRateLimited) as exc:
        _handle_metadata_error(exc)
    return [_chart_to_response(c) for c in charts]


@router.post("/api/metadata/similar", response_model=list[MetadataHitResponse])
def api_metadata_similar(req: Request, body: SimilarRequest):
    ctx = get_app_context(req)
    if ctx.metadata_router is None:
        raise HTTPException(status_code=503, detail={"code": "no_router", "message": "metadata router 未启用"})
    try:
        hits = ctx.metadata_router.get_similar(
            body.song_id, preferred_provider=body.preferred_provider,
        )
    except (MetadataUnavailable, MetadataRateLimited) as exc:
        _handle_metadata_error(exc)
    return [_hit_to_response(h) for h in hits]
