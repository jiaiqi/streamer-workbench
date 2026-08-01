"""R8.0 弹唱：LRC 歌词格式解析（纯函数）。

LRC 格式参考：
  [ti:歌名]                元数据：标题
  [ar:歌手]                元数据：艺术家
  [al:专辑]                元数据：专辑
  [by:编辑者]              元数据：LRC 编辑者
  [offset:+0]              元数据：全局时间偏移（毫秒，+ 加 - 减）
  [00:12.34]歌词第一行      时间戳 + 歌词
  [00:25.67][01:30.00]重复   同一行多时间戳（增强 LRC）
  [99:99.99]歌词            越界时间戳也接受（视作歌曲末尾之后）

设计
----
- 纯函数：parse_lrc(text) -> ParsedLRC（meta + lines）
- 时间单位：毫秒（int），offset 加到每行 time_ms
- 同一行多时间戳：拆成多条 LrcLine 共享同一 text
- 空行 / 无时间戳行 / 异常行：跳过（不抛错；坏 LRC 不应阻塞弹唱）
- 全部时间戳为 0 / 负数：仍接受，UI 层判空（fallback 用 lyrics_plain）

注意
----
- 不依赖 Pillow / 任何 UI 框架；纯 Python；单测友好
- 不强求 UTF-8 BOM；input str 即可（FileEvent 加载是 bytes 时由调用方 decode）
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# 时间戳：分:秒.百分秒（百分秒 1-3 位都可接受；常见 2 位）
_TIMESTAMP_RE = re.compile(r"\[(\d{1,2}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
# 元数据：单行 [key:value] 形式（key 是字母开头 + value 不含 ]）
_META_RE = re.compile(r"^\[([a-zA-Z][a-zA-Z0-9_-]*):([^\]]*)\]$")
# 一行所有 [..] 标签切分（保留顺序）
_TAG_RE = re.compile(r"\[[^\]]+\]")


@dataclass(frozen=True)
class LrcLine:
    """单条 LRC 歌词行。"""
    time_ms: int   # 触发时间（毫秒，含 offset）
    text: str      # 歌词文本（去掉前后空白）


@dataclass(frozen=True)
class ParsedLRC:
    """完整解析结果。"""
    lines: tuple[LrcLine, ...] = ()                # 按 time_ms 升序
    meta: dict = field(default_factory=dict)        # 元数据（ti/ar/al/by/offset 等）


def _parse_timestamp_to_ms(minute: str, second: str, fraction: Optional[str]) -> int:
    """[mm:ss.xx] → 总毫秒。fraction 缺省 = 0；1-3 位百分比（1 位 = 100ms，2 位 = 10ms，3 位 = 1ms）。"""
    m = int(minute)
    s = int(second)
    if fraction is None:
        frac_ms = 0
    else:
        # 1 位 → 100ms（0.1s），2 位 → 10ms（0.01s），3 位 → 1ms（0.001s）
        scale = 3 - len(fraction)
        frac_ms = int(fraction) * (10 ** scale) if scale >= 0 else int(fraction[:3]) * 1
    return (m * 60 + s) * 1000 + frac_ms


def parse_lrc(text: str) -> ParsedLRC:
    """解析 LRC 文本为 ParsedLRC。

    规则：
      1. 按 \\n 切行
      2. 每行先剥离所有 [...] 标签；剩余文本 = 歌词内容
      3. 若所有标签都是 [mm:ss.xx] 形式（可多个）→ 时间戳行
      4. 若有 [key:value] 形式 → 元数据（仅首个元数据行记一次）
      5. 其余行（含无标签空行）→ 跳过
      6. offset 元数据：累加到所有时间戳

    异常行（时间戳格式错、行没 [...] 等）静默跳过，不抛错。
    """
    if not text or not text.strip():
        return ParsedLRC()

    raw_lines: list[LrcLine] = []
    meta: dict = {}
    offset_ms = 0

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        tags = _TAG_RE.findall(line)
        if not tags:
            # 没任何 [...] 标签 → 跳过（不抛错）
            continue

        # 提取标签外的歌词文本
        text_part = _TAG_RE.sub("", line).strip()

        timestamps: list[int] = []
        is_meta_line = False
        for tag in tags:
            inner = tag[1:-1]  # 去掉 [...]
            ts_match = _TIMESTAMP_RE.fullmatch(tag)
            if ts_match:
                minute, second, fraction = ts_match.groups()
                timestamps.append(_parse_timestamp_to_ms(minute, second, fraction))
                continue
            # 元数据：[key:value]
            meta_match = _META_RE.match(tag)
            if meta_match:
                key, value = meta_match.group(1), meta_match.group(2).strip()
                if key not in meta:  # 首条优先
                    meta[key] = value
                is_meta_line = True
                # offset 累加
                if key == "offset":
                    try:
                        offset_ms += int(value)
                    except (TypeError, ValueError):
                        pass
                continue
            # 未知格式标签：当作文本（不计入时间戳 / 元数据）

        if not timestamps:
            # 没有有效时间戳（纯元数据行或异常行）→ 跳过
            continue
        if is_meta_line and not text_part:
            # 纯元数据行（[offset:..] 等）→ 不产生歌词
            continue

        for ts in timestamps:
            raw_lines.append(LrcLine(time_ms=ts + offset_ms, text=text_part))

    # 按 time_ms 升序；同时间多行按出现顺序
    raw_lines.sort(key=lambda ln: (ln.time_ms,))
    return ParsedLRC(lines=tuple(raw_lines), meta=meta)


def find_active_line(lines: tuple[LrcLine, ...], position_ms: int) -> int:
    """找 position_ms 时刻正在唱的歌词行索引（最大 ≤ position_ms）。

    - lines 为空时返回 -1
    - position_ms < 首行时间 → -1（尚未开始）
    - position_ms > 末行时间 → 末行索引（持续最后一句）
    - 二分查找 O(log n)
    """
    if not lines:
        return -1
    if position_ms < lines[0].time_ms:
        return -1
    # 标准 lower_bound：找首个 > position_ms 的位置，再 -1
    lo, hi = 0, len(lines)
    while lo < hi:
        mid = (lo + hi) // 2
        if lines[mid].time_ms <= position_ms:
            lo = mid + 1
        else:
            hi = mid
    return lo - 1


__all__ = ["LrcLine", "ParsedLRC", "parse_lrc", "find_active_line"]
