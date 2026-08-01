/// R4.1.1 EmptyState 单元测试。
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import EmptyState from "./EmptyState";

describe("EmptyState 基础", () => {
  it("渲染标题 + 描述", () => {
    render(<EmptyState title="暂无数据" description="先添加一些歌曲" dark={false} />);
    expect(screen.getByText("暂无数据")).toBeTruthy();
    expect(screen.getByText("先添加一些歌曲")).toBeTruthy();
  });

  it("无描述时只显示标题", () => {
    render(<EmptyState title="空" />);
    expect(screen.getByText("空")).toBeTruthy();
  });

  it("role=status 默认（友好）", () => {
    render(<EmptyState title="空" />);
    expect(screen.getByRole("status")).toBeTruthy();
  });
});

describe("EmptyState 行为按钮", () => {
  it("actionLabel + onAction 渲染主按钮", () => {
    const onAction = vi.fn();
    render(<EmptyState title="空" actionLabel="载入示例" onAction={onAction} />);
    fireEvent.click(screen.getByText("载入示例"));
    expect(onAction).toHaveBeenCalledOnce();
  });

  it("actionPending disable + spinner 文案", () => {
    render(<EmptyState title="空" actionLabel="载入" onAction={() => undefined} actionPending={true} />);
    const btn = screen.getByRole("button") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    expect(btn.getAttribute("aria-busy")).toBe("true");
    expect(btn.getAttribute("data-loading")).toBe("true");
    expect(btn.textContent).toBe("载入中…");
  });

  it("secondaryLabel + onSecondary 渲染次按钮", () => {
    const onSec = vi.fn();
    render(<EmptyState title="空" actionLabel="主" onAction={() => undefined} secondaryLabel="次" onSecondary={onSec} />);
    fireEvent.click(screen.getByText("次"));
    expect(onSec).toHaveBeenCalledOnce();
  });

  it("无回调时按钮不渲染", () => {
    render(<EmptyState title="空" actionLabel="孤立按钮" />);
    expect(screen.queryByRole("button")).toBeNull();
  });
});

describe("EmptyState 形态", () => {
  it("inline 模式不撑高", () => {
    const { container } = render(<EmptyState title="空" inline />);
    const root = container.firstElementChild as HTMLElement;
    expect(root.className).toMatch(/gap-1\.5/);
    expect(root.className).not.toMatch(/min-h-\[140px\]/);
  });

  it("dark 模式应用深色文字", () => {
    const { container } = render(<EmptyState title="空" dark={true} />);
    expect(container.firstElementChild?.className).toMatch(/text-zinc-400/);
  });

  it("data-testid 透传", () => {
    render(<EmptyState title="空" data-testid="empty-test" />);
    expect(screen.getByTestId("empty-test")).toBeTruthy();
  });
});
