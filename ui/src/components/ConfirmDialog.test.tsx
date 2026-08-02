/// L1.4 ConfirmDialog 测试
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render } from "@testing-library/react";
import ConfirmDialog from "./ConfirmDialog";

afterEach(() => cleanup());

describe("ConfirmDialog", () => {
  it("open=false → 不渲染", () => {
    const { queryByTestId } = render(
      <ConfirmDialog open={false} onClose={() => {}} onConfirm={() => {}} title="X" />,
    );
    expect(queryByTestId("confirm-dialog")).toBeNull();
  });

  it("open=true → 渲染 title / description / 两个按钮", () => {
    const { getByTestId, getByText } = render(
      <ConfirmDialog open={true} onClose={() => {}} onConfirm={() => {}}
        title="放弃改动？" description="关闭后已修改的内容将丢失。"
        confirmLabel="放弃" cancelLabel="再想想" />,
    );
    expect(getByTestId("confirm-dialog")).toBeTruthy();
    expect(getByTestId("confirm-dialog-title").textContent).toBe("放弃改动？");
    expect(getByTestId("confirm-dialog-description").textContent).toBe("关闭后已修改的内容将丢失。");
    expect(getByText("放弃")).toBeTruthy();
    expect(getByText("再想想")).toBeTruthy();
  });

  it("点确认按钮 → 调 onConfirm + 调 onClose", () => {
    const onConfirm = vi.fn();
    const onClose = vi.fn();
    const { getByTestId } = render(
      <ConfirmDialog open={true} onClose={onClose} onConfirm={onConfirm} title="X" />,
    );
    fireEvent.click(getByTestId("confirm-dialog-confirm"));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("点取消按钮 → 只调 onClose（不调 onConfirm）", () => {
    const onConfirm = vi.fn();
    const onClose = vi.fn();
    const { getByTestId } = render(
      <ConfirmDialog open={true} onClose={onClose} onConfirm={onConfirm} title="X" />,
    );
    fireEvent.click(getByTestId("confirm-dialog-cancel"));
    expect(onConfirm).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("confirmVariant=destructive → 确认按钮 data-variant=destructive", () => {
    const { getByTestId } = render(
      <ConfirmDialog open={true} onClose={() => {}} onConfirm={() => {}}
        title="删除？" confirmVariant="destructive" />,
    );
    expect(getByTestId("confirm-dialog-confirm").getAttribute("data-variant")).toBe("destructive");
  });

  it("confirmVariant 默认 default → 确认按钮 data-variant=default", () => {
    const { getByTestId } = render(
      <ConfirmDialog open={true} onClose={() => {}} onConfirm={() => {}} title="X" />,
    );
    expect(getByTestId("confirm-dialog-confirm").getAttribute("data-variant")).toBe("default");
  });
});
