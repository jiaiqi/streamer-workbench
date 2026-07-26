"""批量回填弹唱字段 key / capo / difficulty（一次性数据补录脚本）。

数据源：主流吉他谱站（无限延音/高音教/老姚/吉他专家等）最常见弹唱谱版本，
均经联网搜索逐首校准；仅收录有明确「原调 X 选调 Y 变调夹 Z 品」记载的条目。
填的是**主流编配起点**，主播实际按自己音域/编配在编辑界面自行调整。

- 只填空字段；已有值不动（幂等，可重复运行）
- 保存前自动备份（SongLibrary.save 内建）
- difficulty 仅在谱站有明确难度标注（难度值/「简单」描述）时填，否则留空
- capo 取值规则：谱站给「男生 X 品 / 女生 Y 品」区间时取男生侧常见值；
  与原调一致的「原版不夹」记 capo=None

运行（项目根目录）：
    PYTHONPATH=. .venv/bin/python tools/fill_playing_fields.py
"""

from core.data.songs import build_default_library

# title: (key, capo, difficulty)
PLAYING: dict[str, tuple[str, int | None, str | None]] = {
    # ---- 五月天 ----
    "知足": ("C", 4, None),            # 原调 E，选 C 转 D 夹 4 品
    "突然好想你": ("C", 2, None),       # C 调指法夹 2 品
    "倔强": ("A", None, None),          # A 调原版不夹
    "温柔": ("G", None, None),          # 原调 G，G 调不夹（男生）
    "恋爱ing": ("C", None, None),       # 原调 C，C 调不夹
    "私奔到月球": ("C", None, None),    # C 调简单版
    "我不愿让你一个人": ("G", None, None),  # G 调原调编配版
    "你不是真正的快乐": ("C", 5, None),  # 原调 F，选 C 夹 5 品
    "干杯": ("C", 5, None),            # 原调 F，选 C 转 D 夹 5 品
    # ---- 周杰伦 ----
    "晴天": ("G", None, "简单"),        # 原调 G 不夹，谱站难度值 38 分=简单
    "花海": ("G", 2, None),            # 原调 A，选 G 夹 2 品
    "七里香": ("C", 3, None),          # 原调降 E，选 C 夹 3 品
    # ---- 林俊杰 ----
    "江南": ("G", 3, None),            # 原调降 B，选 G 夹 3 品
    "修炼爱情": ("C", 3, None),         # 原调降 E，选 C 夹 3 品
    # ---- 陈奕迅 ----
    "十年": ("G", 1, None),            # 原调降 A，选 G 夹 1 品
    "好久不见": ("C", None, None),      # C 调原版指法不夹
    # ---- 孙燕姿 ----
    "遇见": ("G", 1, None),            # 原调降 A，G 调夹 1 品
    "天黑黑": ("G", 1, None),          # 原调降 A，选 G 夹 1 品
    "我怀念的": ("C", 4, None),         # 原调 E，选 C 夹 4 品
    "我不难过": ("C", 3, None),         # 原调降 E，选 C 夹 3 品
    # ---- 王菲 ----
    "红豆": ("C", None, None),          # 原调 C 不夹
    "如愿": ("G", 2, None),            # 原调 A，选 G 夹 2 品
    # ---- 其他高传唱 ----
    "小情歌": ("C", 2, None),          # 原调 D，选 C 夹 2 品
    "旅行的意义": ("C", 2, "简单"),     # 原调 D 选 C 夹 2，难度值 20 分
    "小幸运": ("C", 5, None),          # 原调 F，选 C 夹 5 品
    "童话": ("F", 1, None),            # 原调升 F，选 F 夹 1 品（老姚版）
    "那些年": ("C", 5, None),          # 原调 F，选 C 夹 5 品
    "奇妙能力歌": ("C", None, "简单"),  # 原调 C 不夹，难度值 36 分=简单
    "有何不可": ("C", 6, "简单"),       # 原调升 F，选 C 夹 6 品（男生 5-6）
    "成都": ("C", 2, "中等"),           # 原调 D，选 C 夹 2 品
}


def main() -> None:
    lib = build_default_library(json_path="data/songs.json")
    by_title = {s.title: s for s in lib.songs}
    filled, kept, missing = [], [], []
    for title, (key, capo, difficulty) in PLAYING.items():
        song = by_title.get(title)
        if song is None:
            missing.append(title)        # 曲库里没有这首歌
            continue
        changed = []
        if not song.key:
            song.key = key
            changed.append(f"key={key}")
        if song.capo is None and capo is not None:
            song.capo = capo
            changed.append(f"capo={capo}")
        if not song.difficulty and difficulty:
            song.difficulty = difficulty
            changed.append(f"难度={difficulty}")
        (filled if changed else kept).append(f"{title}（{'，'.join(changed)}）" if changed else title)
    lib.save("data/songs.json", backup_dir="data/backups")
    no_key = [s.title for s in lib.songs if not s.key]
    print(f"回填 {len(filled)} 首 · 已有值保留 {len(kept)} 首")
    for line in filled:
        print(f"  ✓ {line}")
    if missing:
        print(f"\n曲库未收录（脚本条目跳过）：{'、'.join(missing)}")
    print(f"\n全库 key 完整度：{len(lib.songs) - len(no_key)}/{len(lib.songs)}")
    print(f"仍留空 {len(no_key)} 首（待主播在编辑界面按自己的编配补）：")
    print("、".join(no_key))


if __name__ == "__main__":
    main()
