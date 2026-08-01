/// R4.1.4 ErrorBanner 单元测试。
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import ErrorBanner from "./ErrorBanner";

describe("ErrorBanner 基础", () => {
  it("默认 severity=error 红色 + 默认标题'出错了'", () => {
    render(<ErrorBanner message="加载失败" dark={false} />);
    expect(screen.getByText("出错了")).toBeTruthy();
    expect(screen.getByText("加载失败")).toBeTruthy();
    const banner = screen.getByRole("alert");
    expect(banner.className).toMatch(/bg-red-50/);
  });

  it("severity=warning 黄色 + 默认标题'请注意'", () => {
    render(<ErrorBanner severity="warning" message="数据不完整" />);
    expect(screen.getByText("请注意")).toBeTruthy();
    expect(screen.getByText("数据不完整")).toBeTruthy();
  });

  it("title 自定义覆盖默认", () => {
    render(<ErrorBanner title="网络异常" message="..." />);
    expect(screen.getByText("网络异常")).toBeTruthy();
  });

  it("暗色模式 bg-red-500/10", () => {
    const { container } = render(<ErrorBanner message="..." dark={true} />);
    const banner = container.querySelector('[role="alert"]')!;
    expect(banner.className).toMatch(/bg-red-500/);
  });
});

describe("ErrorBanner 行为", () => {
  it("onRetry 渲染重试按钮 + 点击触发", () => {
    const onRetry = vi.fn();
    render(<ErrorBanner message="..." onRetry={onRetry} />);
    fireEvent.click(screen.getByText("重试"));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("retryPending disable + spinner 文案", () => {
    render(<ErrorBanner message="..." onRetry={() => undefined} retryPending={true} />);
    const btn = screen.getByRole("button") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    expect(btn.getAttribute("aria-busy")).toBe("true");
    expect(btn.textContent).toBe("重试中…");
  });

  it("onDismiss 渲染关闭按钮 + 点击触发", () => {
    const onDismiss = vi.fn();
    render(<ErrorBanner message="..." onDismiss={onDismiss} />);
    fireEvent.click(screen.getByLabelText("关闭"));
    expect(onDismiss).toHaveBeenCalledOnce();
  });
});

describe("ErrorBanner role", () => {
  it("默认 role=alert", () => {
    render(<ErrorBanner message="..." />);
    expect(screen.getByRole("alert")).toBeTruthy();
  });

  it("role=status 切换（success / info 类）", () => {
    render(<ErrorBanner message="..." role="status" />);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("status")).toBeTruthy();
  });

  it("data-severity 透传", () => {
    render(<ErrorBanner severity="warning" message="..." data-testid="eb" />);
    expect(screen.getByTestId("eb").getAttribute("data-severity")).toBe("warning");
  });
});
