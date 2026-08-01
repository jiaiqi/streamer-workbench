/// R8.0 前端 LRC 解析器测试（mirror core/lrc.py）。
import { describe, expect, it } from "vitest";
import { parseLrc, findActiveLine, distributePlainLyrics } from "./lrc";

describe("parseLrc - 空 / 边界", () => {
  it("空字符串 → 空结果", () => {
    const r = parseLrc("");
    expect(r.lines).toEqual([]);
    expect(r.meta).toEqual({});
  });
  it("全空白 → 空结果", () => {
    expect(parseLrc("   \n\n   ").lines).toEqual([]);
  });
  it("null/undefined → 空结果", () => {
    expect(parseLrc(null).lines).toEqual([]);
    expect(parseLrc(undefined).lines).toEqual([]);
  });
});

describe("parseLrc - 标准 [mm:ss.xx]", () => {
  it("单行", () => {
    const r = parseLrc("[00:12.34]路过的人");
    expect(r.lines).toHaveLength(1);
    expect(r.lines[0].timeMs).toBe(12340);
    expect(r.lines[0].text).toBe("路过的人");
  });
  it("多行按时间升序", () => {
    const r = parseLrc("[00:20.00]b\n[00:00.00]a\n[00:10.00]c");
    expect(r.lines.map(l => l.timeMs)).toEqual([0, 10000, 20000]);
  });
  it("百分秒 1/2/3 位都接受", () => {
    expect(parseLrc("[00:00.1]x").lines[0].timeMs).toBe(100);
    expect(parseLrc("[00:00.01]x").lines[0].timeMs).toBe(10);
    expect(parseLrc("[00:00.001]x").lines[0].timeMs).toBe(1);
  });
  it("大数 99:59.999", () => {
    expect(parseLrc("[99:59.999]x").lines[0].timeMs).toBe((99 * 60 + 59) * 1000 + 999);
  });
  it("空歌词保留（节拍/前奏）", () => {
    const r = parseLrc("[00:05.00]");
    expect(r.lines).toHaveLength(1);
    expect(r.lines[0].text).toBe("");
  });
});

describe("parseLrc - 增强 LRC（同行多时间戳）", () => {
  it("两时间戳同歌词", () => {
    const r = parseLrc("[00:10.00][00:20.00]副歌");
    expect(r.lines).toHaveLength(2);
    expect(r.lines[0].text).toBe("副歌");
    expect(r.lines[1].text).toBe("副歌");
    expect(r.lines.map(l => l.timeMs)).toEqual([10000, 20000]);
  });
});

describe("parseLrc - 元数据 + offset", () => {
  it("基本元数据", () => {
    const r = parseLrc("[ti:歌名]\n[ar:歌手]\n[00:10.00]x");
    expect(r.meta.ti).toBe("歌名");
    expect(r.meta.ar).toBe("歌手");
    expect(r.lines).toHaveLength(1);
  });
  it("offset 正向", () => {
    const r = parseLrc("[offset:+500]\n[00:00.00]推迟");
    expect(r.lines[0].timeMs).toBe(500);
  });
  it("offset 负向", () => {
    const r = parseLrc("[offset:-200]\n[00:00.00]提前");
    expect(r.lines[0].timeMs).toBe(-200);
  });
  it("重复 [ti:..]：首次优先", () => {
    const r = parseLrc("[ti:首版]\n[ti:次版]\n[00:00.00]x");
    expect(r.meta.ti).toBe("首版");
  });
});

describe("parseLrc - 容错", () => {
  it("无标签行跳过", () => {
    const r = parseLrc("just text\n[00:10.00]real");
    expect(r.lines).toHaveLength(1);
  });
  it("乱码时间戳跳过", () => {
    const r = parseLrc("[aa:bb.cc]bad\n[00:10.00]good");
    expect(r.lines).toHaveLength(1);
  });
});

describe("findActiveLine", () => {
  const lines = parseLrc("[00:00.00]a\n[00:10.00]b\n[00:20.00]c").lines;

  it("空 lines → -1", () => {
    expect(findActiveLine([], 0)).toBe(-1);
    expect(findActiveLine([], 99999)).toBe(-1);
  });
  it("早于首行 → -1", () => {
    expect(findActiveLine(lines, -100)).toBe(-1);
  });
  it("恰好时间戳上 → 该行", () => {
    expect(findActiveLine(lines, 0)).toBe(0);
    expect(findActiveLine(lines, 10000)).toBe(1);
    expect(findActiveLine(lines, 20000)).toBe(2);
  });
  it("两时间戳之间 → 上一行", () => {
    expect(findActiveLine(lines, 15000)).toBe(1);
  });
  it("晚于末行 → 末行", () => {
    expect(findActiveLine(lines, 99999)).toBe(2);
  });
});

describe("distributePlainLyrics", () => {
  it("按行均分到时间轴", () => {
    const r = distributePlainLyrics("第一行\n第二行\n第三行", 30000);
    expect(r).toHaveLength(3);
    expect(r[0].timeMs).toBe(0);
    expect(r[1].timeMs).toBe(10000);
    expect(r[2].timeMs).toBe(20000);
  });
  it("空文本 → 空", () => {
    expect(distributePlainLyrics("", 60000)).toEqual([]);
    expect(distributePlainLyrics("   \n  \n  ", 60000)).toEqual([]);
  });
});
