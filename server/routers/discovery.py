"""R3 学歌发现路由 — 3 套发现机制 + 智能推荐。

端点:
- GET /api/discovery/recent-learned?limit=20     最近学会
- GET /api/discovery/request-hot?limit=20&since_days=90  点歌热度
- GET /api/discovery/recommend?limit=8            今天该练什么 (综合推荐)
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from server.api.secondary_models import DiscoveryItem, DiscoveryResponse
from server.dependencies import get_app_context


router = APIRouter()


def _to_response_item(di) -> DiscoveryItem:
    return DiscoveryItem(
        song_id=di.song_id,
        title=di.title,
        artist=di.artist,
        difficulty=di.difficulty,
        key=di.key,
        capo=di.capo,
        last_learned_at=di.last_learned_at,
        last_requested_at=di.last_requested_at,
        last_performed_at=di.last_performed_at,
        practice_count=di.practice_count,
        request_count=di.request_count,
        perform_count=di.perform_count,
        reason=di.reason,
    )


def _build_response(result) -> DiscoveryResponse:
    return DiscoveryResponse(
        items=[_to_response_item(di) for di in result.items],
        note=result.note,
    )


@router.get("/api/discovery/recent-learned", response_model=DiscoveryResponse)
def api_recent_learned(req: Request, limit: int = 20):
    """最近学会的歌曲 (按 song_learned 事件倒序)。"""
    ctx = get_app_context(req)
    svc = ctx.discovery_service
    result = svc.recent_learned(limit=limit)
    return _build_response(result)


@router.get("/api/discovery/request-hot", response_model=DiscoveryResponse)
def api_request_hot(req: Request, limit: int = 20, since_days: int = 90):
    """点歌热度 (queue_added + performance_recorded 加权)。"""
    ctx = get_app_context(req)
    svc = ctx.discovery_service
    result = svc.request_hot(limit=limit, since_days=since_days)
    return _build_response(result)


@router.get("/api/discovery/recommend", response_model=DiscoveryResponse)
def api_recommend(req: Request, limit: int = 8):
    """今天该练什么: 综合学习间隔 + 点歌热度 + 难度。"""
    ctx = get_app_context(req)
    svc = ctx.discovery_service
    result = svc.recommend(limit=limit)
    return _build_response(result)
