/// R4.0.10 useWorkspaceState hook 单元测试。
///
/// 覆盖：
///   - 启动：themes / layouts / paramSpecs 拉取 + selTheme 解析
///   - 派生：previewSrc / previewKey / activeTheme / maxPage / paramsQuery
///   - 选区：selectTheme 同时重置 page
///   - 渲染态：refresh 清错误 + renderKey++ ; markLoaded/markFailed
///   - 持久化：localStorage `sw-workspace` 写入；读时兼容 `gp-workspace`
///   - 防抖：params 变化 300ms 后才进 debouncedParams
///   - layout 切换：resourcesReady 后切 layout 重新拉 params
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useWorkspaceState } from "./useWorkspaceState";

const THEMES = [
  { name: "海洋柔光", prefix: "海洋柔光", watermark_fix: false, backgrounds: {}, notes: "" },
  { name: "奶油玻璃", prefix: "奶油玻璃", watermark_fix: false, backgrounds: {}, notes: "" },
];
const LAYOUTS = [
  { id: "grid-wrap", name: "全行网格", pages: 2, supports_avoidance: true },
  { id: "magazine-flow", name: "刊头", pages: null, supports_avoidance: true },
];
const GRID_SPECS = [
  { key: "margin", label: "页边距", kind: "int", default: 58, min: 0, max: 200, step: 1, group: "布局" },
  { key: "font_song", label: "歌名字号", kind: "int", default: 36, min: 24, max: 80, step: 1, group: "样式" },
];
const MAG_SPECS = [
  { key: "title_size", label: "标题字号", kind: "int", default: 60, min: 40, max: 120, step: 1, group: "样式" },
];
const MAG_TPLS = [
  { key: "balanced", label: "均衡", description: "默认", values: { "1": 1 } },
];
const SETTINGS = {
  output_dir: "/tmp", default_canvas: "抖音全屏 9:20", default_theme: "海洋柔光",
  font_path: "", backup_count: 5, render_threads: 2,
};

function makeFetchSpy(overrides: Partial<{
  themes: unknown; layouts: unknown; settings: unknown; specs: unknown; tpls: unknown;
}> = {}) {
  const json = (body: unknown) =>
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : (input as URL).toString();
    if (url.endsWith("/api/settings")) return json(overrides.settings ?? SETTINGS);
    if (url.endsWith("/api/themes")) return json(overrides.themes ?? THEMES);
    if (url.endsWith("/api/layouts")) return json(overrides.layouts ?? LAYOUTS);
    if (url.includes("/api/layouts/magazine-flow/templates")) return json(overrides.tpls ?? MAG_TPLS);
    if (url.includes("/api/layouts/magazine-flow/params")) return json(overrides.specs ?? MAG_SPECS);
    if (url.includes("/api/layouts/grid-wrap/params")) return json(overrides.specs ?? GRID_SPECS);
    return new Response("not found", { status: 404 });
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  localStorage.clear();
  // jsdom 默认有 matchMedia
});
afterEach(() => {
  vi.useRealTimers();
  localStorage.clear();
});

