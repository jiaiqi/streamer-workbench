"""P4 R1: 学歌练习领域模型测试。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.data.practice import (
    PracticeLog,
    PracticeMonthSummary,
    compute_month_summary,
    compute_stats,
    compute_streak,
    _today,
)


class PracticeLogValidationTests(unittest.TestCase):

    def test_valid_log(self):
        log = PracticeLog(song_id="song_x", title_snapshot="江南",
                          minutes=30, self_rating=4)
        log.validate()

    def test_rejects_zero_minutes(self):
        with self.assertRaises(ValueError):
            PracticeLog(minutes=0).validate()

    def test_rejects_rating_out_of_range(self):
        with self.assertRaises(ValueError):
            PracticeLog(minutes=1, self_rating=7).validate()

    def test_rejects_rating_below_0(self):
        with self.assertRaises(ValueError):
            PracticeLog(minutes=1, self_rating=-1).validate()

    def test_rejects_no_song_no_note(self):
        with self.assertRaises(ValueError):
            PracticeLog(minutes=10, note="").validate()

    def test_allows_no_song_with_note(self):
        log = PracticeLog(minutes=10, note="和弦卡壳")
        log.validate()

    def test_default_event_id_generated(self):
        log = PracticeLog(minutes=10)
        assert log.event_id.startswith("evt_")
        assert len(log.event_id) > 10


class ComputeStreakTests(unittest.TestCase):

    def test_empty_logs_no_streak(self):
        streak = compute_streak([], today="2026-07-30")
        self.assertEqual(streak.current_streak, 0)
        self.assertEqual(streak.longest_streak, 0)
        self.assertEqual(streak.total_days, 0)

    def test_single_day_streak(self):
        logs = [PracticeLog(minutes=10, occurred_at="2026-07-30T08:00:00+08:00")]
        streak = compute_streak(logs, today="2026-07-30")
        self.assertEqual(streak.current_streak, 1)
        self.assertEqual(streak.longest_streak, 1)
        self.assertEqual(streak.total_days, 1)

    def test_same_day_multiple_logs_count_once(self):
        logs = [
            PracticeLog(minutes=10, occurred_at="2026-07-30T08:00:00+08:00"),
            PracticeLog(minutes=20, occurred_at="2026-07-30T12:00:00+08:00"),
        ]
        streak = compute_streak(logs, today="2026-07-30")
        self.assertEqual(streak.current_streak, 1)
        self.assertEqual(streak.total_days, 1)

    def test_three_consecutive_days(self):
        logs = [
            PracticeLog(minutes=10, occurred_at="2026-07-28T08:00:00+08:00"),
            PracticeLog(minutes=20, occurred_at="2026-07-29T09:00:00+08:00"),
            PracticeLog(minutes=30, occurred_at="2026-07-30T07:00:00+08:00"),
        ]
        streak = compute_streak(logs, today="2026-07-30")
        self.assertEqual(streak.current_streak, 3)
        self.assertEqual(streak.longest_streak, 3)

    def test_gap_breaks_streak(self):
        logs = [
            PracticeLog(minutes=10, occurred_at="2026-07-28T08:00:00+08:00"),
            PracticeLog(minutes=20, occurred_at="2026-07-29T09:00:00+08:00"),
            PracticeLog(minutes=30, occurred_at="2026-07-31T07:00:00+08:00"),
        ]
        streak = compute_streak(logs, today="2026-07-31")
        self.assertEqual(streak.current_streak, 1)  # 断掉后重新起算
        self.assertEqual(streak.longest_streak, 2)  # 最长仍是 2

    def test_streak_zero_when_today_missing(self):
        logs = [
            PracticeLog(minutes=10, occurred_at="2026-07-28T08:00:00+08:00"),
        ]
        streak = compute_streak(logs, today="2026-07-30")
        # last_date=2026-07-28 != today=2026-07-30 → current_streak=0
        self.assertEqual(streak.current_streak, 0)
        self.assertEqual(streak.longest_streak, 1)


class ComputeMonthSummaryTests(unittest.TestCase):

    def _log(self, minutes=10, rating=4, occurred_at="2026-07-15T10:00:00+08:00",
             song_id="song_x"):
        return PracticeLog(minutes=minutes, self_rating=rating,
                            occurred_at=occurred_at, song_id=song_id,
                            title_snapshot="江南")

    def test_single_log(self):
        logs = [self._log(minutes=30, rating=5)]
        ms = compute_month_summary("2026-07", logs)
        self.assertEqual(ms.total_minutes, 30)
        self.assertEqual(ms.total_sessions, 1)
        self.assertEqual(ms.unique_songs, 1)
        self.assertEqual(ms.rated_count, 1)

    def test_rating_sum_calculated(self):
        logs = [self._log(minutes=10, rating=3), self._log(minutes=20, rating=5)]
        ms = compute_month_summary("2026-07", logs)
        self.assertEqual(ms.rating_sum, 8)
        self.assertEqual(ms.rated_count, 2)

    def test_rating_zero_not_counted(self):
        logs = [self._log(minutes=10, rating=0)]
        ms = compute_month_summary("2026-07", logs)
        self.assertEqual(ms.rated_count, 0)

    def test_wrong_month_filtered_out(self):
        logs = [self._log(minutes=10, occurred_at="2026-06-15T10:00:00+08:00")]
        ms = compute_month_summary("2026-07", logs)
        self.assertEqual(ms.total_sessions, 0)


class ComputeStatsTests(unittest.TestCase):

    def _log(self, minutes=10, rating=0, occurred_at="2026-07-15T10:00:00+08:00",
             song_id="", title_snapshot="", note=""):
        return PracticeLog(minutes=minutes, self_rating=rating,
                            occurred_at=occurred_at, song_id=song_id,
                            title_snapshot=title_snapshot, note=note)

    def test_empty_logs_defaults(self):
        stats = compute_stats([], today="2026-07-30")
        self.assertEqual(stats.total_minutes, 0)
        self.assertEqual(stats.total_sessions, 0)
        self.assertEqual(stats.last_30_days, 0)
        self.assertEqual(stats.top_practiced, ())
        # months 永远返回近 6 个月 (含空月份), 供 UI 渲染折线图
        self.assertEqual(len(stats.months), 6)

    def test_total_minutes_sum(self):
        logs = [self._log(minutes=10), self._log(minutes=20)]
        stats = compute_stats(logs, today="2026-07-30")
        self.assertEqual(stats.total_minutes, 30)

    def test_top_practiced_sorted_by_sessions(self):
        logs = [
            self._log(minutes=5, title_snapshot="A", song_id="s1"),
            self._log(minutes=5, title_snapshot="A", song_id="s1"),
            self._log(minutes=10, title_snapshot="A", song_id="s1"),
            self._log(minutes=10, title_snapshot="B", song_id="s2"),
        ]
        stats = compute_stats(logs, today="2026-07-30")
        self.assertEqual(len(stats.top_practiced), 2)
        # A: 3次 20分钟 > B: 1次 10分钟
        self.assertEqual(stats.top_practiced[0][0], "A")
        self.assertEqual(stats.top_practiced[0][1], 3)
        self.assertEqual(stats.top_practiced[1][0], "B")

    def test_last_30_days_counts(self):
        """last_30_days = 今天 + 前 29 天; 2026-06-30 距 2026-07-30 是 30 天 (超出)。"""
        logs = [
            self._log(minutes=5, occurred_at="2026-07-30T08:00:00+08:00"),
            self._log(minutes=5, occurred_at="2026-07-29T08:00:00+08:00"),
            self._log(minutes=5, occurred_at="2026-07-01T08:00:00+08:00"),
            self._log(minutes=5, occurred_at="2026-06-30T08:00:00+08:00"),
        ]
        stats = compute_stats(logs, today="2026-07-30")
        self.assertEqual(stats.last_30_days, 3)  # 07-30, 07-29, 07-01

    def test_months_returns_6(self):
        logs = [self._log(minutes=10, occurred_at="2026-07-15T08:00:00+08:00")]
        stats = compute_stats(logs, today="2026-07-30")
        self.assertEqual(len(stats.months), 6)
        # 最后一个月是本月
        self.assertEqual(stats.months[-1].month, "2026-07")


if __name__ == "__main__":
    unittest.main()
