/// L1.2 ShortcutsPanel 测试
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render } from "@testing-library/react";
import ShortcutsPanel, { SHORTCUTS } from "./ShortcutsPanel";

afterEach(() => cleanup());

describe("ShortcutsPanel - 渲染", () => {
  it("open=false → 不渲染", () => {
    const { queryByTestId } = render(
      <ShortcutsPanel open={false} onClose={() => {}} />,
    );
    expect(queryByTestId("shortcuts-panel")).toBeNull();
    expect(queryByTestId("shortcuts-panel-backdrop")).toBeNull();
  });

  it("open=true → 渲染面板 + 头部 + 关闭按钮", () => {
    const { getByTestId, getByText } = render(
      <ShortcutsPanel open={true} onClose={() => {}} />,
    );
    expect(getByTestId("shortcuts-panel-backdrop")).toBeTruthy();
    expect(getByTestId("shortcuts-panel")).toBeTruthy();
    expect(getByText("快捷键")).toBeTruthy();
    expect(getByTestId("shortcuts-panel-close")).toBeTruthy();
  });

  it("渲染所有分组 + 每组至少 1 项", () => {
    const { getAllByTestId } = render(
      <ShortcutsPanel open={true} onClose={() => {}} />,
    );
    const groups = getAllByTestId("shortcuts-group");
    expect(groups.length).toBe(SHORTCUTS.length);
    for (const group of SHORTCUTS) {
      expect(group.shortcuts.length).toBeGreaterThan(0);
    }
  });

  it("点击 ✕ 关闭按钮调 onClose", () => {
    const onClose = vi.fn();
    const { getByTestId } = render(<ShortcutsPanel open={true} onClose={onClose} />);
    fireEvent.click(getByTestId("shortcuts-panel-close"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("点击 backdrop 调 onClose（点击面板本体不调）", () => {
    const onClose = vi.fn();
    const { getByTestId } = render(<ShortcutsPanel open={true} onClose={onClose} />);
    fireEvent.click(getByTestId("shortcuts-panel-backdrop"));
    expect(onClose).toHaveBeenCalledTimes(1);

    onClose.mockClear();
    fireEvent.click(getByTestId("shortcuts-panel"));
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe("ShortcutsPanel - 键盘交互", () => {
  it("Esc 关闭面板", () => {
    const onClose = vi.fn();
    render(<ShortcutsPanel open={true} onClose={onClose} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("open=false 时 Esc 不调 onClose", () => {
    const onClose = vi.fn();
    render(<ShortcutsPanel open={false} onClose={onClose} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe("ShortcutsPanel - SHORTCUTS 单源真值", () => {
  it("所有分组都至少有 1 个快捷键", () => {
    for (const g of SHORTCUTS) {
      expect(g.shortcuts.length).toBeGreaterThan(0);
    }
  });

  it("全局快捷键组有 Cmd+K / ? / Esc / Cmd+,", () => {
    const globalGroup = SHORTCUTS.find(g => g.group === "全局");
    expect(globalGroup).toBeTruthy();
    const descs = globalGroup!.shortcuts.map(s => s.description);
    expect(descs.some(d => d.includes("命令面板"))).toBe(true);
    expect(descs.some(d => d.includes("快捷键面板"))).toBe(true);
    expect(descs.some(d => d.includes("关闭对话框"))).toBe(true);
  });
});
