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
    // 预存两条 pending
    localStorage.setItem("quickview-v2-pending", JSON.stringify([
      { command_id: "c1", kind: "queue", target_id: "song_x",
        payload: { song_id: "song_x" }, queued_at: 1 },
      { command_id: "c2", kind: "record", target_id: "req_a",
        payload: { request_id: "req_a", result: "sung" }, queued_at: 2 },
    ]));
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
