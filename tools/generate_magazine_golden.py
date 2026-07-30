"""R1b: 生成 magazine-flow 布局的代表性金标准 PNG。

策略（与 grid-wrap 不同——没有独立预言机）：
- 输出到 tests/golden_magazine/（独立目录，不污染旧 16 张）
- 显式 --confirm-baseline 才覆写；首次生成写入 reproducibility manifest
- 仅做内容指纹对比（PNG bytes sha256），不做 pixel diff
  → 这是「不与引擎自举」的妥协：金标准仅承认结构稳态，不绑定像素
- 任何大幅改动需要重跑 + 人工核对

用法：
    PYTHONPATH=. .venv/bin/python tools/generate_magazine_golden.py --confirm-baseline

主题选择：海洋柔光（标准） + 梦幻海洋（对照）
画布：9:20 + 9:16
歌曲：data/songs.json 的 active 子集
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

from core.engine import render_pages
from core.layouts import get_layout
from core.spec import get_canvas_spec
from core.themes.loader import load_themes
from core.data.songs import SongLibrary


GOLDEN_DIR = ROOT / "tests" / "golden_magazine"
MANIFEST = GOLDEN_DIR / "manifest.json"
FONT_PATH = ROOT / "fonts" / "MaokenAssortedSans.ttf"


def _load_active_lib(songs_json: Path) -> SongLibrary:
    """读 songs.json v5 → 返回 active 子集 library。"""
    lib = SongLibrary()
    raw = json.loads(songs_json.read_text(encoding="utf-8"))
    for item in raw.get("songs", []):
        if item.get("status") == "active":
            from core.data.songs import Song
            lib.songs.append(Song(
                **{k: v for k, v in item.items()
                   if k in {f for f in Song.__dataclass_fields__}}
            ))
    return lib


def _generate_pair(theme_name: str, canvas_id: str, library, theme, font_path: str,
                   out_dir: Path):
    """为 (theme, canvas) 生成对应 PNG 到 out_dir/<theme>-<canvas>-p<N>.png。"""
    spec = get_canvas_spec(canvas_id, avoid=True)
    plugin = get_layout("magazine-flow")
    images = render_pages(theme, plugin, library, spec, font_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    # 清理旧 PNG（不同尺寸 / 旧 canvas_id 命名的；新生成覆盖）
    for old in out_dir.glob(f"{theme_name}-{canvas_id}-p*.png"):
        old.unlink()
    written = []
    for i, img in enumerate(images, start=1):
        path = out_dir / f"{theme_name}-{canvas_id}-p{i}.png"
        img.save(str(path), "PNG")
        written.append(path)
    return written


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-baseline",
                        action="store_true",
                        help="确认要覆写 magazine-flow 代表性金标准")
    args = parser.parse_args()
    if not args.confirm_baseline:
        print(__doc__)
        return 0

    print("[magazine-golden] 加载主题与曲库...")
    themes = load_themes(str(ROOT / "themes"))
    songs_json = ROOT / "data" / "songs.json"
    if not songs_json.exists():
        print(f"[magazine-golden] 找不到 {songs_json}")
        return 1
    library = _load_active_lib(songs_json)
    print(f"[magazine-golden] active 歌曲数: {len(library.mastered())}")

    manifest_entries = []
    cases = [
        ("海洋柔光", "抖音全屏 9:20"),
        ("海洋柔光", "标准 9:16"),
        ("梦幻海洋", "抖音全屏 9:20"),
    ]
    for theme_name, canvas_id in cases:
        print(f"[magazine-golden] 渲染 {theme_name} {canvas_id}...")
        paths = _generate_pair(theme_name, canvas_id, library,
                               themes[theme_name], FONT_PATH,
                               GOLDEN_DIR)
        for p in paths:
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            manifest_entries.append({
                "path": str(p.relative_to(ROOT)),
                "theme": theme_name,
                "canvas": canvas_id,
                "page": int(p.stem.split("-p")[-1]),
                "sha256": digest,
                "size_bytes": p.stat().st_size,
            })

    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "engine": "streamer-workbench/render_pages + magazine-flow v1",
        "note": "新布局金标准（magazine-flow）；content fingerprint 对比",
        "entries": manifest_entries,
    }
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    print(f"[magazine-golden] 生成 {len(manifest_entries)} 个 PNG + manifest")
    print(f"[magazine-golden] 完成 (旧 16 张在 tests/golden/ 完全不动)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
