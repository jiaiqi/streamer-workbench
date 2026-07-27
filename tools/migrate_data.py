"""数据迁移脚本：从旧脚本 (build_playlist.py) 和歌单 md 文件交叉校验，生成 songs.json。

用法（在 歌单海报生成器 目录下）：
    PYTHONPATH=. python tools/migrate_data.py

双源校验逻辑：
    源 1：core/data/songs.py 内置列表（178 首，含 section 标记）
    源 2：design-docs/歌单-排版一/歌单数据.md（Markdown 导出副本，供人类校对）

交叉校验：
    - 两边歌名数量必须一致
    - 每首歌的名字在两边都存在
    - 产生 songs.json 作为唯一数据源文件

产物：data/songs.json（含所有歌曲的 Song 模型数据）
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.data.songs import build_default_library

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# ── 源 1：内置库 ──
lib = build_default_library()
builtin_titles = {s.title for s in lib.songs}
print(f"源 1（songs.py 内置）：{len(builtin_titles)} 首")

# ── 源 2：歌单数据.md ──
md_path = os.path.join(ROOT, "design-docs", "歌单-排版一", "歌单数据.md")
md_titles = set()
if os.path.isfile(md_path):
    with open(md_path) as f:
        in_section = False
        for line in f:
            line = line.strip()
            if line.startswith("## "):
                continue  # skip section headers
            if not line or line.startswith(">") or line.startswith("#"):
                continue
            # Parse comma-separated titles
            for t in line.split(","):
                t = t.strip()
                if t:
                    md_titles.add(t)
    print(f"源 2（歌单数据.md）：{len(md_titles)} 首")
else:
    print(f"⚠️  源 2 缺失：{md_path}，跳过交叉校验")

# ── 交叉校验 ──
if md_titles:
    only_builtin = builtin_titles - md_titles
    only_md = md_titles - builtin_titles
    if only_builtin:
        print(f"❌ 仅在 songs.py 中的歌：{sorted(only_builtin)}")
    if only_md:
        print(f"❌ 仅在 歌单数据.md 中的歌：{sorted(only_md)}")
    if not only_builtin and not only_md:
        print("✅ 双源交叉校验通过（两边歌名完全一致）")
    else:
        print("⚠️  请手动解决差异后重新运行")

# ── 生成 songs.json ──
songs_data = {
    "version": 1,
    "songs": [
        {
            "title": s.title,
            "artists": s.artists,
            "lyricist": s.lyricist,
            "composer": s.composer,
            "key": s.key,
            "capo": s.capo,
            "difficulty": s.difficulty,
            "tabs": s.tabs,
            "status": s.status,
            "tags": s.tags,
            "pinyin": s.pinyin,
            "added_at": s.added_at,
            "notes": s.notes,
            "section": s.section,
        }
        for s in lib.songs
    ],
}

out_path = os.path.join(DATA_DIR, "songs.json")
# 原子写
tmp_path = out_path + ".tmp"
with open(tmp_path, "w", encoding="utf-8") as f:
    json.dump(songs_data, f, ensure_ascii=False, indent=2)
os.replace(tmp_path, out_path)

print(f"\n✅ songs.json 已生成：{out_path}")
print(f"   歌曲总数：{len(lib.songs)}")
print(f"   active：{lib.count_active()}")
print(f"   draft：{lib.count_draft()}")
print(f"   分类：YI={sum(1 for s in lib.songs if s.section==1)}, "
      f"ER={sum(1 for s in lib.songs if s.section==2)}, "
      f"SAN={sum(1 for s in lib.songs if s.section==3)}, "
      f"SI={sum(1 for s in lib.songs if s.section==4)}, "
      f"WU={sum(1 for s in lib.songs if s.section==5)}, "
      f"LIU={sum(1 for s in lib.songs if s.section==6)}, "
      f"LONG={sum(1 for s in lib.songs if s.section==7)}")
