/// M3 P0 ExportDialog 三段式引导 + 取消 + 重试测试
///
/// 覆盖：
/// - 阶段 1 idle：开始导出 + 关闭按钮可见
/// - 阶段 2 running：进度条 + 取消按钮可见
/// - 阶段 3 done：三段式（✅ 完成反馈 / 最近 3 次导出 / 6 动作分 2 行）
/// - 阶段 4 error：错误信息 + 重试 + 关闭按钮
/// - 取消：导出中点取消 → DELETE /api/export/jobs/{id} + 轮询读到 cancelled 后 setError("已取消")
/// - 重试：error 阶段点重试 → 重新 runExport
/// - 再导一次：done 阶段点「再导一次」→ 重新 runExport
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import ExportDialog from "./ExportDialog";

const apiRequest = vi.fn();
const fetchMock = vi.fn();
const copyImageToClipboard = vi.fn();
const revealInFinder = vi.fn();
const shareToMacOS = vi.fn();
const isMacOSShareSupported = vi.fn();

vi.mock("../api/client", async () => {
  // 复用真实 ApiClientError（toRequestFailure 在错误处理路径会 instanceof 检测）
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    apiRequest: (...args: unknown[]) => apiRequest(...args),
  };
});

const toastSuccess = vi.fn();
const toastError = vi.fn();
const toastWarn = vi.fn();
const toastInfo = vi.fn();

vi.mock("./Toast", () => ({
  useToast: () => ({
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
    warn: (...args: unknown[]) => toastWarn(...args),
    info: (...args: unknown[]) => toastInfo(...args),
  }),
}));

const SAMPLE_PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47]).buffer;

const baseProps = {
  dark: false,
  onClose: vi.fn(),
  selTheme: "海洋柔光",
  page: 1,
  maxPage: 2,
  themesCount: 7,
  canvas: "抖音全屏 9:20",
  avoid: true,
  paramsQuery: "",
  lastRenderMs: 200,
  onRendered: vi.fn(),
};

beforeEach(() => {
  apiRequest.mockReset();
  fetchMock.mockReset();
  copyImageToClipboard.mockReset();
  revealInFinder.mockReset();
  shareToMacOS.mockReset();
  isMacOSShareSupported.mockReset();
  toastSuccess.mockClear();
  toastError.mockClear();
  toastWarn.mockClear();
  toastInfo.mockClear();
  baseProps.onClose.mockClear();
  baseProps.onRendered.mockClear();

  isMacOSShareSupported.mockReturnValue(true);
  copyImageToClipboard.mockResolvedValue({ ok: true });
  revealInFinder.mockResolvedValue({ ok: true });
  shareToMacOS.mockResolvedValue({ ok: true });

  // 默认：批量导出 + 成功 done
  apiRequest.mockImplementation((path: string, opts?: { method?: string }) => {
    if (path.startsWith("/api/export/batch") && opts?.method === "POST") {
      return Promise.resolve({ job_id: "test-job-1" });
    }
    if (path.startsWith("/api/export/jobs/")) {
      if (opts?.method === "DELETE") return Promise.resolve({ ok: true });
      return Promise.resolve({
        status: "done", done: 14, total: 14, current: "all",
        total_ms: 1400, output_dir: "/tmp/posters",
      });
    }
    if (path === "/api/export/open") return Promise.resolve({ ok: true });
    return Promise.resolve({});
  });

  fetchMock.mockResolvedValue({
    ok: true,
    arrayBuffer: () => Promise.resolve(SAMPLE_PNG),
  });
  global.fetch = fetchMock;
  (window as unknown as { streamer: unknown }).streamer = {
    copyImageToClipboard,
    revealInFinder,
    shareToMacOS,
    isMacOSShareSupported,
  };
});

afterEach(() => {
  cleanup();
  // @ts-expect-error
  delete global.fetch;
  (window as unknown as { streamer: unknown }).streamer = undefined;
});

