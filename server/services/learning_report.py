"""R3.5 learning-report 海报数据适配：把 StatsService 摘要拍成 LearningReportSnapshot。

不在 StatsService 内部塞海报相关代码——保持统计服务纯净。
海报数据是「跨服务编排」的产物，专门一个 helper 完成。

约束：
- 不修改任何事件 / 曲库状态
- 只读
- 时间窗口：默认最近 30 天（可参数化）
- 字段从 stats 已有方法组合 + 新增 artist 聚合
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

from core.layouts.learning_report import LearningReportSnapshot
from core.data.events import compute_streaks  # R4.0: 共享 streak 算法
from server.services.stats import StatsApplicationService


def build_learning_report_snapshot(
    stats_service: StatsApplicationService,
    *,
    period_label: str = "",
    days: int = 30,
    top_n_artists: int = 5,
) -> LearningReportSnapshot:
    """从 StatsApplicationService 构造 LearningReportSnapshot。

    period_label: 副标题标签（"2026 年 7 月"），为空时按 days 动态生成。
    days: 时间窗口（默认 30 天）
    top_n_artists: 歌手 Top N 上限
    """
    # 周期时间
    now = datetime.now().astimezone()
    end = now
    start = now - timedelta(days=days)
    since_iso = start.isoformat(timespec="seconds")
    until_iso = end.isoformat(timespec="seconds")
    if not period_label:
        period_label = f"近 {days} 天"

    # 累计统计（全部时间）
    overview = stats_service.overview()
    songs_by_id = stats_service._songs_snapshot()[0]

    # 本期聚合
    practice_sessions = 0
    practice_minutes = 0
    practice_dates: set[str] = set()
    songs_learned_map: dict[str, dict] = {}   # id → {title, artist, learned_at}
    recent_practice: list[dict] = []
    artist_counter: Counter = Counter()

    for ev in stats_service._all_events():
        ev_type = ev.get("type", "")
        ev_time = ev.get("occurred_at", "")
        if not (since_iso <= ev_time <= until_iso):
            continue
        meta = ev.get("meta", {}) or {}
        if ev_type == "practice_logged":
            practice_sessions += 1
            minutes = int(meta.get("minutes", 0))
            practice_minutes += minutes
            practice_dates.add(ev_time[:10])
            sid = ev.get("song_id", "")
            title = ev.get("title_snapshot", "")
            if not title and sid in songs_by_id:
                title = songs_by_id[sid].title
            recent_practice.append({
                "title": title or "（无题）",
                "minutes": minutes,
                "self_rating": int(meta.get("self_rating", 0)),
                "occurred_at": ev_time,
                "note": str(meta.get("note", "")).strip(),
            })
            # 歌手聚合
            song = songs_by_id.get(sid)
            if song and song.artists:
                artist_counter[song.artists[0]] += 1
        elif ev_type == "song_learned":
            sid = ev.get("song_id", "")
            title = ev.get("title_snapshot", "")
            if not title and sid in songs_by_id:
                title = songs_by_id[sid].title
            song = songs_by_id.get(sid)
            artist = song.artists[0] if (song and song.artists) else ""
            songs_learned_map[sid] = {
                "id": sid,
                "title": title or "（无题）",
                "artist": artist,
                "learned_at": ev_time,
            }

    # 排序近期练习（按时间倒序）
    recent_practice.sort(key=lambda x: x.get("occurred_at", ""), reverse=True)

    # 难度分布（用 overview 全部时间的）
    difficulty_buckets = []
    for bucket in overview.events_by_type:
        pass  # events_by_type 不是 difficulty，留空
    # 实际从曲库统计（取 distribution(difficulty)）
    diff = stats_service.distribution(metric="difficulty")
    difficulty_buckets = tuple(
        {"label": b.label, "count": b.count} for b in diff.buckets
    )

    # 调性分布
    keys = stats_service.distribution(metric="key")
    key_buckets = tuple(
        {"label": b.label, "count": b.count} for b in keys.buckets
    )

    # Top 歌手
    top_artists = tuple(
        {"name": name, "count": cnt}
        for name, cnt in artist_counter.most_common(top_n_artists)
    )

    # 学会的歌曲（按时间倒序）
    songs_learned_list = sorted(
        songs_learned_map.values(),
        key=lambda x: x.get("learned_at", ""),
        reverse=True,
    )

    # 连续天数 (R4.0 抽到 core.data.events.compute_streaks，与 StatsService 同源)
    current_streak, longest_streak = compute_streaks(practice_dates)

    return LearningReportSnapshot(
        report_title="学歌报告",
        period_label=period_label,
        period_start=since_iso,
        period_end=until_iso,
        total_practice_minutes=practice_minutes,
        total_practice_sessions=practice_sessions,
        current_streak_days=current_streak,
        longest_streak_days=longest_streak,
        songs_learned=tuple(songs_learned_list),
        recent_practice=tuple(recent_practice),
        top_artists=top_artists,
        difficulty_buckets=difficulty_buckets,
        key_buckets=key_buckets,
    )