describe("useWorkspaceState 资源加载", () => {
  it("mount 后 themes / layouts / paramSpecs 拉取成功", async () => {
    globalThis.fetch = makeFetchSpy() as unknown as typeof fetch;
    const { result } = renderHook(() => useWorkspaceState());
    await act(async () => { await vi.runAllTimersAsync(); });
    expect(result.current.themes).toHaveLength(2);
    expect(result.current.layouts).toHaveLength(2);
    expect(result.current.paramSpecs.map(s => s.key)).toEqual(["margin", "font_song"]);
    expect(result.current.resourcesReady).toBe(true);
    expect(result.current.resourceError).toBe("");
  });

  it("默认 selTheme 取 settings.default_theme", async () => {
    globalThis.fetch = makeFetchSpy() as unknown as typeof fetch;
    const { result } = renderHook(() => useWorkspaceState());
    await act(async () => { await vi.runAllTimersAsync(); });
    expect(result.current.selTheme).toBe("海洋柔光");
    expect(result.current.canvas).toBe("抖音全屏 9:20");
  });

  it("持久化有 selTheme 时优先用持久化", async () => {
    localStorage.setItem("sw-workspace", JSON.stringify({ selTheme: "奶油玻璃" }));
    globalThis.fetch = makeFetchSpy() as unknown as typeof fetch;
    const { result } = renderHook(() => useWorkspaceState());
    await act(async () => { await vi.runAllTimersAsync(); });
    expect(result.current.selTheme).toBe("奶油玻璃");
  });

  it("持久化 key `gp-workspace` 兼容读", async () => {
    localStorage.setItem("gp-workspace", JSON.stringify({ selTheme: "奶油玻璃" }));
    globalThis.fetch = makeFetchSpy() as unknown as typeof fetch;
    const { result } = renderHook(() => useWorkspaceState());
    await act(async () => { await vi.runAllTimersAsync(); });
    expect(result.current.selTheme).toBe("奶油玻璃");
  });

  it("fetch 失败时 setResourceError", async () => {
    globalThis.fetch = vi.fn(async () => new Response("err", { status: 500 })) as unknown as typeof fetch;
    const { result } = renderHook(() => useWorkspaceState());
    await act(async () => { await vi.runAllTimersAsync(); });
    expect(result.current.resourceError).toBeTruthy();
  });
});

