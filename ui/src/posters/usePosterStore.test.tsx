/// usePosterStore 状态机测试。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { usePosterStore } from "./usePosterStore";

let fetchSpy: ReturnType<typeof vi.fn>;

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  fetchSpy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : (input as URL).toString();
    const method = init?.method ?? "GET";
    if (url.endsWith("/api/posters") && method === "GET") {
      return jsonResponse({ ok: true });
    }
    if (url.endsWith("/api/posters") && method === "POST") {
      return jsonResponse({
        ok: true, id: "poster_abc", revision: "rev1",
        updated_at: "2026-07-30T00:00:00+00:00",
      });
    }
    if (url.match(/\/api\/posters\/poster_/)) {
      return jsonResponse({
        id: "poster_xyz",
        name: "loaded",
        song_source: { type: "all_active", artists: [] },
        selected_song_ids: [],
        grouping: "none",
        sorting: "manual",
        layout_id: "grid-wrap",
        theme_id: "海洋柔光",
        canvas_id: "9:20",
        page_policy: { mode: "legacy-fixed-2" },
        parameters: {},
        export_settings: { format: "png", jpeg_quality: 92, single_page: false, dpi: 144 },
        revision: "rev-loaded",
        updated_at: "2026-07-30T00:00:00+00:00",
      });
    }
    return jsonResponse({});
  });
  globalThis.fetch = fetchSpy as unknown as typeof fetch;
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

const RENDER = () => {
  const { result } = renderHook(() => usePosterStore());
  return result;
};

describe("usePosterStore", () => {
  it("初始状态机为 idle", async () => {
    let r: ReturnType<typeof RENDER> | null = null;
    await act(async () => {
      r = RENDER();
      await vi.runOnlyPendingTimersAsync();
    });
    expect(r!.current.status).toBe("idle");
    expect(r!.current.revision).toBe("");
  });

  it("防抖：5 次连续 update 只触发 1 次 save", async () => {
    let r: ReturnType<typeof RENDER> | null = null;
    await act(async () => {
      r = RENDER();
      await vi.runOnlyPendingTimersAsync();
    });
    expect(r).not.toBeNull();
    act(() => {
      r!.current.update({ name: "A" });
      r!.current.update({ name: "B" });
      r!.current.update({ name: "C" });
      r!.current.update({ name: "D" });
      r!.current.update({ name: "E" });
    });
    const beforeFlush = fetchSpy.mock.calls.filter(c => (c[1] as RequestInit | undefined)?.method === "POST").length;
    expect(beforeFlush).toBe(0);

    await act(async () => {
      vi.advanceTimersByTime(800);
      await vi.runOnlyPendingTimersAsync();
    });
    const posts = fetchSpy.mock.calls.filter(c =>
      String(c[0]).endsWith("/api/posters")
      && (c[1] as RequestInit | undefined)?.method === "POST"
    );
    expect(posts.length).toBe(1);
    expect(r!.current.status).toBe("saved");
  });

  it("saveNow：跳过防抖立即保存", async () => {
    let r: ReturnType<typeof RENDER> | null = null;
    await act(async () => {
      r = RENDER();
      await vi.runOnlyPendingTimersAsync();
    });
    act(() => { r!.current.update({ name: "强制保存" }); });
    await act(async () => { await r!.current.saveNow(); });
    expect(r!.current.status).toBe("saved");
    expect(r!.current.error).toBeNull();
  });

  it("CAS 冲突：服务端 409 时进入 error 状态", async () => {
    let r: ReturnType<typeof RENDER> | null = null;
    await act(async () => {
      r = RENDER();
      await vi.runOnlyPendingTimersAsync();
    });
    fetchSpy.mockImplementationOnce((url: string, init?: RequestInit) => {
      if (String(url).endsWith("/api/posters") && (init?.method === "POST")) {
        return Promise.resolve(jsonResponse({
          error: { code: "repository_conflict", message: "stale revision" },
        }, 409));
      }
      return Promise.resolve(jsonResponse({}));
    });
    act(() => { r!.current.update({ name: "制造冲突" }); });
    await act(async () => {
      vi.advanceTimersByTime(800);
      await vi.runOnlyPendingTimersAsync();
    });
    expect(r!.current.status).toBe("error");
    expect(r!.current.error?.message).toContain("stale revision");
    expect(r!.current.isDirty).toBe(true);
  });

  it("select：flush 后加载，revision 同步切换", async () => {
    let r: ReturnType<typeof RENDER> | null = null;
    await act(async () => {
      r = RENDER();
      await vi.runOnlyPendingTimersAsync();
    });
    act(() => { r!.current.update({ name: "切换前" }); });
    await act(async () => { await r!.current.select("poster_xyz"); });
    expect(r!.current.current.name).toBe("loaded");
    expect(r!.current.revision).toBe("rev-loaded");
    expect(r!.current.status).toBe("saved");
  });
});

