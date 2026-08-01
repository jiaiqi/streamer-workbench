"""R4 Runtime v1：DataChannel 显式契约 + Layout 能力声明。

背景
----
R0-R3 早期阶段只有「SongLibrary」一种数据通道，layout 直接读 library 字段。
R2.5 引入 live-set（LiveSessionSnapshot）+ R3.5 引入 learning-report
（LearningReportSnapshot）后，layout 与 library 之间的耦合靠 docstring +
duck-typing（layout 内部 isinstance / hasattr 探测 snapshot 字段）维持。

这种模式有几个问题：
  1. 外部调用方（HTTP router / 预览代码）需要自己知道"这个 layout 接受
     哪种 library 类型"，无法从一个统一位置查询。
  2. capabilities() dict 里有 supported_canvas_ids / supports_grouping 等
     字段，但没有"supported_channels"——必须靠 docstring 才能判断。
  3. 新增第 4 种数据通道时（例如未来加「歌手专辑」），所有调用方都要
     手动补 isinstance 兜底，零结构化保护。

R4 Runtime v1 抽象
------------------
最小化、可逆、低风险：只引入 *DataChannel* 域枚举 + LayoutPlugin 显式
声明 supported_channels + 一个 helper。**不**强制 engine.render_page 改签名
（保持向后兼容）；**不**统一 LayoutPlan 数据结构（推迟到 R4 Runtime v2）。

设计要点
--------
  - DataChannel 用 typing.Literal 限定三个值：`song_library` /
    `live_session` / `learning_report`。扩展性靠 tuple 增加新值，不动现有
    实现。
  - CHANNELS 是字面量元组（3 元素），供校验和单测引用。
  - normalize_channel() 接受 Literal 字符串/Channel-like dataclass，
    归一化到字面量值（防御性，未来 dataclass 后端接入时无破坏）。
  - 通道名 = 数据模型名（去 `_snapshot` 后缀），对外最简。
"""
from __future__ import annotations

from typing import Iterable, Literal


# 域枚举：所有 layout 必须从这 3 个值里选 supported_channels
DataChannel = Literal["song_library", "live_session", "learning_report"]

# 字面量元组，供 isinstance((), tuple) 校验和单测引用
CHANNELS: tuple[DataChannel, ...] = (
    "song_library",
    "live_session",
    "learning_report",
)


def normalize_channel(value: object) -> DataChannel:
    """归一化通道名到 DataChannel Literal。

    接受：
      - 字面量字符串（"song_library" 等）
      - 任何带 `.id` 或 `.name` 字段的对象（防御性）
      - 已经是字面量则直接返回

    抛出 ValueError 当无法归一化。
    """
    if isinstance(value, str) and value in CHANNELS:
        return value  # type: ignore[return-value]
    # 防御性：未来可能用 dataclass / Pydantic model
    if hasattr(value, "id") and isinstance(value.id, str) and value.id in CHANNELS:
        return value.id  # type: ignore[return-value]
    raise ValueError(
        f"未知 DataChannel：{value!r}；可选 {CHANNELS}")


def is_supported(channels: Iterable[DataChannel], target: DataChannel) -> bool:
    """判断 target 是否在 channels 列表里。空 tuple 返回 False（默认不支持）。"""
    if not channels:
        return False
    return target in tuple(channels)


__all__ = [
    "DataChannel",
    "CHANNELS",
    "normalize_channel",
    "is_supported",
]
