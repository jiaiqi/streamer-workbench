/// useLiveSession hook 测试 — QuickView v2 核心状态机。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { useLiveSession } from "./useLiveSession";

vi.mock("../api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api/client")>();
  return { ...original, apiRequest: vi.fn() };
});

import { apiRequest } from "../api/client";

const sampleDetail = {
  id: "live_test",
  state: "active",
  title: "测试场次",
  rule_version: "rv1",
  started_at: "2026-07-31T08:00:00Z",
  closed_at: null,
  poster_id: null,
  notes: "",
  queue: [
    {
      request_id: "req_a", session_id: "live_test", song_id: "song_x",
      position: 1, state: "queued", is_bumped: false, original_position: null,
      bump_reason: "", bumped_at: null, requester_name: "小明",
      requester_id: null, entitlement_kind: "", inserted_at: "2026-07-31T08:00:00Z",
    },
  ],
  performances: [],
};

beforeEach(() => {
  localStorage.clear();
  vi.mocked(apiRequest).mockReset();
});
afterEach(() => {
  vi.clearAllMocks();
});

describe("useLiveSession", () => {
  it("sessionId=null 时 session=undefined (等待)", async () => {
    const { result } = renderHook(() => useLiveSession(null));
    expect(result.current.session).toBeUndefined();
  });

  it("sessionId 有效时拉取详情", async () => {
    vi.mocked(apiRequest).mockResolvedValueOnce(sampleDetail as never);
    const { result } = renderHook(() => useLiveSession("live_test"));
    await waitFor(() => {
      expect(result.current.session?.id).toBe("live_test");
      expect(result.current.isActive).toBe(true);
    });
    expect(result.current.title).toBe("测试场次");
  });

  it("网络失败时 session=null + error 文本", async () => {
    vi.mocked(apiRequest).mockRejectedValueOnce(new Error("boom"));
    const { result } = renderHook(() => useLiveSession("live_x"));
    await waitFor(() => {
      expect(result.current.session).toBeNull();
      expect(result.current.error).toContain("boom");
    });
  });

  it("queueRequest 成功调用 POST /queue 并 refresh", async () => {
    vi.mocked(apiRequest).mockResolvedValueOnce(sampleDetail as never); // refresh
    vi.mocked(apiRequest).mockResolvedValueOnce({
      ok: true, request_id: "req_new", song_id: "song_x",
      position: 2, decision: { allowed: true }, duplicate_merged: false,
    } as never); // queue
    const { result } = renderHook(() => useLiveSession("live_test"));
    await waitFor(() => expect(result.current.session).not.toBeNull());
    let res: { ok: boolean; duplicate?: boolean } = { ok: false };
    await act(async () => {
      res = await result.current.queueRequest("song_x", "阿华", "manual", null);
    });
    expect(res.ok).toBe(true);
    expect(vi.mocked(apiRequest).mock.calls.some(
      c => String(c[0]).endsWith("/queue") && c[1]?.method === "POST",
    )).toBe(true);
  });

  it("queueRequest 失败: 入 pending 队列 + 离线暂存消息", async () => {
    vi.mocked(apiRequest).mockResolvedValueOnce(sampleDetail as never); // refresh
    vi.mocked(apiRequest).mockRejectedValueOnce(new Error("网络炸了"));
    const { result } = renderHook(() => useLiveSession("live_test"));
    await waitFor(() => expect(result.current.session).not.toBeNull());
    let res = { ok: true, message: "" };
    await act(async () => {
      res = await result.current.queueRequest("song_y", "张三");
    });
    expect(res.ok).toBe(false);
    expect(res.message).toContain("离线暂存");
    expect(result.current.pendingCount).toBe(1);
    // localStorage 也应持久化
    const raw = localStorage.getItem("quickview-v2-pending");
    expect(raw).toBeTruthy();
  });

  it("recordResult 成功: 调用 POST /record 并 refresh", async () => {
    vi.mocked(apiRequest).mockResolvedValueOnce(sampleDetail as never);
    vi.mocked(apiRequest).mockResolvedValueOnce({
      ok: true, request_id: "req_a", result: "sung", refunded: false, refund_reason: "",
    } as never);
    const { result } = renderHook(() => useLiveSession("live_test"));
    await waitFor(() => expect(result.current.session).not.toBeNull());
    let res = { ok: true, refunded: false };
    await act(async () => {
      res = await result.current.recordResult("req_a", "sung");
    });
    expect(res.ok).toBe(true);
    expect(vi.mocked(apiRequest).mock.calls.some(
      c => String(c[0]).endsWith("/record") && c[1]?.method === "POST",
    )).toBe(true);
  });

  it("retryPending: 逐个重试, 成功的清出, 失败的保留", async () => {
    // mock 顺序 (FIFO):
    //   1. initial refresh → sampleDetail
    //   2. retry 中 POST /queue → ok
    //   3. retry 中 POST /record → reject
    //   4. retry 结束 refresh → sampleDetail
    // 注意 retry 中没有"第 2 次 refresh"——30s setInterval 不会在测试中触发。
    vi.mocked(apiRequest).mockResolvedValueOnce(sampleDetail as never);
    vi.mocked(apiRequest).mockResolvedValueOnce({ ok: true } as never);
    vi.mocked(apiRequest).mockRejectedValueOnce(new Error("still down"));
    vi.mocked(apiRequest).mockResolvedValueOnce(sampleDetail as never);
    // P0-5: 预存两条 pending 时必须带 session_id（新版按 session 分桶）；
    // 旧版无 session_id 的纯数组会被识别为 legacy 不参与当前 session 重放。
    localStorage.setItem("quickview-v2-pending", JSON.stringify({
      live_test: [
        { session_id: "live_test", command_id: "c1", kind: "queue", target_id: "song_x",
          payload: { song_id: "song_x" }, queued_at: 1 },
        { session_id: "live_test", command_id: "c2", kind: "record", target_id: "req_a",
          payload: { request_id: "req_a", result: "sung" }, queued_at: 2 },
      ],
    }));
    const { result } = renderHook(() => useLiveSession("live_test"));
    await waitFor(() => expect(result.current.session).not.toBeNull());
    expect(result.current.pendingCount).toBe(2);
    await act(async () => {
      await result.current.retryPending();
    });
    await waitFor(() => {
      // 1 个成功, 1 个失败保留 → pendingCount = 1
      expect(result.current.pendingCount).toBe(1);
    });
  });

  it("sessionId 切换: 触发新 refresh", async () => {
    vi.mocked(apiRequest).mockResolvedValueOnce(sampleDetail as never);
    const { result, rerender } = renderHook(
      ({ id }: { id: string }) => useLiveSession(id),
      { initialProps: { id: "live_test" } },
    );
    await waitFor(() => expect(result.current.session?.id).toBe("live_test"));
    const other = { ...sampleDetail, id: "live_other" };
    vi.mocked(apiRequest).mockResolvedValueOnce(other as never);
    rerender({ id: "live_other" });
    await waitFor(() => expect(result.current.session?.id).toBe("live_other"));
  });

  // ===== P0-5: QuickView pending 按 session 隔离 =====
  it("P0-5: 切换 session 后 pending 桶独立 — A 的命令不会被补报到 B", async () => {
    // 预存两个 session 的 pending
    localStorage.setItem("quickview-v2-pending", JSON.stringify({
      live_a: [
        { session_id: "live_a", command_id: "a1", kind: "queue", target_id: "song_a",
          payload: { song_id: "song_a" }, queued_at: 1 },
      ],
      live_b: [
        { session_id: "live_b", command_id: "b1", kind: "queue", target_id: "song_b",
          payload: { song_id: "song_b" }, queued_at: 2 },
      ],
    }));
    // 初始挂 live_a → 看到 1 条
    vi.mocked(apiRequest).mockResolvedValueOnce(sampleDetail as never);
    const { result, rerender } = renderHook(
      ({ id }: { id: string }) => useLiveSession(id),
      { initialProps: { id: "live_a" } },
    );
    await waitFor(() => expect(result.current.session?.id).toBe("live_test"));
    expect(result.current.pendingCount).toBe(1);

    // 切到 live_b → 应该看到自己桶的 1 条，不是 live_a 的
    const other = { ...sampleDetail, id: "live_b" };
    vi.mocked(apiRequest).mockResolvedValueOnce(other as never);
    rerender({ id: "live_b" });
    await waitFor(() => expect(result.current.pendingCount).toBe(1));
    // 进一步：调用 retryPending 不应该把 live_a 的命令补报到 live_b
    // 用队列断言：retry 期间只能看到对 live_b 的 POST /queue
    vi.mocked(apiRequest).mockResolvedValue({ ok: true } as never);
    await act(async () => {
      await result.current.retryPending();
    });
    // 验证整个测试期间，没有任何调用把 live_a 的命令补报到 live_b
    const calls = vi.mocked(apiRequest).mock.calls;
    const queueCalls = calls.filter(([url]) => String(url).includes("/queue"));
    for (const [url, opts] of queueCalls) {
      // 如果 URL 含 live_b，body 一定是 song_b（不是 song_a）
      if (String(url).includes("live_b")) {
        const body = (opts as { body?: { song_id?: string } })?.body;
        expect(body?.song_id).toBe("song_b");
      }
    }
  });

  it("P0-5: legacy 桶（无 session_id）不会被重放到当前 session", async () => {
    // 旧版纯数组格式 → loadStore 归到 __legacy 桶
    localStorage.setItem("quickview-v2-pending", JSON.stringify([
      { command_id: "old1", kind: "queue", target_id: "song_legacy",
        payload: { song_id: "song_legacy" }, queued_at: 1 },
    ]));
    vi.mocked(apiRequest).mockResolvedValueOnce(sampleDetail as never);
    const { result } = renderHook(() => useLiveSession("live_test"));
    await waitFor(() => expect(result.current.session).not.toBeNull());
    // legacy 不归当前 session → pendingCount=0
    expect(result.current.pendingCount).toBe(0);
    // retry 也不应该 POST /queue（legacy 不重放）
    vi.mocked(apiRequest).mockClear();
    await act(async () => {
      await result.current.retryPending();
    });
    const queueCalls = vi.mocked(apiRequest).mock.calls
      .filter(([url]) => String(url).includes("/queue"));
    expect(queueCalls).toHaveLength(0);
  });

  it("close 调 POST /close (即便失败也不抛)", async () => {
    vi.mocked(apiRequest).mockResolvedValueOnce(sampleDetail as never);
    vi.mocked(apiRequest).mockResolvedValueOnce({ ok: true } as never); // close ok
    vi.mocked(apiRequest).mockResolvedValueOnce({ ...sampleDetail, state: "closed" } as never); // refresh after close
    const { result } = renderHook(() => useLiveSession("live_test"));
    await waitFor(() => expect(result.current.session).not.toBeNull());
    await act(async () => {
      await result.current.close();
    });
    expect(vi.mocked(apiRequest).mock.calls.some(
      c => String(c[0]).endsWith("/close") && c[1]?.method === "POST",
    )).toBe(true);
  });
});
