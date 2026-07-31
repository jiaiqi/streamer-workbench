"""P4 R1: 学歌练习领域模型——打卡事件、统计口径与周期计算。

事件协议（遵循 Event v2 白名单）:
- practice_logged: 用户记录一次练习打卡
- 每次打卡写 1 条事件; 补报幂等 (event_id 去重)

Schema v1 (2026-07-30):
  song_id:        可选 song_id 引用 (未会歌曲 记 learning candidate)
  title_snapshot: 练习时歌曲名快照 (防改名后历史断链)
  minutes:        练习时长 (分钟, >=1)
  self_rating:    自评 (1-5, None=未填)
  note:           备注/卡点
  occurred_at:    练习日期 (与 recorded_at 分开; 补报可指定过去日期)
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, List, Optional


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _today() -> str:
    return date.today().isoformat()


def _new_event_id() -> str:
    return f"evt_{uuid.uuid4().hex}"


@dataclass(frozen=True)
class PracticeLog:
    """单次练习打卡记录。

    按 v3 §S4 协议: song_id / title_snapshot / minutes / self_rating / note
    全部是稳定引用 + 统计用字段。
    """
    event_id: str = field(default_factory=_new_event_id)
    song_id: str = ""                  # 可为空: 无具体歌曲只记学习卡点
    title_snapshot: str = ""           # 歌曲名快照 (歌曲改名后不变)
    minutes: int = 0                   # >= 1
    self_rating: int = 0               # 1..5, 0=未填
    note: str = ""
    occurred_at: str = field(default_factory=_now_iso)   # 练习日期 (可指定过去)
    recorded_at: str = field(default_factory=_now_iso)  # 服务器补报时间
    source: str = "learning-ui"        # 谁记录的

    def validate(self) -> None:
        if self.minutes < 1:
            raise ValueError(f"minutes 必须 >= 1: {self.minutes}")
        if self.self_rating < 0 or self.self_rating > 5:
            raise ValueError(f"self_rating 必须在 0..5: {self.self_rating}")
        if not self.song_id and not self.note.strip():
            raise ValueError("无歌曲时 note 不能为空 (必须记录学习卡点)")


@dataclass(frozen=True)
class PracticeStreak:
    """连续练习天数。

    从 practice_logged 事件流中计算: 有 >=1 个 occurred_at 当天的练习即算连续。
    """
    current_streak: int = 0      # 今天是否连续 (不算过去)
    longest_streak: int = 0      # 历史最长连续天数
    total_days: int = 0          # 有记录的天数
    first_date: str = ""         # 首次打卡日期 (YYYY-MM-DD)
    last_date: str = ""          # 最近打卡日期


@dataclass(frozen=True)
class PracticeMonthSummary:
    """单月练习汇总 (统计口径 v1)。"""
    month: str                    # YYYY-MM
    total_minutes: int = 0
    total_sessions: int = 0
    unique_songs: int = 0
    rating_sum: int = 0           # 平均 rating = rating_sum / rated_count
    rated_count: int = 0
    learned_count: int = 0        # 本月标记为 active 的歌曲数
    new_learned: int = 0          # 本月新学会 (未会→active)


@dataclass(frozen=True)
class PracticeDaySummary:
    """单日练习汇总。"""
    date: str                     # YYYY-MM-DD
    total_minutes: int = 0
    total_sessions: int = 0
    songs: tuple = ()             # tuple[(title_snapshot, minutes), ...]


@dataclass(frozen=True)
class LearningStats:
    """累计学习统计 (学习页主数据)。"""
    total_minutes: int = 0
    total_sessions: int = 0
    current_streak: PracticeStreak = field(default_factory=PracticeStreak)
    last_30_days: int = 0        # 最近 30 天打卡天数
    songs_practiced: int = 0     # 有打卡记录的歌曲总数
    top_practiced: tuple = ()    # tuple[(title, sessions, minutes), ...] TOP5
    month_current: PracticeMonthSummary = field(default_factory=lambda: PracticeMonthSummary(month=""))
    months: tuple = ()           # tuple[PracticeMonthSummary, ...] 近 6 个月


# ── 计算工具 ──


def compute_streak(logs: List[PracticeLog], today: Optional[str] = None) -> PracticeStreak:
    """从打卡列表计算连续天数。

    today: 可选 YYYY-MM-DD 字符串; 缺省=今天。
    返回 (current_streak, longest_streak, total_days, first_date, last_date)。
    """
    if not logs:
        return PracticeStreak()
    today = today or _today()
    # 按 occurred_at 的日期去重 (同一天多次练习只算一次)
    unique_dates = sorted({
        log.occurred_at[:10] for log in logs
    })
    first = unique_dates[0]
    last = unique_dates[-1]
    total = len(unique_dates)
    # 算 longest streak: 连续 >=1 次练习的日期序列
    longest = cur = 1
    for i in range(1, len(unique_dates)):
        prev = date.fromisoformat(unique_dates[i - 1])
        curr = date.fromisoformat(unique_dates[i])
        delta = (curr - prev).days
        if delta == 1:
            cur += 1
        else:
            longest = max(longest, cur)
            cur = 1
    longest = max(longest, cur)
    # current_streak: 从 last_date 往回数。
    # 语义 (GitHub-style):
    #   - last_date == today          → streak 还活着，从今天往回数
    #   - last_date == today - 1 day  → 今天还没打但 streak 尚未断，从昨天往回数
    #   - 其他                         → streak 已断, 0
    current_streak = 0
    today_date = date.fromisoformat(today)
    last_date = date.fromisoformat(last)
    gap_from_today = (today_date - last_date).days
    if gap_from_today in (0, 1):
        current_streak = 1
        for i in range(len(unique_dates) - 2, -1, -1):
            prev = date.fromisoformat(unique_dates[i])
            curr = date.fromisoformat(unique_dates[i + 1])
            if (curr - prev).days == 1:
                current_streak += 1
            else:
                break
    return PracticeStreak(
        current_streak=current_streak,
        longest_streak=longest,
        total_days=total,
        first_date=first,
        last_date=last,
    )


def compute_month_summary(month: str, logs: List[PracticeLog]) -> PracticeMonthSummary:
    """计算单月汇总。

    month: YYYY-MM
    """
    minutes = sessions = rating_sum = rated_count = 0
    songs = set()
    for log in logs:
        if log.occurred_at[:7] != month:
            continue
        minutes += log.minutes
        sessions += 1
        if log.song_id:
            songs.add(log.song_id)
        if log.self_rating >= 1:
            rating_sum += log.self_rating
            rated_count += 1
    return PracticeMonthSummary(
        month=month,
        total_minutes=minutes,
        total_sessions=sessions,
        unique_songs=len(songs),
        rating_sum=rating_sum,
        rated_count=rated_count,
    )


def compute_stats(logs: List[PracticeLog], today: Optional[str] = None) -> LearningStats:
    """汇总全部打卡 → LearningStats。

    包含: total/minutes/sessions, streak, last_30_days, top_practiced,
    months 近 6 个月, month_current。
    """
    today = today or _today()
    month_today = today[:7]

    total_minutes = sum(l.minutes for l in logs)
    total_sessions = len(logs)
    songs_practiced = len({l.song_id for l in logs if l.song_id})

    # 近 30 天
    import datetime as _dt
    today_dt = _dt.date.fromisoformat(today)
    last30 = 0
    for l in logs:
        try:
            d = _dt.date.fromisoformat(l.occurred_at[:10])
        except (ValueError, TypeError):
            continue
        if (today_dt - d).days <= 29:
            last30 += 1

    streak = compute_streak(logs, today)

    # TOP5 by sessions
    from collections import defaultdict
    counter = defaultdict(lambda: {"sessions": 0, "minutes": 0, "title": ""})
    for l in logs:
        key = l.title_snapshot or l.song_id
        counter[key]["sessions"] += 1
        counter[key]["minutes"] += l.minutes
        if not counter[key]["title"]:
            counter[key]["title"] = key
    top = sorted(counter.values(), key=lambda x: (-x["sessions"], -x["minutes"]))[:5]
    top_practiced = tuple(
        (t["title"], t["sessions"], t["minutes"]) for t in top
    )

    # months: 近 6 个月
    import datetime as _dt
    months = []
    for i in range(5, -1, -1):
        # 计算 month string
        year = today_dt.year
        month = today_dt.month - i
        while month <= 0:
            month += 12
            year -= 1
        while month > 12:
            month -= 12
            year += 1
        m = f"{year:04d}-{month:02d}"
        months.append(compute_month_summary(m, logs))

    month_current = months[-1] if months else PracticeMonthSummary(month=month_today)

    return LearningStats(
        total_minutes=total_minutes,
        total_sessions=total_sessions,
        current_streak=streak,
        last_30_days=last30,
        songs_practiced=songs_practiced,
        top_practiced=top_practiced,
        month_current=month_current,
        months=tuple(months),
    )
