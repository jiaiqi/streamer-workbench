/// L1.4 SongEditDialog 草稿保护测试
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import SongEditDialog from "./SongEditDialog";
import { makeSong } from "../test-fixtures";

const apiRequest = vi.fn();
vi.mock("../api/client", () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
}));

const SAMPLE = makeSong();

/** shadcn Dialog 用 portal 渲染到 body 末尾，querySelector 必须用 document 不能用 container */
function getTitleInput() {
  return document.querySelector("#song-title") as HTMLInputElement | null;
}

beforeEach(() => {
  apiRequest.mockReset();
  apiRequest.mockResolvedValue({});
});
afterEach(() => cleanup());

describe("SongEditDialog - 草稿保护（L1.4）", () => {
  it("初始无改动 → 关闭按钮直接 onClose（不弹确认）", () => {
    const onClose = vi.fn();
    const { getByText } = render(
      <SongEditDialog target={SAMPLE} onClose={onClose} onSaved={async () => {}} />,
    );
    fireEvent.click(getByText("取消"));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(document.querySelector('[data-testid="confirm-dialog"]')).toBeNull();
  });

  it("编辑表单后点取消 → 弹确认对话框（destructive 变体）", async () => {
    const onClose = vi.fn();
    const { getByText } = render(
      <SongEditDialog target={SAMPLE} onClose={onClose} onSaved={async () => {}} />,
    );
    await waitFor(() => expect(getTitleInput()).toBeTruthy());
    const titleInput = getTitleInput()!;
    expect(titleInput.value).toBe("江南");
    fireEvent.change(titleInput, { target: { value: "江南（修改）" } });
    expect(getTitleInput()!.value).toBe("江南（修改）");
    fireEvent.click(getByText("取消"));
    await waitFor(() => {
      expect(document.querySelector('[data-testid="confirm-dialog"]')).toBeTruthy();
      expect(document.querySelector('[data-testid="confirm-dialog-title"]')?.textContent).toBe("放弃未保存的改动？");
      expect(document.querySelector('[data-testid="confirm-dialog-confirm"]')?.getAttribute("data-variant")).toBe("destructive");
    });
    expect(onClose).not.toHaveBeenCalled();
  });

  it("改完后点「再想想」/「取消」→ 留在表单不关", async () => {
    const onClose = vi.fn();
    const { getByText } = render(
      <SongEditDialog target={SAMPLE} onClose={onClose} onSaved={async () => {}} />,
    );
    await waitFor(() => expect(getTitleInput()).toBeTruthy());
    fireEvent.change(getTitleInput()!, { target: { value: "X" } });
    fireEvent.click(getByText("取消"));
    await waitFor(() => {
      expect(document.querySelector('[data-testid="confirm-dialog"]')).toBeTruthy();
    });
    const confirmCancel = document.querySelector('[data-testid="confirm-dialog-cancel"]') as HTMLElement;
    fireEvent.click(confirmCancel);
    await waitFor(() => {
      expect(document.querySelector('[data-testid="confirm-dialog"]')).toBeNull();
    });
    expect(onClose).not.toHaveBeenCalled();
    expect(getTitleInput()!.value).toBe("X");
  });

  it("改完后点「放弃改动」→ 调 onClose（discard）", async () => {
    const onClose = vi.fn();
    const { getByText } = render(
      <SongEditDialog target={SAMPLE} onClose={onClose} onSaved={async () => {}} />,
    );
    await waitFor(() => expect(getTitleInput()).toBeTruthy());
    fireEvent.change(getTitleInput()!, { target: { value: "X" } });
    fireEvent.click(getByText("取消"));
    await waitFor(() => {
      expect(document.querySelector('[data-testid="confirm-dialog"]')).toBeTruthy();
    });
    fireEvent.click(document.querySelector('[data-testid="confirm-dialog-confirm"]')!);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("保存成功后直接 onClose（dirty 已变 true 也要让走）", async () => {
    const onClose = vi.fn();
    const onSaved = vi.fn().mockResolvedValue(undefined);
    apiRequest.mockResolvedValueOnce({ ok: true });
    const { getByText } = render(
      <SongEditDialog target={SAMPLE} onClose={onClose} onSaved={onSaved} />,
    );
    await waitFor(() => expect(getTitleInput()).toBeTruthy());
    fireEvent.change(getTitleInput()!, { target: { value: "新江南" } });
    fireEvent.click(getByText("保存"));
    await waitFor(() => {
      expect(onClose).toHaveBeenCalledTimes(1);
      expect(onSaved).toHaveBeenCalledTimes(1);
    });
    expect(document.querySelector('[data-testid="confirm-dialog"]')).toBeNull();
  });
});
