"""R3 学歌发现服务 — 3 套发现机制 + 智能推荐。

数据源: events.jsonl 事件流
- recent_learned: song_learned 事件 (按 occurred_at 倒序)
- request_hot: queue_added / performance_recorded 事件 (按次数 + 最近演唱)
- recommend: 综合 learning_interval_score + hot_score + difficulty

设计原则:
- 全部从 events.jsonl 现算, 不存中间结果 (符合"统计 = events + 当前状态 现算的视图"原则)
- 单次扫描 O(N), N 事件量 (个人使用每日数十事件) 足够
- 冷启动: 0 事件时返回空列表, 不展示伪趋势
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, List, Optional

from server.ports.repositories import EventQuery


# ===== DTO =====

@dataclass(frozen=True)
class DiscoveryItem:
    """单个发现项 (歌曲 + 排序依据 + 上下文)。"""
    song_id: str
    title: str
    artist: str = ""
    difficulty: str = ""  # 简单 / 中等 / 困难 / ""
    key: str = ""
    capo: int = 0
    # 上下文指标
    last_learned_at: str = ""      # 最近学会时间
    last_requested_at: str = ""    # 最近点歌时间
    last_performed_at: str = ""    # 最近演唱时间
    practice_count: int = 0        # 累计打卡次数
    request_count: int = 0         # 累计点歌次数
    perform_count: int = 0         # 累计演唱次数
    # 推荐解释 (recommend 模式用)
    reason: str = ""


@dataclass(frozen=True)
class DiscoveryResult:
    items: List[DiscoveryItem] = field(default_factory=list)
    note: str = ""


def _artist_str(song) -> str:
    if song is None:
        return ""
    artists = getattr(song, "artists", None) or []
    if isinstance(artists, list):
        return ", ".join(str(a) for a in artists)
    return str(artists)


# ===== Service =====

class DiscoveryApplicationService:
    """3 套发现机制 + 智能推荐。

    注入:
    - event_store: FileEventStore (events.jsonl)
    - song_repository: FileSongRepository (拿歌曲元数据, 可选)
    """

    def __init__(self, *, event_store, song_repository=None):
        self._events = event_store
        self._songs = song_repository

    def _all_events(self):
        return self._events.iter(EventQuery())

    def _songs_by_id(self) -> dict:
        if not self._songs:
            return {}
        try:
            lib = self._songs.load().value
            return {s.id: s for s in lib.songs}
        except Exception:
            return {}

    # ---- 1. recent_learned ----
    def recent_learned(self, *, limit: int = 20) -> DiscoveryResult:
        latest: dict[str, dict] = {}
        for ev in self._all_events():
            if ev.get("type") != "song_learned":
                continue
            sid = ev.get("song_id", "")
            if not sid:
                continue
            prev = latest.get(sid)
            ts = ev.get("occurred_at", "")
            if prev is None or ts > prev.get("occurred_at", ""):
                latest[sid] = ev
        if not latest:
            return DiscoveryResult(items=[], note="尚未标记任何歌曲为已会")
        sorted_events = sorted(
            latest.values(), key=lambda e: e.get("occurred_at", ""), reverse=True
        )[:limit]
        songs_by_id = self._songs_by_id()
        items = []
        for ev in sorted_events:
            sid = ev.get("song_id", "")
            song = songs_by_id.get(sid)
            items.append(DiscoveryItem(
                song_id=sid,
                title=ev.get("title_snapshot", "") or (song.title if song else f"(未知歌曲) {sid[:18]}…"),
                artist=_artist_str(song),
                difficulty=song.difficulty if song else "",
                key=song.key if song else "",
                capo=song.capo if song else 0,
                last_learned_at=ev.get("occurred_at", ""),
            ))
        return DiscoveryResult(items=items, note="")

    # ---- 2. request_hot ----
    def request_hot(self, *, limit: int = 20, since_days: int = 90) -> DiscoveryResult:
        cutoff = (datetime.now() - timedelta(days=since_days)).isoformat(timespec="seconds")
        queue: Counter = Counter()
        perform: Counter = Counter()
        last_requested: dict[str, str] = {}
        last_performed: dict[str, str] = {}
        for ev in self._all_events():
            if ev.get("occurred_at", "") < cutoff:
                continue
            et = ev.get("type", "")
            sid = ev.get("song_id", "")
            if not sid:
                continue
            if et == "queue_added":
                queue[sid] += 1
                ts = ev.get("occurred_at", "")
                if ts > last_requested.get(sid, ""):
                    last_requested[sid] = ts
            elif et in ("performance_recorded", "performance_sung"):
                # 实际事件类型是 performance_sung (R2 实现), 兼容保留 performance_recorded
                perform[sid] += 1
                ts = ev.get("occurred_at", "")
                if ts > last_performed.get(sid, ""):
                    last_performed[sid] = ts
        if not queue and not perform:
            return DiscoveryResult(items=[], note=f"近 {since_days} 天无点歌 / 演唱记录")
        scored: list[tuple[str, float]] = []
        for sid in (set(queue) | set(perform)):
            scored.append((sid, queue[sid] * 1.0 + perform[sid] * 2.0))
        scored.sort(key=lambda x: x[1], reverse=True)
        songs_by_id = self._songs_by_id()
        items = []
        for sid, score in scored[:limit]:
            song = songs_by_id.get(sid)
            if song:
                title = song.title
            else:
                title = f"(未知歌曲) {sid[:18]}…"
            items.append(DiscoveryItem(
                song_id=sid,
                title=title,
                artist=_artist_str(song),
                difficulty=song.difficulty if song else "",
                key=song.key if song else "",
                capo=song.capo if song else 0,
                last_requested_at=last_requested.get(sid, ""),
                last_performed_at=last_performed.get(sid, ""),
                request_count=queue[sid],
                perform_count=perform[sid],
                reason=f"点歌 {queue[sid]} 次 · 演唱 {perform[sid]} 次 (热度 {score:g})",
            ))
        return DiscoveryResult(items=items, note="")

    # ---- 3. recommend (今天该练什么) ----
    def recommend(self, *, limit: int = 8) -> DiscoveryResult:
        songs_by_id = self._songs_by_id()
        if not songs_by_id:
            return DiscoveryResult(items=[], note="曲库为空")

        last_practice: dict[str, str] = {}
        practice_count: dict[str, int] = {}
        last_learned: dict[str, str] = {}
        hot: Counter = Counter()

        for ev in self._all_events():
            sid = ev.get("song_id", "")
            if not sid or sid not in songs_by_id:
                continue
            et = ev.get("type", "")
            ts = ev.get("occurred_at", "")
            if et == "practice_logged":
                practice_count[sid] = practice_count.get(sid, 0) + 1
                if ts > last_practice.get(sid, ""):
                    last_practice[sid] = ts
            elif et == "song_learned":
                if ts > last_learned.get(sid, ""):
                    last_learned[sid] = ts
            elif et == "queue_added":
                cutoff = (datetime.now() - timedelta(days=90)).isoformat(timespec="seconds")
                if ts >= cutoff:
                    hot[sid] += 1

        scored: list[tuple[str, float, str]] = []
        for sid, song in songs_by_id.items():
            # 已会的歌不推荐 (除非仍被打卡 = 复习)
            if sid in last_learned and sid not in last_practice:
                continue
            lp = last_practice.get(sid, "")
            if lp:
                try:
                    lp_date = date.fromisoformat(lp[:10])
                    interval_days = (date.today() - lp_date).days
                except (ValueError, TypeError):
                    interval_days = 0
            else:
                interval_days = 30
            interval_score = min(interval_days / 7.0, 1.0)
            hot_score = min(hot.get(sid, 0) / 5.0, 1.0)
            diff_bonus = {"困难": 0.2, "中等": 0.1, "简单": 0.0}.get(song.difficulty, 0.0)
            final = interval_score * 0.5 + hot_score * 0.3 + diff_bonus

            reason_parts = []
            if lp:
                reason_parts.append(f"{interval_days} 天前练过")
            else:
                reason_parts.append("尚未练习")
            if hot.get(sid, 0) > 0:
                reason_parts.append(f"近 90 天被点 {hot[sid]} 次")
            if diff_bonus > 0:
                reason_parts.append(f"难度 {song.difficulty} (加成)")

            scored.append((sid, final, " · ".join(reason_parts)))

        scored.sort(key=lambda x: x[1], reverse=True)
        items = []
        for sid, score, reason in scored[:limit]:
            song = songs_by_id[sid]
            items.append(DiscoveryItem(
                song_id=sid,
                title=song.title,
                artist=_artist_str(song),
                difficulty=song.difficulty,
                key=song.key,
                capo=song.capo or 0,
                last_learned_at=last_learned.get(sid, ""),
                practice_count=practice_count.get(sid, 0),
                request_count=hot.get(sid, 0),
                reason=reason,
            ))
        if not items:
            return DiscoveryResult(items=[], note="曲库都标记为已会, 无新歌可推荐")
        return DiscoveryResult(items=items, note="")
