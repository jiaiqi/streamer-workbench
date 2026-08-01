/// R8.0 TabsPanel 单元测试
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";
import TabsPanel from "./TabsPanel";
import { parseChordpro } from "./chordpro";

afterEach(() => cleanup());

const SAMPLE_TAB = `{title: 测试}
{key: C}
{start_of_verse}
[C]歌词[Am]更多[F]歌词
[G]下一行
{end_of_verse}
{start_of_chorus}
[Am]副歌[Em]行
{end_of_chorus}`;

describe("TabsPanel - 状态", () => {
  it("parsed.lines=[] → empty", () => {
    const { getByTestId } = render(
      <TabsPanel dark={false} parsed={{ lines: [], meta: {} }} currentTimeMs={0} totalMs={60000} />
    );
    const panel = getByTestId("tabs-panel");
    expect(panel.getAttribute("data-state")).toBe("empty");
    expect(panel.textContent).toContain("还没有曲谱");
  });

  it("有 lines → ready", () => {
    const parsed = parseChordpro(SAMPLE_TAB);
    const { getByTestId } = render(
      <TabsPanel dark={false} parsed={parsed} currentTimeMs={0} totalMs={60000} />
    );
    const panel = getByTestId("tabs-panel");
    expect(panel.getAttribute("data-state")).toBe("ready");
  });
});

describe("TabsPanel - 当前行高亮", () => {
  it("currentTimeMs 推进时激活行切换", () => {
    const parsed = parseChordpro(SAMPLE_TAB);
    // 3 个 lyric 行：歌词（0）/ 下一行（1）/ 副歌行（2）
    // totalMs=30000 → perLine=10000
    const { container, rerender } = render(
      <TabsPanel dark={false} parsed={parsed} currentTimeMs={0} totalMs={30000} />
    );
    let active = container.querySelector('[data-active="true"]');
    expect(active).toBeTruthy();
    // 切到 15000 → 第 1 行（下一行）激活
    rerender(<TabsPanel dark={false} parsed={parsed} currentTimeMs={15000} totalMs={30000} />);
    const activeLines = container.querySelectorAll('[data-active="true"][data-line-index]');
    expect(activeLines.length).toBeGreaterThanOrEqual(1);
  });
});

describe("TabsPanel - 渲染内容", () => {
  it("chord token 存在", () => {
    const parsed = parseChordpro("[C]歌词");
    const { container } = render(
      <TabsPanel dark={false} parsed={parsed} currentTimeMs={0} totalMs={30000} />
    );
    const tokens = container.querySelectorAll('[data-testid="tabs-chord-token"]');
    expect(tokens.length).toBe(1);
    expect(tokens[0].textContent).toBe("C");
  });

  it("section 标签影响 data-section", () => {
    const parsed = parseChordpro("{start_of_verse}\n[C]a\n{end_of_verse}\n{start_of_chorus}\n[Am]b");
    const { container } = render(
      <TabsPanel dark={false} parsed={parsed} currentTimeMs={0} totalMs={30000} />
    );
    const verseLines = container.querySelectorAll('[data-section="verse"]');
    const chorusLines = container.querySelectorAll('[data-section="chorus"]');
    expect(verseLines.length).toBeGreaterThan(0);
    expect(chorusLines.length).toBeGreaterThan(0);
  });

  it("comment 行", () => {
    const parsed = parseChordpro("{comment: 前奏}\n[C]开始");
    const { getByTestId } = render(
      <TabsPanel dark={false} parsed={parsed} currentTimeMs={0} totalMs={30000} />
    );
    expect(getByTestId("tabs-panel-comment").textContent).toContain("前奏");
  });
});