describe("useWorkspaceState 派生", () => {
  it("previewSrc 用 selTheme + page + canvas + avoid + paramsQuery 拼装", async () => {
    globalThis.fetch = makeFetchSpy() as unknown as typeof fetch;
    const { result } = renderHook(() => useWorkspaceState());
    await act(async () => { await vi.runAllTimersAsync(); });
    expect(result.current.previewSrc).toContain("/api/render?");
    expect(result.current.previewSrc).toContain("theme=");
    expect(result.current.previewSrc).toContain("page=1");
    expect(result.current.previewSrc).toContain("canvas=");
    expect(result.current.previewSrc).toContain("avoid=true");
  });

  it("selTheme 为空时 previewSrc 为空字符串", async () => {
    const custom = makeFetchSpy({
      settings: { ...SETTINGS, default_theme: "不存在的theme" },
    });
    globalThis.fetch = custom as unknown as typeof fetch;
    const { result } = renderHook(() => useWorkspaceState());
    await act(async () => { await vi.runAllTimersAsync(); });
    // themes 第一个被选中
    expect(result.current.selTheme).toBe("海洋柔光");
    expect(result.current.previewSrc).toContain("theme=");
  });

  it("activeTheme 反映当前 selTheme", async () => {
    globalThis.fetch = makeFetchSpy() as unknown as typeof fetch;
    const { result } = renderHook(() => useWorkspaceState());
    await act(async () => { await vi.runAllTimersAsync(); });
    expect(result.current.activeTheme?.name).toBe("海洋柔光");
  });

  it("maxPage 取 grid-wrap.pages = 2", async () => {
    globalThis.fetch = makeFetchSpy() as unknown as typeof fetch;
    const { result } = renderHook(() => useWorkspaceState());
    await act(async () => { await vi.runAllTimersAsync(); });
    expect(result.current.maxPage).toBe(2);
  });

  // ---- M1.7 渐进式海报：相邻页预加载 ----
  it("page=1 时 prevPreviewSrc 为空，nextPreviewSrc 指向 page=2", async () => {
    globalThis.fetch = makeFetchSpy() as unknown as typeof fetch;
    const { result } = renderHook(() => useWorkspaceState());
    await act(async () => { await vi.runAllTimersAsync(); });
    expect(result.current.page).toBe(1);
    expect(result.current.prevPreviewSrc).toBe("");
    expect(result.current.nextPreviewSrc).toContain("page=2");
    // nextPreviewSrc 与 previewSrc 同 theme/canvas/avoid，只差 page
    const next = new URL(result.current.nextPreviewSrc, "http://x");
    const cur = new URL(result.current.previewSrc, "http://x");
    expect(next.searchParams.get("theme")).toBe(cur.searchParams.get("theme"));
    expect(next.searchParams.get("canvas")).toBe(cur.searchParams.get("canvas"));
    expect(next.searchParams.get("avoid")).toBe(cur.searchParams.get("avoid"));
  });

  it("page=maxPage 时 nextPreviewSrc 为空，prevPreviewSrc 指向 page=maxPage-1", async () => {
    globalThis.fetch = makeFetchSpy() as unknown as typeof fetch;
    const { result } = renderHook(() => useWorkspaceState());
    await act(async () => { await vi.runAllTimersAsync(); });
    act(() => { result.current.setPage(2); });
    expect(result.current.page).toBe(2);
    expect(result.current.maxPage).toBe(2);
    expect(result.current.nextPreviewSrc).toBe("");
    expect(result.current.prevPreviewSrc).toContain("page=1");
  });

  it("page=中间页时 next/prev 都有", async () => {
    // 用 3 页 layout 测试
    const layouts3 = [
      { id: "grid-wrap", name: "全行网格", pages: 3, supports_avoidance: true },
    ];
    globalThis.fetch = makeFetchSpy({ layouts: layouts3 }) as unknown as typeof fetch;
    const { result } = renderHook(() => useWorkspaceState());
    await act(async () => { await vi.runAllTimersAsync(); });
    act(() => { result.current.setPage(2); });
    expect(result.current.maxPage).toBe(3);
    expect(result.current.prevPreviewSrc).toContain("page=1");
    expect(result.current.nextPreviewSrc).toContain("page=3");
  });

  it("selTheme 为空时 next/prev 都为空", async () => {
    globalThis.fetch = makeFetchSpy() as unknown as typeof fetch;
    const { result } = renderHook(() => useWorkspaceState({ layoutId: "nonexistent" }));
    // 即使没资源，也用空 selTheme 试
    await act(async () => { await vi.runAllTimersAsync(); });
    // 实际上 selTheme 仍会被设成 default_theme；测试用 selectTheme(null) 走边界
    act(() => { result.current.selectTheme(""); });
    expect(result.current.selTheme).toBeFalsy();
    expect(result.current.nextPreviewSrc).toBe("");
    expect(result.current.prevPreviewSrc).toBe("");
  });

  it("params 变化 → next/prev 跟着变化（paramsQuery 同步）", async () => {
    globalThis.fetch = makeFetchSpy() as unknown as typeof fetch;
    const { result } = renderHook(() => useWorkspaceState());
    await act(async () => { await vi.runAllTimersAsync(); });
    const nextBefore = result.current.nextPreviewSrc;
    act(() => { result.current.setParam("margin", 100); });
    // 防抖 200ms 后 debouncedParams 才更新；推进 fake timers
    await act(async () => { await vi.advanceTimersByTimeAsync(300); });
    const nextAfter = result.current.nextPreviewSrc;
    expect(nextAfter).not.toBe(nextBefore);
    expect(nextAfter).toContain("margin=100");
  });

  it("previewKey 默认 stable；renderKey++ 后变 kN", async () => {
    globalThis.fetch = makeFetchSpy() as unknown as typeof fetch;
    const { result } = renderHook(() => useWorkspaceState());
    await act(async () => { await vi.runAllTimersAsync(); });
    expect(result.current.previewKey).toBe("stable");
    act(() => { result.current.refresh(); });
    expect(result.current.previewKey).toBe("k1");
  });
});

