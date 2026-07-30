"""P4 R3: 学歌练习 HTTP 路由（/api/practice*）。

端点:
- POST /api/practice/log            打卡 (幂等, event_id 去重)
- GET  /api/practice/stats           累计统计 (total/streak/last_30/top/months)
- GET  /api/practice/streak          连续天数
- GET  /api/practice/months/{month}  单月汇总
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from server.api.errors import ApiError
from server.api.handlers import api_error_response
from server.api.secondary_models import (
    PracticeLogRequest,
    PracticeLogResponse,
    PracticeMonthSummaryResponse,
    PracticeStatsResponse,
    PracticeStreakResponse,
)
from server.dependencies import get_app_context
from server.services.practice import (
    PracticeServiceError,
    PracticeValidationFailed,
)


router = APIRouter()


@router.post("/api/practice/log", response_model=PracticeLogResponse)
def api_practice_log(payload: PracticeLogRequest, req: Request):
    """打卡。幂等: 相同 event_id 重复提交 → already_processed=True。"""
    svc = get_app_context(req).practice_service
    try:
        result = svc.log({
            "song_id": payload.song_id,
            "title_snapshot": payload.title_snapshot,
            "minutes": payload.minutes,
            "self_rating": payload.self_rating,
            "note": payload.note,
            "occurred_at": payload.occurred_at,
            "event_id": payload.event_id or None,
            "source": "learning-api",
        })
    except PracticeValidationFailed as exc:
        return api_error_response(req, 400, ApiError("invalid_practice", str(exc)))
    except PracticeServiceError as exc:
        return api_error_response(req, 500, ApiError("practice_error", str(exc)))
    return PracticeLogResponse(
        event_id=result.log.event_id,
        already_processed=result.already_processed,
        minutes=result.log.minutes,
        self_rating=result.log.self_rating,
        note=result.log.note,
        title_snapshot=result.log.title_snapshot,
    )


@router.get("/api/practice/stats", response_model=PracticeStatsResponse)
def api_practice_stats(req: Request, today: str | None = None):
    """累计学习统计。"""
    svc = get_app_context(req).practice_service
    stats = svc.get_stats(today=today)
    top = [
        {"title": t[0], "sessions": t[1], "minutes": t[2]}
        for t in stats.top_practiced
    ]
    months = [
        {
            "month": m.month, "total_minutes": m.total_minutes,
            "total_sessions": m.total_sessions, "unique_songs": m.unique_songs,
            "rated_count": m.rated_count,
            "rating_avg": (m.rating_sum / m.rated_count) if m.rated_count else 0.0,
        }
        for m in stats.months
    ]
    return PracticeStatsResponse(
        total_minutes=stats.total_minutes,
        total_sessions=stats.total_sessions,
        current_streak_days=stats.current_streak.current_streak,
        longest_streak_days=stats.current_streak.longest_streak,
        last_30_days=stats.last_30_days,
        songs_practiced=stats.songs_practiced,
        top_practiced=top,
        month_current_minutes=stats.month_current.total_minutes,
        month_current_sessions=stats.month_current.total_sessions,
        months=months,
    )


@router.get("/api/practice/streak", response_model=PracticeStreakResponse)
def api_practice_streak(req: Request, today: str | None = None):
    """连续练习天数。"""
    svc = get_app_context(req).practice_service
    streak = svc.get_streak(today=today)
    return PracticeStreakResponse(
        current_streak=streak.current_streak,
        longest_streak=streak.longest_streak,
        total_days=streak.total_days,
        first_date=streak.first_date,
        last_date=streak.last_date,
    )


@router.get("/api/practice/months/{month}",
            response_model=PracticeMonthSummaryResponse)
def api_practice_month(month: str, req: Request):
    """单月汇总。month = YYYY-MM。"""
    if len(month) != 7 or month[4] != "-":
        return api_error_response(
            req, 400, ApiError("invalid_month",
                                f"month 必须是 YYYY-MM 格式: {month!r}"),
        )
    svc = get_app_context(req).practice_service
    ms = svc.get_month_summary(month)
    return PracticeMonthSummaryResponse(
        month=ms.month,
        total_minutes=ms.total_minutes,
        total_sessions=ms.total_sessions,
        unique_songs=ms.unique_songs,
        rated_count=ms.rated_count,
        rating_avg=(ms.rating_sum / ms.rated_count) if ms.rated_count else 0.0,
    )
