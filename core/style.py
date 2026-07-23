"""颜色角色契约：所有排版只认角色名、不认具体颜色。

5 个角色：text(歌名) / label(标签文字) / pill(标签底色) / line(下划线) / mist(柔光)。
移植自 歌单-排版一\build_playlist.py 的 THEMES style 字典。
"""
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class Style:
    text: Tuple[int, int, int]
    label: Tuple[int, int, int]
    pill: Tuple[int, int, int, int]
    line: Tuple[int, int, int]
    mist: Tuple[int, int, int, int]
