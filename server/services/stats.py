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
from typing import Any, Dict, List, Optional, Tuple

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
class RequestedSongItem:
    """M2.5: 点歌热度 Top N（含最近一次点歌时间）"""
    song_id: str
    title: str
    artist: str = ""
    count: int = 0
    last_requested: str = ""


@dataclass(frozen=True)
class RecentlySungItem:
    """M2.5: 最近演唱 Top N（按时间倒序）"""
    song_id: str
    title: str
    artist: str = ""
    last_sung: str = ""
    times_sung: int = 0


@dataclass(frozen=True)
class InsightsResult:
    top_requested: List[RequestedSongItem] = field(default_factory=list)
    recently_sung: List[RecentlySungItem] = field(default_factory=list)
    note: str = ""


# P1-A3: 下一步建议 DTO
# 评估 5.6 / 8.18 第 5.3 节：行动型统计洞察
#   - 学歌复习：learned_at > 30 天前且本周没练习
#   - 难唱推荐：difficulty=hard + 最近 5 次表演不会/延期
#   - 表演间隔：上次表演 > 7 天前的 top 点歌曲目

@dataclass(frozen=True)
class NextStepItem:
    """单个下一步建议。"""
    kind: str  # 'review' | 'difficult' | 'restage' | 'practice'
    song_id: str
    title: str
    artist: str = ""
    reason: str = ""  # 人读理由（如「31 天前学会，本周未练」）
    days_since: int = 0  # 距今天数
    metric: int = 0  # 附加计数（不会次数 / 点歌次数 / 练习次数）


