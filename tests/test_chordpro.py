"""R8.0 弹唱：ChordPro 曲谱解析测试（20+ 项）。

覆盖：
- 空 / 纯元数据
- 标准 chord 标记 [C] / [Am] / [F#] / [Cmaj7]
- 多 chord 同行
- 元数据 {title:..}{key:..}{capo:..}
- section 标签 {start_of_verse}/{end_of_chorus} 等
- 注释 {comment:..}
- 异常 / 越界行静默跳过
- collect_chord_names 去重保序
"""
from __future__ import annotations

import unittest

from core.chordpro import (
    ChordPosition, ChordProLine, ParsedChordPro,
    parse_chordpro, collect_chord_names,
)


class TestParseEmpty(unittest.TestCase):
    def test_empty(self):
        result = parse_chordpro("")
        self.assertEqual(result.lines, ())
        self.assertEqual(result.meta, {})

    def test_whitespace_only(self):
        result = parse_chordpro("   \n\n   \n")
        self.assertEqual(result.lines, ())

    def test_meta_only(self):
        text = "{title: 歌名}\n{artist: 歌手}\n{key: C}\n{capo: 2}"
        result = parse_chordpro(text)
        self.assertEqual(result.meta.get("title"), "歌名")
        self.assertEqual(result.meta.get("artist"), "歌手")
        self.assertEqual(result.meta.get("key"), "C")
        self.assertEqual(result.meta.get("capo"), "2")
        self.assertEqual(result.lines, ())


class TestParseBasic(unittest.TestCase):
    def test_single_chord(self):
        text = "[C]歌词第一行"
        result = parse_chordpro(text)
        self.assertEqual(len(result.lines), 1)
        self.assertEqual(result.lines[0].text, "歌词第一行")
        self.assertEqual(len(result.lines[0].chords), 1)
        self.assertEqual(result.lines[0].chords[0].name, "C")
        self.assertEqual(result.lines[0].chords[0].char_index, 0)

    def test_chord_mid_word(self):
        # 现实里 chord 在字符前的位置 [C]歌 → char_index=0
        text = "歌[C]词"
        result = parse_chordpro(text)
        # 歌词 = "歌词"，chord 在第 1 个字符（"词"）前
        self.assertEqual(result.lines[0].text, "歌词")
        self.assertEqual(result.lines[0].chords[0].char_index, 1)

    def test_multiple_chords(self):
        text = "[C]路过的人[Am]我早已忘记[F]经过"
        result = parse_chordpro(text)
        self.assertEqual(len(result.lines), 1)
        self.assertEqual(result.lines[0].text, "路过的人我早已忘记经过")
        chords = result.lines[0].chords
        self.assertEqual(len(chords), 3)
        # 歌词字符索引：路(0)过(1)的(2)人(3) → 4；我(4)早(5)已(6)忘(7)记(8) → 9；经(9)过(10) → 11
        self.assertEqual(chords[0].name, "C")
        self.assertEqual(chords[0].char_index, 0)
        self.assertEqual(chords[1].name, "Am")
        self.assertEqual(chords[1].char_index, 4)
        self.assertEqual(chords[2].name, "F")
        self.assertEqual(chords[2].char_index, 9)

    def test_chord_variants(self):
        # 各种 chord 命名约定
        result = parse_chordpro("[F#m7]x[Bb]y[Cmaj9]z")
        chords = result.lines[0].chords
        self.assertEqual([c.name for c in chords], ["F#m7", "Bb", "Cmaj9"])


class TestParseMultiLine(unittest.TestCase):
    def test_multiple_lines(self):
        text = """[C]第一行
[G]第二行
[Am]第三行"""
        result = parse_chordpro(text)
        self.assertEqual(len(result.lines), 3)
        self.assertEqual([ln.text for ln in result.lines],
                         ["第一行", "第二行", "第三行"])
        self.assertEqual([ln.chords[0].name for ln in result.lines],
                         ["C", "G", "Am"])
        # line_index 顺序
        self.assertEqual([ln.line_index for ln in result.lines], [0, 1, 2])

    def test_empty_lines_kept(self):
        # 空行应保留（UI 渲染段落间距）
        text = """[C]第一行

[Am]第二行"""
        result = parse_chordpro(text)
        self.assertEqual(len(result.lines), 3)
        self.assertEqual(result.lines[1].text, "")
        self.assertEqual(result.lines[1].chords, ())

    def test_chordless_lines_kept(self):
        # 没有 chord 的纯歌词行
        text = """[C]前一行
纯歌词行
[Am]后一行"""
        result = parse_chordpro(text)
        self.assertEqual(len(result.lines), 3)
        self.assertEqual(result.lines[0].text, "前一行")
        self.assertEqual(result.lines[1].text, "纯歌词行")
        self.assertEqual(result.lines[1].chords, ())
        self.assertEqual(result.lines[2].text, "后一行")


