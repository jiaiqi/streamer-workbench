/// App.tsx 集成：workspace 左栏接入 WorkspacePosterBridge。
/// 仅验证挂载与关键区域渲染，不覆盖预览/导出主流程。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";

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
    return new Response(JSON.stringify([]), {
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
});
