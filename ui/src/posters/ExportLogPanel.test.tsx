/// R4.2.3 ExportLogPanel 单元测试。
///
/// 覆盖：
/// - 加载/错误/空/就绪 4 个状态
/// - 3 种 kind 标签渲染（grid-export / live-poster / learning-report）
/// - kindFilter 过滤
/// - count > 1 时显示 × N
/// - 相对时间（"刚刚" / "N 分钟前"）
/// - 标题和 "最近 N 条" 计数
///
/// 风格：使用项目现有 vitest 习惯（node.getAttribute、node.toBeTruthy），
/// 不用 jest-dom 的 toHaveAttribute。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import ExportLogPanel, { __test } from "./ExportLogPanel";
import type { ExportLogEntryResponse, ExportLogRecentResponse } from "../api/generated";

/* ---- 共享 ---- */

const listExportLog = vi.fn();

vi.mock("../api/client", () => ({
  listExportLog: (...args: unknown[]) => listExportLog(...args),
}));

function makeItem(overrides: Partial<ExportLogEntryResponse> = {}): ExportLogEntryResponse {
  const now = new Date().toISOString();
  return {
    event_id: "evt_abc",
    occurred_at: now,
    source: "export-api",
    kind: "grid-export",
    subject: "海洋柔光",
    count: 1,
    total_ms: 540,
    filename: "海洋柔光-p1.png",
    output_dir: "/tmp/out",
    session_id: "",
    title: "",
    days: 0,
    period_label: "",
    ...overrides,
  };
}

