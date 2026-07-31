/// LiveView 单元测试：后台管理面板，验证「主播加歌」对话框 + 手动覆盖。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import LiveView from "./LiveView";

vi.mock("../api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api/client")>();
  return { ...original, apiRequest: vi.fn() };
});

import { apiRequest } from "../api/client";

const songA = {
  id: "song_a", title: "江南", artists: ["林俊杰"], key: "C", capo: null,
  status: "active", section: 2, pinyin: "jiang nan", lyricist: "", composer: "",
  difficulty: "", tabs: "", tags: [], added_at: "", notes: "", learned_at: "",
  tab_files: [],
};
const songB = {
  id: "song_b", title: "十年", artists: ["陈奕迅"], key: "G", capo: null,
  status: "active", section: 2, pinyin: "shi nian", lyricist: "", composer: "",
  difficulty: "", tabs: "", tags: [], added_at: "", notes: "", learned_at: "",
  tab_files: [],
};

const emptySummary = {
  id: "s1", state: "active", title: "测试场次", rule_version: "rv1",
  started_at: "2026-07-31T08:00:00Z", closed_at: null, queue_size: 0,
};
const emptyDetail = {
  id: "s1", state: "active", title: "测试场次", rule_version: "rv1",
  started_at: "2026-07-31T08:00:00Z", closed_at: null,
  poster_id: null, notes: "", queue: [], performances: [],
};
const closed = { ...emptySummary, state: "closed", closed_at: "2026-07-31T10:00:00Z" };
const closedDetail = { ...emptyDetail, state: "closed", closed_at: "2026-07-31T10:00:00Z" };

beforeEach(() => { vi.mocked(apiRequest).mockReset(); });
afterEach(() => { vi.clearAllMocks(); cleanup(); });

function mockEndpoint(method: string, path: RegExp, data: unknown) {
  vi.mocked(apiRequest).mockImplementationOnce(async (url, init) => {
    const m = (init?.method as string | undefined) ?? "GET";
    if (method === m && path.test(String(url))) return data as never;
    throw new Error(`unmocked ${m} ${String(url)}`);
  });
}

