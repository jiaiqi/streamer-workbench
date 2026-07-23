"""画布规格：把散落在旧脚本里的全局常量和开关收拢成显式参数对象。

画布尺寸是自由参数（不再用 bool 切换），避让区以 Rect 列表暴露给排版插件。
移植自 歌单-排版一\build_playlist.py 的 FULL/AVOID/R_at/OFF 常量。
"""
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class CanvasSpec:
    width: int = 1080
    height: int = 1920                 # 自由参数，不再由 bool 推导
    avoid_zones: Tuple = ()           # 禁文区列表，每个元素为 (x0, y0, x1, y1)；空=不避让
    margin: int = 58
    font_song: int = 36               # avoid_zones 非空时引擎自动降为 34
    font_label: int = 40
    row_h: int = 44
    label_h: int = 74
    sec_gap: int = 26
    r_below: int = 856                 # 分界线下右边界（grid-wrap 专用，避让时用）

    @property
    def content_offset(self) -> int:
        """内容居中偏移：height > 1920 时下移居中，等于旧脚本的 OFF。"""
        return max(0, (self.height - 1920) // 2)

    def r_at(self, y: int) -> int:
        """绕排右边界：返回歌名文字顶部为 y 的行可用的右边界。"""
        if self.avoid_zones and y + 36 > 1080:
            return self.r_below
        return self.width - self.margin

    @property
    def is_fullscreen(self) -> bool:
        return self.height > 1920


# 画布预设（UI 下拉选项，不是引擎逻辑）
CANVAS_PRESETS = {
    "抖音全屏 9:20": CanvasSpec(
        width=1080, height=2400, avoid_zones=((940, 1080, 1080, 2400),)),
    "标准 9:16": CanvasSpec(width=1080, height=1920),
}
