"""R2.5: 生成 live-set 布局的代表性金标准 PNG。

策略（与 magazine-flow 一致，没有独立预言机）：
- 输出到 tests/golden_live_set/（独立目录，不污染 grid-wrap 16 张 + magazine 6 张）
- 显式 --confirm-baseline 才覆写；首次生成写入 reproducibility manifest
- 仅做内容指纹对比（PNG bytes sha256），不做 pixel diff
  → 承认结构稳态，不绑定像素
- 任何大幅改动需要重跑 + 人工核对

用法：
    PYTHONPATH=. .venv/bin/python tools/generate_live_set_golden.py --confirm-baseline

5 个代表性用例（覆盖空场 / 单曲 / 多场 / 大场次 / 混合状态）：
  01-empty.png      空场直播（仅 session 标题）
  02-single.png     单首 queued
  03-multi.png      5 首歌（1 current + 2 queued + 2 sung）
  04-large.png      12 首歌（1 current + 5 queued + 6 sung）
  05-mixed.png      含 postponed / cancelled / skipped 多种结果
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
from core.layouts.live_set import LiveSessionSnapshot
from core.spec import get_canvas_spec
from core.themes.loader import load_themes
from core.data.songs import SongLibrary


GOLDEN_DIR = ROOT / "tests" / "golden_live_set"
MANIFEST = GOLDEN_DIR / "manifest.json"
FONT_PATH = ROOT / "fonts" / "MaokenAssortedSans.ttf"


# ── 5 个代表性用例 ──

def _case_empty() -> LiveSessionSnapshot:
    return LiveSessionSnapshot(
        session_id="live_empty",
        session_title="周五晚直播",
        session_state="closed",
        started_at="2026-07-31T20:00:00+08:00",
        closed_at="2026-07-31T22:00:00+08:00",
        rule_version="rule_default01",
    )


def _case_single() -> LiveSessionSnapshot:
    return LiveSessionSnapshot(
        session_id="live_single",
        session_title="周三晚点歌",
        session_state="active",
        started_at="2026-07-31T20:00:00+08:00",
        rule_version="rule_default01",
        requests=(
            {"id": "r1", "song_id": "s1", "song_title": "恋爱ing",
             "requester_name": "小明", "requested_at": "2026-07-31T20:05:00+08:00",
             "state": "queued", "is_bumped": False},
        ),
    )


def _case_multi() -> LiveSessionSnapshot:
    return LiveSessionSnapshot(
        session_id="live_multi",
        session_title="周末歌友会",
        session_state="active",
        started_at="2026-07-31T20:00:00+08:00",
        rule_version="rule_default01",
        requests=(
            {"id": "r1", "song_id": "s1", "song_title": "恋爱ing",
             "requester_name": "小明", "requested_at": "2026-07-31T20:05:00+08:00",
             "state": "current", "is_bumped": False},
            {"id": "r2", "song_id": "s2", "song_title": "小幸运",
             "requester_name": "小红", "requested_at": "2026-07-31T20:10:00+08:00",
             "state": "queued", "is_bumped": False},
            {"id": "r3", "song_id": "s3", "song_title": "告白气球",
             "requester_name": "张三", "requested_at": "2026-07-31T20:15:00+08:00",
             "state": "queued", "is_bumped": True},
        ),
        performances=(
            {"request_id": "r4", "song_id": "s4", "song_title": "稻香",
             "requester_name": "李四", "result": "sung",
             "performed_at": "2026-07-31T20:30:00+08:00"},
            {"request_id": "r5", "song_id": "s5", "song_title": "晴天",
             "requester_name": "王五", "result": "sung",
             "performed_at": "2026-07-31T20:50:00+08:00"},
        ),
    )


def _case_large() -> LiveSessionSnapshot:
    """大场次：12 首歌，1 current + 5 queued + 6 sung + 1 跳过的。"""
    queued_songs = [
        ("如果你也听说", "粉A"),
        ("七里香", "粉B"),
        ("夜曲", "粉C"),
        ("说好的幸福呢", "粉D"),
        ("搁浅", "粉E"),
    ]
    sung_songs = [
        ("枫", "粉1", "2026-07-31T20:05:00+08:00"),
        ("夜的第七章", "粉2", "2026-07-31T20:18:00+08:00"),
        ("退后", "粉3", "2026-07-31T20:32:00+08:00"),
        ("听妈妈的话", "粉4", "2026-07-31T20:48:00+08:00"),
        ("蜗牛", "粉5", "2026-07-31T21:05:00+08:00"),
        ("轨迹", "粉6", "2026-07-31T21:22:00+08:00"),
    ]
    return LiveSessionSnapshot(
        session_id="live_large",
        session_title="大型歌友会·夏季专场",
        session_state="active",
        started_at="2026-07-31T19:30:00+08:00",
        rule_version="rule_summer01",
        requests=(
            {"id": "r0", "song_id": "cur", "song_title": "一路向北",
             "requester_name": "主粉", "requested_at": "2026-07-31T21:35:00+08:00",
             "state": "current", "is_bumped": False},
        ) + tuple(
            {"id": f"q{i}", "song_id": f"q{i}", "song_title": title,
             "requester_name": req, "requested_at": f"2026-07-31T19:4{i}:00+08:00",
             "state": "queued", "is_bumped": False}
            for i, (title, req) in enumerate(queued_songs, start=0)
        ),
        performances=tuple(
            {"request_id": f"s{i}", "song_id": f"s{i}", "song_title": title,
             "requester_name": req, "result": "sung", "performed_at": ts}
            for i, (title, req, ts) in enumerate(sung_songs)
        ) + (
            {"request_id": "skip1", "song_id": "sk1", "song_title": "太难",
             "requester_name": "粉X", "result": "skipped",
             "performed_at": "2026-07-31T20:55:00+08:00",
             "reason": "key 太高"},
        ),
    )


def _case_mixed() -> LiveSessionSnapshot:
    """混合状态：含 postponed / cancelled / duplicate_merged。"""
    return LiveSessionSnapshot(
        session_id="live_mixed",
        session_title="会员特别场",
        session_state="closed",
        started_at="2026-07-31T19:00:00+08:00",
        closed_at="2026-07-31T21:30:00+08:00",
        rule_version="rule_vip01",
        requests=(
            {"id": "r1", "song_id": "s1", "song_title": "海阔天空",
             "requester_name": "粉A", "requested_at": "2026-07-31T19:05:00+08:00",
             "state": "queued", "is_bumped": False},
        ),
        performances=(
            {"request_id": "p1", "song_id": "sp1", "song_title": "光辉岁月",
             "requester_name": "粉1", "result": "sung",
             "performed_at": "2026-07-31T19:15:00+08:00"},
            {"request_id": "p2", "song_id": "sp2", "song_title": "真的爱你",
             "requester_name": "粉2", "result": "sung",
             "performed_at": "2026-07-31T19:30:00+08:00"},
            {"request_id": "p3", "song_id": "sp3", "song_title": "大地",
             "requester_name": "粉3", "result": "cancelled",
             "performed_at": "2026-07-31T19:50:00+08:00",
             "reason": "主播嗓子不适"},
            {"request_id": "p4", "song_id": "sp4", "song_title": "喜欢你",
             "requester_name": "粉4", "result": "postponed",
             "performed_at": "2026-07-31T20:10:00+08:00",
             "reason": "等下次"},
            {"request_id": "p5", "song_id": "sp5", "song_title": "海阔天空",
             "requester_name": "粉5", "result": "duplicate_merged",
             "performed_at": "2026-07-31T20:25:00+08:00",
             "reason": "与 p5 同歌"},
        ),
    )


CASES = [
    ("01-empty", _case_empty),
    ("02-single", _case_single),
    ("03-multi", _case_multi),
    ("04-large", _case_large),
    ("05-mixed", _case_mixed),
]


def _generate(theme_name: str, canvas_id: str, snapshot: LiveSessionSnapshot,
              out_dir: Path, font_path: str) -> list[Path]:
    """渲染单张金标准 PNG。"""
    spec = get_canvas_spec(canvas_id, avoid=True)
    themes = load_themes(str(ROOT / "themes"))
    if theme_name not in themes:
        raise KeyError(f"未知主题：{theme_name}")
    theme = themes[theme_name]
    plugin = get_layout("live-set")
    # library 是 LiveSessionSnapshot，直接渲染 page 1
    img = render_page(theme, plugin, snapshot, spec, 1, font_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    # 清理旧 PNG
    for old in out_dir.glob(f"{theme_name}-{canvas_id}-*.png"):
        old.unlink()
    written = []
    for case_name, _ in CASES:
        # 重新生成对应 case 的 snapshot
        snap = next(s() for n, s in CASES if n == case_name)
        img = render_page(theme, plugin, snap, spec, 1, font_path)
        path = out_dir / f"{theme_name}-{canvas_id}-{case_name}.png"
        img.save(str(path), "PNG")
        written.append(path)
    return written


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-baseline", action="store_true",
                        help="确认要覆写 live-set 代表性金标准")
    args = parser.parse_args()
    if not args.confirm_baseline:
        print(__doc__)
        return
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    theme_name = "海洋柔光"
    canvas_id = "抖音全屏 9:20"
    all_paths: list[Path] = []
    for case_name, case_fn in CASES:
        snap = case_fn()
        spec = get_canvas_spec(canvas_id, avoid=True)
        themes = load_themes(str(ROOT / "themes"))
        theme = themes[theme_name]
        plugin = get_layout("live-set")
        img = render_page(theme, plugin, snap, spec, 1, str(FONT_PATH))
        out = GOLDEN_DIR / f"{theme_name}-{canvas_id}-{case_name}.png"
        img.save(str(out), "PNG")
        all_paths.append(out)
        print(f"  ✓ {out.name} ({out.stat().st_size // 1024} KB)")
    # manifest
    entries = []
    for p in all_paths:
        entries.append({
            "path": str(p.relative_to(ROOT)),
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "size": p.stat().st_size,
        })
    manifest = {
        "schema_version": 1,
        "engine": "live-set-r25",
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
