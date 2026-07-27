"""画布规格：把散落在旧脚本里的全局常量和开关收拢成显式参数对象。

画布尺寸是自由参数（不再用 bool 切换），避让区以 Rect 列表暴露给排版插件，
由排版插件自行实现避让策略。CanvasSpec 本身不关心具体避让逻辑。
移植自 歌单-排版一\build_playlist.py 的 FULL/AVOID/R_at/OFF 常量。
"""
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class CanvasSpec:
    width: int = 1080
    height: int = 1920                 # 自由参数，不再由 bool 推导
    avoid_zones: Tuple = ()           # 禁文区列表，每个元素为 (x0, y0, x1, y1)；空=不避让
    baseline_height: int = 1920       # 内容基准高度（content_offset 计算用，代替硬编码 1920）
    margin: int = 58
    font_song: int = 36               # 非避让模式下歌名字号
    font_song_avoid: int = 34         # 避让模式下歌名字号（代替 engine.py 硬编码 34）
    font_label: int = 40
    row_h: int = 44
    label_h: int = 74
    sec_gap: int = 26

    @property
    def content_offset(self) -> int:
        """内容居中偏移：height > baseline_height 时下移居中，等于旧脚本的 OFF。"""
        return max(0, (self.height - self.baseline_height) // 2)

    @property
    def is_fullscreen(self) -> bool:
        return self.height > self.baseline_height


# 全高避让区模板（server/main.py 中三处重复硬编码改为引用此模板拼接画布高度）
# 使用方式：replace(spec, avoid_zones=((AVOID_ZONES_X0, AVOID_ZONES_Y0, AVOID_ZONES_X1, base.height),))
AVOID_ZONES_X0 = 940
AVOID_ZONES_Y0 = 1080
AVOID_ZONES_X1 = 1080


# 画布预设（UI 下拉选项，不是引擎逻辑）
CANVAS_PRESETS = {
    "抖音全屏 9:20": CanvasSpec(
        width=1080, height=2400, avoid_zones=((940, 1080, 1080, 2400),)),
    "标准 9:16": CanvasSpec(width=1080, height=1920),
}
