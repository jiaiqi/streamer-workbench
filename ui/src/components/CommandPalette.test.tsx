/// R4.1.5 CommandPalette 单元测试。
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, act } from "@testing-library/react";
import CommandPalette, { type Command } from "./CommandPalette";

function makeCommands(): Command[] {
  return [
    { id: "view-workspace", title: "切换到海报工作台", group: "视图", action: vi.fn() },
    { id: "view-library", title: "切换到歌曲库", group: "视图", action: vi.fn() },
    { id: "act-seed", title: "载入示例曲库", group: "操作", action: vi.fn() },
    { id: "poster-new", title: "新建海报草稿", group: "海报", action: vi.fn() },
    { id: "quickview-open", title: "打开直播速查", group: "速查", keywords: ["速查", "live"], action: vi.fn() },
  ];
}

describe("CommandPalette 基础", () => {
  it("open=false 不渲染", () => {
    render(<CommandPalette open={false} onClose={() => undefined} commands={makeCommands()} />);
    expect(screen.queryByTestId("command-palette")).toBeNull();
  });

  it("open=true 渲染 + focus 输入框", async () => {
    render(<CommandPalette open={true} onClose={() => undefined} commands={makeCommands()} dark={false} />);
    expect(screen.getByTestId("command-palette")).toBeTruthy();
    await act(async () => { await new Promise(r => setTimeout(r, 10)); });
    expect(screen.getByTestId("command-palette-input")).toBeTruthy();
  });

  it("渲染所有命令 + 分组标题", () => {
    render(<CommandPalette open={true} onClose={() => undefined} commands={makeCommands()} />);
    expect(screen.getByText("视图")).toBeTruthy();
    expect(screen.getByText("操作")).toBeTruthy();
    expect(screen.getByText("海报")).toBeTruthy();
    expect(screen.getByText("速查")).toBeTruthy();
    expect(screen.getAllByRole("option")).toHaveLength(5);
  });
});

describe("CommandPalette 搜索过滤", () => {
  it("输入 '曲库' 过滤掉其他", () => {
    render(<CommandPalette open={true} onClose={() => undefined} commands={makeCommands()} />);
    const input = screen.getByTestId("command-palette-input");
    fireEvent.change(input, { target: { value: "曲库" } });
    // '载入示例曲库' + '切换到歌曲库' = 2
    expect(screen.getAllByRole("option")).toHaveLength(2);
  });

  it("keywords 匹配 'live' 命中速查", () => {
    render(<CommandPalette open={true} onClose={() => undefined} commands={makeCommands()} />);
    const input = screen.getByTestId("command-palette-input");
    fireEvent.change(input, { target: { value: "live" } });
    expect(screen.getAllByRole("option")).toHaveLength(1);
    expect(screen.getByText("打开直播速查")).toBeTruthy();
  });

  it("无匹配显示空态", () => {
    render(<CommandPalette open={true} onClose={() => undefined} commands={makeCommands()} />);
    fireEvent.change(screen.getByTestId("command-palette-input"), { target: { value: "xyz不存在" } });
    expect(screen.getByText("没有匹配的命令")).toBeTruthy();
  });
});

describe("CommandPalette 键盘导航", () => {
  it("ArrowDown 高亮下一项", () => {
    render(<CommandPalette open={true} onClose={() => undefined} commands={makeCommands()} />);
    // 初始 highlight=0
    expect(screen.getAllByRole("option")[0].getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(window, { key: "ArrowDown" });
    expect(screen.getAllByRole("option")[1].getAttribute("aria-selected")).toBe("true");
  });

  it("ArrowUp 在 0 时不越界", () => {
    render(<CommandPalette open={true} onClose={() => undefined} commands={makeCommands()} />);
    fireEvent.keyDown(window, { key: "ArrowUp" });
    expect(screen.getAllByRole("option")[0].getAttribute("aria-selected")).toBe("true");
  });

  it("Enter 执行当前高亮命令", () => {
    const cmds = makeCommands();
    render(<CommandPalette open={true} onClose={() => undefined} commands={cmds} />);
    fireEvent.keyDown(window, { key: "ArrowDown" }); // highlight=1 → 切换到歌曲库
    fireEvent.keyDown(window, { key: "Enter" });
    expect(cmds[1].action).toHaveBeenCalledOnce();
  });

  it("Esc 关闭面板", () => {
    const onClose = vi.fn();
    render(<CommandPalette open={true} onClose={onClose} commands={makeCommands()} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
  });
});

describe("CommandPalette 鼠标交互", () => {
  it("点击命令触发 action + 关闭", () => {
    const cmds = makeCommands();
    const onClose = vi.fn();
    render(<CommandPalette open={true} onClose={onClose} commands={cmds} />);
    fireEvent.click(screen.getByTestId("command-view-workspace"));
    expect(cmds[0].action).toHaveBeenCalledOnce();
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("disabled 命令不触发 action", () => {
    const cmds: Command[] = [
      { id: "blocked", title: "blocked", group: "操作", action: vi.fn(), disabledReason: "暂不可用" },
    ];
    render(<CommandPalette open={true} onClose={() => undefined} commands={cmds} />);
    fireEvent.click(screen.getByTestId("command-blocked"));
    expect(cmds[0].action).not.toHaveBeenCalled();
  });

  it("背景点击关闭", () => {
    const onClose = vi.fn();
    render(<CommandPalette open={true} onClose={onClose} commands={makeCommands()} />);
    // 背景是 dialog 的外层 div（fixed inset-0）
    const backdrop = screen.getByTestId("command-palette").parentElement!;
    fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledOnce();
  });
});

describe("CommandPalette 视觉", () => {
  it("快捷键 kbd 显示在命令右侧", () => {
    const cmds: Command[] = [
      { id: "a", title: "带快捷键", group: "操作", shortcut: "⌘E", action: vi.fn() },
    ];
    render(<CommandPalette open={true} onClose={() => undefined} commands={cmds} />);
    expect(screen.getByText("⌘E")).toBeTruthy();
  });

  it("暗色模式应用深色", () => {
    const { container } = render(<CommandPalette open={true} onClose={() => undefined} commands={makeCommands()} dark={true} />);
    const dialog = container.querySelector('[role="dialog"]')!;
    expect(dialog.className).toMatch(/bg-zinc-800/);
  });
});
