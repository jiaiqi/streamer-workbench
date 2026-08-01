"""R3.5: 生成 learning-report 布局的代表性金标准 PNG。

策略（与 live-set / magazine-flow 一致）：
- 输出到 tests/golden_learning_report/（独立目录）
- 显式 --confirm-baseline 才覆写
- 仅做内容指纹对比（PNG bytes sha256）

5 个代表性用例（覆盖冷启动 / 月度 / 活跃 / 按调性 / 难曲）：
  01-empty.png     零数据冷启动
  02-month.png     月度 30 天活跃
  03-active.png    百日活跃 + 难度分布
  04-keyed.png     按调性汇总（C/G/Am 等）
  05-difficult.png 含高难度曲

用法：
    PYTHONPATH=. .venv/bin/python tools/generate_learning_report_golden.py --confirm-baseline
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image
from core.engine import render_page
from core.layouts import get_layout
from core.layouts.learning_report import LearningReportSnapshot
from core.spec import get_canvas_spec
from core.themes.loader import load_themes


GOLDEN_DIR = ROOT / "tests" / "golden_learning_report"
MANIFEST = GOLDEN_DIR / "manifest.json"
FONT_PATH = ROOT / "fonts" / "MaokenAssortedSans.ttf"


# ── 5 个代表性用例 ──

def _case_empty() -> LearningReportSnapshot:
    return LearningReportSnapshot(
        report_title="学歌报告",
        period_label="2026 年 7 月",
        period_start="2026-07-01T00:00:00+08:00",
        period_end="2026-07-31T23:59:59+08:00",
    )


def _case_month() -> LearningReportSnapshot:
    """月度活跃：30 天 8 次练习 + 学会 3 首。"""
    return LearningReportSnapshot(
        report_title="七月学歌报告",
        period_label="2026 年 7 月",
        period_start="2026-07-01T00:00:00+08:00",
        period_end="2026-07-31T23:59:59+08:00",
        total_practice_minutes=235,
        total_practice_sessions=8,
        current_streak_days=3,
        longest_streak_days=5,
        songs_learned=(
            {"id": "s1", "title": "如果声音不记得", "artist": "吴青峰",
             "learned_at": "2026-07-08T20:30:00+08:00"},
            {"id": "s2", "title": "起风了", "artist": "买辣椒也用券",
             "learned_at": "2026-07-15T21:00:00+08:00"},
            {"id": "s3", "title": "夜空中最亮的星", "artist": "逃跑计划",
             "learned_at": "2026-07-28T19:30:00+08:00"},
        ),
        recent_practice=(
            {"title": "夜空中最亮的星", "minutes": 30, "self_rating": 4,
             "occurred_at": "2026-07-31T20:00:00+08:00", "note": "副歌稳了"},
            {"title": "起风了", "minutes": 20, "self_rating": 3,
             "occurred_at": "2026-07-30T20:00:00+08:00"},
            {"title": "夜空中最亮的星", "minutes": 25, "self_rating": 3,
             "occurred_at": "2026-07-29T21:00:00+08:00"},
        ),
        top_artists=(
            {"name": "吴青峰", "count": 5},
            {"name": "逃跑计划", "count": 3},
            {"name": "买辣椒也用券", "count": 2},
        ),
    )


def _case_active() -> LearningReportSnapshot:
    """百日活跃：12 首歌学会 + 大量练习。"""
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
        top_artists=(
            {"name": "歌手 00", "count": 12},
            {"name": "歌手 01", "count": 10},
            {"name": "歌手 02", "count": 8},
            {"name": "歌手 03", "count": 6},
            {"name": "歌手 04", "count": 4},
        ),
        difficulty_buckets=(
            {"label": "简单", "count": 18},
            {"label": "中等", "count": 32},
            {"label": "困难", "count": 8},
            {"label": "未标", "count": 0},
        ),
    )


def _case_keyed() -> LearningReportSnapshot:
    """按调性汇总：典型 pop 调性偏好。"""
    return LearningReportSnapshot(
        report_title="我的调性画像",
        period_label="2026 年 7 月",
        period_start="2026-07-01T00:00:00+08:00",
        period_end="2026-07-31T23:59:59+08:00",
        total_practice_minutes=180,
        total_practice_sessions=12,
        current_streak_days=2,
        longest_streak_days=4,
        songs_learned=(
            {"id": "s1", "title": "海阔天空", "artist": "Beyond", "learned_at": "2026-07-10"},
            {"id": "s2", "title": "突然的自我", "artist": "伍佰", "learned_at": "2026-07-22"},
        ),
        top_artists=(
            {"name": "Beyond", "count": 4},
            {"name": "伍佰", "count": 3},
            {"name": "陈奕迅", "count": 2},
        ),
        key_buckets=(
            {"label": "C", "count": 8},
            {"label": "G", "count": 6},
            {"label": "Am", "count": 5},
            {"label": "Em", "count": 4},
            {"label": "D", "count": 3},
            {"label": "F", "count": 2},
        ),
    )


def _case_difficult() -> LearningReportSnapshot:
    """高难度曲专攻。"""
    return LearningReportSnapshot(
        report_title="高难度专攻报告",
        period_label="2026 年 6 月 - 7 月",
        period_start="2026-06-01T00:00:00+08:00",
        period_end="2026-07-31T23:59:59+08:00",
        total_practice_minutes=860,
        total_practice_sessions=22,
        current_streak_days=0,
        longest_streak_days=9,
        songs_learned=(
            {"id": "s1", "title": "不为谁而作的歌", "artist": "林俊杰",
             "learned_at": "2026-07-12T20:00:00+08:00"},
            {"id": "s2", "title": "她说", "artist": "林俊杰",
             "learned_at": "2026-07-25T20:00:00+08:00"},
        ),
        recent_practice=(
            {"title": "她说", "minutes": 45, "self_rating": 3,
             "occurred_at": "2026-07-31T19:00:00+08:00", "note": "转调难"},
            {"title": "她说", "minutes": 50, "self_rating": 2,
             "occurred_at": "2026-07-30T19:00:00+08:00"},
            {"title": "不为谁而作的歌", "minutes": 60, "self_rating": 4,
             "occurred_at": "2026-07-25T20:00:00+08:00"},
        ),
        top_artists=(
            {"name": "林俊杰", "count": 6},
            {"name": "陈奕迅", "count": 3},
        ),
        difficulty_buckets=(
            {"label": "简单", "count": 1},
            {"label": "中等", "count": 4},
            {"label": "困难", "count": 9},
            {"label": "未标", "count": 0},
        ),
    )


CASES = [
    ("01-empty", _case_empty),
    ("02-month", _case_month),
    ("03-active", _case_active),
    ("04-keyed", _case_keyed),
    ("05-difficult", _case_difficult),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-baseline", action="store_true",
                        help="确认要覆写 learning-report 代表性金标准")
    args = parser.parse_args()
    if not args.confirm_baseline:
        print(__doc__)
        return
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    theme_name = "海洋柔光"
    canvas_id = "抖音全屏 9:20"
    spec = get_canvas_spec(canvas_id, avoid=True)
    themes = load_themes(str(ROOT / "themes"))
    theme = themes[theme_name]
    plugin = get_layout("learning-report")
    all_paths: list[Path] = []
    for case_name, case_fn in CASES:
        snap = case_fn()
        img = render_page(theme, plugin, snap, spec, 1, str(FONT_PATH))
        out = GOLDEN_DIR / f"{theme_name}-{canvas_id}-{case_name}.png"
        img.save(str(out), "PNG")
        all_paths.append(out)
        print(f"  ✓ {out.name} ({out.stat().st_size // 1024} KB)")
    entries = []
    for p in all_paths:
        entries.append({
            "path": str(p.relative_to(ROOT)),
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "size": p.stat().st_size,
        })
    manifest = {
        "schema_version": 1,
        "engine": "learning-report-r35",
        "theme": theme_name,
        "canvas": canvas_id,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "entries": entries,
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"\n✓ 写入 manifest：{MANIFEST.relative_to(ROOT)}")
    print(f"  共 {len(entries)} 张金标准 PNG")


if __name__ == "__main__":
    main()
