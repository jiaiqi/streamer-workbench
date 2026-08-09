/// M3 P3 ExportLogDrawer 单元测试
///
/// 覆盖：
/// - 行可点击 → 弹抽屉（drawer-overlay + drawer 容器）
/// - 抽屉显示完整字段（类型/主题/时间/数量/输出目录/文件名/完整路径）
/// - Esc 关闭
/// - 点击遮罩关闭
/// - 「在 Finder 中显示」→ 调 streamer.revealInFinder（Electron 模式）
/// - 浏览器模式 reveal → toast.warn
/// - 复制路径 → 调 navigator.clipboard.writeText
/// - 无 fullPath 时 reveal 按钮 disabled
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ExportLogPanel from "./ExportLogPanel";
import type { ExportLogEntryResponse } from "../api/generated";

/* ---- Toast mock ---- */
const toastSuccess = vi.fn();
const toastError = vi.fn();
const toastWarn = vi.fn();
const toastInfo = vi.fn();
vi.mock("../components/Toast", () => ({
  useToast: () => ({
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
    warn: (...args: unknown[]) => toastWarn(...args),
    info: (...args: unknown[]) => toastInfo(...args),
    show: () => undefined,
    dismiss: () => undefined,
  }),
}));

/* ---- listExportLog mock ---- */
const listExportLogMock = vi.fn();
vi.mock("../api/client", () => ({
  listExportLog: (...args: unknown[]) => listExportLogMock(...args),
}));

const SAMPLE_ITEM: ExportLogEntryResponse = {
  event_id: "evt-001",
  kind: "grid-export",
  subject: "8 月歌单海报",
  filename: "playlist-20260810.png",
  output_dir: "/Users/jiaqi/data/output/grid-export",
  count: 14,
  total_ms: 1400,
  occurred_at: "2026-08-10T10:30:00Z",
  source: "test",
  title: "我的海报",
  days: 30,
  period_label: "近 30 天",
  session_id: "sess-001",
};

beforeEach(() => {
  listExportLogMock.mockReset();
  toastSuccess.mockClear();
  toastError.mockClear();
  toastWarn.mockClear();
  toastInfo.mockClear();
  listExportLogMock.mockResolvedValue({ items: [SAMPLE_ITEM] });
  // 默认无 Electron
  delete (window as { streamer?: unknown }).streamer;
});

afterEach(() => {
  cleanup();
  delete (window as { streamer?: unknown }).streamer;
});

