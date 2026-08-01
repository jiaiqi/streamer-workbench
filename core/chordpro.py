"""R8.0 弹唱：ChordPro 曲谱格式解析（纯函数）。

ChordPro 格式参考（https://www.chordpro.org/）：
  {title: 歌名}
  {artist: 歌手}
  {key: C}
  {capo: 2}
  {comment: 前奏}
  {start_of_verse}
  [C]歌词第一行[G]歌词
  {end_of_verse}
  {start_of_chorus}
  副歌[F]歌词[Am]文字
  {end_of_chorus}

设计
----
- 纯函数：parse_chordpro(text) -> ParsedChordPro
- 行级结构：每行 = (chords, text) + section/label
- chord 位置：相对歌词字符索引（0-based）
- 元数据：{key:value} 单行 / 多行
- section 标签：{start_of_*} / {end_of_*} 配对；未配对不报错
- 注释：{comment:..} 视为行级注释，存为 line.comment

注意
----
- 不依赖任何 UI；纯 Python；单测友好
- 不处理 {...} 之外的简化标记（ChordPro 6 spec；这里只覆盖主流子集）
- 异常行 / 未闭合标签：跳过（不抛错；坏曲谱不阻塞弹唱）
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# 指令标签：{name} 或 {name: value}
_DIRECTIVE_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_-]*)(?::\s*([^{}]*?)\s*)?\}")
# 行内 chord：[ChordName]（行内而非整行）
_CHORD_RE = re.compile(r"\[([^\]\n]+?)\]")


@dataclass(frozen=True)
class ChordPosition:
    """行内 chord：相对歌词字符的位置。"""
    char_index: int  # 歌词字符串中的位置（0-based）
    name: str       # chord 名（C / Am / F# / Cmaj7 等）


@dataclass(frozen=True)
class ChordProLine:
    """单行曲谱。"""
    line_index: int                          # 行号（0-based）
    text: str = ""                           # 歌词文本（去掉所有 [...]）
    chords: tuple[ChordPosition, ...] = ()   # 行内 chord 位置
    directive: Optional[str] = None          # 整行指令（comment / start_of_* / end_of_*）
    section: Optional[str] = None            # 所属 section（verse / chorus / bridge …）


@dataclass(frozen=True)
class ParsedChordPro:
    """完整解析结果。"""
    lines: tuple[ChordProLine, ...] = ()
    meta: dict = field(default_factory=dict)  # title / artist / key / capo 等


# section 标签映射（start_of_X / end_of_X）
_SECTION_NAMES = {
    "verse", "chorus", "bridge", "intro", "outro",
    "prechorus", "interlude", "solo", "tab",
}


def parse_chordpro(text: str) -> ParsedChordPro:
    """解析 ChordPro 文本为 ParsedChordPro。

    规则：
      1. 按 \\n 切行
      2. 每行扫所有 {...} 指令：
         - 元数据 {key:value}：存 meta，**不产生 line**
         - {comment:..}：存为 line（directive=comment，text=comment_value）
         - {start_of_X} / {end_of_X}：section 标签
         - 其他指令：跳过
      3. 剩余行内容（含 [Chord]）：行内 chord 位置 + 歌词文本
      4. section 状态：当前 section 标签（start_of_*）应用到后续歌词行
    """
    if not text or not text.strip():
        return ParsedChordPro()

    raw_lines: list[ChordProLine] = []
    meta: dict = {}
    current_section: Optional[str] = None

    for line_index, raw_line in enumerate(text.splitlines()):
        # 1. 扫指令
        directives = _DIRECTIVE_RE.findall(raw_line)
        stripped = _DIRECTIVE_RE.sub("", raw_line).strip()

        # 元数据行
        is_meta_only = False
        for name, value in directives:
            lname = name.lower()
            if value is not None and lname not in {
                "start_of_verse", "end_of_verse",
                "start_of_chorus", "end_of_chorus",
                "start_of_bridge", "end_of_bridge",
                "comment",
                "start_of_tab", "end_of_tab",
            }:
                # 普通元数据：title / artist / key / capo / album 等
                if lname not in meta:
                    meta[lname] = value.strip()
                is_meta_only = True
            elif lname == "comment" and value is not None:
                # 行级注释
                raw_lines.append(ChordProLine(
                    line_index=line_index,
                    text=value.strip(),
                    directive="comment",
                    section=current_section,
                ))
                is_meta_only = True  # comment 不再产生第二行
            elif lname in {
                "start_of_verse", "end_of_verse",
                "start_of_chorus", "end_of_chorus",
                "start_of_bridge", "end_of_bridge",
            }:
                # section 标签：提取 section 名（verse / chorus / bridge）
                section_name = lname.replace("start_of_", "").replace("end_of_", "")
                if lname.startswith("start_of_"):
                    current_section = section_name
                # 不为 end_of_* 产生 line
                is_meta_only = (not stripped)
            # 其他指令（soc / eoc / start_of_tab 等）：跳过

        if is_meta_only and not stripped:
            continue

        # 2. 行内 chord + 歌词
        # 字符级扫 stripped：[...] 识别为 chord，其他字符 append 到 lyrics_chars。
        # 这样 chord.char_index 才是歌词里的真实位置（不是 strip 后的）。
        chords: list[ChordPosition] = []
        lyrics_chars: list[str] = []
        i = 0
        while i < len(stripped):
            if stripped[i] == "[":
                end = stripped.find("]", i + 1)
                if end < 0:
                    # 未闭合的 [ 当作普通字符
                    lyrics_chars.append(stripped[i])
                    i += 1
                    continue
                chord_name = stripped[i + 1:end].strip()
                if chord_name:
                    chords.append(ChordPosition(
                        char_index=len(lyrics_chars), name=chord_name))
                i = end + 1
            else:
                lyrics_chars.append(stripped[i])
                i += 1
        lyrics_text = "".join(lyrics_chars)
        # 歌词里的转义 \{ \} \\ 还原
        lyrics_text = lyrics_text.replace("\\{", "{").replace("\\}", "}").replace("\\\\", "\\")

        # 当前行若是空歌词（只是 section 标签）也保留（用于 UI 渲染空行/分割）
        raw_lines.append(ChordProLine(
            line_index=line_index,
            text=lyrics_text,
            chords=tuple(chords),
            section=current_section,
        ))

    return ParsedChordPro(lines=tuple(raw_lines), meta=meta)


def collect_chord_names(parsed: ParsedChordPro) -> tuple[str, ...]:
    """提取整首曲谱里所有出现过的 chord 名（去重保序）。"""
    seen: set[str] = set()
    result: list[str] = []
    for line in parsed.lines:
        for chord in line.chords:
            if chord.name not in seen:
                seen.add(chord.name)
                result.append(chord.name)
    return tuple(result)


__all__ = [
    "ChordPosition", "ChordProLine", "ParsedChordPro",
    "parse_chordpro", "collect_chord_names",
]
