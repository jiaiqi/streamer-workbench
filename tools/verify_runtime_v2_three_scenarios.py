"""R4 Runtime v2 退出条件 #1 验证：3 个场景同一稳定计划格式。

3 个独立数据通道 → analyze → plan → render 全链路
- 场景 1：grid-wrap + SongLibrary（已会曲库）
- 场景 2：live-set + LiveSessionSnapshot（直播复盘）
- 场景 3：learning-report + LearningReportSnapshot（学歌报告）

输出：
- 控制台：3 个场景的 plan 结构对比表 + 一致性检查
- data/verify_runtime_v2/{layout_id}.json：每个场景的 LayoutPlan 序列化
- data/verify_runtime_v2/{layout_id}.png：每个场景的渲染结果

跑法：
    PYTHONPATH=. ./.venv/bin/python tools/verify_runtime_v2_three_scenarios.py

R4 退出条件进度 8/11 → 本批推进到 9/11。
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import sys
from pathlib import Path
from types import MappingProxyType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.data.songs import Song, SongLibrary
from core.engine import render_page
from core.layouts import LayoutContext, LayoutPlan, get_layout
from core.layouts.learning_report import LearningReportSnapshot
from core.layouts.live_set import LiveSessionSnapshot
from core.spec import get_canvas_spec
from core.themes.loader import load_themes

OUT_DIR = ROOT / "data" / "verify_runtime_v2"
FONT_PATH = ROOT / "fonts" / "MaokenAssortedSans.ttf"
THEME_NAME = "海洋柔光"
CANVAS_ID = "抖音全屏 9:20"


# ── 3 个场景代表 fixture（与金标准生成器保持一致） ──

def _grid_wrap_library() -> SongLibrary:
    """7 首歌（grid-wrap 标准用例）。"""
    titles = ["枫", "后来", "恋爱ing", "黑色毛衣", "江南", "童年",
              "Take Me Home, Country Roads"]
    return SongLibrary([Song(id=t, title=t, artists=(), tags=(), section=1, status="active")
                        for t in titles])


def _live_set_snap() -> LiveSessionSnapshot:
    """中等场次：1 current + 2 queued + 2 sung（live-set _case_multi 等价）。"""
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
    """百日活跃（learning-report _case_active 等价 — 12 首歌学会 + 大量练习）。"""
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


# ── 把 frozen dataclass 序列化成可 JSON 的 dict ──

def _to_jsonable(obj: Any) -> Any:
    """递归：frozen dataclass / tuple / MappingProxyType → dict / list / 标量。"""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        result = {"__type__": type(obj).__name__}
        for f in dataclasses.fields(obj):
            result[f.name] = _to_jsonable(getattr(obj, f.name))
        return result
    if isinstance(obj, MappingProxyType):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


# ── 3 个场景跑端到端 ──

SCENARIOS = [
    ("grid-wrap", "SongLibrary (7 首歌)", _grid_wrap_library),
    ("live-set", "LiveSessionSnapshot (1 current + 2 queued + 2 sung)", _live_set_snap),
    ("learning-report", "LearningReportSnapshot (12 学歌 + 10 练习)", _learning_report_snap),
]


def _hash_plan(plan: LayoutPlan) -> str:
    """plan 的稳定 hash — 用序列化后 sha256。"""
    raw = json.dumps(_to_jsonable(plan), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def _hash_png(png_bytes: bytes) -> str:
    return hashlib.sha256(png_bytes).hexdigest()[:12]


def _render_one(layout_id: str, library, ctx: LayoutContext) -> tuple[LayoutPlan, bytes]:
    """对单个 layout 跑 plan + render。

    返回 (plan, png_bytes)。png_bytes 来自 PIL Image 的 save 到 BytesIO。
    """
    import io
    from PIL import Image
    layout = get_layout(layout_id)
    plan = layout.plan(library, ctx)
    spec = ctx.canvas
    theme = load_themes(str(ROOT / "themes"))[THEME_NAME]
    pages = plan.pages
    img = render_page(theme, layout, library, spec, pages[0].page, str(FONT_PATH))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return plan, buf.getvalue()


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    spec = get_canvas_spec(CANVAS_ID, avoid=True)
    ctx = LayoutContext(canvas=spec, parameters={})

    print("=" * 78)
    print("R4 Runtime v2 退出条件 #1 验证 — 三个场景同一稳定计划格式")
    print("=" * 78)
    print(f"Theme: {THEME_NAME} | Canvas: {CANVAS_ID}")
    print()

    rows: list[dict[str, Any]] = []
    plan_hashes: dict[str, str] = {}
    render_hashes: dict[str, str] = {}

    for layout_id, desc, fixture_fn in SCENARIOS:
        library = fixture_fn()
        plan, png_bytes = _render_one(layout_id, library, ctx)
        plan_hash = _hash_plan(plan)
        render_hash = _hash_png(png_bytes)
        plan_hashes[layout_id] = plan_hash
        render_hashes[layout_id] = render_hash

        total_sections = sum(len(p.sections) for p in plan.pages)
        rows.append({
            "layout": layout_id,
            "pages": len(plan.pages),
            "sections": total_sections,
            "plan_hash": plan_hash,
            "render_hash": render_hash,
            "desc": desc,
        })

        # 写 JSON
        (OUT_DIR / f"{layout_id}.json").write_text(
            json.dumps(_to_jsonable(plan), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # 写 PNG（直接落盘 png_bytes）
        (OUT_DIR / f"{layout_id}.png").write_bytes(png_bytes)

    # ── 表格 ──
    print(f"{'Layout':<18} {'pages':>6} {'sections':>9} {'plan_hash':<14} {'render_hash':<14}")
    print("-" * 70)
    for r in rows:
        print(f"{r['layout']:<18} {r['pages']:>6} {r['sections']:>9} "
              f"{r['plan_hash']:<14} {r['render_hash']:<14}")
    print()

    # ── 一致性检查 ──
    print("结构一致性检查：")
    top_fields = set()
    for layout_id, _, _ in SCENARIOS:
        plan = get_layout(layout_id).plan(_grid_wrap_library() if layout_id == "grid-wrap" else (
            _live_set_snap() if layout_id == "live-set" else _learning_report_snap()
        ), ctx)
        top_fields.add(tuple(sorted(f.name for f in dataclasses.fields(plan))))
    if len(top_fields) == 1:
        print(f"  ✓ 3 个场景 LayoutPlan 顶层字段完全一致（{next(iter(top_fields))}）")
    else:
        print(f"  ✗ 3 个场景 LayoutPlan 顶层字段不一致：{top_fields}")
        return 1

    # 同一 layout 多次 plan 稳定
    print("Plan 稳定性检查：")
    for layout_id, _, fixture_fn in SCENARIOS:
        library = fixture_fn()
        layout = get_layout(layout_id)
        h1 = _hash_plan(layout.plan(library, ctx))
        h2 = _hash_plan(layout.plan(library, ctx))
        ok = h1 == h2 == plan_hashes[layout_id]
        print(f"  {'✓' if ok else '✗'} {layout_id}: hash1={h1} hash2={h2} (期望 {plan_hashes[layout_id]})")
        if not ok:
            return 1

    # 同一 layout 多次 render 稳定
    print("Render 稳定性检查：")
    for layout_id, _, fixture_fn in SCENARIOS:
        import io
        library = fixture_fn()
        layout = get_layout(layout_id)
        theme = load_themes(str(ROOT / "themes"))[THEME_NAME]
        img1 = render_page(theme, layout, library, spec, 1, str(FONT_PATH))
        img2 = render_page(theme, layout, library, spec, 1, str(FONT_PATH))
        buf1, buf2 = io.BytesIO(), io.BytesIO()
        img1.save(buf1, format="PNG")
        img2.save(buf2, format="PNG")
        h1 = _hash_png(buf1.getvalue())
        h2 = _hash_png(buf2.getvalue())
        ok = h1 == h2 == render_hashes[layout_id]
        print(f"  {'✓' if ok else '✗'} {layout_id}: hash1={h1} hash2={h2} (期望 {render_hashes[layout_id]})")
        if not ok:
            return 1

    print()
    print("=" * 78)
    print("✓ R4 Runtime v2 退出条件 #1 验证通过")
    print(f"  3 个场景：{', '.join(layout_id for layout_id, _, _ in SCENARIOS)}")
    print(f"  全部走完 analyze → plan → render 链路")
    print(f"  全部产出同结构 LayoutPlan（frozen dataclass，hashable）")
    print(f"  全部 plan + render 多次结果稳定")
    print(f"  产物：{OUT_DIR.relative_to(ROOT)}/")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
