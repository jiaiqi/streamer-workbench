/// L1.6 StatusBar 测试
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render } from "@testing-library/react";
import StatusBar from "./StatusBar";

afterEach(() => cleanup());

describe("StatusBar - 渲染", () => {
  it("hidden=true → 不渲染", () => {
    const { queryByTestId } = render(<StatusBar view="workspace" hidden />);
    expect(queryByTestId("status-bar")).toBeNull();
  });

  it("默认 view=workspace → 显示「视图: 工作台」", () => {
    const { getByTestId } = render(<StatusBar view="workspace" />);
    const el = getByTestId("status-bar");
    expect(el.getAttribute("data-view")).toBe("workspace");
    expect(getByTestId("status-bar-view").textContent).toContain("工作台");
  });

  it("所有 8 个 view 标签正确", () => {
    const views = ["workspace", "library", "learning", "live", "stats", "play", "settings", "preview"] as const;
    for ( const v of views) {
      const { unmount, getByTestId } = render(<StatusBar view={v} />);
      const viewEl = getByTestId("status-bar-view");
      expect(viewEl.textContent).toBeTruthy();
      unmount();
    }
  });

  it("op=idle → 绿色 idle 点 + 绿字「空闲」", () => {
    const { getByTestId } = render(<StatusBar view="workspace" op="idle" />);
    const op = getByTestId("status-bar-op");
    expect(op.getAttribute("data-testid")).toBe("status-bar-op");
    expect(op.textContent).toContain("空闲");
  });

  it("op=rendering → amber 点 + 「渲染中…」", () => {
    const { getByTestId } = render(<StatusBar view="workspace" op="rendering" />);
    const op = getByTestId("status-bar-op");
    expect(op.textContent).toContain("渲染中");
  });
});

describe("StatusBar - 渲染耗时", () => {
  it("lastRenderMs=null → 不显示", () => {
    const { queryByTestId } = render(<StatusBar view="workspace" lastRenderMs={null} />);
    expect(queryByTestId("status-bar-render")).toBeNull();
  });

  it("lastRenderMs=234 → 显示「234ms」", () => {
    const { getByTestId } = render(<StatusBar view="workspace" lastRenderMs={234} />);
    expect(getByTestId("status-bar-render").textContent).toContain("234ms");
  });

  it("lastRenderMs=0 → 不显示（避免 0ms 噪音）", () => {
    const { queryByTestId } = render(<StatusBar view="workspace" lastRenderMs={0} />);
    expect(queryByTestId("status-bar-render")).toBeNull();
  });
});

describe("StatusBar - 上次保存时间", () => {
  it("lastSaveTime=null → 不显示", () => {
    const { queryByTestId } = render(<StatusBar view="workspace" lastSaveTime={null} />);
    expect(queryByTestId("status-bar-save")).toBeNull();
  });

  it("lastSaveTime=30s 前 → 显示「30s 前」", () => {
    const date = new Date(Date.now() - 30 * 1000);
    const { getByTestId } = render(<StatusBar view="workspace" lastSaveTime={date.toISOString()} />);
    expect(getByTestId("status-bar-save").textContent).toMatch(/\d+s 前/);
  });

  it("lastSaveTime=5 分钟前 → 显示「5m 前」", () => {
    const date = new Date(Date.now() - 5 * 60 * 1000);
    const { getByTestId } = render(<StatusBar view="workspace" lastSaveTime={date.toISOString()} />);
    expect(getByTestId("status-bar-save").textContent).toContain("5m 前");
  });
});

describe("StatusBar - 错误重试", () => {
  it("errorMessage=null → 不显示错误 badge", () => {
    const { queryByTestId } = render(<StatusBar view="workspace" errorMessage={null} />);
    expect(queryByTestId("status-bar-error")).toBeNull();
  });

  it("errorMessage='网络错误' → 红色 badge + onRetry 调", () => {
    const onRetry = vi.fn();
    const { getByTestId } = render(
      <StatusBar view="workspace" errorMessage="网络错误" onRetry={onRetry} />,
    );
    const btn = getByTestId("status-bar-error");
    expect(btn.textContent).toContain("错误");
    fireEvent.click(btn);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
