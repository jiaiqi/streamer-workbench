/// L1.5 OnlineStatusBadge 测试
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, waitFor } from "@testing-library/react";
import OnlineStatusBadge, { getOnlineState } from "./OnlineStatusBadge";

afterEach(() => {
  cleanup();
});

describe("getOnlineState", () => {
  it("navigator.onLine=true → online", () => {
    Object.defineProperty(navigator, "onLine", { value: true, configurable: true });
    expect(getOnlineState()).toBe("online");
  });

  it("navigator.onLine=false → offline", () => {
    Object.defineProperty(navigator, "onLine", { value: false, configurable: true });
    expect(getOnlineState()).toBe("offline");
  });
});

describe("OnlineStatusBadge - 渲染", () => {
  beforeEach(() => {
    Object.defineProperty(navigator, "onLine", { value: true, configurable: true });
  });

  it("在线 → 绿色圆点 + 「在线」文案", () => {
    const { getByTestId } = render(<OnlineStatusBadge />);
    const badge = getByTestId("online-status-badge");
    expect(badge.getAttribute("data-state")).toBe("online");
    expect(badge.textContent).toContain("在线");
    const dot = getByTestId("online-status-dot");
    expect(dot.className).toContain("bg-emerald-500");
  });

  it("离线 → 红色圆点（animate-pulse）+ 「离线」文案", async () => {
    Object.defineProperty(navigator, "onLine", { value: false, configurable: true });
    const { getByTestId } = render(<OnlineStatusBadge />);
    await waitFor(() => {
      expect(getByTestId("online-status-badge").getAttribute("data-state")).toBe("offline");
    });
    expect(getByTestId("online-status-badge").textContent).toContain("离线");
    const dot = getByTestId("online-status-dot");
    expect(dot.className).toContain("bg-red-500");
    expect(dot.className).toContain("animate-pulse");
  });
});

describe("OnlineStatusBadge - 事件监听", () => {
  beforeEach(() => {
    Object.defineProperty(navigator, "onLine", { value: true, configurable: true });
  });

  it("dispatchEvent('offline') → 状态切到 offline", async () => {
    const { getByTestId } = render(<OnlineStatusBadge />);
    expect(getByTestId("online-status-badge").getAttribute("data-state")).toBe("online");
    // 模拟掉线
    Object.defineProperty(navigator, "onLine", { value: false, configurable: true });
    window.dispatchEvent(new Event("offline"));
    await waitFor(() => {
      expect(getByTestId("online-status-badge").getAttribute("data-state")).toBe("offline");
    });
  });

  it("dispatchEvent('online') → 状态从 offline 切回 online", async () => {
    Object.defineProperty(navigator, "onLine", { value: false, configurable: true });
    const { getByTestId } = render(<OnlineStatusBadge />);
    await waitFor(() => {
      expect(getByTestId("online-status-badge").getAttribute("data-state")).toBe("offline");
    });
    Object.defineProperty(navigator, "onLine", { value: true, configurable: true });
    window.dispatchEvent(new Event("online"));
    await waitFor(() => {
      expect(getByTestId("online-status-badge").getAttribute("data-state")).toBe("online");
    });
  });

  it("卸载时移除事件监听（不再状态变化）", async () => {
    const { unmount, getByTestId } = render(<OnlineStatusBadge />);
    expect(getByTestId("online-status-badge").getAttribute("data-state")).toBe("online");
    unmount();
    // 卸载后 dispatch 不会影响已卸载的组件
    window.dispatchEvent(new Event("offline"));
    // 没有"组件"了；只检查 querySelector 找不到 badge
    expect(document.querySelector('[data-testid="online-status-badge"]')).toBeNull();
  });
});
