/// P0-4b: useLocalBackend hook 测试。
///
/// 测试策略：
/// - mock global fetch 模拟 /api/health 返回 200 / 抛错
/// - mock navigator.onLine + online/offline 事件
/// - 验证 state 流转（checking → up / down）+ recheck 手动触发
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useLocalBackend } from "./useLocalBackend";

function mockFetchResponse(ok: boolean, body: unknown = { ok: true }) {
  return vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), {
      status: ok ? 200 : 500,
      headers: { "content-type": "application/json" },
    }),
  );
}

function mockFetchReject() {
  return vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
}

describe("useLocalBackend", () => {
  let originalFetch: typeof globalThis.fetch;
  let originalOnLine: boolean;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    originalOnLine = navigator.onLine;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    Object.defineProperty(navigator, "onLine", { value: originalOnLine, configurable: true });
  });

  it("启动后探测成功 → state=up", async () => {
    globalThis.fetch = mockFetchResponse(true) as unknown as typeof globalThis.fetch;
    const { result } = renderHook(() => useLocalBackend());
    await waitFor(() => {
      expect(result.current.state).toBe("up");
    });
    expect(result.current.isOnlineFeatures).toBe(navigator.onLine);
  });

  it("启动后探测失败 → state=down", async () => {
    globalThis.fetch = mockFetchReject() as unknown as typeof globalThis.fetch;
    const { result } = renderHook(() => useLocalBackend());
    await waitFor(() => {
      expect(result.current.state).toBe("down");
    });
  });

  it("isOnlineFeatures 同时需要 internet + localBackend up", async () => {
    Object.defineProperty(navigator, "onLine", { value: false, configurable: true });
    globalThis.fetch = mockFetchResponse(true) as unknown as typeof globalThis.fetch;
    const { result } = renderHook(() => useLocalBackend());
    await waitFor(() => {
      expect(result.current.state).toBe("up");
    });
    expect(result.current.isOnlineFeatures).toBe(false);
  });

  it("recheck() 手动触发再探测", async () => {
    const fetchMock = mockFetchResponse(true) as unknown as typeof globalThis.fetch;
    globalThis.fetch = fetchMock;
    const { result } = renderHook(() => useLocalBackend());
    await waitFor(() => {
      expect(result.current.state).toBe("up");
    });
    // 切换到失败
    globalThis.fetch = mockFetchReject() as unknown as typeof globalThis.fetch;
    await act(async () => {
      await result.current.recheck();
    });
    expect(result.current.state).toBe("down");
  });

  it("online 事件触发 isOnlineFeatures 变化", async () => {
    Object.defineProperty(navigator, "onLine", { value: false, configurable: true });
    globalThis.fetch = mockFetchResponse(true) as unknown as typeof globalThis.fetch;
    const { result } = renderHook(() => useLocalBackend());
    await waitFor(() => {
      expect(result.current.state).toBe("up");
    });
    expect(result.current.isOnlineFeatures).toBe(false);

    Object.defineProperty(navigator, "onLine", { value: true, configurable: true });
    act(() => {
      window.dispatchEvent(new Event("online"));
    });
    expect(result.current.isOnlineFeatures).toBe(true);
  });
});
