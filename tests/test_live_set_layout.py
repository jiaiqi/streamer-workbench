"""R2.5 live-set 布局单元测试。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.layouts import REGISTRY, get_layout
from core.layouts.live_set import (
    LiveSessionSnapshot,
    _format_date,
    _RESULT_GLYPH,
    _safe,
)
from core.layouts.base import ParamSpec


class LiveSetRegistrationTests(unittest.TestCase):

    def test_layout_registered(self):
        self.assertIn("live-set", REGISTRY)
        layout = get_layout("live-set")
        self.assertEqual(layout.id, "live-set")
        self.assertEqual(layout.pages, 1)

    def test_capabilities_declared(self):
        layout = get_layout("live-set")
        caps = layout.capabilities()
        self.assertEqual(caps["page_policy_mode"], "fixed-1")
        self.assertIn("9:20", caps["supported_canvas_ids"])
        self.assertIn("9:16", caps["supported_canvas_ids"])
        self.assertEqual(caps["input_kind"], "live_session_snapshot")

    def test_params_have_keys(self):
        layout = get_layout("live-set")
        params = layout.params()
        keys = {p.key for p in params}
        self.assertIn("margin", keys)
        self.assertIn("font_current", keys)
        self.assertIn("font_queued", keys)
        self.assertIn("font_sung", keys)
        self.assertIn("show_timestamps", keys)
        self.assertIn("show_requester", keys)
        # 默认值检查
        d = {p.key: p.default for p in params}
        self.assertEqual(d["show_timestamps"], True)
        self.assertEqual(d["show_requester"], True)


class LiveSessionSnapshotTests(unittest.TestCase):

    def test_empty_snapshot(self):
        snap = LiveSessionSnapshot()
        self.assertEqual(snap.total_count, 0)
        self.assertEqual(snap.sung_count, 0)
        self.assertEqual(snap.queued_count, 0)
        self.assertEqual(snap.current_count, 0)
        buckets = snap.categorize()
        self.assertEqual(len(buckets["current"]), 0)
        self.assertEqual(len(buckets["queued"]), 0)
        self.assertEqual(len(buckets["sung"]), 0)
        self.assertEqual(len(buckets["skipped"]), 0)

    def test_count_only_sung(self):
        snap = LiveSessionSnapshot(
            requests=(
                {"id": "r1", "song_id": "s1", "song_title": "A", "requester_name": "x", "state": "current"},
                {"id": "r2", "song_id": "s2", "song_title": "B", "requester_name": "y", "state": "queued"},
            ),
            performances=(
                {"request_id": "r3", "song_id": "s3", "song_title": "C", "result": "sung", "performed_at": "2026-07-31T20:00"},
                {"request_id": "r4", "song_id": "s4", "song_title": "D", "result": "cancelled"},
            ),
        )
        self.assertEqual(snap.total_count, 2)
        self.assertEqual(snap.sung_count, 1)
        self.assertEqual(snap.queued_count, 1)        # r2（r1 是 current）
        self.assertEqual(snap.current_count, 1)

    def test_categorize_buckets(self):
        snap = LiveSessionSnapshot(
            requests=(
                {"id": "r1", "song_id": "s1", "song_title": "A", "state": "current"},
                {"id": "r2", "song_id": "s2", "song_title": "B", "state": "queued"},
                {"id": "r3", "song_id": "s3", "song_title": "C", "state": "queued"},
            ),
            performances=(
                {"request_id": "r4", "song_id": "s4", "song_title": "D", "result": "sung", "performed_at": "2026-07-31T20:00"},
                {"request_id": "r2", "song_id": "s2", "song_title": "B", "result": "skipped"},
            ),
        )
        buckets = snap.categorize()
        self.assertEqual(len(buckets["current"]), 1)
        # queued: r3 (r2 被 skip 算 skipped)
        self.assertEqual(len(buckets["queued"]), 1)
        self.assertEqual(buckets["queued"][0]["id"], "r3")
        self.assertEqual(len(buckets["sung"]), 1)
        self.assertEqual(len(buckets["skipped"]), 1)


class HelperTests(unittest.TestCase):

    def test_format_date_iso(self):
        self.assertEqual(_format_date("2026-07-31T20:30:00"), "07-31 20:30")

    def test_format_date_empty(self):
        self.assertEqual(_format_date(""), "")
        self.assertEqual(_format_date("garbage"), "garbage")

    def test_safe(self):
        self.assertEqual(_safe("恋爱ing", "小明"), "恋爱ing · 小明")
        self.assertEqual(_safe("恋爱ing", ""), "恋爱ing")
        self.assertEqual(_safe("恋爱ing", "   "), "恋爱ing")
        self.assertEqual(_safe("", "小明"), "（无题） · 小明")

    def test_result_glyphs(self):
        self.assertEqual(_RESULT_GLYPH["sung"], "✓")
        self.assertEqual(_RESULT_GLYPH["cancelled"], "✗")


class LiveSetLayoutEdgeCases(unittest.TestCase):

    def test_analyze_empty(self):
        layout = get_layout("live-set")

        class _Canvas:
            height = 1920
            width = 1080
            margin = 58

        snap = LiveSessionSnapshot()
        report = layout.analyze(snap, _Canvas())
        self.assertEqual(report.page_count, 1)
        self.assertEqual(report.sections_count, 4)  # 4 段设计（v2 不依赖数据）

    def test_analyze_wrong_library_type(self):
        layout = get_layout("live-set")

        class _Canvas:
            height = 1920
            width = 1080
            margin = 58

        report = layout.analyze("not a snapshot", _Canvas())
        self.assertEqual(report.page_count, 1)
        self.assertEqual(report.sections_count, 0)  # wrong type → degrade → 0 sections
        self.assertIsNotNone(report.degrade_reason)

    def test_categorize_returns_one_page(self):
        layout = get_layout("live-set")
        snap = LiveSessionSnapshot(requests=({"id": "r1", "song_id": "s1", "song_title": "A"},))
        pages = layout.categorize(snap)
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].page, 1)


if __name__ == "__main__":
    unittest.main()
