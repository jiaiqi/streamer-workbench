/// LiveView 单元测试：覆盖列表/创建/选中/快捷键核心路径。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import LiveView from "./LiveView";

vi.mock("../api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api/client")>();
  return { ...original, apiRequest: vi.fn() };
});

import { apiRequest } from "../api/client";

const emptySummary = {
  id: "s1", state: "active", title: "测试场次", rule_version: "rv1",
  started_at: "2026-07-31T08:00:00Z", closed_at: null, queue_size: 0,
};
const emptyDetail = {
  id: "s1", state: "active", title: "测试场次", rule_version: "rv1",
  started_at: "2026-07-31T08:00:00Z", closed_at: null,
  poster_id: null, notes: "", queue: [], performances: [],
};

beforeEach(() => {
  vi.mocked(apiRequest).mockReset();
});
afterEach(() => {
  vi.clearAllMocks();
  cleanup();
});

function mockEndpoint(method: string, path: RegExp, data: unknown) {
  vi.mocked(apiRequest).mockImplementationOnce(async (url, init) => {
    const m = (init?.method as string | undefined) ?? "GET";
    if (method === m && path.test(String(url))) return data as never;
    throw new Error(`unmocked ${m} ${String(url)}`);
  });
}

function mockSongsList() {
  vi.mocked(apiRequest).mockImplementation(async (url) => {
    if (String(url).endsWith("/api/songs/list")) {
      return { songs: [], active: 0, draft: 0, total: 0 } as never;
    }
    if (String(url).endsWith("/api/live-sessions")) {
      return [] as never;
    }
    throw new Error(`unmocked GET ${String(url)}`);
  });
}

describe("LiveView", () => {
  it("列表为空时显示空态提示", async () => {
    mockSongsList();
    render(<LiveView dark={false} />);
    await waitFor(() => {
      expect(screen.getByText(/还没有会话/)).toBeTruthy();
    });
  });

  it("加载会话列表后渲染卡片", async () => {
    mockEndpoint("GET", /\/api\/live-sessions$/, [emptySummary]);
    mockEndpoint("GET", /\/api\/songs\/list$/, { songs: [], active: 0, draft: 0, total: 0 });
    render(<LiveView dark={false} />);
    await waitFor(() => {
      expect(screen.getByTestId("live-session-s1")).toBeTruthy();
      expect(screen.getByText("测试场次")).toBeTruthy();
    });
  });

  it("创建按钮调用 POST /api/live-sessions", async () => {
    mockEndpoint("GET", /\/api\/live-sessions$/, []);
    mockEndpoint("GET", /\/api\/songs\/list$/, { songs: [], active: 0, draft: 0, total: 0 });
    mockEndpoint("POST", /\/api\/live-sessions$/, { ...emptySummary, id: "s_new", title: "" });
    mockEndpoint("GET", /\/api\/live-sessions\/s_new$/, { ...emptyDetail, id: "s_new" });
    render(<LiveView dark={false} />);
    await waitFor(() => screen.getByTestId("live-create"));
    fireEvent.click(screen.getByTestId("live-create"));
    await waitFor(() => {
      const calls = vi.mocked(apiRequest).mock.calls;
      const post = calls.find(c => String(c[0]) === "/api/live-sessions" && c[1]?.method === "POST");
      expect(post).toBeTruthy();
    });
  });

  it("已结束场次隐藏入队表单", async () => {
    const closed = { ...emptySummary, state: "closed", closed_at: "2026-07-31T10:00:00Z" };
    const closedDetail = { ...emptyDetail, state: "closed", closed_at: "2026-07-31T10:00:00Z" };
    mockEndpoint("GET", /\/api\/live-sessions$/, [closed]);
    mockEndpoint("GET", /\/api\/songs\/list$/, { songs: [], active: 0, draft: 0, total: 0 });
    mockEndpoint("GET", /\/api\/live-sessions\/s1$/, closedDetail);
    render(<LiveView dark={false} />);
    await waitFor(() => screen.getByTestId("live-session-s1"));
    fireEvent.click(screen.getByTestId("live-session-s1"));
    await waitFor(() => {
      expect(screen.queryByTestId("live-queue-submit")).toBeNull();
      expect(screen.getByText(/本场已结束/)).toBeTruthy();
    });
  });
});
