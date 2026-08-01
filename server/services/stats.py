"""R4 统计聚合服务 — 总览 / 事件时间线 / Top N / 分布。

全部从 events.jsonl + songs.json + 当前状态 现算, 不存中间结果。

数据源:
- events.jsonl: 全部历史事件 (queue_added / performance_* / practice_logged / ...)
- songs.json: 曲库当前状态 (mastered/draft, 难度, Key, 歌手)
- posters/: 海报文件夹 (已导出数, 由 caller 提供路径列表)

冷启动: 数据不足时返回空聚合, 配合 note 引导用户.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, List, Optional

from server.ports.repositories import EventQuery
from core.data.events import compute_streaks  # R4.0: 共享 streak 算法


# ===== DTO =====

@dataclass(frozen=True)
class OverviewStats:
    """全局概览。"""
    total_songs: int
    active_songs: int
    draft_songs: int
    # 事件聚合
    total_events: int
    events_by_type: dict[str, int]
    # 学歌
    total_practice_minutes: int
    total_practice_sessions: int
    current_streak_days: int
    longest_streak_days: int
    # 直播
    total_queue_requests: int
    total_performances: int
    # 海报
    total_posters_exported: int
    note: str = ""


@dataclass(frozen=True)
class FeedItem:
    """时间线条目。"""
    event_id: str
    occurred_at: str
    type: str
    source: str
    song_id: str = ""
    title_snapshot: str = ""
    meta: dict[str, Any] = field(default_factory=dict)
    summary: str = ""


@dataclass(frozen=True)
class FeedResult:
    items: List[FeedItem] = field(default_factory=list)
    note: str = ""


@dataclass(frozen=True)
class TopSongItem:
    song_id: str
    title: str
    artist: str = ""
    count: int = 0
    minutes: int = 0  # 仅 practice 有


@dataclass(frozen=True)
class TopSongsResult:
    metric: str
    items: List[TopSongItem] = field(default_factory=list)
    note: str = ""


@dataclass(frozen=True)
class DistributionBucket:
    label: str
    count: int


@dataclass(frozen=True)
class DistributionResult:
    metric: str  # difficulty / key / status
    buckets: List[DistributionBucket] = field(default_factory=list)
    note: str = ""


# ===== Service =====

class StatsApplicationService:
    def __init__(self, *, event_store, song_repository=None, poster_count: int = 0):
        self._events = event_store
        self._songs = song_repository
        self._poster_count = poster_count

    def _all_events(self):
        return self._events.iter(EventQuery())

    def _songs_snapshot(self) -> dict:
        """返回 (songs_by_id, total, active, draft)。"""
        if not self._songs:
            return ({}, 0, 0, 0)
        try:
            lib = self._songs.load().value
            songs_by_id = {s.id: s for s in lib.songs}
            active = sum(1 for s in lib.songs if s.status == "active")
            draft = sum(1 for s in lib.songs if s.status == "draft")
            return (songs_by_id, len(lib.songs), active, draft)
        except Exception:
            return ({}, 0, 0, 0)

    # ---- overview ----
    def overview(self) -> OverviewStats:
        songs_by_id, total, active, draft = self._songs_snapshot()
        type_counter: Counter = Counter()
        practice_minutes = 0
        practice_sessions = 0
        queue_requests = 0
        performances = 0
        practice_dates: set[str] = set()
        for ev in self._all_events():
            t = ev.get("type", "")
            type_counter[t] += 1
            if t == "practice_logged":
                practice_sessions += 1
                meta = ev.get("meta", {}) or {}
                practice_minutes += int(meta.get("minutes", 0))
                ts = ev.get("occurred_at", "")
                if ts:
                    practice_dates.add(ts[:10])
            elif t == "queue_added":
                queue_requests += 1
            elif t in ("performance_sung", "performance_recorded", "performance_postponed",
                       "performance_skipped", "performance_cancelled", "performance_unknown"):
                performances += 1
        # 连续天数 (复用 practice.py 的 compute_streak 算法, 但这里简化: 从事件 occurred_at 取日期集合)
        current_streak, longest_streak = self._compute_streaks(practice_dates)
        note = ""
        if total == 0:
            note = "曲库为空, 导入示例数据开始体验"
        elif type_counter.total() == 0:
            note = "暂无事件, 标记学会 / 启动直播 / 打卡 让统计开始"
        return OverviewStats(
            total_songs=total,
            active_songs=active,
            draft_songs=draft,
            total_events=sum(type_counter.values()),
            events_by_type=dict(type_counter),
            total_practice_minutes=practice_minutes,
            total_practice_sessions=practice_sessions,
            current_streak_days=current_streak,
            longest_streak_days=longest_streak,
            total_queue_requests=queue_requests,
            total_performances=performances,
            total_posters_exported=self._poster_count,
            note=note,
        )

    def _compute_streaks(self, dates: set[str]) -> tuple[int, int]:
        """R4.0: 抽到 core.data.events.compute_streaks 公共实现。
        保留方法名仅为最小化调用点改动，行为完全等价。
        """
        return compute_streaks(dates)

    # ---- feed (timeline) ----
    def feed(self, *, limit: int = 50) -> FeedResult:
        songs_by_id, *_ = self._songs_snapshot()
        items: List[FeedItem] = []
        for ev in self._all_events():
            t = ev.get("type", "")
            sid = ev.get("song_id", "")
            title = ev.get("title_snapshot", "")
            # 旧事件可能没记 title_snapshot, 从曲库回填
            if not title and sid in songs_by_id:
                title = songs_by_id[sid].title
            meta = ev.get("meta", {}) or {}
            summary = self._summarize(t, meta, title)
            items.append(FeedItem(
                event_id=ev.get("event_id", ""),
                occurred_at=ev.get("occurred_at", ""),
                type=t,
                source=ev.get("source", ""),
                song_id=sid,
                title_snapshot=title,
                meta=meta,
                summary=summary,
            ))
        items.sort(key=lambda x: x.occurred_at, reverse=True)
        items = items[:limit]
        if not items:
            return FeedResult(items=[], note="暂无事件")
        return FeedResult(items=items)

    def _summarize(self, t: str, meta: dict, title: str) -> str:
        if t == "practice_logged":
            mins = int(meta.get("minutes", 0))
            rating = int(meta.get("self_rating", 0))
            note = str(meta.get("note", "")).strip()
            parts = [f"练习 {mins} 分钟"]
            if title:
                parts.append(f"《{title}》")
            if rating:
                parts.append(f"自评 {rating}/5")
            if note:
                parts.append(f"— {note}")
            return " ".join(parts)
        if t == "song_learned":
            return f"标记学会《{title}》"
        if t == "song_unlearned":
            return f"取消学会《{title}》"
        if t == "song_added":
            return f"加入曲库《{title}》"
        if t == "song_deleted":
            return f"删除《{title}》"
        if t == "song_edited":
            return f"编辑《{title}》"
        if t == "queue_added":
            requester = meta.get("requester_name") or "观众"
            return f"{requester} 点歌《{title}》"
        if t == "queue_priority_changed":
            return f"调整优先级《{title}》"
        if t == "queue_rejected":
            return f"拒绝点歌《{title}》"
        if t == "performance_sung":
            return f"演唱《{title}》"
        if t == "performance_postponed":
            return f"延期《{title}》"
        if t == "performance_skipped":
            return f"跳过《{title}》"
        if t == "performance_cancelled":
            return f"取消《{title}》"
        if t == "performance_unknown":
            return f"未识别《{title}》"
        if t == "entitlement_granted":
            return f"授予权益 (song {sid[:8]})"
        if t == "entitlement_consumed":
            return f"消费权益 (song {sid[:8]})"
        if t == "poster_exported":
            theme = meta.get("theme", "?")
            pages = meta.get("pages", "?")
            return f"导出海报 {theme} × {pages} 页"
        return t

    # ---- top songs ----
    def top_songs(self, *, metric: str = "request", limit: int = 10) -> TopSongsResult:
        songs_by_id, *_ = self._songs_snapshot()
        counter: Counter = Counter()
        minutes: dict[str, int] = {}
        if metric == "request":
            for ev in self._all_events():
                if ev.get("type") == "queue_added":
                    sid = ev.get("song_id", "")
                    if sid:
                        counter[sid] += 1
        elif metric == "perform":
            for ev in self._all_events():
                if ev.get("type", "").startswith("performance_"):
                    sid = ev.get("song_id", "")
                    if sid:
                        counter[sid] += 1
        elif metric == "practice":
            for ev in self._all_events():
                if ev.get("type") == "practice_logged":
                    sid = ev.get("song_id", "")
                    if sid:
                        counter[sid] += 1
                        meta = ev.get("meta", {}) or {}
                        minutes[sid] = minutes.get(sid, 0) + int(meta.get("minutes", 0))
        else:
            return TopSongsResult(metric=metric, items=[], note=f"未知 metric: {metric}")
        items = []
        for sid, count in counter.most_common(limit):
            song = songs_by_id.get(sid)
            if song:
                title = song.title
                artist = ", ".join(song.artists) if song.artists else ""
            else:
                title = f"(未知歌曲) {sid[:18]}…"
                artist = ""
            items.append(TopSongItem(
                song_id=sid, title=title, artist=artist,
                count=count, minutes=minutes.get(sid, 0),
            ))
        if not items:
            return TopSongsResult(metric=metric, items=[], note=f"暂无 {metric} 数据")
        return TopSongsResult(metric=metric, items=items)

    # ---- distribution ----
    def distribution(self, *, metric: str = "difficulty") -> DistributionResult:
        songs_by_id, total, active, draft = self._songs_snapshot()
        all_songs = list(songs_by_id.values())
        if not all_songs:
            return DistributionResult(metric=metric, note="曲库为空")
        if metric == "difficulty":
            counter: Counter = Counter()
            for s in all_songs:
                d = s.difficulty or "未标"
                counter[d] += 1
            # 固定顺序: 简单 / 中等 / 困难 / 未标
            order = ["简单", "中等", "困难", "未标"]
            buckets = [DistributionBucket(label=l, count=counter.get(l, 0)) for l in order]
            return DistributionResult(metric=metric, buckets=buckets)
        if metric == "status":
            buckets = [
                DistributionBucket(label="已会 (active)", count=active),
                DistributionBucket(label="在学 (draft)", count=draft),
            ]
            return DistributionResult(metric=metric, buckets=buckets)
        if metric == "key":
            counter = Counter()
            for s in all_songs:
                k = s.key or "未标"
                counter[k] += 1
            buckets = [DistributionBucket(label=k, count=v) for k, v in
                       sorted(counter.items(), key=lambda x: -x[1])]
            return DistributionResult(metric=metric, buckets=buckets)
        return DistributionResult(metric=metric, note=f"未知 metric: {metric}")
