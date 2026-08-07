/// M2.16 ExportDialog 分享按钮测试
///
/// 覆盖：
/// - 导出完成后显示「复制到剪贴板 / Finder 中显示 / 系统分享」三个按钮
/// - 非 macOS 平台下「系统分享」按钮 disabled
/// - macOS 平台下三个按钮全部可用
/// - 点击「复制到剪贴板」调 streamer.copyImageToClipboard 并成功 toast
/// - 点击「系统分享」调 streamer.shareToMacOS，unsupported 时弹 warn toast
/// - fetch /api/render 失败时所有分享按钮 disabled
/// - 浏览器模式（无 window.streamer）按钮不抛错
/// - 打开 dialog 时拉一次 /api/render，关闭或 selTheme/page 变化时重拉
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

const SAMPLE_PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47]).buffer; // PNG header
const SAMPLE_DONE = { count: 1, totalMs: 500, outputDir: "/tmp/posters" };

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

  // 默认 macOS 平台 + fetch 返回 sample png
  isMacOSShareSupported.mockReturnValue(true);
  copyImageToClipboard.mockResolvedValue({ ok: true });
  revealInFinder.mockResolvedValue({ ok: true });
  shareToMacOS.mockResolvedValue({ ok: true });

  // 模拟单页导出 API（POST /api/export?theme=...&page=...&canvas=...&avoid=...）
  // + 批量导出 batch + jobs poll
  apiRequest.mockImplementation((path: string, opts?: { method?: string }) => {
    if (path.startsWith("/api/export/batch") && opts?.method === "POST") {
      return Promise.resolve({ job_id: "test-job-1" });
    }
    if (path.startsWith("/api/export/jobs/")) {
      return Promise.resolve({
        status: "done",
        done: 14,            // themesCount(7) * maxPage(2) = 14
        total: 14,
        current: "all",
        total_ms: 1400,
        output_dir: "/tmp/posters",
      });
    }
    if (path.startsWith("/api/export?") || path.startsWith("/api/export/batch")) {
      return Promise.resolve({ duration_ms: 100 });
    }
    if (path === "/api/export/open") return Promise.resolve({ ok: true });
    return Promise.resolve({});
  });

  fetchMock.mockResolvedValue({
    ok: true,
    arrayBuffer: () => Promise.resolve(SAMPLE_PNG),
  });
  // 安装到 window.fetch
  // @ts-expect-error
  global.fetch = fetchMock;

  // 装 streamer
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

const baseProps = {
  dark: false,
  onClose: () => {},
  selTheme: "海洋柔光",
  page: 1,
  maxPage: 2,
  themesCount: 7,
  canvas: "抖音全屏 9:20",
  avoid: true,
  paramsQuery: "",
  lastRenderMs: 200,
  onRendered: () => {},
};

