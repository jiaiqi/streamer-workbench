"""主题模型：一个主题 = 背景图 + 配色角色 + 字体 + 输出前缀。

数据全部来自 theme.json，代码里不再出现 THEMES 这种硬编码字典。
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..style import Style


@dataclass(frozen=True)
class ThemeMetadata:
    """M3 P3 续：主题 metadata — 智能推荐算法使用。

    字段：
      tags              关键词列表（用于匹配歌名/标题/标签）
      scenes            适用场景列表（直播/弹唱/教学/儿童/抒情/...）
      mood              氛围（fresh/deep/cute/elegant/warm/retro/...）
      language_friendly 适合的语言（"cn"/"en"/"jp"/"all"）
      song_count_range  适合的歌曲数量范围 [min, max]
    """
    tags: Tuple[str, ...] = field(default_factory=tuple)
    scenes: Tuple[str, ...] = field(default_factory=tuple)
    mood: str = ""
    language_friendly: str = "all"
    song_count_range: Tuple[int, int] = field(default_factory=lambda: (0, 9999))

    def __post_init__(self) -> None:
        object.__setattr__(self, "tags", tuple(self.tags))
        object.__setattr__(self, "scenes", tuple(self.scenes))
        # song_count_range 强制为 (min, max) 形式
        if len(self.song_count_range) != 2:
            object.__setattr__(self, "song_count_range", (0, 9999))
        else:
            lo, hi = self.song_count_range
            object.__setattr__(self, "song_count_range", (int(lo), int(hi)))


@dataclass
class Theme:
    name: str
    dir: str                       # 主题目录绝对路径
    output_prefix: str
    backgrounds: Dict[str, str]   # {"1": "background-1.png", "2": "..."}
    watermark_fix: bool
    styles: Dict[int, Style]       # {1: Style, 2: Style}
    font: str = None
    notes: str = ""
    # R4 Runtime v2: 能力矩阵 — theme 声明兼容哪些 layout。
    # 空 tuple = 全部兼容（v1 兼容：旧 theme.json 不加此字段走空 tuple）。
    # 非空 tuple：只列兼容的 layout id；其他 layout 视为不兼容。
    # v2 收口：默认空 tuple；新加 theme 可用此字段声明。
    compatible_layouts: Tuple[str, ...] = field(default_factory=tuple)
    # M3 P3 续：智能推荐 metadata（v1 兼容：缺省空 ThemeMetadata）
    metadata: ThemeMetadata = field(default_factory=ThemeMetadata)

    def background_path(self, page: int) -> str:
        import os
        return os.path.join(self.dir, self.backgrounds[str(page)])