@dataclass(frozen=True)
class NextStepsResult:
    items: List[NextStepItem] = field(default_factory=list)
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

    # ---- M2.5 综合洞察 ----
    def insights(self, *, request_limit: int = 10, sung_limit: int = 10) -> InsightsResult:
        """聚合 events.jsonl：
          - top_requested: 点歌次数 Top N + 最近一次点歌时间
          - recently_sung: 最近演唱 Top N + 演唱次数（按时间倒序）
        """
        songs_by_id, *_ = self._songs_snapshot()

        def _resolve(sid: str) -> Tuple[str, str]:
            song = songs_by_id.get(sid)
            if song is None:
                return f"(未知歌曲) {sid[:18]}…", ""
            title = song.title or ""
            artist = "、".join(song.artists) if song.artists else ""
            return title, artist

        # 1) top_requested: 累加 queue_added
        req_counter: Counter = Counter()
        req_last: Dict[str, str] = {}
        for ev in self._all_events():
            if ev.get("type") != "queue_added":
                continue
            sid = ev.get("song_id", "")
            if not sid:
                continue
            req_counter[sid] += 1
            t = ev.get("occurred_at") or ev.get("created_at", "")
            if t and (sid not in req_last or t > req_last[sid]):
                req_last[sid] = t
        top_req: List[RequestedSongItem] = []
        for sid, count in req_counter.most_common(request_limit):
            title, artist = _resolve(sid)
            top_req.append(RequestedSongItem(
                song_id=sid, title=title, artist=artist,
                count=count, last_requested=req_last.get(sid, ""),
            ))

        # 2) recently_sung: 按 performance_sung 时间倒序
        sung_last: Dict[str, str] = {}
        sung_count: Counter = Counter()
        for ev in self._all_events():
            if ev.get("type") != "performance_sung":
                continue
            sid = ev.get("song_id", "")
            if not sid:
                continue
            sung_count[sid] += 1
            t = ev.get("occurred_at") or ev.get("created_at", "")
            if t and (sid not in sung_last or t > sung_last[sid]):
                sung_last[sid] = t
        # 按 last_sung 倒序
        recent_sung: List[RecentlySungItem] = []
        for sid, last in sorted(sung_last.items(), key=lambda kv: kv[1], reverse=True)[:sung_limit]:
            title, artist = _resolve(sid)
            recent_sung.append(RecentlySungItem(
                song_id=sid, title=title, artist=artist,
                last_sung=last, times_sung=sung_count.get(sid, 0),
            ))

        note = ""
        if not top_req and not recent_sung:
            note = "暂无点歌 / 演唱数据；先开几场直播或录入练习记录"
        return InsightsResult(
            top_requested=top_req,
            recently_sung=recent_sung,
            note=note,
        )

    # ---- P1-A3: 行动型统计洞察（下一步建议） ----
    def next_steps(
        self,
        *,
        review_window_days: int = 30,    # 距今超过 N 天的 learned_at → 复习
        restage_window_days: int = 7,    # 距今超过 N 天的 last_sung → 表演间隔
        difficult_recent_n: int = 5,     # 最近 N 次表演里不会/延期次数
        practice_window_days: int = 7,   # 本周（距今 < N 天）内练习过算"近期已练"
        max_per_kind: int = 5,
    ) -> NextStepsResult:
        """返回 3 类建议：

        - **review** (学歌复习)：`learned_at` 距今 > review_window_days 且本周
          （距今 < practice_window_days）没有 practice_logged 事件的 active 歌
        - **difficult** (难唱推荐)：`difficulty=hard` 且最近 difficult_recent_n 次
          表演结果里"不会"(`performance_unknown` / `performance_skipped`)次数 ≥ 2
        - **restage** (表演间隔)：top 点歌（queue_added 累加 ≥ 3 次）但上次表演
          `performance_sung` 距今 > restage_window_days

        数据不足时返回空 items + note 引导用户录入数据。
        """
        from datetime import datetime, timezone

        songs_by_id, total, active, draft = self._songs_snapshot()
        if total == 0:
            return NextStepsResult(
                note="曲库为空；先导入示例数据或添加几首歌")
        # today (UTC) — 用 ISO date 比较
        today = datetime.now(timezone.utc).date()

        def _days_since(iso: str) -> int:
            if not iso:
                return -1
            try:
                d = datetime.fromisoformat(iso.replace("Z", "+00:00")).date()
            except Exception:
                return -1
            return (today - d).days

        # 聚合事件
        last_practice: Dict[str, str] = {}
        last_sung: Dict[str, str] = {}
        sung_count: Counter = Counter()
        unknown_recent: Counter = Counter()  # song_id → 最近 N 次里不会次数
        # 维护每个 song_id 的"最近 N 次表演结果"（按时间倒序遍历）
        recent_results_per_song: Dict[str, List[str]] = {}

        # 单遍 events.jsonl 收集
        for ev in self._all_events():
            t = ev.get("type", "")
            sid = ev.get("song_id", "")
            if not sid:
                continue
            ts = ev.get("occurred_at") or ""
            if t == "practice_logged":
                if ts and (sid not in last_practice or ts > last_practice[sid]):
                    last_practice[sid] = ts
            elif t == "performance_sung":
                if ts and (sid not in last_sung or ts > last_sung[sid]):
                    last_sung[sid] = ts
                sung_count[sid] += 1
            elif t in ("performance_unknown", "performance_skipped",
                       "performance_postponed", "performance_cancelled"):
                # 累加"不会"信号；difficult 计算时取最近 N 次
                results = recent_results_per_song.setdefault(sid, [])
                results.append(t)

        # 限制每个 song_id 的 recent_results 长度（不切片，但 total events 可能很大；
        # 折中：只对前 2000 个事件做累加 — 对单机工具已足够）
        # 这里再 trim
        for sid, results in recent_results_per_song.items():
            if len(results) > difficult_recent_n:
                recent_results_per_song[sid] = results[-difficult_recent_n:]

        items: List[NextStepItem] = []

        # 1) review：learned_at 距今 > 30 天 + 本周没练习
        review_count = 0
        for sid, song in songs_by_id.items():
            if song.status != "active":
                continue
            learned = getattr(song, "learned_at", "") or ""
            d = _days_since(learned)
            if d < review_window_days:
                continue
            # 本周（距今 < practice_window_days）有练习 → 跳过
            last_p = last_practice.get(sid, "")
            if last_p and _days_since(last_p) < practice_window_days:
                continue
            artist = "、".join(song.artists) if song.artists else ""
            items.append(NextStepItem(
                kind="review",
                song_id=sid, title=song.title or "", artist=artist,
                reason=f"{d} 天前学会，本周未练" if d > 0 else "已学但未练",
                days_since=d, metric=d,
            ))
            review_count += 1
            if review_count >= max_per_kind:
                break
        # 按 days_since 倒序
        review_items = sorted(
            [i for i in items if i.kind == "review"],
            key=lambda i: i.days_since, reverse=True)[:max_per_kind]
        items = [i for i in items if i.kind != "review"] + review_items

        # 2) difficult：difficulty=hard 且最近 N 次里"不会"≥ 2
        difficult_count = 0
        for sid, song in songs_by_id.items():
            if song.status != "active":
                continue
            if (song.difficulty or "").lower() != "hard":
                continue
            results = recent_results_per_song.get(sid, [])
            if len(results) < 2:
                continue
            unknown_n = sum(1 for r in results
                            if r in ("performance_unknown", "performance_skipped"))
            if unknown_n < 2:
                continue
            last_s = last_sung.get(sid, "")
            d = _days_since(last_s) if last_s else 0
            artist = "、".join(song.artists) if song.artists else ""
            items.append(NextStepItem(
                kind="difficult",
                song_id=sid, title=song.title or "", artist=artist,
                reason=f"最近 {len(results)} 次表演 {unknown_n} 次不会/延期",
                days_since=d, metric=unknown_n,
            ))
            difficult_count += 1
            if difficult_count >= max_per_kind:
                break
        # 按 metric 倒序
        diff_items = sorted(
            [i for i in items if i.kind == "difficult"],
            key=lambda i: i.metric, reverse=True)[:max_per_kind]
        items = [i for i in items if i.kind != "difficult"] + diff_items

        # 3) restage：top 点歌 ≥ 3 次 + last_sung > 7 天
        # 先算点歌计数
        req_counter: Counter = Counter()
        for ev in self._all_events():
            if ev.get("type") != "queue_added":
                continue
            sid = ev.get("song_id", "")
            if sid:
                req_counter[sid] += 1
        restage_count = 0
        for sid, song in songs_by_id.items():
            if song.status != "active":
                continue
            if req_counter.get(sid, 0) < 3:
                continue
            last_s = last_sung.get(sid, "")
            if last_s and _days_since(last_s) <= restage_window_days:
                continue
            d = _days_since(last_s) if last_s else -1
            artist = "、".join(song.artists) if song.artists else ""
            items.append(NextStepItem(
                kind="restage",
                song_id=sid, title=song.title or "", artist=artist,
                reason=(f"点歌 {req_counter[sid]} 次但"
                        f"{d if d >= 0 else '从未'}前唱过" if d >= 0
                        else f"点歌 {req_counter[sid]} 次但从未唱过"),
                days_since=d, metric=req_counter[sid],
            ))
            restage_count += 1
            if restage_count >= max_per_kind:
                break
        restage_items = sorted(
            [i for i in items if i.kind == "restage"],
            key=lambda i: i.metric, reverse=True)[:max_per_kind]
        items = [i for i in items if i.kind != "restage"] + restage_items

        note = ""
        if not items:
            note = ("没有可行动的下一步建议；继续学歌、点歌、演唱让数据沉淀"
                    "（当前 %d 首 active，%d 首 draft）" % (active, draft))
        return NextStepsResult(items=items, note=note)

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
