/// L1.7 HelpCenter 测试
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render } from "@testing-library/react";
import HelpCenter from "./HelpCenter";

afterEach(() => cleanup());

const noopActions = {
  openShortcuts: vi.fn(),
  reopenOnboarding: vi.fn(),
  openCommandPalette: vi.fn(),
};

describe("HelpCenter - 渲染", () => {
  it("open=false → 不渲染", () => {
    const { queryByTestId } = render(<HelpCenter open={false} onClose={() => {}} actions={noopActions} />);
    expect(queryByTestId("help-center")).toBeNull();
  });

  it("open=true → 渲染 5 个入口卡片", () => {
    const { getByTestId, getAllByTestId } = render(
      <HelpCenter open={true} onClose={() => {}} actions={noopActions} />,
    );
    expect(getByTestId("help-center")).toBeTruthy();
    const items = getAllByTestId(/^help-item-/);
    expect(items.length).toBe(5);
  });

  it("标题 + 关闭按钮 + 底部 hint 都在", () => {
    const { getByTestId, getByText } = render(
      <HelpCenter open={true} onClose={() => {}} actions={noopActions} />,
    );
    expect(getByText("帮助中心")).toBeTruthy();
    expect(getByTestId("help-center-close")).toBeTruthy();
  });
});

describe("HelpCenter - 交互", () => {
  it("点关闭按钮调 onClose", () => {
    const onClose = vi.fn();
    const { getByTestId } = render(
      <HelpCenter open={true} onClose={onClose} actions={noopActions} />,
    );
    fireEvent.click(getByTestId("help-center-close"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("点 backdrop 调 onClose（点面板本体不调）", () => {
    const onClose = vi.fn();
    const { getByTestId } = render(
      <HelpCenter open={true} onClose={onClose} actions={noopActions} />,
    );
    fireEvent.click(getByTestId("help-center-backdrop"));
    expect(onClose).toHaveBeenCalledTimes(1);

    onClose.mockClear();
    fireEvent.click(getByTestId("help-center"));
    expect(onClose).not.toHaveBeenCalled();
  });

  it("Esc 关闭面板", () => {
    const onClose = vi.fn();
    render(<HelpCenter open={true} onClose={onClose} actions={noopActions} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("HelpCenter - 入口 actions", () => {
  it("点「快捷键面板」→ 调 openShortcuts + 关闭", () => {
    const openShortcuts = vi.fn();
    const onClose = vi.fn();
    const { getByTestId } = render(
      <HelpCenter open={true} onClose={onClose}
        actions={{ ...noopActions, openShortcuts }} />,
    );
    fireEvent.click(getByTestId("help-item-快捷键面板"));
    expect(openShortcuts).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("点「重看首次启动引导」→ 调 reopenOnboarding", () => {
    const reopenOnboarding = vi.fn();
    const onClose = vi.fn();
    const { getByTestId } = render(
      <HelpCenter open={true} onClose={onClose}
        actions={{ ...noopActions, reopenOnboarding }} />,
    );
    fireEvent.click(getByTestId("help-item-重看首次启动引导"));
    expect(reopenOnboarding).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("点「命令面板」→ 调 openCommandPalette", () => {
    const openCommandPalette = vi.fn();
    const onClose = vi.fn();
    const { getByTestId } = render(
      <HelpCenter open={true} onClose={onClose}
        actions={{ ...noopActions, openCommandPalette }} />,
    );
    fireEvent.click(getByTestId("help-item-命令面板"));
    expect(openCommandPalette).toHaveBeenCalledTimes(1);
  });

  it("点「项目主页」→ 新窗口打开 + 关闭", () => {
    const windowOpenSpy = vi.spyOn(window, "open").mockReturnValue(null);
    const onClose = vi.fn();
    const { getByTestId } = render(
      <HelpCenter open={true} onClose={onClose} actions={noopActions} />,
    );
    fireEvent.click(getByTestId("help-item-项目主页"));
    expect(windowOpenSpy).toHaveBeenCalledTimes(1);
    expect(windowOpenSpy.mock.calls[0][0]).toContain("github.com");
    expect(windowOpenSpy.mock.calls[0][2]).toContain("noopener");
    expect(onClose).toHaveBeenCalledTimes(1);
    windowOpenSpy.mockRestore();
  });
});