describe("ExportDialog - 分享按钮（M2.16）", () => {
  it("done 后显示三个分享按钮", async () => {
    const { getByTestId } = render(
      <ExportDialog {...baseProps} open onClose={() => {}} />,
    );
    fireEvent.click(document.querySelector("button.primary-action")!);
    // 等待 done 状态显示（poll 300ms + setState）
    await waitFor(() => {
      expect(getByTestId("export-copy-clipboard")).toBeTruthy();
      expect(getByTestId("export-reveal-finder")).toBeTruthy();
      expect(getByTestId("export-mac-share")).toBeTruthy();
    }, { timeout: 3000 });
  });

  it("非 macOS 平台下「系统分享」按钮 disabled", async () => {
    isMacOSShareSupported.mockReturnValue(false);
    const { getByTestId } = render(
      <ExportDialog {...baseProps} open onClose={() => {}} />,
    );
    fireEvent.click(document.querySelector("button.primary-action")!);
    // 等到复制按钮 enabled（说明 PNG 加载完成、sharePngLoading=false）
    await waitFor(() => {
      expect((getByTestId("export-copy-clipboard") as HTMLButtonElement).disabled).toBe(false);
    }, { timeout: 2000 });
    const macBtn = getByTestId("export-mac-share") as HTMLButtonElement;
    expect(macBtn.disabled).toBe(true);
    // 复制和 finder 跨平台可用
    expect((getByTestId("export-copy-clipboard") as HTMLButtonElement).disabled).toBe(false);
    expect((getByTestId("export-reveal-finder") as HTMLButtonElement).disabled).toBe(false);
  });

  it("点击「复制到剪贴板」调 streamer.copyImageToClipboard", async () => {
    const { getByTestId } = render(
      <ExportDialog {...baseProps} open onClose={() => {}} />,
    );
    fireEvent.click(document.querySelector("button.primary-action")!);
    await waitFor(() => expect(getByTestId("export-copy-clipboard")).toBeTruthy());
    // 等待 fetch /api/render 完成（sharePng 落地、sharePngLoading 变 false）
    await waitFor(() => {
      const btn = getByTestId("export-copy-clipboard") as HTMLButtonElement;
      expect(btn.disabled).toBe(false);
    }, { timeout: 2000 });
    fireEvent.click(getByTestId("export-copy-clipboard"));
    await waitFor(() => {
      expect(copyImageToClipboard).toHaveBeenCalledTimes(1);
      const arg = copyImageToClipboard.mock.calls[0][0];
      expect(arg.data).toBeInstanceOf(ArrayBuffer);
      expect(arg.data.byteLength).toBe(SAMPLE_PNG.byteLength);
    });
  });

  it("复制失败时调用方收到错误（不抛错）", async () => {
    copyImageToClipboard.mockResolvedValue({ ok: false, error: "权限被拒" });
    const { getByTestId } = render(
      <ExportDialog {...baseProps} open onClose={() => {}} />,
    );
    fireEvent.click(document.querySelector("button.primary-action")!);
    // 等 PNG 加载完
    await waitFor(() => {
      expect((getByTestId("export-copy-clipboard") as HTMLButtonElement).disabled).toBe(false);
    }, { timeout: 2000 });
    expect(() => {
      fireEvent.click(getByTestId("export-copy-clipboard"));
    }).not.toThrow();
    // 等 handler 的 await + setSharePending(null) 完成 → 按钮重新 enabled
    await waitFor(() => expect(toastError).toHaveBeenCalled());
  });

  it("点击「系统分享」调 streamer.shareToMacOS 并传 defaultName", async () => {
    const { getByTestId } = render(
      <ExportDialog {...baseProps} open onClose={() => {}} />,
    );
    fireEvent.click(document.querySelector("button.primary-action")!);
    await waitFor(() => {
      expect((getByTestId("export-mac-share") as HTMLButtonElement).disabled).toBe(false);
    }, { timeout: 2000 });
    fireEvent.click(getByTestId("export-mac-share"));
    await waitFor(() => {
      expect(shareToMacOS).toHaveBeenCalledTimes(1);
      const arg = shareToMacOS.mock.calls[0][0];
      expect(arg.data).toBeInstanceOf(ArrayBuffer);
      expect(arg.defaultName).toMatch(/海洋柔光.*9_20.*p1\.png/);
    });
  });

  it("非 macOS 平台点击被阻止（disabled）", async () => {
    isMacOSShareSupported.mockReturnValue(false);
    const { getByTestId } = render(
      <ExportDialog {...baseProps} open onClose={() => {}} />,
    );
    fireEvent.click(document.querySelector("button.primary-action")!);
    await waitFor(() => expect(getByTestId("export-mac-share")).toBeTruthy());
    fireEvent.click(getByTestId("export-mac-share"));
    expect(shareToMacOS).not.toHaveBeenCalled();
  });

  it("shareToMacOS 返回 unsupported → 不抛错（warn toast 处理）", async () => {
    shareToMacOS.mockResolvedValue({ ok: false, code: "unsupported" });
    isMacOSShareSupported.mockReturnValue(true);
    const { getByTestId } = render(
      <ExportDialog {...baseProps} open onClose={() => {}} />,
    );
    fireEvent.click(document.querySelector("button.primary-action")!);
    await waitFor(() => {
      expect((getByTestId("export-mac-share") as HTMLButtonElement).disabled).toBe(false);
    }, { timeout: 2000 });
    fireEvent.click(getByTestId("export-mac-share"));
    await waitFor(() => expect(toastWarn).toHaveBeenCalled());
  });

  it("fetch /api/render 失败时复制按钮 disabled（降级）", async () => {
    fetchMock.mockResolvedValue({ ok: false, arrayBuffer: () => Promise.reject(new Error("boom")) });
    const { getByTestId } = render(
      <ExportDialog {...baseProps} open onClose={() => {}} />,
    );
    fireEvent.click(document.querySelector("button.primary-action")!);
    await waitFor(() => expect(getByTestId("export-copy-clipboard")).toBeTruthy());
    await waitFor(() => {
      expect((getByTestId("export-copy-clipboard") as HTMLButtonElement).disabled).toBe(true);
      expect((getByTestId("export-mac-share") as HTMLButtonElement).disabled).toBe(true);
    });
  });

  it("浏览器模式（无 window.streamer）按钮 enabled 但 click no-op", async () => {
    (window as unknown as { streamer: unknown }).streamer = undefined;
    const { getByTestId } = render(
      <ExportDialog {...baseProps} open onClose={() => {}} />,
    );
    fireEvent.click(document.querySelector("button.primary-action")!);
    await waitFor(() => expect(getByTestId("export-copy-clipboard")).toBeTruthy());
    // 浏览器模式：按钮不抛错，handler 内部 if (!window.streamer?.copyImageToClipboard) return
    expect(() => {
      fireEvent.click(getByTestId("export-copy-clipboard"));
      fireEvent.click(getByTestId("export-reveal-finder"));
    }).not.toThrow();
  });

  it("打开时拉 /api/render 拿 PNG bytes", async () => {
    render(<ExportDialog {...baseProps} open onClose={() => {}} />);
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
      const url = fetchMock.mock.calls[0][0] as string;
      // URL 会被 encodeURIComponent：海洋柔光 → %E6%B5%B7%E6%B4%8B%E6%9F%94%E5%85%89
      expect(url).toMatch(/^\/api\/render\?theme=%E6%B5%B7%E6%B4%8B/);
      expect(url).toMatch(/[?&]page=1\b/);
      expect(url).toMatch(/[?&]canvas=/);
    });
  });

  it("selTheme 变化时重新拉 PNG", async () => {
    const { rerender } = render(<ExportDialog {...baseProps} open onClose={() => {}} selTheme="海洋柔光" />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    rerender(<ExportDialog {...baseProps} open onClose={() => {}} selTheme="月夜星河" />);
    await waitFor(() => {
      const urls = fetchMock.mock.calls.map((c) => c[0] as string);
      // 月夜星河 → %E6%9C%88%E5%A4%9C%E6%98%9F%E6%B2%B3
      expect(urls.some((u) => u.includes("%E6%9C%88%E5%A4%9C%E6%98%9F%E6%B2%B3"))).toBe(true);
    });
  });
});

// 内部用 getByRole helper（避免 import testing-library 顶部过大）
function getByRole(_role: string, _opts: { name: RegExp }): HTMLElement {
  // 直接用 querySelector 走 fallback
  return _opts.name.test(/开始导出/)
    ? (Array.from(document.querySelectorAll("button")).find((b) => /开始导出/.test(b.textContent || "")) as HTMLElement)
    : (Array.from(document.querySelectorAll("button")).find((b) => _opts.name.test(b.textContent || "")) as HTMLElement);
}