describe("ExportLogDrawer - M3 P3", () => {
  it("点击行 → 弹抽屉（drawer-overlay + drawer 容器）", async () => {
    const user = userEvent.setup();
    render(<ExportLogPanel dark={false} limit={5} inline={false} title="导出" />);
    await waitFor(() => screen.getByTestId("export-log-panel-item"));
    await user.click(screen.getByTestId("export-log-panel-item"));
    expect(screen.getByTestId("export-log-drawer-overlay")).toBeTruthy();
    expect(screen.getByTestId("export-log-drawer")).toBeTruthy();
  });

  it("抽屉显示完整字段（类型/主题/数量/耗时）", async () => {
    const user = userEvent.setup();
    render(<ExportLogPanel dark={false} limit={5} />);
    await waitFor(() => screen.getByTestId("export-log-panel-item"));
    await user.click(screen.getByTestId("export-log-panel-item"));
    expect(screen.getByTestId("export-log-drawer-field-类型").textContent).toContain("grid-export");
    expect(screen.getByTestId("export-log-drawer-field-主题").textContent).toContain("8 月歌单海报");
    expect(screen.getByTestId("export-log-drawer-field-数量").textContent).toContain("14");
    // total_ms 1400 → "1.40 秒"
    expect(screen.getByTestId("export-log-drawer-field-耗时").textContent).toContain("1.40");
  });

  it("抽屉显示输出目录/文件名/完整路径", async () => {
    const user = userEvent.setup();
    render(<ExportLogPanel dark={false} limit={5} />);
    await waitFor(() => screen.getByTestId("export-log-panel-item"));
    await user.click(screen.getByTestId("export-log-panel-item"));
    const paths = screen.getAllByTestId("export-log-drawer-path");
    // 三个路径：output_dir, filename, fullPath
    expect(paths.length).toBe(3);
    expect(paths[0].textContent).toContain("/Users/jiaqi/data/output/grid-export");
    expect(paths[1].textContent).toContain("playlist-20260810.png");
    expect(paths[2].textContent).toContain("/Users/jiaqi/data/output/grid-export/playlist-20260810.png");
  });

  it("Esc 关闭抽屉", async () => {
    const user = userEvent.setup();
    render(<ExportLogPanel dark={false} limit={5} />);
    await waitFor(() => screen.getByTestId("export-log-panel-item"));
    await user.click(screen.getByTestId("export-log-panel-item"));
    expect(screen.getByTestId("export-log-drawer")).toBeTruthy();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByTestId("export-log-drawer")).toBeNull();
  });

  it("点击遮罩关闭抽屉", async () => {
    const user = userEvent.setup();
    render(<ExportLogPanel dark={false} limit={5} />);
    await waitFor(() => screen.getByTestId("export-log-panel-item"));
    await user.click(screen.getByTestId("export-log-panel-item"));
    fireEvent.click(screen.getByTestId("export-log-drawer-overlay"));
    expect(screen.queryByTestId("export-log-drawer")).toBeNull();
  });

  it("点 ✕ 按钮关闭抽屉", async () => {
    const user = userEvent.setup();
    render(<ExportLogPanel dark={false} limit={5} />);
    await waitFor(() => screen.getByTestId("export-log-panel-item"));
    await user.click(screen.getByTestId("export-log-panel-item"));
    await user.click(screen.getByTestId("export-log-drawer-close"));
    expect(screen.queryByTestId("export-log-drawer")).toBeNull();
  });

  it("点击 X 按钮外区域不关闭（点击内容区不触发 onClose）", async () => {
    const user = userEvent.setup();
    render(<ExportLogPanel dark={false} limit={5} />);
    await waitFor(() => screen.getByTestId("export-log-panel-item"));
    await user.click(screen.getByTestId("export-log-panel-item"));
    // 点击 drawer 内容（不是 overlay）
    const drawer = screen.getByTestId("export-log-drawer");
    fireEvent.click(drawer);
    expect(screen.getByTestId("export-log-drawer")).toBeTruthy();
  });

  it("Electron 模式：点「在 Finder 中显示」→ 调 streamer.revealInFinder", async () => {
    const revealSpy = vi.fn(async () => ({ ok: true }));
    (window as { streamer?: unknown }).streamer = { revealInFinder: revealSpy };
    const user = userEvent.setup();
    render(<ExportLogPanel dark={false} limit={5} />);
    await waitFor(() => screen.getByTestId("export-log-panel-item"));
    await user.click(screen.getByTestId("export-log-panel-item"));
    await user.click(screen.getByTestId("export-log-drawer-reveal"));
    await waitFor(() => {
      expect(revealSpy).toHaveBeenCalledWith({
        filePath: "/Users/jiaqi/data/output/grid-export/playlist-20260810.png",
      });
      expect(toastSuccess).toHaveBeenCalledWith("已在 Finder 中高亮文件");
    });
  });

  it("Electron 模式 reveal 失败 → toast.error", async () => {
    (window as { streamer?: unknown }).streamer = {
      revealInFinder: vi.fn(async () => ({ ok: false, error: "no access" })),
    };
    const user = userEvent.setup();
    render(<ExportLogPanel dark={false} limit={5} />);
    await waitFor(() => screen.getByTestId("export-log-panel-item"));
    await user.click(screen.getByTestId("export-log-panel-item"));
    await user.click(screen.getByTestId("export-log-drawer-reveal"));
    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith("Finder 定位失败：no access");
    });
  });

  it("浏览器模式（无 streamer）reveal → toast.warn", async () => {
    const user = userEvent.setup();
    render(<ExportLogPanel dark={false} limit={5} />);
    await waitFor(() => screen.getByTestId("export-log-panel-item"));
    await user.click(screen.getByTestId("export-log-panel-item"));
    await user.click(screen.getByTestId("export-log-drawer-reveal"));
    await waitFor(() => {
      expect(toastWarn).toHaveBeenCalledWith("Finder 定位仅 Electron 桌面端支持");
    });
  });

  it("点「复制路径」→ 调 navigator.clipboard.writeText + toast.success", async () => {
    const writeTextSpy = vi.fn(async () => undefined);
    // jsdom 默认有 navigator.clipboard，spy 现有 writeText
    vi.spyOn(navigator.clipboard, "writeText").mockImplementation(writeTextSpy);
    const user = userEvent.setup();
    render(<ExportLogPanel dark={false} limit={5} />);
    await waitFor(() => screen.getByTestId("export-log-panel-item"));
    await user.click(screen.getByTestId("export-log-panel-item"));
    await user.click(screen.getByTestId("export-log-drawer-copy-path"));
await waitFor(() => {
      expect(writeTextSpy).toHaveBeenCalledWith(
        "/Users/jiaqi/data/output/grid-export/playlist-20260810.png"
      );
      expect(toastSuccess).toHaveBeenCalledWith("完整路径已复制到剪贴板");
    });
  });

  it("复制失败 → toast.error", async () => {
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("denied"));
    const user = userEvent.setup();
    render(<ExportLogPanel dark={false} limit={5} />);
    await waitFor(() => screen.getByTestId("export-log-panel-item"));
    await user.click(screen.getByTestId("export-log-panel-item"));
    await user.click(screen.getByTestId("export-log-drawer-copy-path"));
    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith("复制失败：denied");
    });
  });

  it("点文件名旁的 📋 → 复制文件名（只复制 basename）", async () => {
    const writeTextSpy = vi.fn(async () => undefined);
    // jsdom 默认有 navigator.clipboard，spy 现有 writeText
    vi.spyOn(navigator.clipboard, "writeText").mockImplementation(writeTextSpy);
    const user = userEvent.setup();
    render(<ExportLogPanel dark={false} limit={5} />);
    await waitFor(() => screen.getByTestId("export-log-panel-item"));
    await user.click(screen.getByTestId("export-log-panel-item"));
    // 三个 copy button：output_dir / filename / fullPath
    const copyBtns = screen.getAllByTestId("export-log-drawer-copy-button");
    expect(copyBtns.length).toBe(3);
    // 第 2 个对应 filename
    await user.click(copyBtns[1]);
    await waitFor(() => {
      expect(writeTextSpy).toHaveBeenCalledWith("playlist-20260810.png");
      expect(toastSuccess).toHaveBeenCalledWith("文件名已复制到剪贴板");
    });
  });

  it("无 output_dir 时 reveal 按钮 disabled", async () => {
    listExportLogMock.mockResolvedValue({
      items: [{ ...SAMPLE_ITEM, output_dir: undefined, filename: undefined }],
    });
    const user = userEvent.setup();
    render(<ExportLogPanel dark={false} limit={5} />);
    await waitFor(() => screen.getByTestId("export-log-panel-item"));
    await user.click(screen.getByTestId("export-log-panel-item"));
    const reveal = screen.getByTestId("export-log-drawer-reveal") as HTMLButtonElement;
    expect(reveal.disabled).toBe(true);
  });

  it("行 hover 视觉 + cursor-pointer", async () => {
    render(<ExportLogPanel dark={false} limit={5} />);
    await waitFor(() => screen.getByTestId("export-log-panel-item"));
    const li = screen.getByTestId("export-log-panel-item") as HTMLElement;
    expect(li.className).toContain("cursor-pointer");
    // tabIndex=0 支持键盘聚焦
    expect(li.getAttribute("tabindex")).toBe("0");
  });
});
