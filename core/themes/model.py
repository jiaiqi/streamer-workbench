"""主题模型：一个主题 = 背景图 + 配色角色 + 字体 + 输出前缀。

数据全部来自 theme.json，代码里不再出现 THEMES 这种硬编码字典。
"""
from dataclasses import dataclass, field
from typing import Dict, Tuple

from ..style import Style


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

    def background_path(self, page: int) -> str:
        import os
        return os.path.join(self.dir, self.backgrounds[str(page)])
