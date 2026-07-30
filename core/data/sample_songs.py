"""P1 R1a.2 内置样例曲库——首用引导专用。

来源：内置曲目集合（与 build_playlist.py YI/ER/SAN/WU 列表子集对齐，
不重复全部几百首内嵌库）。只用于「曲库空时一键导入示例」入口，
不可作为 develop 期默认库（开发期库仍走 data/songs.json）。

合同：
- 全部 status="active"（演示「已会」状态）
- song_id 走 legacy_song_id(title) 确定性派生，与 songs v4→v5 迁移同源
- section 字段标注与现有 YI/ER/SAN/WU 表对应（金标准防御：分组与 grid-wrap 一致）
"""
from __future__ import annotations

from core.data.songs import Song, legacy_song_id


# 各 section 的最小演示集合——保证有 1 字/2 字/3 字/4 字/5 字 5 个分组出现
SAMPLE_SECTIONS: list[tuple[int, list[str]]] = [
    (1, ["枫"]),
    (2, ["江南", "十年", "晴天", "安静", "知足"]),
    (3, ["七里香", "晴天", "小情歌"]),  # 实际取三位数首
    (4, ["那些年", "小幸运", "夏天的风"]),
    (5, ["突然好想你", "背对背拥抱", "奇妙能力歌"]),
]


def _build_sample_seed() -> list[Song]:
    """构造稳定的样例曲目列表。"""
    out: list[Song] = []
    seen_titles: set[str] = set()
    for section_id, titles in SAMPLE_SECTIONS:
        for t in titles:
            if t in seen_titles:
                continue
            seen_titles.add(t)
            out.append(
                Song(
                    title=t,
                    id=legacy_song_id(t),
                    status="active",
                    section=section_id,
                )
            )
    return out


# 模块级缓存：seed 不可变
SAMPLE_SEED: list[Song] = _build_sample_seed()


def is_library_empty(library) -> bool:
    """判断给定 SongLibrary 是否为空（0 首歌曲）。"""
    return len(library.songs) == 0


def seed_to_library(library) -> list[Song]:
    """把样例曲目加入给定 SongLibrary（修改对象），返回新加入的 Song 列表。

    已存在 title/id 的歌曲不会被添加，避免重复；返回的是真正加入的子集。
    """
    if not is_library_empty(library):
        return []
    added: list[Song] = []
    existing_titles = {s.title for s in library.songs}
    existing_ids = {s.id for s in library.songs}
    for song in SAMPLE_SEED:
        if song.title in existing_titles or song.id in existing_ids:
            continue
        library.songs.append(song)
        existing_titles.add(song.title)
        existing_ids.add(song.id)
        added.append(song)
    return added