class TestParseSection(unittest.TestCase):
    def test_start_of_verse(self):
        text = """{start_of_verse}
[C]verse 歌词
{end_of_verse}"""
        result = parse_chordpro(text)
        # 至少 1 行歌词
        self.assertEqual(len(result.lines), 1)
        self.assertEqual(result.lines[0].section, "verse")
        self.assertEqual(result.lines[0].text, "verse 歌词")

    def test_section_propagates(self):
        # section 标签后的歌词行都标记为该 section
        text = """{start_of_chorus}
[C]chorus 第一行
[G]chorus 第二行
{end_of_chorus}"""
        result = parse_chordpro(text)
        # section 行 + 2 歌词行
        self.assertGreaterEqual(len(result.lines), 2)
        lyric_lines = [ln for ln in result.lines if ln.text]
        self.assertEqual(len(lyric_lines), 2)
        for ln in lyric_lines:
            self.assertEqual(ln.section, "chorus")

    def test_multiple_sections(self):
        text = """{start_of_verse}
[C]verse
{end_of_verse}
{start_of_chorus}
[Am]chorus
{end_of_chorus}"""
        result = parse_chordpro(text)
        verse_lines = [ln for ln in result.lines if ln.section == "verse" and ln.text]
        chorus_lines = [ln for ln in result.lines if ln.section == "chorus" and ln.text]
        self.assertEqual(len(verse_lines), 1)
        self.assertEqual(len(chorus_lines), 1)
        self.assertEqual(verse_lines[0].text, "verse")
        self.assertEqual(chorus_lines[0].text, "chorus")


class TestParseComment(unittest.TestCase):
    def test_comment_kept(self):
        text = """{comment: 前奏}
[C]开始唱歌"""
        result = parse_chordpro(text)
        # comment + 1 歌词行
        self.assertEqual(len(result.lines), 2)
        self.assertEqual(result.lines[0].directive, "comment")
        self.assertEqual(result.lines[0].text, "前奏")
        self.assertEqual(result.lines[1].text, "开始唱歌")

    def test_comment_with_chord(self):
        # 罕见但合法：{comment: 某段} 后跟 [C]歌词
        text = "{comment: 副歌反复}\n[C]反复唱"
        result = parse_chordpro(text)
        self.assertEqual(result.lines[0].directive, "comment")
        self.assertEqual(result.lines[0].text, "副歌反复")
        self.assertEqual(result.lines[1].text, "反复唱")


class TestCollectChordNames(unittest.TestCase):
    def test_dedup_preserve_order(self):
        text = "[C]a[Am]b[F]c[G]d[C]e[Am]f"
        result = parse_chordpro(text)
        names = collect_chord_names(result)
        self.assertEqual(names, ("C", "Am", "F", "G"))

    def test_empty(self):
        self.assertEqual(collect_chord_names(ParsedChordPro()), ())
        self.assertEqual(collect_chord_names(parse_chordpro("no chords here")), ())


class TestParseErrorTolerance(unittest.TestCase):
    def test_unknown_directive_skipped(self):
        # 未识别的指令 {} 不抛错
        text = """{unknown_directive: value}
[C]still works"""
        result = parse_chordpro(text)
        self.assertEqual(len(result.lines), 1)
        self.assertEqual(result.lines[0].text, "still works")

    def test_malformed_chord_skipped(self):
        # [ 单独未闭合 → 当作普通字符保留（不抛错）
        text = """[C]good
[malformed
[Am]also good"""
        result = parse_chordpro(text)
        # 3 行：good / "[malformed"（未闭合当作普通字符）/ also good
        self.assertEqual(len(result.lines), 3)
        self.assertEqual(result.lines[0].text, "good")
        self.assertEqual(result.lines[0].chords[0].name, "C")
        self.assertEqual(result.lines[1].text, "[malformed")
        self.assertEqual(result.lines[1].chords, ())
        self.assertEqual(result.lines[2].text, "also good")
        self.assertEqual(result.lines[2].chords[0].name, "Am")

    def test_mixed_with_meta(self):
        text = """{title: 测试}
[C]歌词
{comment: 提示}
[Am]更多歌词"""
        result = parse_chordpro(text)
        self.assertEqual(result.meta.get("title"), "测试")
        # comment + 2 歌词行
        self.assertGreaterEqual(len(result.lines), 3)
        # 提取歌词文本
        lyrics = [ln.text for ln in result.lines if ln.text]
        self.assertIn("歌词", lyrics)
        self.assertIn("更多歌词", lyrics)


if __name__ == "__main__":
    unittest.main()