describe("LiveView 后台管理", () => {
  it("列表为空时显示空态提示", async () => {
    mockEndpoint("GET", /\/api\/live-sessions$/, []);
    mockEndpoint("GET", /\/api\/songs\/list$/, { songs: [], active: 0, draft: 0, total: 0 });
    render(<LiveView dark={false} />);
    await waitFor(() => {
      expect(screen.getByText(/还没有会话/)).toBeTruthy();
    });
  });

  it("加载会话列表后渲染卡片", async () => {
    mockEndpoint("GET", /\/api\/live-sessions$/, [emptySummary]);
    mockEndpoint("GET", /\/api\/songs\/list$/, { songs: [songA, songB], active: 2, draft: 0, total: 2 });
    render(<LiveView dark={false} />);
    await waitFor(() => {
      expect(screen.getByTestId("live-session-s1")).toBeTruthy();
    });
  });

  it("创建按钮调用 POST /api/live-sessions", async () => {
    mockEndpoint("GET", /\/api\/live-sessions$/, []);
    mockEndpoint("GET", /\/api\/songs\/list$/, { songs: [], active: 0, draft: 0, total: 0 });
    mockEndpoint("POST", /\/api\/live-sessions$/, { ...emptySummary, id: "s_new" });
    mockEndpoint("GET", /\/api\/live-sessions\/s_new$/, { ...emptyDetail, id: "s_new" });
    render(<LiveView dark={false} />);
    await waitFor(() => screen.getByTestId("live-create"));
    fireEvent.click(screen.getByTestId("live-create"));
    await waitFor(() => {
      const post = vi.mocked(apiRequest).mock.calls.find(c =>
        String(c[0]) === "/api/live-sessions" && c[1]?.method === "POST");
      expect(post).toBeTruthy();
    });
  });

  it("主播加歌按钮弹出曲库选歌对话框", async () => {
    mockEndpoint("GET", /\/api\/live-sessions$/, [emptySummary]);
    mockEndpoint("GET", /\/api\/songs\/list$/, { songs: [songA, songB], active: 2, draft: 0, total: 2 });
    mockEndpoint("GET", /\/api\/live-sessions\/s1$/, emptyDetail);
    render(<LiveView dark={false} />);
    await waitFor(() => screen.getByTestId("live-session-s1"));
    fireEvent.click(screen.getByTestId("live-session-s1"));
    await waitFor(() => screen.getByTestId("live-manual-pick"));
    fireEvent.click(screen.getByTestId("live-manual-pick"));
    await waitFor(() => {
      expect(screen.getByTestId("live-manual-picker")).toBeTruthy();
      expect(screen.getByText("江南")).toBeTruthy();
      expect(screen.getByText("十年")).toBeTruthy();
    });
  });

  it("从曲库选歌后以 manual 模式 POST /queue", async () => {
    mockEndpoint("GET", /\/api\/live-sessions$/, [emptySummary]);
    mockEndpoint("GET", /\/api\/songs\/list$/, { songs: [songA, songB], active: 2, draft: 0, total: 2 });
    mockEndpoint("GET", /\/api\/live-sessions\/s1$/, emptyDetail);
    render(<LiveView dark={false} />);
    await waitFor(() => screen.getByTestId("live-session-s1"));
    fireEvent.click(screen.getByTestId("live-session-s1"));
    await waitFor(() => screen.getByTestId("live-manual-pick"));
    fireEvent.click(screen.getByTestId("live-manual-pick"));
    await waitFor(() => screen.getByText("江南"));

    // 准备 queue 响应 + 后续 detail 刷新
    mockEndpoint("POST", /\/api\/live-sessions\/s1\/queue$/, {
      ok: true, request_id: "req_1", song_id: "song_a", position: 1,
      decision: { allowed: true }, duplicate_merged: false,
    });
    mockEndpoint("GET", /\/api\/live-sessions\/s1$/, {
      ...emptyDetail, queue: [{
        request_id: "req_1", song_id: "song_a", position: 1, state: "queued",
        is_bumped: false, requester_name: "主播", entitlement_kind: "manual",
        inserted_at: "2026-07-31T08:00:00Z",
      }],
    });

    fireEvent.click(screen.getByText("江南"));
    await waitFor(() => {
      const queueCall = vi.mocked(apiRequest).mock.calls.find(c =>
        /\/api\/live-sessions\/s1\/queue$/.test(String(c[0])) && c[1]?.method === "POST");
      expect(queueCall).toBeTruthy();
      const body = queueCall?.[1]?.body as { entitlement_kind?: string; song_id?: string };
      expect(body?.entitlement_kind).toBe("manual");
      expect(body?.song_id).toBe("song_a");
    });
  });

  it("已结束场次不显示主播加歌按钮", async () => {
    mockEndpoint("GET", /\/api\/live-sessions$/, [closed]);
    mockEndpoint("GET", /\/api\/songs\/list$/, { songs: [songA], active: 1, draft: 0, total: 1 });
    mockEndpoint("GET", /\/api\/live-sessions\/s1$/, closedDetail);
    render(<LiveView dark={false} />);
    await waitFor(() => screen.getByTestId("live-session-s1"));
    fireEvent.click(screen.getByTestId("live-session-s1"));
    await waitFor(() => {
      expect(screen.queryByTestId("live-manual-pick")).toBeNull();
    });
  });

  it("队列为空时显示空态", async () => {
    mockEndpoint("GET", /\/api\/live-sessions$/, [emptySummary]);
    mockEndpoint("GET", /\/api\/songs\/list$/, { songs: [], active: 0, draft: 0, total: 0 });
    mockEndpoint("GET", /\/api\/live-sessions\/s1$/, emptyDetail);
    render(<LiveView dark={false} />);
    await waitFor(() => screen.getByTestId("live-session-s1"));
    fireEvent.click(screen.getByTestId("live-session-s1"));
    await waitFor(() => {
      expect(screen.getByText("队列空")).toBeTruthy();
    });
  });
});
