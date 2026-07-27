"""重建金标准参照图（危险操作：会重设回归基准！）

⚠️ 警告：tests/golden/ 是版本化的回归基准。重建意味着「宣布当前引擎
输出为新的正确标准」，之前能拦截的回归将一并被合法化。只有在以下情况
才应运行本脚本：
  1. 歌曲数据集发生预期内变更（加歌/删歌/改分组）；
  2. 排版算法发生预期内变更（人已肉眼确认新输出正确）；
  3. Pillow/字体升级导致的已知渲染差异，已人工核对。

策略（2026-07-25 重建）：调用独立预言机——旧脚本
  歌单-排版一/build_playlist.py（178 首全 active 数据集）
生成 16 张参照图（7 主题×2 页全屏绕排 + 海洋柔光标准版 2 张），
扁平命名复制到 tests/golden/。

禁止改回「引擎自举」：参照图与被测对象同源会让 diff=0 变成恒等式，
金标准门将永远绿灯、形同虚设（2026-07-25 教训）。

前提：
  - 预言机随仓库检出（.archive/design-docs/歌单-排版一，2026-07-27 合并入库）
  - 运行环境需有 numpy（旧脚本依赖）；Pillow 必须 == 12.2.0
    （与引擎环境一致，否则字体光栅化差异会导致永久 diff）

用法（在 歌单海报生成器 目录下）：
    PYTHONPATH=. python tools/regenerate_golden.py --confirm-rebaseline
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORACLE_DIR = os.path.join(ROOT, ".archive", "design-docs", "歌单-排版一")
ORACLE_SCRIPT = os.path.join(ORACLE_DIR, "build_playlist.py")
GOLDEN_DST = os.path.join(ROOT, "tests", "golden")

# 主题 → 旧脚本输出文件名前缀（与 theme.json 的 output_prefix 一致）
PREFIX = {
    "海洋柔光": "梓涵吃不饱-AI海洋歌单-柔光UI版",
    "梦幻海洋": "梓涵吃不饱-AI歌单-梦幻海洋版",
    "奶油花园": "梓涵吃不饱-AI歌单-奶油花园版",
    "青提气泡": "梓涵吃不饱-AI歌单-青提气泡版",
    "卡通音符": "梓涵吃不饱-AI歌单-卡通音符版",
    "奶油玻璃": "梓涵吃不饱-AI歌单-奶油玻璃版",
    "轻复古唱片": "梓涵吃不饱-AI歌单-轻复古唱片版",
}


def main():
    if "--confirm-rebaseline" not in sys.argv:
        print(__doc__)
        print("❌ 未提供 --confirm-rebaseline，已中止。请确认你理解重建基准的含义。")
        sys.exit(1)
    if not os.path.isfile(ORACLE_SCRIPT):
        print(f"❌ 找不到独立预言机：{ORACLE_SCRIPT}")
        print("   请将设计仓库与本仓库并列放置，或在上级目录建软链：")
        print("   （已并入本仓库 .archive/design-docs/，无需软链）")
        sys.exit(1)

    os.makedirs(GOLDEN_DST, exist_ok=True)

    # 1. 全屏绕排 14 张（--fullscreen --avoid-rail）
    for name in PREFIX:
        subprocess.run(
            [sys.executable, ORACLE_SCRIPT, "--theme", name,
             "--fullscreen", "--avoid-rail"],
            cwd=ORACLE_DIR, check=True)
    # 2. 海洋柔光标准版 2 张（无 fullscreen/avoid）
    subprocess.run(
        [sys.executable, ORACLE_SCRIPT, "--theme", "海洋柔光"],
        cwd=ORACLE_DIR, check=True)

    # 3. 复制为扁平命名 + 清理旧脚本在主题目录留下的无 tag 产物
    count = 0
    for name, prefix in PREFIX.items():
        for page in (1, 2):
            src = os.path.join(ORACLE_DIR, name, f"{prefix}-{page}.png")
            shutil.copy2(src, os.path.join(GOLDEN_DST, f"{name}-全屏p{page}.png"))
            count += 1
    for page in (1, 2):
        src = os.path.join(ORACLE_DIR, "海洋柔光",
                           f"{PREFIX['海洋柔光']}-{page}.png")
        shutil.copy2(src, os.path.join(GOLDEN_DST, f"海洋柔光-标准p{page}.png"))
        count += 1
    for name, prefix in PREFIX.items():
        for page in (1, 2):
            leftover = os.path.join(ORACLE_DIR, name, f"{prefix}-{page}.png")
            if os.path.isfile(leftover):
                os.remove(leftover)

    print(f"\n重建完成: {count}/16 张金标准参照图（独立预言机生成）→ {GOLDEN_DST}")
    print("下一步：跑 PYTHONPATH=. python tests/test_golden.py 确认 16/16 diff=0，")
    print("然后将 tests/golden/ 的变更随 git 提交（基准已重设，需在提交信息中说明原因）。")


if __name__ == "__main__":
    main()