describe("ExportDialog - 三段式引导（M3 P0）", () => {
  it("idle 阶段显示范围选择 + 开始导出 + 关闭", () => {
    const { getByTestId, queryByTestId } = render(
      <ExportDialog {...baseProps} open onClose={baseProps.onClose} />,
    );
    const dlg = getByTestId("export-dialog");
    expect(dlg.getAttribute("data-stage")).toBe("idle");
    expect(getByTestId("export-start")).toBeTruthy();
    expect(getByTestId("export-close-idle")).toBeTruthy();
    // 范围选择 radio 至少 3 个
    const radios = document.querySelectorAll('input[name="export-scope"]');
    expect(radios.length).toBe(3);
    // running/done/error 阶段的元素不出现
    expect(queryByTestId("export-cancel")).toBeNull();
    expect(queryByTestId("export-done-section")).toBeNull();
    expect(queryByTestId("export-error-section")).toBeNull();
  });

  it("点击「开始导出」进入 running 阶段（进度条 + 取消）", async () => {
    const { getByTestId } = render(
      <ExportDialog {...baseProps} open onClose={baseProps.onClose} />,
    );
    fireEvent.click(getByTestId("export-start"));
    // 立即进入 running（POST batch + 第一次 poll 之前）
    await waitFor(() => {
      expect(getByTestId("export-progress")).toBeTruthy();
      expect(getByTestId("export-cancel")).toBeTruthy();
    });
    // 等轮询读到 done 进入完成态
    await waitFor(() => {
      expect(getByTestId("export-done-section")).toBeTruthy();
    }, { timeout: 3000 });
  });

  it("done 阶段显示三段式（✅ 完成 / 最近 3 次 / 6 动作）", async () => {
    const { getByTestId, queryByTestId } = render(
      <ExportDialog {...baseProps} open onClose={baseProps.onClose} />,
    );
    fireEvent.click(getByTestId("export-start"));
    await waitFor(() => {
      const section = getByTestId("export-done-section");
      expect(section).toBeTruthy();
    }, { timeout: 3000 });
    // 6 动作：打开目录 / 复制 / Finder / 系统分享 / 再导一次 / 关闭
    expect(getByTestId("export-open-dir")).toBeTruthy();
    expect(getByTestId("export-copy-clipboard")).toBeTruthy();
    expect(getByTestId("export-reveal-finder")).toBeTruthy();
    expect(getByTestId("export-mac-share")).toBeTruthy();
    expect(getByTestId("export-retry-again")).toBeTruthy();
    expect(getByTestId("export-close-done")).toBeTruthy();
    // 范围选择 + 错误信息应隐藏
    expect(queryByTestId("export-start")).toBeNull();
    expect(queryByTestId("export-error-section")).toBeNull();
    // 三段式整体仍在
    expect(getByTestId("export-recent-log")).toBeTruthy();
  });

  it("done 阶段「再导一次」重新 runExport", async () => {
    const { getByTestId } = render(
      <ExportDialog {...baseProps} open onClose={baseProps.onClose} />,
    );
    fireEvent.click(getByTestId("export-start"));
    await waitFor(() => getByTestId("export-retry-again"), { timeout: 3000 });
    const batchCallCount = apiRequest.mock.calls.filter(
      c => (c[0] as string).startsWith("/api/export/batch") && (c[1] as { method?: string })?.method === "POST",
    ).length;
    fireEvent.click(getByTestId("export-retry-again"));
    await waitFor(() => {
      const newCount = apiRequest.mock.calls.filter(
        c => (c[0] as string).startsWith("/api/export/batch") && (c[1] as { method?: string })?.method === "POST",
      ).length;
      expect(newCount).toBeGreaterThan(batchCallCount);
    });
  });

  it("done 阶段「关闭」调 onClose", async () => {
    const { getByTestId } = render(
      <ExportDialog {...baseProps} open onClose={baseProps.onClose} />,
    );
    fireEvent.click(getByTestId("export-start"));
    await waitFor(() => getByTestId("export-close-done"), { timeout: 3000 });
    fireEvent.click(getByTestId("export-close-done"));
    expect(baseProps.onClose).toHaveBeenCalledTimes(1);
  });
});

describe("ExportDialog - 取消（M3 P0）", () => {
  it("导出中点「取消」→ DELETE /api/export/jobs/{id} + toast.info", async () => {
    // 第一次 poll 返回 running（done 字段 < total），后续返回 cancelled
    let pollCount = 0;
    apiRequest.mockImplementation((path: string, opts?: { method?: string }) => {
      if (path.startsWith("/api/export/batch") && opts?.method === "POST") {
        return Promise.resolve({ job_id: "test-job-2" });
      }
      if (path.startsWith("/api/export/jobs/") && opts?.method === "DELETE") {
        return Promise.resolve({ ok: true });
      }
      if (path.startsWith("/api/export/jobs/")) {
        pollCount += 1;
        if (pollCount === 1) {
          // 第一次 poll：让用户有时间点取消
          return Promise.resolve({ status: "running", done: 3, total: 14, current: "T1 p1" });
        }
        return Promise.resolve({ status: "cancelled", done: 3, total: 14, current: "cancelled" });
      }
      return Promise.resolve({});
    });
    const { getByTestId } = render(
      <ExportDialog {...baseProps} open onClose={baseProps.onClose} />,
    );
    fireEvent.click(getByTestId("export-start"));
    // 等出现取消按钮（running）
    await waitFor(() => getByTestId("export-cancel"));
    fireEvent.click(getByTestId("export-cancel"));
    // 调 DELETE
    await waitFor(() => {
      const delCalls = apiRequest.mock.calls.filter(
        c => (c[0] as string).startsWith("/api/export/jobs/") && (c[1] as { method?: string })?.method === "DELETE",
      );
      expect(delCalls.length).toBe(1);
    });
    // toast.info 应被调
    expect(toastInfo).toHaveBeenCalled();
    // 轮询读到 cancelled → error 阶段
    await waitFor(() => {
      expect(getByTestId("export-error-section")).toBeTruthy();
    }, { timeout: 3000 });
    expect(getByTestId("export-error-message").textContent).toContain("已取消");
  });

  it("导出中 Esc 不关闭（避免误操作）", async () => {
    let pollCount = 0;
    apiRequest.mockImplementation((path: string, opts?: { method?: string }) => {
      if (path.startsWith("/api/export/batch") && opts?.method === "POST") {
        return Promise.resolve({ job_id: "test-job-3" });
      }
      if (path.startsWith("/api/export/jobs/")) {
        pollCount += 1;
        if (pollCount === 1) {
          return Promise.resolve({ status: "running", done: 1, total: 14, current: "T1 p1" });
        }
        // 后续保持 running 不结束，方便验证 Esc 不关闭
        return new Promise(() => undefined);
      }
      return Promise.resolve({});
    });
    const { getByTestId } = render(
      <ExportDialog {...baseProps} open onClose={baseProps.onClose} />,
    );
    fireEvent.click(getByTestId("export-start"));
    await waitFor(() => getByTestId("export-cancel"));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(baseProps.onClose).not.toHaveBeenCalled();
  });
});