describe("usePosterStore 撤销/重做 (P2 R4)", () => {
  it("初始 canUndo=false / canRedo=false", async () => {
    let r: ReturnType<typeof RENDER> | null = null;
    await act(async () => {
      r = RENDER();
      await vi.runOnlyPendingTimersAsync();
    });
    expect(r!.current.canUndo).toBe(false);
    expect(r!.current.canRedo).toBe(false);
  });

  it("update 后 canUndo=true", async () => {
    let r: ReturnType<typeof RENDER> | null = null;
    await act(async () => {
      r = RENDER();
      await vi.runOnlyPendingTimersAsync();
    });
    act(() => { r!.current.update({ name: "v1" }); });
    expect(r!.current.canUndo).toBe(true);
    expect(r!.current.canRedo).toBe(false);
  });

  it("undo 恢复上一次值，redo 再回到当前", async () => {
    let r: ReturnType<typeof RENDER> | null = null;
    await act(async () => {
      r = RENDER();
      await vi.runOnlyPendingTimersAsync();
    });
    act(() => { r!.current.update({ name: "A" }); });
    act(() => { r!.current.update({ name: "B" }); });
    expect(r!.current.current.name).toBe("B");

    act(() => { r!.current.undo(); });
    expect(r!.current.current.name).toBe("A");
    expect(r!.current.canRedo).toBe(true);

    act(() => { r!.current.undo(); });
    expect(r!.current.current.name).toBe("未命名海报");
    expect(r!.current.canUndo).toBe(false);

    act(() => { r!.current.redo(); });
    expect(r!.current.current.name).toBe("A");

    act(() => { r!.current.redo(); });
    expect(r!.current.current.name).toBe("B");
    expect(r!.current.canRedo).toBe(false);
  });

  it("undo 后再 update → 清空 future (重做栈)", async () => {
    let r: ReturnType<typeof RENDER> | null = null;
    await act(async () => {
      r = RENDER();
      await vi.runOnlyPendingTimersAsync();
    });
    act(() => { r!.current.update({ name: "A" }); });
    act(() => { r!.current.update({ name: "B" }); });
    act(() => { r!.current.undo(); });
    expect(r!.current.canRedo).toBe(true);

    act(() => { r!.current.update({ name: "C" }); });
    expect(r!.current.canRedo).toBe(false);
    expect(r!.current.current.name).toBe("C");
  });

  it("newDraft 清空 past 和 future", async () => {
    let r: ReturnType<typeof RENDER> | null = null;
    await act(async () => {
      r = RENDER();
      await vi.runOnlyPendingTimersAsync();
    });
    act(() => { r!.current.update({ name: "A" }); });
    act(() => { r!.current.update({ name: "B" }); });
    expect(r!.current.canUndo).toBe(true);

    act(() => { r!.current.newDraft(); });
    expect(r!.current.canUndo).toBe(false);
    expect(r!.current.canRedo).toBe(false);
    expect(r!.current.current.name).toBe("未命名海报");
  });

  it("undo 在空栈时是 no-op", async () => {
    let r: ReturnType<typeof RENDER> | null = null;
    await act(async () => {
      r = RENDER();
      await vi.runOnlyPendingTimersAsync();
    });
    expect(r!.current.current.name).toBe("未命名海报");
    act(() => { r!.current.undo(); });
    expect(r!.current.current.name).toBe("未命名海报");
  });

  it("select 清空历史栈", async () => {
    let r: ReturnType<typeof RENDER> | null = null;
    await act(async () => {
      r = RENDER();
      await vi.runOnlyPendingTimersAsync();
    });
    act(() => { r!.current.update({ name: "A" }); });
    expect(r!.current.canUndo).toBe(true);
    await act(async () => { await r!.current.select("poster_xyz"); });
    expect(r!.current.canUndo).toBe(false);
    expect(r!.current.canRedo).toBe(false);
  });
});
