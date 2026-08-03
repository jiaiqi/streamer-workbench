"""R4 统计路由 — 总览 / 时间线 / Top N / 分布 / 综合洞察。"""
from __future__ import annotations

from fastapi import APIRouter, Request

from server.api.secondary_models import (
    OverviewStatsResponse,
    FeedItemResponse,
    FeedResponse,
    TopSongItemResponse,
    TopSongsResponse,
    DistributionBucketResponse,
    DistributionResponse,
    RequestedSongItemResponse,
    RecentlySungItemResponse,
    InsightsResponse,
)
from server.dependencies import get_app_context


router = APIRouter()


@router.get("/api/stats/overview", response_model=OverviewStatsResponse)
def api_overview(req: Request):
    ctx = get_app_context(req)
    svc = ctx.stats_service
    o = svc.overview()
    return OverviewStatsResponse(
        total_songs=o.total_songs,
        active_songs=o.active_songs,
        draft_songs=o.draft_songs,
        total_events=o.total_events,
        events_by_type=o.events_by_type,
        total_practice_minutes=o.total_practice_minutes,
        total_practice_sessions=o.total_practice_sessions,
        current_streak_days=o.current_streak_days,
        longest_streak_days=o.longest_streak_days,
        total_queue_requests=o.total_queue_requests,
        total_performances=o.total_performances,
        total_posters_exported=o.total_posters_exported,
        note=o.note,
    )


@router.get("/api/stats/feed", response_model=FeedResponse)
def api_feed(req: Request, limit: int = 50):
    ctx = get_app_context(req)
    svc = ctx.stats_service
    f = svc.feed(limit=limit)
    return FeedResponse(
        items=[FeedItemResponse(
            event_id=i.event_id,
            occurred_at=i.occurred_at,
            type=i.type,
            source=i.source,
            song_id=i.song_id,
            title_snapshot=i.title_snapshot,
            meta=i.meta,
            summary=i.summary,
        ) for i in f.items],
        note=f.note,
    )


@router.get("/api/stats/top-songs", response_model=TopSongsResponse)
def api_top_songs(req: Request, metric: str = "request", limit: int = 10):
    ctx = get_app_context(req)
    svc = ctx.stats_service
    t = svc.top_songs(metric=metric, limit=limit)
    return TopSongsResponse(
        metric=t.metric,
        items=[TopSongItemResponse(
            song_id=i.song_id, title=i.title, artist=i.artist,
            count=i.count, minutes=i.minutes,
        ) for i in t.items],
        note=t.note,
    )


@router.get("/api/stats/distribution", response_model=DistributionResponse)
def api_distribution(req: Request, metric: str = "difficulty"):
    ctx = get_app_context(req)
    svc = ctx.stats_service
    d = svc.distribution(metric=metric)
    return DistributionResponse(
        metric=d.metric,
        buckets=[DistributionBucketResponse(label=b.label, count=b.count) for b in d.buckets],
        note=d.note,
    )


# ---- M2.5 综合洞察 ----
@router.get("/api/stats/insights", response_model=InsightsResponse)
def api_insights(req: Request, request_limit: int = 10, sung_limit: int = 10):
    """M2.5: 综合洞察
    - top_requested: 点歌次数 Top N（+ 最近点歌时间）
    - recently_sung: 最近演唱 Top N（按时间倒序 + 演唱次数）
    """
    request_limit = max(1, min(50, int(request_limit)))
    sung_limit = max(1, min(50, int(sung_limit)))
    ctx = get_app_context(req)
    svc = ctx.stats_service
    i = svc.insights(request_limit=request_limit, sung_limit=sung_limit)
    return InsightsResponse(
        top_requested=[RequestedSongItemResponse(
            song_id=x.song_id, title=x.title, artist=x.artist,
            count=x.count, last_requested=x.last_requested,
        ) for x in i.top_requested],
        recently_sung=[RecentlySungItemResponse(
            song_id=x.song_id, title=x.title, artist=x.artist,
            last_sung=x.last_sung, times_sung=x.times_sung,
        ) for x in i.recently_sung],
        note=i.note,
    )
