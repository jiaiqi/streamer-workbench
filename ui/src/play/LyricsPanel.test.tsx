/// R8.0 LyricsPanel 单元测试
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";
import LyricsPanel from "./LyricsPanel";
import type { LrcLine } from "./lrc";

const lines: LrcLine[] = [
  { timeMs: 0, text: "前奏" },
  { timeMs: 10000, text: "第一句" },
  { timeMs: 20000, text: "第二句" },
];

afterEach(() => cleanup());

describe("LyricsPanel - 状态", () => {
  it("lines=[] → empty 态", () => {
    const { getByTestId } = render(<LyricsPanel dark={false} lines={[]} currentTimeMs={0} />);
    const panel = getByTestId("lyrics-panel");
    expect(panel.getAttribute("data-state")).toBe("empty");
    expect(panel.textContent).toContain("还没有歌词");
  });

  it("有 lines → ready 态", () => {
    const { getByTestId } = render(<LyricsPanel dark={false} lines={lines} currentTimeMs={5000} />);
    const panel = getByTestId("lyrics-panel");
    expect(panel.getAttribute("data-state")).toBe("ready");
    expect(panel.getAttribute("data-active-index")).toBe("0");
  });
});

describe("LyricsPanel - 当前行高亮", () => {
  it("currentTimeMs=0 → 第 0 行高亮", () => {
    const { container } = render(<LyricsPanel dark={false} lines={lines} currentTimeMs={0} />);
    const items = container.querySelectorAll('[data-testid="lyrics-panel-line"]');
    expect(items[0].getAttribute("data-active")).toBe("true");
    expect(items[1].getAttribute("data-active")).toBe("false");
  });

  it("currentTimeMs=15000 → 第 1 行高亮", () => {
    const { container } = render(<LyricsPanel dark={false} lines={lines} currentTimeMs={15000} />);
    const items = container.querySelectorAll('[data-testid="lyrics-panel-line"]');
    expect(items[1].getAttribute("data-active")).toBe("true");
  });

  it("currentTimeMs 早于首行 → 无高亮", () => {
    const { container } = render(<LyricsPanel dark={false} lines={lines} currentTimeMs={-1000} />);
    const items = container.querySelectorAll('[data-testid="lyrics-panel-line"]');
    items.forEach(item => expect(item.getAttribute("data-active")).toBe("false"));
  });

  it("currentTimeMs 晚于末行 → 末行高亮", () => {
    const { container } = render(<LyricsPanel dark={false} lines={lines} currentTimeMs={99999} />);
    const items = container.querySelectorAll('[data-testid="lyrics-panel-line"]');
    expect(items[2].getAttribute("data-active")).toBe("true");
  });
});

describe("LyricsPanel - 文本渲染", () => {
  it("空文本行显示占位（空白）", () => {
    const sparse: LrcLine[] = [
      { timeMs: 0, text: "前" },
      { timeMs: 5000, text: "" },
      { timeMs: 10000, text: "后" },
    ];
    const { container } = render(<LyricsPanel dark={false} lines={sparse} currentTimeMs={0} />);
    expect(container.textContent).toContain("（空白）");
  });

  it("data-time-ms 属性", () => {
    const { container } = render(<LyricsPanel dark={false} lines={lines} currentTimeMs={0} />);
    const items = container.querySelectorAll('[data-testid="lyrics-panel-line"]');
    expect(items[0].getAttribute("data-time-ms")).toBe("0");
    expect(items[1].getAttribute("data-time-ms")).toBe("10000");
  });
});