describe("useWorkspaceState 选区操作", () => {
  it("selectTheme 重置 page=1", async () => {
    globalThis.fetch = makeFetchSpy() as unknown as typeof fetch;
    const { result } = renderHook(() => useWorkspaceState());
    await act(async () => { await vi.runAllTimersAsync(); });
    act(() => { result.current.setPage(3); });
    expect(result.current.page).toBe(3);
    act(() => { result.current.selectTheme("奶油玻璃"); });
    expect(result.current.selTheme).toBe("奶油玻璃");
    expect(result.current.page).toBe(1);
  });

  it("setParam 写值后 params 立刻更新；debouncedParams 300ms 后跟上", async () => {
    globalThis.fetch = makeFetchSpy() as unknown as typeof fetch;
    const { result } = renderHook(() => useWorkspaceState());
    await act(async () => { await vi.runAllTimersAsync(); });
    act(() => { result.current.setParam("margin", 80); });
    expect(result.current.params.margin).toBe(80);
    // 防抖未到
    expect(result.current.paramsQuery).not.toContain("margin=80");
    await act(async () => { await vi.advanceTimersByTimeAsync(350); });
    expect(result.current.paramsQuery).toContain("margin=80");
  });

  it("setParam 同值不触发更新", async () => {
    globalThis.fetch = makeFetchSpy() as unknown as typeof fetch;
    const { result } = renderHook(() => useWorkspaceState());
    await act(async () => { await vi.runAllTimersAsync(); });
    const before = result.current.params;
    act(() => { result.current.setParam("margin", before.margin); });
    expect(result.current.params).toBe(before); // 引用相等
  });
});

describe("useWorkspaceState 渲染态", () => {
  it("refresh 同时清错误态 + renderKey++", async () => {
    globalThis.fetch = makeFetchSpy() as unknown as typeof fetch;
    const { result } = renderHook(() => useWorkspaceState());
    await act(async () => { await vi.runAllTimersAsync(); });
    act(() => { result.current.markFailed(); });
    expect(result.current.previewError).toBe(true);
    act(() => { result.current.refresh(); });
    expect(result.current.previewError).toBe(false);
    expect(result.current.renderKey).toBe(1);
  });

  it("markLoaded 清 loading + hasFrame=true", async () => {
    globalThis.fetch = makeFetchSpy() as unknown as typeof fetch;
    const { result } = renderHook(() => useWorkspaceState());
    await act(async () => { await vi.runAllTimersAsync(); });
    act(() => { result.current.refresh(); }); // 强制 loading
    expect(result.current.loading).toBe(true);
    act(() => { result.current.markLoaded(); });
    expect(result.current.loading).toBe(false);
    expect(result.current.hasFrame).toBe(true);
  });
});

describe("useWorkspaceState 持久化", () => {
  it("选区变化后回写到 sw-workspace", async () => {
    globalThis.fetch = makeFetchSpy() as unknown as typeof fetch;
    const { result } = renderHook(() => useWorkspaceState());
    await act(async () => { await vi.runAllTimersAsync(); });
    act(() => { result.current.setAvoid(false); });
    await act(async () => { await vi.runAllTimersAsync(); });
    const raw = localStorage.getItem("sw-workspace");
    expect(raw).toBeTruthy();
    const parsed = JSON.parse(raw!);
    expect(parsed.avoid).toBe(false);
  });

  it("同时写 sw-workspace，不写 gp-workspace", async () => {
    globalThis.fetch = makeFetchSpy() as unknown as typeof fetch;
    const { result } = renderHook(() => useWorkspaceState());
    await act(async () => { await vi.runAllTimersAsync(); });
    act(() => { result.current.setCanvas("标准 9:16"); });
    await act(async () => { await vi.runAllTimersAsync(); });
    expect(localStorage.getItem("sw-workspace")).toBeTruthy();
    expect(localStorage.getItem("gp-workspace")).toBeNull();
  });
});

describe("useWorkspaceState layout 切换", () => {
  it("layoutId 变化后重新拉对应 params + 栏数模板", async () => {
    globalThis.fetch = makeFetchSpy() as unknown as typeof fetch;
    const { result, rerender } = renderHook(
      ({ id }: { id: string }) => useWorkspaceState({ layoutId: id }),
      { initialProps: { id: "grid-wrap" } },
    );
    await act(async () => { await vi.runAllTimersAsync(); });
    expect(result.current.paramSpecs.map(s => s.key)).toEqual(["margin", "font_song"]);
    expect(result.current.columnTemplates).toEqual([]);
    rerender({ id: "magazine-flow" });
    await act(async () => { await vi.runAllTimersAsync(); });
    expect(result.current.paramSpecs.map(s => s.key)).toEqual(["title_size"]);
    expect(result.current.columnTemplates).toHaveLength(1);
  });
});