function mockRecentResponse(items: ExportLogEntryResponse[]): ExportLogRecentResponse {
  return { items };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

beforeEach(() => {
  listExportLog.mockReset();
});

/* ---- 4 个状态 ---- */

describe("ExportLogPanel - 4 个状态", () => {
  it("loading: 显示加载中文", () => {
    listExportLog.mockReturnValue(new Promise(() => {}));
    render(<ExportLogPanel dark={false} />);
    const panel = screen.getByTestId("export-log-panel");
    expect(panel.getAttribute("data-state")).toBe("loading");
    expect(screen.getByText("加载导出记录…")).toBeTruthy();
  });

  it("error: 显示错误信息 + role=alert", async () => {
    listExportLog.mockRejectedValue(new Error("服务挂了"));
    render(<ExportLogPanel dark={false} />);
    await waitFor(() => {
      expect(screen.getByTestId("export-log-panel").getAttribute("data-state")).toBe("error");
    });
    const node = screen.getByTestId("export-log-panel");
    expect(node.getAttribute("role")).toBe("alert");
    expect(node.textContent).toContain("服务挂了");
  });

  it("empty: 显示空态文案", async () => {
    listExportLog.mockResolvedValue(mockRecentResponse([]));
    render(<ExportLogPanel dark={false} />);
    await waitFor(() => {
      expect(screen.getByTestId("export-log-panel").getAttribute("data-state")).toBe("empty");
    });
    expect(screen.getByText("还没有导出记录")).toBeTruthy();
  });

  it("ready: 显示条目列表", async () => {
    listExportLog.mockResolvedValue(
      mockRecentResponse([makeItem({ subject: "海洋柔光 p1" })]));
    render(<ExportLogPanel dark={false} />);
    await waitFor(() => {
      expect(screen.getByTestId("export-log-panel").getAttribute("data-state")).toBe("ready");
    });
    expect(screen.getByText("海洋柔光 p1")).toBeTruthy();
  });
});

/* ---- 3 种 kind 渲染 ---- */

describe("ExportLogPanel - kind 渲染", () => {
  it("grid-export 显示「工作台」", async () => {
    listExportLog.mockResolvedValue(
      mockRecentResponse([makeItem({ kind: "grid-export", subject: "海洋柔光" })]));
    render(<ExportLogPanel dark={false} />);
    await waitFor(() => screen.getByTestId("export-log-panel-item"));
    const kind = within(screen.getByTestId("export-log-panel-item"))
      .getByTestId("export-log-panel-kind");
    expect(kind.textContent).toBe("工作台");
  });

  it("live-poster 显示「复盘海报」", async () => {
    listExportLog.mockResolvedValue(
      mockRecentResponse([makeItem({ kind: "live-poster", subject: "周五夜聊",
                                     source: "live-poster-api" })]));
    render(<ExportLogPanel dark={false} />);
    await waitFor(() => screen.getByTestId("export-log-panel-item"));
    const kind = within(screen.getByTestId("export-log-panel-item"))
      .getByTestId("export-log-panel-kind");
    expect(kind.textContent).toBe("复盘海报");
  });

  it("learning-report 显示「学歌报告」", async () => {
    listExportLog.mockResolvedValue(
      mockRecentResponse([makeItem({ kind: "learning-report", subject: "近 7 天",
                                     source: "learning-report-api" })]));
    render(<ExportLogPanel dark={false} />);
    await waitFor(() => screen.getByTestId("export-log-panel-item"));
    const kind = within(screen.getByTestId("export-log-panel-item"))
      .getByTestId("export-log-panel-kind");
    expect(kind.textContent).toBe("学歌报告");
  });

  it("未知 kind 标记为 other + 显示原始字符串", async () => {
    listExportLog.mockResolvedValue(
      mockRecentResponse([makeItem({ kind: "future-kind", subject: "未来类型" })]));
    render(<ExportLogPanel dark={false} />);
    await waitFor(() => screen.getByTestId("export-log-panel-item"));
    const kind = within(screen.getByTestId("export-log-panel-item"))
      .getByTestId("export-log-panel-kind");
    expect(kind.textContent).toBe("future-kind");
  });
});

/* ---- kindFilter ---- */

describe("ExportLogPanel - kindFilter", () => {
  it("kindFilter='live-poster' 只显示 live-poster", async () => {
    listExportLog.mockResolvedValue(mockRecentResponse([
      makeItem({ event_id: "evt_1", kind: "grid-export", subject: "A" }),
      makeItem({ event_id: "evt_2", kind: "live-poster", subject: "B" }),
      makeItem({ event_id: "evt_3", kind: "learning-report", subject: "C" }),
    ]));
    render(<ExportLogPanel dark={false} kindFilter="live-poster" />);
    await waitFor(() => {
      expect(screen.getAllByTestId("export-log-panel-item")).toHaveLength(1);
    });
    const items = screen.getAllByTestId("export-log-panel-item");
    expect(items[0].getAttribute("data-kind")).toBe("live-poster");
  });

  it("kindFilter='all' 显示所有", async () => {
    listExportLog.mockResolvedValue(mockRecentResponse([
      makeItem({ event_id: "evt_1", kind: "grid-export" }),
      makeItem({ event_id: "evt_2", kind: "live-poster" }),
      makeItem({ event_id: "evt_3", kind: "learning-report" }),
    ]));
    render(<ExportLogPanel dark={false} kindFilter="all" />);
    await waitFor(() => {
      expect(screen.getAllByTestId("export-log-panel-item")).toHaveLength(3);
    });
  });

  it("过滤后为空时显示空态", async () => {
    listExportLog.mockResolvedValue(mockRecentResponse([
      makeItem({ kind: "grid-export" }),
    ]));
    render(<ExportLogPanel dark={false} kindFilter="live-poster" />);
    await waitFor(() => {
      expect(screen.getByTestId("export-log-panel").getAttribute("data-state")).toBe("empty");
    });
  });
});

/* ---- count 渲染 ---- */

describe("ExportLogPanel - count", () => {
  it("count=1 不显示 × N", async () => {
    listExportLog.mockResolvedValue(
      mockRecentResponse([makeItem({ count: 1, subject: "单张" })]));
    render(<ExportLogPanel dark={false} />);
    await waitFor(() => screen.getByTestId("export-log-panel-item"));
    const item = screen.getByTestId("export-log-panel-item");
    expect(item.textContent).not.toContain("× 1");
  });

  it("count>1 显示 × N", async () => {
    listExportLog.mockResolvedValue(
      mockRecentResponse([makeItem({ count: 12, subject: "批量" })]));
    render(<ExportLogPanel dark={false} />);
    await waitFor(() => screen.getByTestId("export-log-panel-item"));
    expect(screen.getByTestId("export-log-panel-item").textContent).toContain("× 12");
  });
});

/* ---- 标题 / 计数 ---- */

describe("ExportLogPanel - 标题 / 计数", () => {
  it("默认标题「最近导出」", async () => {
    listExportLog.mockResolvedValue(
      mockRecentResponse([makeItem({ subject: "X" })]));
    render(<ExportLogPanel dark={false} />);
    await waitFor(() => screen.getByTestId("export-log-panel"));
    expect(screen.getByText("最近导出")).toBeTruthy();
  });

  it("自定义 title 生效", async () => {
    listExportLog.mockResolvedValue(mockRecentResponse([makeItem()]));
    render(<ExportLogPanel dark={false} title="上次导出的" />);
    await waitFor(() => screen.getByTestId("export-log-panel"));
    expect(screen.getByText("上次导出的")).toBeTruthy();
  });

  it("「最近 N 条」计数显示条数", async () => {
    listExportLog.mockResolvedValue(mockRecentResponse([
      makeItem({ event_id: "1" }), makeItem({ event_id: "2" }),
    ]));
    render(<ExportLogPanel dark={false} />);
    await waitFor(() => screen.getAllByTestId("export-log-panel-item"));
    expect(screen.getByText("最近 2 条")).toBeTruthy();
  });
});

/* ---- 相对时间 ---- */

describe("ExportLogPanel - 相对时间", () => {
  it("小于 30 秒显示「刚刚」", async () => {
    const recent = new Date(Date.now() - 10_000).toISOString();
    listExportLog.mockResolvedValue(
      mockRecentResponse([makeItem({ occurred_at: recent })]));
    render(<ExportLogPanel dark={false} />);
    await waitFor(() => screen.getByTestId("export-log-panel-item"));
    expect(screen.getByTestId("export-log-panel-item").textContent).toContain("刚刚");
  });

  it("5 分钟前显示「5 分钟前」", async () => {
    const recent = new Date(Date.now() - 5 * 60_000).toISOString();
    listExportLog.mockResolvedValue(
      mockRecentResponse([makeItem({ occurred_at: recent })]));
    render(<ExportLogPanel dark={false} />);
    await waitFor(() => screen.getByTestId("export-log-panel-item"));
    expect(screen.getByTestId("export-log-panel-item").textContent).toContain("5 分钟前");
  });
});

/* ---- 暗色模式 ---- */

describe("ExportLogPanel - 暗色模式", () => {
  it("dark=true 渲染时无崩溃", async () => {
    listExportLog.mockResolvedValue(mockRecentResponse([makeItem()]));
    render(<ExportLogPanel dark={true} />);
    await waitFor(() => screen.getByTestId("export-log-panel"));
    expect(screen.getByTestId("export-log-panel").outerHTML).toBeTruthy();
  });
});

/* ---- 内部工具函数 ---- */

describe("ExportLogPanel - __test helpers", () => {
  it("formatRelative: 已知字符串能解析", () => {
    const now = new Date("2026-08-01T12:00:00Z");
    expect(__test.formatRelative("2026-08-01T12:00:00Z", now)).toBe("刚刚");
    expect(__test.formatRelative("2026-08-01T11:55:00Z", now)).toBe("5 分钟前");
  });
  it("classifyKind: 3 种 kind + other", () => {
    expect(__test.classifyKind("grid-export")).toBe("grid-export");
    expect(__test.classifyKind("live-poster")).toBe("live-poster");
    expect(__test.classifyKind("learning-report")).toBe("learning-report");
    expect(__test.classifyKind("xxx")).toBe("other");
    expect(__test.classifyKind(undefined)).toBe("other");
  });
});
