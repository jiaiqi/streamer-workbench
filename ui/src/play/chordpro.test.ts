/// R8.0 前端 ChordPro 解析器测试（mirror core/chordpro.py）。
import { describe, expect, it } from "vitest";
import { parseChordpro, collectChordNames } from "./chordpro";

describe("parseChordpro - 空 / 边界", () => {
  it("空字符串 → 空", () => {
    const r = parseChordpro("");
    expect(r.lines).toEqual([]);
    expect(r.meta).toEqual({});
  });
  it("null/undefined → 空", () => {
    expect(parseChordpro(null).lines).toEqual([]);
  });
  it("纯元数据", () => {
    const r = parseChordpro("{title: 歌名}\n{artist: 歌手}\n{key: C}");
    expect(r.meta.title).toBe("歌名");
    expect(r.meta.artist).toBe("歌手");
    expect(r.meta.key).toBe("C");
    expect(r.lines).toEqual([]);
  });
});

describe("parseChordpro - 行内 chord", () => {
  it("单 chord", () => {
    const r = parseChordpro("[C]歌词");
    expect(r.lines).toHaveLength(1);
    expect(r.lines[0].text).toBe("歌词");
    expect(r.lines[0].chords).toEqual([{ charIndex: 0, name: "C" }]);
  });
  it("chord 在词中间", () => {
    const r = parseChordpro("歌[C]词");
    expect(r.lines[0].text).toBe("歌词");
    expect(r.lines[0].chords[0]).toEqual({ charIndex: 1, name: "C" });
  });
  it("多 chord 同行", () => {
    const r = parseChordpro("[C]路过[Am]忘记[F]经过");
    const chords = r.lines[0].chords;
    expect(chords.map(c => c.name)).toEqual(["C", "Am", "F"]);
    expect(chords.map(c => c.charIndex)).toEqual([0, 2, 4]);
  });
  it("复杂 chord 名（带 # / 7 / sus）", () => {
    const r = parseChordpro("[F#m7]x[Bb]y[Cmaj9]z");
    expect(r.lines[0].chords.map(c => c.name)).toEqual(["F#m7", "Bb", "Cmaj9"]);
  });
});

describe("parseChordpro - 多行 + 段落", () => {
  it("多行 line_index 顺序", () => {
    const r = parseChordpro("[C]a\n[G]b\n[Am]c");
    expect(r.lines.map(l => l.lineIndex)).toEqual([0, 1, 2]);
    expect(r.lines.map(l => l.text)).toEqual(["a", "b", "c"]);
  });
  it("空行保留（UI 段落间距）", () => {
    const r = parseChordpro("[C]a\n\n[Am]b");
    expect(r.lines).toHaveLength(3);
    expect(r.lines[1].text).toBe("");
  });
  it("纯歌词行（无 chord）", () => {
    const r = parseChordpro("[C]前\n纯歌词\n[Am]后");
    expect(r.lines[1].text).toBe("纯歌词");
    expect(r.lines[1].chords).toEqual([]);
  });
  it("section 标签 {start_of_chorus}", () => {
    const r = parseChordpro("{start_of_chorus}\n[C]chorus");
    const lyricLines = r.lines.filter(l => l.text);
    expect(lyricLines[0].section).toBe("chorus");
  });
  it("section 传播到后续行", () => {
    const r = parseChordpro("{start_of_verse}\n[C]a\n[G]b");
    const lyricLines = r.lines.filter(l => l.text);
    expect(lyricLines.every(l => l.section === "verse")).toBe(true);
  });
});

describe("parseChordpro - 注释 + 容错", () => {
  it("comment 行", () => {
    const r = parseChordpro("{comment: 前奏}\n[C]开始");
    expect(r.lines[0].directive).toBe("comment");
    expect(r.lines[0].text).toBe("前奏");
    expect(r.lines[1].text).toBe("开始");
  });
  it("未闭合 [ 当普通字符", () => {
    const r = parseChordpro("[C]good\n[malformed\n[Am]also good");
    expect(r.lines).toHaveLength(3);
    expect(r.lines[0].text).toBe("good");
    expect(r.lines[1].text).toBe("[malformed");
    expect(r.lines[1].chords).toEqual([]);
    expect(r.lines[2].text).toBe("also good");
  });
});

describe("collectChordNames", () => {
  it("去重保序", () => {
    const r = parseChordpro("[C]a[Am]b[F]c[G]d[C]e");
    expect(collectChordNames(r)).toEqual(["C", "Am", "F", "G"]);
  });
  it("空曲谱", () => {
    expect(collectChordNames(parseChordpro("no chords"))).toEqual([]);
  });
});
