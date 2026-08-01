/// R4.2 StatsView 数据反哺测试。
///
/// 覆盖：
///   - Top tab 显示「据此创建海报」按钮 + 点击触发回调
///   - Feed tab 显示「据此创建 Preset」按钮 + 点击触发回调
///   - 错误态显示 ErrorBanner
///   - 创建中 disable + spinner
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import StatsView from "./StatsView";

const TOP_RESPONSE = {
  items: [
    { song_id: "s1", title: "晴天", artists: ["周杰伦"], count: 10 },
    { song_id: "s2", title: "十年", artists: ["陈奕迅"], count: 8 },
    { song_id: "s3", title: "后来", artists: ["刘若英"], count: 6 },
  ],
};
const FEED_RESPONSE = {
  items: [
    { event_id: "e1", type: "song_request", song_id: "s1", summary: "晴天 (点歌)", occurred_at: "2026-07-30T20:00:00+08:00" },
    { event_id: "e2", type: "performance", song_id: "s1", summary: "晴天 (已唱)", occurred_at: "2026-07-30T20:30:00+08:00" },
    { event_id: "e3", type: "song_request", song_id: "s2", summary: "十年 (点歌)", occurred_at: "2026-07-30T20:31:00+08:00" },
  ],
};

function makeFetch(overrides: { top?: unknown; feed?: unknown } = {}) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : (input as URL).toString();
    const json = (body: unknown) => new Response(JSON.stringify(body), {
      status: 200, headers: { "content-type": "application/json" },
    });
    if (url.includes("/api/stats/top-songs")) return json(overrides.top ?? TOP_RESPONSE);
    if (url.includes("/api/stats/feed")) return json(overrides.feed ?? FEED_RESPONSE);
    if (url.includes("/api/stats/overview")) return json({ total_events: 0, active_songs: 0, draft_songs: 0, total_songs: 0, note: "no data" });
    if (url.includes("/api/stats/distribution")) return json({ metric: "difficulty", buckets: [], note: "no data" });
    return json({});
  });
}

beforeEach(() => { /* waitFor 兼容，不需 fakeTimers */ });
afterEach(() => { vi.restoreAllMocks(); });

describe("StatsView Top tab 数据反哺", () => {
  it("Top tab 显示「据此创建海报」按钮", async () => {
    globalThis.fetch = makeFetch() as unknown as typeof fetch;
    const onCreate = vi.fn(async () => undefined);
    render(<StatsView dark={false} onCreatePosterFromTop={onCreate} />);
    fireEvent.click(screen.getByTestId("stats-tab-top"));
    await waitFor(() => {
      expect(screen.getByTestId("top-create-poster")).toBeTruthy();
    });
    expect(screen.getByTestId("top-create-poster").textContent).toContain("据此创建海报");
    expect(screen.getByTestId("top-create-poster").textContent).toContain("3 首");
  });

  it("点击按钮触发 onCreatePosterFromTop + 传 songIds", async () => {
    globalThis.fetch = makeFetch() as unknown as typeof fetch;
    const onCreate = vi.fn(async () => undefined);
    render(<StatsView dark={false} onCreatePosterFromTop={onCreate} />);
    fireEvent.click(screen.getByTestId("stats-tab-top"));
    await waitFor(() => screen.getByTestId("top-create-poster"));
    fireEvent.click(screen.getByTestId("top-create-poster"));
    await waitFor(() => {
      expect(onCreate).toHaveBeenCalledOnce();
      const [songIds, metric] = onCreate.mock.calls[0];
      expect(songIds).toEqual(["s1", "s2", "s3"]);
      expect(metric).toBe("request");
    });
  });

  it("创建中显示 spinner + disable", async () => {
    let resolveCreate: (() => void) | null = null;
    const onCreate = vi.fn(() => new Promise<void>(r => { resolveCreate = r; }));
    globalThis.fetch = makeFetch() as unknown as typeof fetch;
    render(<StatsView dark={false} onCreatePosterFromTop={onCreate} />);
    fireEvent.click(screen.getByTestId("stats-tab-top"));
    await waitFor(() => screen.getByTestId("top-create-poster"));
    fireEvent.click(screen.getByTestId("top-create-poster"));
    await waitFor(() => {
      const btn = screen.getByTestId("top-create-poster") as HTMLButtonElement;
      expect(btn.disabled).toBe(true);
      expect(btn.textContent).toContain("创建中");
    });
    resolveCreate?.();
  });

  it("onCreatePoster 抛出错误 → ErrorBanner", async () => {
    globalThis.fetch = makeFetch() as unknown as typeof fetch;
    const onCreate = vi.fn(async () => { throw new Error("保存失败"); });
    render(<StatsView dark={false} onCreatePosterFromTop={onCreate} />);
    fireEvent.click(screen.getByTestId("stats-tab-top"));
    await waitFor(() => screen.getByTestId("top-create-poster"));
    fireEvent.click(screen.getByTestId("top-create-poster"));
    await waitFor(() => {
      expect(screen.getByText("创建海报失败")).toBeTruthy();
      expect(screen.getByText("保存失败")).toBeTruthy();
    });
  });

  it("不传回调时按钮不渲染", async () => {
    globalThis.fetch = makeFetch() as unknown as typeof fetch;
    render(<StatsView dark={false} />);
    fireEvent.click(screen.getByTestId("stats-tab-top"));
    await waitFor(() => {
      expect(screen.queryByTestId("top-create-poster")).toBeNull();
    });
  });
});

describe("StatsView Feed tab 数据反哺", () => {
  it("Feed tab 显示「据此创建 Preset」按钮", async () => {
    globalThis.fetch = makeFetch() as unknown as typeof fetch;
    const onCreate = vi.fn(async () => undefined);
    render(<StatsView dark={false} onCreatePresetFromFeed={onCreate} />);
    fireEvent.click(screen.getByTestId("stats-tab-feed"));
    await waitFor(() => {
      expect(screen.getByTestId("feed-create-preset")).toBeTruthy();
    });
  });

  it("点击 Preset 按钮触发回调 + 去重 song_ids", async () => {
    globalThis.fetch = makeFetch() as unknown as typeof fetch;
    const onCreate = vi.fn(async () => undefined);
    render(<StatsView dark={false} onCreatePresetFromFeed={onCreate} />);
    fireEvent.click(screen.getByTestId("stats-tab-feed"));
    await waitFor(() => screen.getByTestId("feed-create-preset"));
    fireEvent.click(screen.getByTestId("feed-create-preset"));
    await waitFor(() => {
      expect(onCreate).toHaveBeenCalledOnce();
      const [songIds, name] = onCreate.mock.calls[0];
      // FEED_RESPONSE 有 3 条事件：s1, s1, s2 → 去重后 [s1, s2]
      expect(songIds).toEqual(["s1", "s2"]);
      expect(name).toMatch(/^时间线 \d{4}-\d{2}-\d{2}$/);
    });
  });
});
