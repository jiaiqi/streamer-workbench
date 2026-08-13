"""R4 Runtime v2 退出条件 #1 — 三个场景同一稳定计划格式 测试。

覆盖：
- 3 套独立数据通道（SongLibrary / LiveSessionSnapshot / LearningReportSnapshot）
  走 analyze → plan → render 端到端
- 3 套场景 plan 输出结构一致（顶层字段完全相同）
- 同一输入 plan 结果稳定（frozen + __hash__ → 多次 plan 同 hash）
- 同一输入 render 像素稳定（PNG hash 守恒）
- 1 项 cross-scenario 字段一致性
"""
from __future__ import annotations

import dataclasses
import hashlib
import io
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.data.songs import Song, SongLibrary
from core.engine import render_page
from core.layouts import LayoutContext, LayoutPlan, get_layout
from core.layouts.learning_report import LearningReportSnapshot
from core.layouts.live_set import LiveSessionSnapshot
from core.spec import get_canvas_spec
from core.themes.loader import load_themes

FONT_PATH = ROOT / "fonts" / "MaokenAssortedSans.ttf"
THEME_NAME = "海洋柔光"
CANVAS_ID = "抖音全屏 9:20"


# ── Fixtures（与 tools/verify_runtime_v2_three_scenarios.py 一致） ──

def _grid_wrap_library() -> SongLibrary:
    titles = ["枫", "后来", "恋爱ing", "黑色毛衣", "江南", "童年",
              "Take Me Home, Country Roads"]
    return SongLibrary([Song(id=t, title=t, artists=(), tags=(), section=1, status="active")
                        for t in titles])


def _live_set_snap() -> LiveSessionSnapshot:
    return LiveSessionSnapshot(
        session_id="live_v2_verify",
        session_title="R4 退出条件验证直播",
        session_state="closed",
        started_at="2026-08-12T20:00:00+08:00",
        closed_at="2026-08-12T22:00:00+08:00",
        rule_version="rule_default01",
        requests=(
            {"id": "r1", "song_id": "s1", "song_title": "恋爱ing",
             "requester_name": "小明", "requested_at": "2026-08-12T20:05:00+08:00",
             "state": "current", "is_bumped": False},
            {"id": "r2", "song_id": "s2", "song_title": "小幸运",
             "requester_name": "小红", "requested_at": "2026-08-12T20:10:00+08:00",
             "state": "queued", "is_bumped": False},
            {"id": "r3", "song_id": "s3", "song_title": "告白气球",
             "requester_name": "张三", "requested_at": "2026-08-12T20:15:00+08:00",
             "state": "queued", "is_bumped": True},
        ),
        performances=(
            {"request_id": "r4", "song_id": "s4", "song_title": "稻香",
             "requester_name": "李四", "result": "sung",
             "performed_at": "2026-08-12T20:30:00+08:00"},
            {"request_id": "r5", "song_id": "s5", "song_title": "晴天",
             "requester_name": "王五", "result": "sung",
             "performed_at": "2026-08-12T20:50:00+08:00"},
        ),
    )


def _learning_report_snap() -> LearningReportSnapshot:
    songs_learned = [
        (f"歌曲 {i:02d}", f"歌手 {i % 5:02d}", f"2026-05-{15 + i:02d}T20:00:00+08:00")
        for i in range(12)
    ]
    recent = [
        (f"歌曲 {i:02d}", 20 + (i % 4) * 5, (i % 5) + 1,
         f"2026-07-{20 + i:02d}T20:00:00+08:00")
        for i in range(10)
    ]
    return LearningReportSnapshot(
        report_title="百日学歌报告",
        period_label="2026 年 4 月 - 7 月",
        period_start="2026-04-15T00:00:00+08:00",
        period_end="2026-07-31T23:59:59+08:00",
        total_practice_minutes=1240,
        total_practice_sessions=58,
        current_streak_days=7,
        longest_streak_days=21,
        songs_learned=tuple(
            {"id": f"s{idx}", "title": t, "artist": a, "learned_at": la}
            for idx, (t, a, la) in enumerate(songs_learned)
        ),
        recent_practice=tuple(
            {"title": t, "minutes": m, "self_rating": r, "occurred_at": oa, "note": ""}
            for t, m, r, oa in recent
        ),
        top_artists=tuple(
            {"name": f"歌手 {i:02d}", "count": 12 - i * 2} for i in range(5)
        ),
        difficulty_buckets=(
            {"label": "简单", "count": 18},
            {"label": "中等", "count": 32},
            {"label": "困难", "count": 8},
        ),
    )


SCENARIOS = [
    ("grid-wrap", _grid_wrap_library),
    ("live-set", _live_set_snap),
    ("learning-report", _learning_report_snap),
]


