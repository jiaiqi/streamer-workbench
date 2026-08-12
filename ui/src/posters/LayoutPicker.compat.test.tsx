/// R4 Runtime v2 v2.5: LayoutPicker 兼容性警告 UI 测试。
///
/// 覆盖：
/// - 兼容时不显示警告
/// - 不兼容时显示警告
/// - 无 currentThemeId 时不拉 matrix
/// - matrix API 失败时静默不阻挡
/// - 切换 layout 不清掉警告（警告由 theme + layout 联合决定）
/// - API 客户端函数：checkCompatibility / getCompatibilityMatrix 等
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import LayoutPicker from "./LayoutPicker";
import type { PosterStore } from "./usePosterStore";

function makeStore(): PosterStore {
  return {
    current: {
      id: "p1",
      name: "测试海报",
      theme_id: "海洋柔光",
      layout_id: "grid-wrap" as const,
      page_policy: { mode: "legacy-fixed-2" as const },
      parameters: {},
      song_source: { kind: "all" },
      canvas_id: "9:16",
      created_at: "2026-01-01T00:00:00",
      updated_at: "2026-01-01T00:00:00",
    },
    status: "idle" as const,
    isDirty: false,
    canUndo: false,
    canRedo: false,
    lastSavedAt: null,
    error: null,
    posters: [],
    newDraft: vi.fn(),
    select: vi.fn(async () => {}),
    update: vi.fn(),
    rename: vi.fn(async () => {}),
    duplicate: vi.fn(),
    deleteCurrent: vi.fn(async () => {}),
    saveNow: vi.fn(),
    flush: vi.fn(async () => {}),
    undo: vi.fn(),
    redo: vi.fn(),
    refreshList: vi.fn(),
    batch: vi.fn(),
  } as unknown as PosterStore;
}

const COMPAT_MATRIX = {
  layouts: ["grid-wrap", "magazine-flow"],
  themes: ["海洋柔光", "月夜星河"],
  matrix: {
    "grid-wrap": {
      "海洋柔光": { compatible: true, reason: "" },
      "月夜星河": { compatible: false, reason: "layout「grid-wrap」声明不兼容 theme「月夜星河」" },
    },
    "magazine-flow": {
      "海洋柔光": { compatible: true, reason: "" },
      "月夜星河": { compatible: true, reason: "" },
    },
  },
};

describe("LayoutPicker 兼容性警告", () => {
  beforeEach(() => {
    global.fetch = vi.fn();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("兼容时（grid-wrap + 海洋柔光）不显示警告", async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: true, status: 200, headers: { get: (k: string) => k === "content-type" ? "application/json" : "" }, json: async () => COMPAT_MATRIX, headers: { get: (k: string) => k === "content-type" ? "application/json" : "" },
    });
    const store = makeStore();
    render(<LayoutPicker store={store} currentThemeId="海洋柔光" />);
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalled();
    });
    expect(screen.queryByTestId("layout-compat-warning")).toBeNull();
  });

  it("不兼容时（grid-wrap + 月夜星河）显示警告", async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: true, status: 200, json: async () => COMPAT_MATRIX, headers: { get: (k: string) => k === "content-type" ? "application/json" : "" },
    });
    const store = makeStore();
    render(<LayoutPicker store={store} currentThemeId="月夜星河" />);
    await waitFor(() => {
      expect(screen.getByTestId("layout-compat-warning")).toBeTruthy();
    });
    expect(screen.getByTestId("layout-compat-warning").textContent).toMatch(/不兼容/);
  });

  it("无 currentThemeId 时不拉 matrix 也不显示警告", async () => {
    const store = makeStore();
    render(<LayoutPicker store={store} />);
    // 等待一下
    await new Promise(r => setTimeout(r, 50));
    expect(global.fetch).not.toHaveBeenCalled();
    expect(screen.queryByTestId("layout-compat-warning")).toBeNull();
  });

  it("matrix API 失败时静默不阻挡 layout 渲染", async () => {
    (global.fetch as any).mockRejectedValueOnce(new Error("network down"));
    const store = makeStore();
    render(<LayoutPicker store={store} currentThemeId="月夜星河" />);
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalled();
    });
    // 警告不显示（matrix 拉取失败）
    expect(screen.queryByTestId("layout-compat-warning")).toBeNull();
    // 但 layout 选项仍可点击
    expect(screen.getByTestId("layout-opt-grid-wrap")).toBeTruthy();
    expect(screen.getByTestId("layout-opt-magazine-flow")).toBeTruthy();
  });

  it("切换 layout（grid-wrap → magazine-flow）不改变警告显示逻辑（theme 仍是月夜星河）", async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: true, status: 200, json: async () => COMPAT_MATRIX, headers: { get: (k: string) => k === "content-type" ? "application/json" : "" },
    });
    const store = makeStore();
    const { rerender } = render(
      <LayoutPicker store={store} currentThemeId="月夜星河" />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("layout-compat-warning")).toBeTruthy();
    });
    // 模拟切换到 magazine-flow（仍月夜星河，magazine-flow 兼容月夜星河）
    store.current.layout_id = "magazine-flow";
    rerender(<LayoutPicker store={store} currentThemeId="月夜星河" />);
    expect(screen.queryByTestId("layout-compat-warning")).toBeNull();
  });
});


describe("R4 v2.5 client API", () => {
  beforeEach(() => {
    global.fetch = vi.fn();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("checkCompatibility 调 /api/compatibility 并传 query", async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: true, status: 200, json: async () => ({ compatible: true, reason: "" }), headers: { get: (k: string) => k === "content-type" ? "application/json" : "" },
    });
    const { checkCompatibility } = await import("@/api/posters");
    const result = await checkCompatibility("grid-wrap", "月夜星河");
    expect(result.compatible).toBe(true);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/compatibility?"),
      expect.any(Object),
    );
    const url = (global.fetch as any).mock.calls[0][0];
    expect(url).toContain("layout_id=grid-wrap");
    expect(url).toContain("theme_id=");
  });

  it("getCompatibilityMatrix 调 /api/compatibility/matrix", async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: true, status: 200, json: async () => COMPAT_MATRIX, headers: { get: (k: string) => k === "content-type" ? "application/json" : "" },
    });
    const { getCompatibilityMatrix } = await import("@/api/posters");
    const result = await getCompatibilityMatrix();
    expect(result.layouts).toContain("grid-wrap");
    expect(result.themes).toContain("月夜星河");
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/compatibility/matrix"),
      expect.any(Object),
    );
  });

  it("getCompatibleLayoutsForTheme 调 /api/compatibility/layouts?theme_id=", async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: true, status: 200, json: async () => ({ items: ["magazine-flow"] }), headers: { get: (k: string) => k === "content-type" ? "application/json" : "" },
    });
    const { getCompatibleLayoutsForTheme } = await import("@/api/posters");
    const result = await getCompatibleLayoutsForTheme("月夜星河");
    expect(result.items).toEqual(["magazine-flow"]);
  });
});
