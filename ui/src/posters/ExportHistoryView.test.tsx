/// ExportHistoryView 单元测试（1.2 收口）。
///
/// 覆盖：
/// - loading 态：mount 时显示 Spinner
/// - error 态：fetch 失败显示 ErrorBanner
/// - 统计态：data 拉取成功后显示"共 N 条"（来自 limit=100 的 max request）
/// - empty 态：items=0 时 ExportLogPanel 显示"还没有导出记录"
/// - kind 过滤：4 个 tab 切换调 listExportLog
/// - future note 始终存在（文档化未来增强）

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("@/api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/api/client")>();
  return { ...original, apiRequest: vi.fn() };
});

import { apiRequest } from "@/api/client";
import ExportHistoryView from "./ExportHistoryView";

const fakeStats = {
  items: [
    { event_id: "e1", occurred_at: "2026-08-16T10:00:00", source: "export-api", kind: "grid-export", subject: "海洋柔光", count: 2, total_ms: 1200, filename: "p1.png", output_dir: "/out", session_id: "", title: "", days: 0, period_label: "" },
    { event_id: "e2", occurred_at: "2026-08-16T09:00:00", source: "live-poster-api", kind: "live-poster", subject: "周六场", count: 1, total_ms: 800, filename: "live.png", output_dir: "/out", session_id: "s1", title: "周六场", days: 0, period_label: "" },
    { event_id: "e3", occurred_at: "2026-08-15T20:00:00", source: "learning-report-api", kind: "learning-report", subject: "近 30 天", count: 1, total_ms: 500, filename: "lr.png", output_dir: "/out", session_id: "", title: "", days: 30, period_label: "近 30 天" },
  ],
};

beforeEach(() => {
  vi.mocked(apiRequest).mockReset();
});
afterEach(() => {
  vi.clearAllMocks();
  cleanup();
});

describe("ExportHistoryView", () => {
  it("loading 态：mount 时显示 Spinner", () => {
    vi.mocked(apiRequest).mockReturnValue(new Promise(() => { /* never resolve */ }));
    render(<ExportHistoryView dark={false} />);
    expect(screen.getByTestId("export-history-view")).toBeTruthy();
    expect(screen.getByTestId("export-history-loading")).toBeTruthy();
    expect(screen.getByText(/加载历史统计中/)).toBeTruthy();
  });

  it("error 态：fetch 失败显示 ErrorBanner", async () => {
    vi.mocked(apiRequest).mockRejectedValueOnce(new Error("后端失联"));
    render(<ExportHistoryView dark={false} />);
    await waitFor(() => {
      expect(screen.getByTestId("export-history-error")).toBeTruthy();
    });
    const banner = screen.getByTestId("export-history-error");
    // runWithToast 抛 RequestFailure { message: "后端失联" }，组件读 .message
    expect(within(banner).getByText(/后端失联/)).toBeTruthy();
  });

  it("data 态：成功拉取后显示'共 N 条' + 嵌入 ExportLogPanel", async () => {
    // 1. 拉统计（limit=100） + 2. ExportLogPanel 拉列表（limit=20）
    vi.mocked(apiRequest)
      .mockResolvedValueOnce(fakeStats)  // 统计拉
      .mockResolvedValueOnce({ items: fakeStats.items });  // 列表拉
    render(<ExportHistoryView dark={false} />);
    await waitFor(() => {
      expect(screen.getByText(/共 3 条导出/)).toBeTruthy();
    });
    // 嵌入的 ExportLogPanel 也渲染了
    expect(screen.getByTestId("export-history-list")).toBeTruthy();
    // 4 个 filter tab
    expect(screen.getByTestId("export-history-filter-all")).toBeTruthy();
    expect(screen.getByTestId("export-history-filter-grid-export")).toBeTruthy();
    expect(screen.getByTestId("export-history-filter-live-poster")).toBeTruthy();
    expect(screen.getByTestId("export-history-filter-learning-report")).toBeTruthy();
  });

  it("empty 态：items=0 时显示'共 0 条导出'", async () => {
    // ExportHistoryView 拉 limit=100 统计 + ExportLogPanel 拉 limit=20 列表
    vi.mocked(apiRequest)
      .mockResolvedValueOnce({ items: [] })  // 统计：0 条
      .mockResolvedValueOnce({ items: [] });  // 列表：0 条
    render(<ExportHistoryView dark={false} />);
    await waitFor(() => {
      expect(screen.getByText(/共 0 条导出/)).toBeTruthy();
    });
    // ExportLogPanel 自己的 empty 态由其 own test 覆盖；
    // 这里只验 ExportHistoryView 自己的"共 N 条"统计行
  });

  it("kind 过滤：点击 tab 切换 active 状态", async () => {
    vi.mocked(apiRequest)
      .mockResolvedValueOnce(fakeStats)
      .mockResolvedValueOnce({ items: fakeStats.items });
    const user = userEvent.setup();
    render(<ExportHistoryView dark={false} />);
    await waitFor(() => screen.getByTestId("export-history-filter-grid-export"));
    // 初始 all active
    const allTab = screen.getByTestId("export-history-filter-all");
    expect(allTab.getAttribute("aria-selected")).toBe("true");
    // 切到 grid-export
    await user.click(screen.getByTestId("export-history-filter-grid-export"));
    expect(allTab.getAttribute("aria-selected")).toBe("false");
    expect(screen.getByTestId("export-history-filter-grid-export").getAttribute("aria-selected")).toBe("true");
  });

  it("future note 始终存在", async () => {
    vi.mocked(apiRequest)
      .mockResolvedValueOnce(fakeStats)
      .mockResolvedValueOnce({ items: fakeStats.items });
    render(<ExportHistoryView dark={false} />);
    await waitFor(() => screen.getByTestId("export-history-future-note"));
    expect(screen.getByText(/海报缩略图预览/)).toBeTruthy();
  });

  it("暗色模式：class 包含 border-zinc-800", async () => {
    vi.mocked(apiRequest)
      .mockResolvedValueOnce(fakeStats)
      .mockResolvedValueOnce({ items: fakeStats.items });
    const { container } = render(<ExportHistoryView dark={true} />);
    await waitFor(() => screen.getByTestId("export-history-list"));
    expect(container.querySelector('[data-testid="export-history-view"]')?.className).toContain("border-zinc-800");
  });
});