describe("ExportDialog - 错误 + 重试（M3 P0）", () => {
  it("批量导出返回 error → 错误阶段显示「重试 + 关闭」", async () => {
    apiRequest.mockImplementation((path: string) => {
      if (path.startsWith("/api/export/batch")) {
        return Promise.resolve({ job_id: "test-job-err" });
      }
      if (path.startsWith("/api/export/jobs/")) {
        return Promise.resolve({
          status: "error", done: 2, total: 14,
          current: "T1 p2", error: "渲染失败",
        });
      }
      return Promise.resolve({});
    });
    const { getByTestId } = render(
      <ExportDialog {...baseProps} open onClose={baseProps.onClose} />,
    );
    fireEvent.click(getByTestId("export-start"));
    await waitFor(() => {
      expect(getByTestId("export-error-section")).toBeTruthy();
    }, { timeout: 3000 });
    expect(getByTestId("export-error-message").textContent).toContain("渲染失败");
    expect(getByTestId("export-retry")).toBeTruthy();
    expect(getByTestId("export-close-error")).toBeTruthy();
  });

  it("错误阶段「重试」重新 runExport（不再 error 时回到 done）", async () => {
    let isFirst = true;
    apiRequest.mockImplementation((path: string) => {
      if (path.startsWith("/api/export/batch")) {
        return Promise.resolve({ job_id: isFirst ? "test-job-err" : "test-job-ok" });
      }
      if (path.startsWith("/api/export/jobs/")) {
        if (isFirst) {
          return Promise.resolve({
            status: "error", done: 0, total: 14, current: "x", error: "boom",
          });
        }
        return Promise.resolve({
          status: "done", done: 14, total: 14, current: "all",
          total_ms: 1400, output_dir: "/tmp/posters",
        });
      }
      return Promise.resolve({});
    });
    const { getByTestId } = render(
      <ExportDialog {...baseProps} open onClose={baseProps.onClose} />,
    );
    fireEvent.click(getByTestId("export-start"));
    await waitFor(() => getByTestId("export-retry"), { timeout: 3000 });
    isFirst = false;
    fireEvent.click(getByTestId("export-retry"));
    await waitFor(() => {
      expect(getByTestId("export-done-section")).toBeTruthy();
    }, { timeout: 3000 });
  });

  it("错误阶段「关闭」调 onClose", async () => {
    apiRequest.mockImplementation((path: string) => {
      if (path.startsWith("/api/export/batch")) return Promise.resolve({ job_id: "j" });
      if (path.startsWith("/api/export/jobs/")) {
        return Promise.resolve({ status: "error", done: 0, total: 14, current: "x", error: "boom" });
      }
      return Promise.resolve({});
    });
    const { getByTestId } = render(
      <ExportDialog {...baseProps} open onClose={baseProps.onClose} />,
    );
    fireEvent.click(getByTestId("export-start"));
    await waitFor(() => getByTestId("export-close-error"), { timeout: 3000 });
    fireEvent.click(getByTestId("export-close-error"));
    expect(baseProps.onClose).toHaveBeenCalledTimes(1);
  });

  it("POST batch 网络失败 → 错误阶段", async () => {
    apiRequest.mockImplementation((path: string, opts?: { method?: string }) => {
      if (path.startsWith("/api/export/batch") && opts?.method === "POST") {
        return Promise.reject(new Error("网络中断"));
      }
      return Promise.resolve({});
    });
    const { getByTestId } = render(
      <ExportDialog {...baseProps} open onClose={baseProps.onClose} />,
    );
    fireEvent.click(getByTestId("export-start"));
    await waitFor(() => {
      expect(getByTestId("export-error-section")).toBeTruthy();
    }, { timeout: 3000 });
    expect(getByTestId("export-error-message").textContent).toContain("网络中断");
  });
});
