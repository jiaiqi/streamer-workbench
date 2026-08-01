"""R3.5 learning-report 布局单元测试。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.layouts import REGISTRY, get_layout
from core.layouts.learning_report import (
    LearningReportSnapshot,
    _format_date,
    _format_date_range,
)


class LearningReportRegistrationTests(unittest.TestCase):

    def test_layout_registered(self):
        self.assertIn("learning-report", REGISTRY)
        layout = get_layout("learning-report")
        self.assertEqual(layout.id, "learning-report")
        self.assertEqual(layout.pages, 1)

    def test_capabilities_declared(self):
        layout = get_layout("learning-report")
        caps = layout.capabilities()
        self.assertEqual(caps["page_policy_mode"], "fixed-1")
        self.assertIn("9:20", caps["supported_canvas_ids"])
        self.assertIn("9:16", caps["supported_canvas_ids"])
        self.assertEqual(caps["input_kind"], "learning_report_snapshot")

    def test_params_have_keys(self):
        layout = get_layout("learning-report")
        params = layout.params()
        keys = {p.key for p in params}
        self.assertIn("margin", keys)
        self.assertIn("font_title", keys)
        self.assertIn("font_section", keys)
        self.assertIn("show_timeline", keys)
        self.assertIn("top_n_artists", keys)
        d = {p.key: p.default for p in params}
        self.assertEqual(d["show_timeline"], True)
        self.assertEqual(d["top_n_artists"], 5)


class LearningReportSnapshotTests(unittest.TestCase):

    def test_empty_snapshot(self):
        snap = LearningReportSnapshot()
        self.assertTrue(snap.is_empty)
        summary = snap.analyze_summary()
        self.assertEqual(summary["total_practice_sessions"], 0)
        self.assertEqual(summary["songs_learned_count"], 0)

    def test_non_empty_when_practice_exists(self):
        snap = LearningReportSnapshot(
            total_practice_sessions=3,
            total_practice_minutes=45,
            recent_practice=(
                {"title": "A", "minutes": 15, "occurred_at": "2026-07-30T20:00"},
            ),
        )
        self.assertFalse(snap.is_empty)

    def test_non_empty_when_songs_learned(self):
        snap = LearningReportSnapshot(
            songs_learned=({"id": "s1", "title": "A", "learned_at": "2026-07-30T20:00"},),
        )
        self.assertFalse(snap.is_empty)


class HelperTests(unittest.TestCase):

    def test_format_date_iso(self):
        self.assertEqual(_format_date("2026-07-31T20:30:00"), "07-31")

    def test_format_date_empty(self):
        self.assertEqual(_format_date(""), "")
        self.assertEqual(_format_date("garbage"), "garbage")

    def test_format_date_range(self):
        self.assertEqual(
            _format_date_range("2026-07-01T00:00", "2026-07-31T23:59"),
            "07-01 → 07-31",
        )
        # 空 start 走空路径
        self.assertEqual(_format_date_range("", "2026-07-31T23:59"), "")
        self.assertEqual(_format_date_range("2026-07-01T00:00", ""), "自 07-01")
        self.assertEqual(_format_date_range("", ""), "")


class LearningReportLayoutEdgeCases(unittest.TestCase):

    def test_analyze_empty(self):
        layout = get_layout("learning-report")

        class _Canvas:
            height = 1920
            width = 1080
            margin = 58

        snap = LearningReportSnapshot()
        report = layout.analyze(snap, _Canvas())
        self.assertEqual(report["page_count"], 1)
        self.assertTrue(report["empty"])

    def test_analyze_wrong_library_type(self):
        layout = get_layout("learning-report")

        class _Canvas:
            height = 1920
            width = 1080
            margin = 58

        report = layout.analyze("not a snapshot", _Canvas())
        self.assertEqual(report["page_count"], 1)
        self.assertTrue(report["empty"])
        self.assertIsNotNone(report["degrade_reason"])

    def test_categorize_returns_one_page(self):
        layout = get_layout("learning-report")
        snap = LearningReportSnapshot()
        pages = layout.categorize(snap)
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].page, 1)


if __name__ == "__main__":
    unittest.main()
