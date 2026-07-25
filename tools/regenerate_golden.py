"""从设计仓库的旧脚本成品重新生成金标准参照图，放入 tests/golden/。

用法（在 歌单海报生成器 目录下）：
    PYTHONPATH=. python tools/regenerate_golden.py

金标准参照图来源：../歌单-排版一/<主题>/<prefix>-糖圆体全屏绕排-{page}.png
（需存在，由设计仓库的 build_playlist.py 生成，或通过软链指向）

产物：tests/golden/<主题>-全屏p{1,2}.png（扁平命名，便于 CI 引用）
"""
import os
import sys
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN_SRC = os.path.join(ROOT, "..", "歌单-排版一")
GOLDEN_DST = os.path.join(ROOT, "tests", "golden")
os.makedirs(GOLDEN_DST, exist_ok=True)

# 主题 → 文件名前缀（与旧脚本 THEMES 字典一致）
THEME_PREFIXES = {
    "海洋柔光": "梓涵吃不饱-AI海洋歌单-柔光UI版",
    "梦幻海洋": "梓涵吃不饱-AI歌单-梦幻海洋版",
    "奶油花园": "梓涵吃不饱-AI歌单-奶油花园版",
    "青提气泡": "梓涵吃不饱-AI歌单-青提气泡版",
    "卡通音符": "梓涵吃不饱-AI歌单-卡通音符版",
    "奶油玻璃": "梓涵吃不饱-AI歌单-奶油玻璃版",
    "轻复古唱片": "梓涵吃不饱-AI歌单-轻复古唱片版",
}

if not os.path.isdir(GOLDEN_SRC):
    print(f"❌ 参照图源目录不存在: {GOLDEN_SRC}")
    print("   请确认已在项目上级目录创建软链：")
    print(f"   ln -s playlist-poster-design/歌单-排版一 {GOLDEN_SRC}")
    sys.exit(1)

copied = 0
for name, prefix in THEME_PREFIXES.items():
    for page in (1, 2):
        src = os.path.join(GOLDEN_SRC, name, f"{prefix}-糖圆体全屏绕排-{page}.png")
        dst = os.path.join(GOLDEN_DST, f"{name}-全屏p{page}.png")
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            copied += 1
            print(f"  ✅ {name} p{page}")
        else:
            print(f"  ⚠️ {name} p{page} 缺失 (src={src})")

print(f"\n复制完成: {copied}/14 张金标准参照图 → {GOLDEN_DST}")
