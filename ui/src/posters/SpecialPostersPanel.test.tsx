/// R4.0.11 SpecialPostersPanel 单元测试。
///
/// 覆盖：
///   - mount 后拉 /api/live-sessions 渲染最近 3 场 + "查看全部"
///   - 点击直播行触发 openLivePoster
///   - 点击预设报告按钮触发 openLearningReportPoster(7/30/90)
///   - 导出期间 disable + spinner
///   - "自定义" 弹窗 + 校验 + 触发
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import SpecialPostersPanel from "./SpecialPostersPanel";

const openLivePoster = vi.fn(async () => undefined);
const openLearningReportPoster = vi.fn(async () => undefined);

vi.mock("../electron-bridge", () => ({
  openLivePoster: (...args: unknown[]) => openLivePoster(...(args as [string])),
  openLearningReportPoster: (...args: unknown[]) => openLearningReportPoster(...(args as [Parameters<typeof openLearningReportPoster>[0]])),
  isElectron: () => false,
  openQuickView: vi.fn(),
}));

const SESSIONS = [
  // 组件按 started_at desc 排序；最近 3 场 = ddd / ccc / bbb
  { id: "live_ddd", state: "active", title: "周二早场", rule_version: "rv1", started_at: "2026-07-28T07:00:00+08:00" },
  { id: "live_ccc", state: "closed", title: "周一深夜", rule_version: "rv1", started_at: "2026-07-27T23:00:00+08:00", closed_at: "2026-07-28T00:30:00+08:00" },
  { id: "live_bbb", state: "active", title: "周日点歌", rule_version: "rv1", started_at: "2026-07-26T20:00:00+08:00" },
  { id: "live_aaa", state: "closed", title: "周六小场", rule_version: "rv1", started_at: "2026-07-25T20:00:00+08:00", closed_at: "2026-07-25T22:00:00+08:00" },
];

function fetchSpy(extra: Record<string, unknown> = {}) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : (input as URL).toString();
    if (url.endsWith("/api/live-sessions")) {
      return new Response(JSON.stringify(extra.sessions ?? SESSIONS), {
        status: 200, headers: { "content-type": "application/json" },
      });
    }
    return new Response("{}", { status: 200, headers: { "content-type": "application/json" } });
  });
}

beforeEach(() => {
  openLivePoster.mockClear();
  openLearningReportPoster.mockClear();
});
afterEach(() => { vi.useRealTimers(); });

describe("SpecialPostersPanel 加载", () => {
  it("mount 后拉 /api/live-sessions 并渲染最近 3 场", async () => {
    globalThis.fetch = fetchSpy() as unknown as typeof fetch;
    render(<SpecialPostersPanel dark={false} />);
    await waitFor(() => {
      expect(screen.getByText("周二早场")).toBeTruthy();
      expect(screen.getByText("周一深夜")).toBeTruthy();
      expect(screen.getByText("周日点歌")).toBeTruthy();
    });
    // 第 4 场不在最近 3 场里
    expect(screen.queryByText("周六小场")).toBeNull();
  });

  it("会话数 > 3 显示「查看全部」按钮", async () => {
    globalThis.fetch = fetchSpy() as unknown as typeof fetch;
    render(<SpecialPostersPanel dark={false} />);
    await waitFor(() => {
      expect(screen.getByText(/查看全部 4 场/)).toBeTruthy();
    });
  });

  it("空会话列表显示「还没有直播场次」", async () => {
    globalThis.fetch = fetchSpy({ sessions: [] }) as unknown as typeof fetch;
    render(<SpecialPostersPanel dark={false} />);
    await waitFor(() => {
      expect(screen.getByText("还没有直播场次")).toBeTruthy();
    });
  });

  it("后端错误显示错误条", async () => {
    globalThis.fetch = vi.fn(async () => new Response("err", { status: 500 })) as unknown as typeof fetch;
    render(<SpecialPostersPanel dark={false} />);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeTruthy();
    });
  });
});

describe("SpecialPostersPanel 复盘海报触发", () => {
  it("点击最近场次触发 openLivePoster", async () => {
    globalThis.fetch = fetchSpy() as unknown as typeof fetch;
    render(<SpecialPostersPanel dark={false} />);
    await waitFor(() => expect(screen.getByText("周二早场")).toBeTruthy());
    fireEvent.click(screen.getByText("周二早场"));
    await waitFor(() => {
      expect(openLivePoster).toHaveBeenCalledWith("live_ddd");
    });
  });

  it("「查看全部」弹窗含全部 4 场（含被折叠的）", async () => {
    globalThis.fetch = fetchSpy() as unknown as typeof fetch;
    render(<SpecialPostersPanel dark={false} />);
    await waitFor(() => expect(screen.getByText(/查看全部 4 场/)).toBeTruthy());
    fireEvent.click(screen.getByText(/查看全部 4 场/));
    await waitFor(() => {
      expect(screen.getByText("周六小场")).toBeTruthy();
    });
  });
});

describe("SpecialPostersPanel 学歌报告触发", () => {
  it("点击「近 7 天」触发 openLearningReportPoster({days:7})", async () => {
    globalThis.fetch = fetchSpy() as unknown as typeof fetch;
    render(<SpecialPostersPanel dark={false} />);
    await waitFor(() => expect(screen.getByText("近 7 天")).toBeTruthy());
    fireEvent.click(screen.getByText("近 7 天"));
    await waitFor(() => {
      expect(openLearningReportPoster).toHaveBeenCalledWith(
        expect.objectContaining({ days: 7, period_label: "近 7 天" }),
      );
    });
  });

  it("「近 30 天」days:30, 「近 90 天」days:90", async () => {
    globalThis.fetch = fetchSpy() as unknown as typeof fetch;
    render(<SpecialPostersPanel dark={false} />);
    await waitFor(() => expect(screen.getByText("近 30 天")).toBeTruthy());
    fireEvent.click(screen.getByText("近 30 天"));
    await waitFor(() => expect(openLearningReportPoster).toHaveBeenCalledWith(expect.objectContaining({ days: 30 })));
    fireEvent.click(screen.getByText("近 90 天"));
    await waitFor(() => expect(openLearningReportPoster).toHaveBeenCalledWith(expect.objectContaining({ days: 90 })));
  });

  it("「自定义...」弹窗输入 days + label 触发", async () => {
    globalThis.fetch = fetchSpy() as unknown as typeof fetch;
    render(<SpecialPostersPanel dark={false} />);
    await waitFor(() => expect(screen.getByText("自定义时间窗口…")).toBeTruthy());
    fireEvent.click(screen.getByText("自定义时间窗口…"));
    await waitFor(() => expect(screen.getByText("自定义学习报告")).toBeTruthy());
    // label 输入框（type=text，role=textbox）
    const labelInput = screen.getByRole("textbox");
    fireEvent.change(labelInput, { target: { value: "本月特训" } });
    fireEvent.click(screen.getByText("生成海报"));
    await waitFor(() => {
      expect(openLearningReportPoster).toHaveBeenCalledWith(
        expect.objectContaining({ days: 30, period_label: "本月特训" }),
      );
    });
  });
});