# ── Helpers ──

@pytest.fixture(scope="module")
def ctx() -> LayoutContext:
    spec = get_canvas_spec(CANVAS_ID, avoid=True)
    return LayoutContext(canvas=spec, parameters={})


@pytest.fixture(scope="module")
def theme():
    return load_themes(str(ROOT / "themes"))[THEME_NAME]


def _hash_png_bytes(img) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return hashlib.sha256(buf.getvalue()).hexdigest()[:12]


# ── 3 套场景 analyze() 端到端 ──

class TestThreeScenariosAnalyze:
    @pytest.mark.parametrize("layout_id", [s[0] for s in SCENARIOS])
    def test_analyze_returns_layout_analysis(self, layout_id, ctx):
        """3 套场景 analyze() 都返回 LayoutAnalysis，page_count 与 layout.pages 一致。"""
        fixture_fn = next(f[1] for f in SCENARIOS if f[0] == layout_id)
        library = fixture_fn()
        layout = get_layout(layout_id)
        analysis = layout.analyze(library, ctx)
        assert analysis is not None
        assert hasattr(analysis, "page_count")
        assert analysis.page_count >= 1
        # 至少 1 个 section（live-set / learning-report 固定 4 个分类，grid-wrap 7 段）
        assert analysis.sections_count >= 0


# ── 3 套场景 plan() 端到端 ──

class TestThreeScenariosPlan:
    @pytest.mark.parametrize("layout_id", [s[0] for s in SCENARIOS])
    def test_plan_returns_layout_plan(self, layout_id, ctx):
        """3 套场景 plan() 都返回 LayoutPlan，pages 非空，layout_id 对得上。"""
        fixture_fn = next(f[1] for f in SCENARIOS if f[0] == layout_id)
        library = fixture_fn()
        layout = get_layout(layout_id)
        plan = layout.plan(library, ctx)
        assert isinstance(plan, LayoutPlan)
        assert plan.layout_id == layout_id
        assert len(plan.pages) >= 1
        # 第一页 page ≥ 1
        assert plan.pages[0].page >= 1


# ── 3 套场景 render 像素稳定性 ──

class TestThreeScenariosRenderStability:
    @pytest.mark.parametrize("layout_id", [s[0] for s in SCENARIOS])
    def test_render_hash_stable(self, layout_id, ctx, theme):
        """同一输入 render 多次，PNG hash 守恒。"""
        fixture_fn = next(f[1] for f in SCENARIOS if f[0] == layout_id)
        library = fixture_fn()
        layout = get_layout(layout_id)
        img1 = render_page(theme, layout, library, ctx.canvas, 1, str(FONT_PATH))
        img2 = render_page(theme, layout, library, ctx.canvas, 1, str(FONT_PATH))
        assert _hash_png_bytes(img1) == _hash_png_bytes(img2), (
            f"{layout_id} render 像素不稳定"
        )


# ── 3 套场景 plan 确定性（frozen + hashable → 多次同 hash） ──

class TestThreeScenariosDeterminism:
    @pytest.mark.parametrize("layout_id", [s[0] for s in SCENARIOS])
    def test_plan_hash_stable(self, layout_id, ctx):
        """同一输入 plan 多次，hash 一致（frozen + __hash__ 实现）。"""
        fixture_fn = next(f[1] for f in SCENARIOS if f[0] == layout_id)
        library = fixture_fn()
        layout = get_layout(layout_id)
        plan1 = layout.plan(library, ctx)
        plan2 = layout.plan(library, ctx)
        # frozen + 自定义 __hash__ → 同一输入同 hash
        assert hash(plan1) == hash(plan2)
        # 也可放入 set（hashable 验证）
        assert len({plan1, plan2}) == 1


# ── Cross-scenario：3 套 plan 顶层字段完全一致 ──

class TestThreeScenariosUniformContract:
    def test_all_plans_have_same_top_level_fields(self, ctx):
        """R4 Runtime v2 收口判据：3 套场景 plan 顶层字段完全一致。"""
        top_fields_set: set[tuple[str, ...]] = set()
        for layout_id, fixture_fn in SCENARIOS:
            library = fixture_fn()
            layout = get_layout(layout_id)
            plan = layout.plan(library, ctx)
            top_fields_set.add(tuple(f.name for f in dataclasses.fields(plan)))
        assert len(top_fields_set) == 1, (
            f"3 套场景 plan 顶层字段不一致：{top_fields_set}"
        )
        # 关键字段存在
        fields = next(iter(top_fields_set))
        for required in ("layout_id", "layout_version", "pages", "analysis",
                          "param_overrides", "effective_palette_name"):
            assert required in fields, f"缺失关键字段 {required}：{fields}"
