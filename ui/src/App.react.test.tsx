/// App.tsx 集成：workspace 左栏接入 WorkspacePosterBridge。
/// 仅验证挂载与关键区域渲染，不覆盖预览/导出主流程。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";

vi.mock("./posters/WorkspacePosterBridge", () => ({
  default: () => <div data-testid="workspace-bridge">bridge</div>,
}));

// 把后端依赖 mock 掉避免 fetch
const fetchSpy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
  const url = typeof input === "string" ? input : (input as URL).toString();
  const method = init?.method ?? "GET";
  // 不同端点返回不同形状；保持 App 调用至少 1 个非空
  if (url.endsWith("/api/layouts/grid-wrap/params")) {
    return new Response(JSON.stringify([]), {
      status: 200, headers: { "content-type": "application/json" },
    });
  }
  if (url.endsWith("/api/themes")) {
    return new Response(JSON.stringify([
      { name: "海洋柔光", prefix: "海洋柔光", watermark_fix: false, backgrounds: {}, notes: "" },
    ]), {
      status: 200, headers: { "content-type": "application/json" },
    });
  }
  if (url.endsWith("/api/layouts")) {
    return new Response(JSON.stringify([]), {
      status: 200, headers: { "content-type": "application/json" },
    });
  }
  if (url.endsWith("/api/songs/list")) {
    return new Response(JSON.stringify({ total: 0, active: 0, draft: 0, songs: [] }), {
      status: 200, headers: { "content-type": "application/json" },
    });
  }
  if (url.endsWith("/api/settings")) {
    return new Response(JSON.stringify({
      ok: true, default_canvas: "9:20", default_theme: "海洋柔光",
      appearance: { appearanceMode: "system", applicationAccentId: "bambooMoon" },
      settings_revision: "rev-settings", appearance_revision: "rev-appearance",
      appearance_saved: { appearanceMode: "system", applicationAccentId: "bambooMoon" },
    }), { status: 200, headers: { "content-type": "application/json" } });
  }
  if (url.endsWith("/api/posters")) {
    return new Response(JSON.stringify([]), {
      status: 200, headers: { "content-type": "application/json" },
    });
  }
  return new Response(JSON.stringify({ ok: true }), {
    status: 200, headers: { "content-type": "application/json" },
  });
});
beforeEach(() => {
  vi.useFakeTimers();
  globalThis.fetch = fetchSpy as unknown as typeof fetch;
});
afterEach(() => vi.useRealTimers());

describe("App workspace 视图", () => {
  it("工作台视图挂载 WorkspacePosterBridge", async () => {
    const App = (await import("./App")).default;
    await act(async () => {
      render(<App />);
      await vi.runOnlyPendingTimersAsync();
    });
    // workspace 默认视图，左栏有桥接
    expect(screen.getByTestId("workspace-bridge")).toBeTruthy();
  });

  // ---- M1.7 渐进式海报：相邻页预加载 ----
  it("workspace 渲染时挂载 next-preload img（grid-wrap 默认 page=1 → 只有 next）", async () => {
    const App = (await import("./App")).default;
    await act(async () => {
      render(<App />);
      await vi.runOnlyPendingTimersAsync();
    });
    const next = screen.queryByTestId("poster-next-preload") as HTMLImageElement | null;
    const prev = screen.queryByTestId("poster-prev-preload");
    expect(next).toBeTruthy();
    expect(prev).toBeNull();  // page=1 → 没有 prev
    expect(next!.getAttribute("src")).toContain("/api/render?");
    expect(next!.getAttribute("src")).toContain("page=2");
    // hidden img 不会进 a11y tree
    expect(next!.getAttribute("aria-hidden")).toBe("true");
  });

  // ---- L1.2 快捷键面板：? 键 ----
  it("按 ? 键打开 ShortcutsPanel", async () => {
    localStorage.setItem("sw-onboarded", "v1");  // 跳过 onboarding
    const App = (await import("./App")).default;
    await act(async () => {
      render(<App />);
      await vi.runOnlyPendingTimersAsync();
    });
    expect(screen.queryByTestId("shortcuts-panel")).toBeNull();
    // 触发 ? 键（Shift+/）
    await act(async () => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "?" }));
    });
    expect(screen.getByTestId("shortcuts-panel")).toBeTruthy();
  });

  // ---- L1.3 Onboarding ----
  it("localStorage 未标记 → 首次启动显示 Onboarding", async () => {
    localStorage.removeItem("sw-onboarded");
    const App = (await import("./App")).default;
    await act(async () => {
      render(<App />);
      await vi.runOnlyPendingTimersAsync();
    });
    // Onboarding 用 useEffect 异步设 visible — 等几帧
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    expect(screen.getByTestId("onboarding-panel")).toBeTruthy();
  });

  it("localStorage 已标记 → 不显示 Onboarding", async () => {
    localStorage.setItem("sw-onboarded", "v1");
    const App = (await import("./App")).default;
    await act(async () => {
      render(<App />);
      await vi.runOnlyPendingTimersAsync();
    });
    expect(screen.queryByTestId("onboarding-panel")).toBeNull();
  });

  // ---- L1.5 离线检测 ----
  it("在线状态：顶栏 OnlineStatusBadge data-state=online", async () => {
    localStorage.setItem("sw-onboarded", "v1");
    Object.defineProperty(navigator, "onLine", { value: true, configurable: true });
    const App = (await import("./App")).default;
    await act(async () => {
      render(<App />);
      await vi.runOnlyPendingTimersAsync();
    });
    // 让 OnlineStatusBadge useEffect 跑完
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    expect(screen.getByTestId("online-status-badge").getAttribute("data-state")).toBe("online");
  });

  it("离线：顶栏 OnlineStatusBadge data-state=offline", async () => {
    localStorage.setItem("sw-onboarded", "v1");
    Object.defineProperty(navigator, "onLine", { value: false, configurable: true });
    const App = (await import("./App")).default;
    await act(async () => {
      render(<App />);
      await vi.runOnlyPendingTimersAsync();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    expect(screen.getByTestId("online-status-badge").getAttribute("data-state")).toBe("offline");
  });

  it("从在线掉到离线：warning toast 弹出", async () => {
    localStorage.setItem("sw-onboarded", "v1");
    Object.defineProperty(navigator, "onLine", { value: true, configurable: true });
    const App = (await import("./App")).default;
    await act(async () => {
      render(<App />);
      await vi.runOnlyPendingTimersAsync();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    expect(screen.getByTestId("online-status-badge").getAttribute("data-state")).toBe("online");
    // 模拟掉线
    Object.defineProperty(navigator, "onLine", { value: false, configurable: true });
    await act(async () => {
      window.dispatchEvent(new Event("offline"));
      await vi.advanceTimersByTimeAsync(50);
    });
    // warning toast 出现
    const warning = document.querySelector('[data-testid="toast-item"][data-kind="warning"]');
    expect(warning).toBeTruthy();
    expect(warning!.textContent).toContain("网络已断开");
  });
});
