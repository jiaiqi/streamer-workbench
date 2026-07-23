"""一次性迁移脚本：把 歌单-排版一 的 7 套主题背景图 + 设计理念 复制到新项目 themes/，
并基于旧 build_playlist.py 的 THEMES 字典生成 theme.json。

原则：复制不移动；新项目不改动 歌单-排版一 任何文件。
运行：python tools/migrate_themes.py
"""
import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "..", "歌单-排版一")
DST_ROOT = os.path.join(ROOT, "themes")


def _o(text, label, pill, line, mist):
    return dict(text=text, label=label, pill=pill, line=line, mist=mist)


_OCEAN = _o((43, 84, 78), (36, 110, 96), (188, 224, 210, 130), (232, 146, 118), (255, 255, 255, 66))
_GRAPE = _o((46, 82, 69), (30, 104, 76), (198, 233, 210, 128), (232, 146, 118), (255, 255, 255, 66))

THEMES = {
    "海洋柔光": dict(prefix="梓涵吃不饱-AI海洋歌单-柔光UI版",
                    bgs=("background-1.png", "background-2.png"), watermark=False,
                    style={1: _OCEAN, 2: _OCEAN}),
    "梦幻海洋": dict(prefix="梓涵吃不饱-AI歌单-梦幻海洋版",
                    bgs=("bg1.png", "bg2.png"), watermark=True,
                    style={1: _OCEAN, 2: _OCEAN}),
    "奶油花园": dict(prefix="梓涵吃不饱-AI歌单-奶油花园版",
                    bgs=("bg1.png", "bg2.png"), watermark=True,
                    style={1: _o((107, 74, 63), (138, 74, 56), (247, 199, 178, 118), (232, 146, 118), (255, 252, 248, 68)),
                           2: _o((95, 70, 88), (124, 74, 99), (240, 208, 224, 118), (201, 138, 169), (255, 250, 253, 68))}),
    "青提气泡": dict(prefix="梓涵吃不饱-AI歌单-青提气泡版",
                    bgs=("bg1.png", "bg2.png"), watermark=True,
                    style={1: _GRAPE, 2: _GRAPE}),
    "卡通音符": dict(prefix="梓涵吃不饱-AI歌单-卡通音符版",
                    bgs=("bg1.png", "bg2.png"), watermark=True,
                    style={1: _o((46, 82, 69), (30, 104, 76), (198, 233, 210, 128), (232, 146, 118), (255, 255, 255, 60)),
                           2: _o((107, 74, 63), (138, 74, 56), (247, 199, 178, 128), (232, 146, 118), (255, 252, 248, 60))}),
    "奶油玻璃": dict(prefix="梓涵吃不饱-AI歌单-奶油玻璃版",
                    bgs=("background-1.png", "background-2.png"), watermark=False,
                    style={1: _o((70, 80, 100), (64, 106, 148), (228, 238, 246, 120), (230, 158, 148), (255, 255, 255, 72)),
                           2: _o((70, 80, 100), (64, 106, 148), (228, 238, 246, 120), (230, 158, 148), (255, 255, 255, 72))}),
    "轻复古唱片": dict(prefix="梓涵吃不饱-AI歌单-轻复古唱片版",
                      bgs=("background-1.png", "background-2.png"), watermark=False,
                      style={1: _o((96, 70, 58), (148, 74, 50), (250, 222, 190, 130), (196, 96, 66), (255, 252, 246, 66)),
                             2: _o((96, 70, 58), (148, 74, 50), (250, 222, 190, 130), (196, 96, 66), (255, 252, 246, 66))}),
}


def main():
    for name, cfg in THEMES.items():
        dst = os.path.join(DST_ROOT, name)
        os.makedirs(dst, exist_ok=True)
        for bg in cfg["bgs"]:
            src_bg = os.path.join(SRC, name, bg)
            if os.path.isfile(src_bg):
                shutil.copy(src_bg, os.path.join(dst, bg))
            else:
                print(f"[warn] {name} 缺背景 {bg}")
        # 设计理念.md
        sp = os.path.join(SRC, name, "设计理念.md")
        if os.path.isfile(sp):
            shutil.copy(sp, os.path.join(dst, "设计理念.md"))
        theme = {
            "name": name,
            "output_prefix": cfg["prefix"],
            "backgrounds": {"1": cfg["bgs"][0], "2": cfg["bgs"][1]},
            "watermark_fix": cfg["watermark"],
            "styles": {"1": cfg["style"][1], "2": cfg["style"][2]},
            "font": None,
            "notes": "迁移自 歌单-排版一；背景为用户供图/AI 生成",
        }
        with open(os.path.join(dst, "theme.json"), "w", encoding="utf-8") as f:
            json.dump(theme, f, ensure_ascii=False, indent=2)
        print(f"migrated {name}: bgs={cfg['bgs']} watermark={cfg['watermark']}")
    print("DONE")


if __name__ == "__main__":
    main()
