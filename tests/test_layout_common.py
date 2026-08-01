"""R4.0 抽出的 core/layouts/_common.py 公共 helper 单测。

覆盖：format_date_* / truncate / safe_label / result_glyph + compute_streaks
（streak 虽在 core/data/events.py，但用同一测试夹具验证公共契约）。

每个 helper 必须与原 layout 内嵌实现 1:1 等价，确保未来重构不会无意
改变金标准输出。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.data.events import compute_streaks
from core.layouts import _common


class FormatDateShortTests(unittest.TestCase):

    def test_iso_to_mm_dd(self):
        self.assertEqual(_common.format_date_short("2026-07-29T08:00:00+08:00"), "07-29")
        self.assertEqual(_common.format_date_short("2026-01-01T00:00:00+00:00"), "01-01")
        self.assertEqual(_common.format_date_short("2026-12-31T23:59:59+08:00"), "12-31")

    def test_empty_or_invalid_returns_input(self):
        self.assertEqual(_common.format_date_short(""), "")
        self.assertEqual(_common.format_date_short("plain text"), "plain text")
        # 没有 'T' → 原样返回
        self.assertEqual(_common.format_date_short("2026-07-29"), "2026-07-29")


class FormatDateLongTests(unittest.TestCase):

    def test_iso_to_mm_dd_hh_mm(self):
        self.assertEqual(_common.format_date_long("2026-07-29T08:30:00+08:00"), "07-29 08:30")
        self.assertEqual(_common.format_date_long("2026-01-01T00:00:00+00:00"), "01-01 00:00")

    def test_iso_with_microseconds(self):
        self.assertEqual(_common.format_date_long("2026-07-29T08:30:45.123456+08:00"), "07-29 08:30")

    def test_empty_or_invalid_returns_input(self):
        self.assertEqual(_common.format_date_long(""), "")
        self.assertEqual(_common.format_date_long("nope"), "nope")


class FormatDateRangeTests(unittest.TestCase):

    def test_both_dates(self):
        self.assertEqual(
            _common.format_date_range("2026-07-01T00:00:00+08:00", "2026-07-31T00:00:00+08:00"),
            "07-01 → 07-31",
        )

    def test_only_start(self):
        self.assertEqual(_common.format_date_range("2026-07-01T00:00:00+08:00", ""), "自 07-01")

    def test_empty(self):
        self.assertEqual(_common.format_date_range("", ""), "")


class TruncateTests(unittest.TestCase):

    def _make_draw(self, char_w: int = 10):
        """构造一个 mock ImageDraw：每个字符固定 char_w 像素。"""
        d = MagicMock()
        def textlength(text, font=None):
            return len(text) * char_w
        d.textlength.side_effect = textlength
        return d

    def test_short_text_unchanged(self):
        d = self._make_draw(char_w=10)
        # "abc" → 30 像素 < 100，不截断
        self.assertEqual(_common.truncate("abc", 100, d, font=None), "abc")

    def test_long_text_truncated_with_ellipsis(self):
        d = self._make_draw(char_w=10)
        # "abcdefghij" (10 字符 = 100 px) > 50 像素，截到 4 字符 + "…" = 50 px
        self.assertEqual(_common.truncate("abcdefghij", 50, d, font=None), "abcd…")

    def test_minimum_two_chars_kept(self):
        d = self._make_draw(char_w=10)
        # max_w 极小（5 px）→ 减到 2 字符（"ab" = 20 px + "…" = 30 px 仍 > 5）
        # 但 len(s) > 2 才会继续减，len=2 跳出；最后 "ab" + "…" = "ab…"
        result = _common.truncate("abcdef", 5, d, font=None)
        self.assertEqual(result, "ab…")


class SafeLabelTests(unittest.TestCase):

    def test_title_and_requester(self):
        self.assertEqual(_common.safe_label("枫", "张三"), "枫 · 张三")

    def test_only_title(self):
        self.assertEqual(_common.safe_label("枫", ""), "枫")
        self.assertEqual(_common.safe_label("枫", "  "), "枫")  # 纯空白

    def test_empty_title_falls_back(self):
        self.assertEqual(_common.safe_label("", "张三"), "（无题） · 张三")
        self.assertEqual(_common.safe_label("", ""), "（无题）")

    def test_strip_whitespace(self):
        self.assertEqual(_common.safe_label("  枫  ", "  张三  "), "枫 · 张三")


class ResultGlyphTests(unittest.TestCase):

    def test_known_results(self):
        self.assertEqual(_common.result_glyph("sung"), "✓")
        self.assertEqual(_common.result_glyph("skipped"), "⏭")
        self.assertEqual(_common.result_glyph("cancelled"), "✗")
        self.assertEqual(_common.result_glyph("postponed"), "⏸")
        self.assertEqual(_common.result_glyph("unknown"), "?")
        self.assertEqual(_common.result_glyph("duplicate_merged"), "⊕")

    def test_unknown_result_returns_dot(self):
        self.assertEqual(_common.result_glyph(""), "·")
        self.assertEqual(_common.result_glyph("nonsense"), "·")


class DrawPillTests(unittest.TestCase):

    def test_returns_correct_width(self):
        d = MagicMock()
        d.textlength.return_value = 50  # → tw = 50 + 36 = 86
        tw = _common.draw_pill(d, 100, 200, "test", font=None,
                               bg_color=(1, 2, 3), fg_color=(4, 5, 6))
        self.assertEqual(tw, 86)
        # 验证 rounded_rectangle 用对了 (x, y, x+tw, y+44)
        d.rounded_rectangle.assert_called_once()
        args = d.rounded_rectangle.call_args[0][0]
        self.assertEqual(args, (100, 200, 186, 244))  # 100 + 86 = 186
        # 验证 text 起点 = (x + 18, y + 4)
        d.text.assert_called_once()
        text_args = d.text.call_args[0][0]
        self.assertEqual(text_args, (118, 204))


class HorizontalRuleTests(unittest.TestCase):

    def test_default_width(self):
        d = MagicMock()
        _common.horizontal_rule(d, 10, 100, 50, "red")
        d.line.assert_called_once_with((10, 50, 100, 50), fill="red", width=2)

    def test_custom_width(self):
        d = MagicMock()
        _common.horizontal_rule(d, 0, 50, 30, (0, 0, 0), width=5)
        d.line.assert_called_once_with((0, 30, 50, 30), fill=(0, 0, 0), width=5)


class ComputeStreaksTests(unittest.TestCase):
    """compute_streaks 是从 server/services/{stats,learning_report} 抽出的。

    关键契约：current_streak 从 today 往回数；longest_streak 是历史最长。
    """

    def test_empty_set(self):
        self.assertEqual(compute_streaks(set()), (0, 0))

    def test_single_day_today(self):
        from datetime import date
        today = date.today().isoformat()
        self.assertEqual(compute_streaks({today}), (1, 1))

    def test_single_day_yesterday_no_current(self):
        from datetime import date, timedelta
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        # 今天没打卡，current=0；longest=1
        self.assertEqual(compute_streaks({yesterday}), (0, 1))

    def test_consecutive_today_yesterday(self):
        from datetime import date, timedelta
        today = date.today().isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        # 连续 2 天：current=2，longest=2
        self.assertEqual(compute_streaks({today, yesterday}), (2, 2))

    def test_three_consecutive(self):
        from datetime import date, timedelta
        today = date.today()
        dates = {(today - timedelta(days=i)).isoformat() for i in range(3)}
        self.assertEqual(compute_streaks(dates), (3, 3))

    def test_broken_longest_higher(self):
        from datetime import date, timedelta
        today = date.today()
        # 当前只打卡今天 (current=1)；但 5 天前连续 3 天 (longest=3)
        dates = {(today).isoformat()}
        for i in range(7, 10):  # 7, 8, 9 天前 → 连续 3 天
            dates.add((today - timedelta(days=i)).isoformat())
        self.assertEqual(compute_streaks(dates), (1, 3))


if __name__ == "__main__":
    unittest.main()
