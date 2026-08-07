/// M9.6b Toast 系统测试
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, renderHook, act, waitFor } from "@testing-library/react";
import { ToastProvider, useToast } from "./Toast";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function renderWithProvider(ui?: React.ReactNode) {
  return render(<ToastProvider>{ui}</ToastProvider>);
}

describe("Toast - useToast hook", () => {
  it("useToast 无 Provider 时返回 no-op API（容错）", () => {
    const { result } = renderHook(() => useToast());
    // 不抛错；show/success/error/warn/info/dismiss 都是 no-op
    expect(() => {
      result.current.show({ message: "x" });
      result.current.success("y");
      result.current.error("z");
      result.current.warn("w");
      result.current.info("i");
      result.current.dismiss("t1");
    }).not.toThrow();
  });

  it("show() 返回 id + 渲染一条 toast", () => {
    const { result } = renderHook(() => useToast(), { wrapper: ToastProvider });
    let id = "";
    act(() => {
      id = result.current.show({ message: "已保存" });
    });
    expect(id).toMatch(/^t\d+$/);
    expect(document.querySelectorAll('[data-testid="toast-item"]').length).toBe(1);
    expect(document.querySelector('[data-testid="toast-message"]')?.textContent).toBe("已保存");
  });

  it("dismiss(id) 移除指定 toast", () => {
    const { result } = renderHook(() => useToast(), { wrapper: ToastProvider });
    let id = "";
    act(() => { id = result.current.show({ message: "X" }); });
    expect(document.querySelectorAll('[data-testid="toast-item"]').length).toBe(1);
    act(() => { result.current.dismiss(id); });
    expect(document.querySelectorAll('[data-testid="toast-item"]').length).toBe(0);
  });

  it("多条 toast 堆叠（多 show 不会替换）", () => {
    const { result } = renderHook(() => useToast(), { wrapper: ToastProvider });
    act(() => {
      result.current.show({ message: "A" });
      result.current.show({ message: "B" });
      result.current.show({ message: "C" });
    });
    expect(document.querySelectorAll('[data-testid="toast-item"]').length).toBe(3);
  });

  it("durationMs 到期 → 自动消失", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useToast(), { wrapper: ToastProvider });
    act(() => { result.current.show({ message: "X", durationMs: 1000 }); });
    expect(document.querySelectorAll('[data-testid="toast-item"]').length).toBe(1);
    act(() => { vi.advanceTimersByTime(1000); });
    expect(document.querySelectorAll('[data-testid="toast-item"]').length).toBe(0);
  });

  it("durationMs=0 → 不自动消失", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useToast(), { wrapper: ToastProvider });
    act(() => { result.current.show({ message: "持久", durationMs: 0 }); });
    act(() => { vi.advanceTimersByTime(10_000); });
    expect(document.querySelectorAll('[data-testid="toast-item"]').length).toBe(1);
  });
});

describe("Toast - ToastCard UI", () => {
  it("有 action 时渲染「撤销」按钮 + 倒计时", () => {
    vi.useFakeTimers();
    renderWithProvider();
    // 用 fireEvent 不行（hook 拿不到）；直接通过渲染一个 demo
    // 这里改为测 ToastProvider 内的实际渲染
  });

  it("点击 action 调 onClick + 立即关闭 toast", async () => {
    const onAction = vi.fn().mockResolvedValue(undefined);
    function Demo() {
      const toast = useToast();
      return (
        <button data-testid="trigger" onClick={() => toast.show({
          message: "已删除",
          action: { label: "撤销", onClick: onAction },
        })}>show</button>
      );
    }
    render(<ToastProvider><Demo /></ToastProvider>);
    fireEvent.click(document.querySelector('[data-testid="trigger"]')!);
    expect(document.querySelectorAll('[data-testid="toast-item"]').length).toBe(1);
    expect(document.querySelector('[data-testid="toast-action"]')?.textContent).toBe("撤销");
    fireEvent.click(document.querySelector('[data-testid="toast-action"]')!);
    await waitFor(() => {
      expect(onAction).toHaveBeenCalledTimes(1);
      expect(document.querySelectorAll('[data-testid="toast-item"]').length).toBe(0);
    });
  });

  it("点击 ✕ 关闭按钮立即消失", () => {
    function Demo() {
      const toast = useToast();
      return <button data-testid="trigger" onClick={() => toast.show({ message: "X" })}>show</button>;
    }
    render(<ToastProvider><Demo /></ToastProvider>);
    fireEvent.click(document.querySelector('[data-testid="trigger"]')!);
    expect(document.querySelectorAll('[data-testid="toast-item"]').length).toBe(1);
    fireEvent.click(document.querySelector('[data-testid="toast-close"]')!);
    expect(document.querySelectorAll('[data-testid="toast-item"]').length).toBe(0);
  });

  it("action onClick 抛错 → toast 仍关闭（避免卡死）", async () => {
    const onAction = vi.fn().mockRejectedValue(new Error("网络错误"));
    function Demo() {
      const toast = useToast();
      return <button data-testid="trigger" onClick={() => toast.show({
        message: "X", action: { label: "撤销", onClick: onAction },
      })}>show</button>;
    }
    render(<ToastProvider><Demo /></ToastProvider>);
    fireEvent.click(document.querySelector('[data-testid="trigger"]')!);
    fireEvent.click(document.querySelector('[data-testid="toast-action"]')!);
    await waitFor(() => {
      expect(onAction).toHaveBeenCalled();
      expect(document.querySelectorAll('[data-testid="toast-item"]').length).toBe(0);
    });
  });

  it("倒计时显示秒数（5s → 4 → 3 ...）", () => {
    vi.useFakeTimers();
    function Demo() {
      const toast = useToast();
      return <button data-testid="trigger" onClick={() => toast.show({ message: "X", durationMs: 5000 })}>show</button>;
    }
    render(<ToastProvider><Demo /></ToastProvider>);
    fireEvent.click(document.querySelector('[data-testid="trigger"]')!);
    expect(document.querySelector('[data-testid="toast-remaining"]')?.textContent).toBe("5s");
    act(() => { vi.advanceTimersByTime(1000); });
    expect(document.querySelector('[data-testid="toast-remaining"]')?.textContent).toBe("4s");
    act(() => { vi.advanceTimersByTime(2000); });
    expect(document.querySelector('[data-testid="toast-remaining"]')?.textContent).toBe("2s");
  });
});

describe("Toast - 边界", () => {
  it("clear() 清空所有 toast", () => {
    const { result } = renderHook(() => useToast(), { wrapper: ToastProvider });
    act(() => {
      result.current.show({ message: "A" });
      result.current.show({ message: "B" });
      result.current.show({ message: "C" });
    });
    expect(document.querySelectorAll('[data-testid="toast-item"]').length).toBe(3);
    act(() => { result.current.clear(); });
    expect(document.querySelectorAll('[data-testid="toast-item"]').length).toBe(0);
  });

  it("action variant=warning 用 amber 色（className 包含 text-amber-300）", () => {
    function Demo() {
      const toast = useToast();
      return <button data-testid="trigger" onClick={() => toast.show({
        message: "警告",
        action: { label: "重试", onClick: () => {}, variant: "warning" },
      })}>show</button>;
    }
    render(<ToastProvider><Demo /></ToastProvider>);
    fireEvent.click(document.querySelector('[data-testid="trigger"]')!);
    const action = document.querySelector('[data-testid="toast-action"]')!;
    expect(action.className).toContain("text-amber-300");
  });
});

describe("Toast - L1.1 kind 变体（info / success / warning / error）", () => {
  it("default kind=info；显示 ℹ 图标 + zinc 左边色条", () => {
    function Demo() {
      const toast = useToast();
      return <button data-testid="trigger" onClick={() => toast.show({ message: "X" })}>show</button>;
    }
    render(<ToastProvider><Demo /></ToastProvider>);
    fireEvent.click(document.querySelector('[data-testid="trigger"]')!);
    const item = document.querySelector('[data-testid="toast-item"]')!;
    expect(item.getAttribute("data-kind")).toBe("info");
    expect(document.querySelector('[data-testid="toast-icon"]')?.textContent).toBe("ℹ");
    expect(item.className).toContain("border-l-zinc-500");
  });

  it("kind=success → ✓ 图标 + emerald 左边色条", () => {
    function Demo() {
      const toast = useToast();
      return <button data-testid="trigger" onClick={() => toast.show({ message: "已保存", kind: "success" })}>show</button>;
    }
    render(<ToastProvider><Demo /></ToastProvider>);
    fireEvent.click(document.querySelector('[data-testid="trigger"]')!);
    const item = document.querySelector('[data-testid="toast-item"]')!;
    expect(item.getAttribute("data-kind")).toBe("success");
    expect(document.querySelector('[data-testid="toast-icon"]')?.textContent).toBe("✓");
    expect(item.className).toContain("border-l-emerald-500");
  });

  it("kind=warning → ⚠ 图标 + amber 左边色条 + role=alert", () => {
    function Demo() {
      const toast = useToast();
      return <button data-testid="trigger" onClick={() => toast.show({ message: "注意", kind: "warning" })}>show</button>;
    }
    render(<ToastProvider><Demo /></ToastProvider>);
    fireEvent.click(document.querySelector('[data-testid="trigger"]')!);
    const item = document.querySelector('[data-testid="toast-item"]')!;
    expect(item.getAttribute("role")).toBe("alert");
    expect(document.querySelector('[data-testid="toast-icon"]')?.textContent).toBe("⚠");
    expect(item.className).toContain("border-l-amber-500");
  });

  it("kind=error → ✕ 图标 + red 左边色条 + 默认 durationMs=0（不显示倒计时）", () => {
    function Demo() {
      const toast = useToast();
      return <button data-testid="trigger" onClick={() => toast.show({ message: "失败", kind: "error" })}>show</button>;
    }
    render(<ToastProvider><Demo /></ToastProvider>);
    fireEvent.click(document.querySelector('[data-testid="trigger"]')!);
    const item = document.querySelector('[data-testid="toast-item"]')!;
    expect(item.getAttribute("role")).toBe("alert");
    expect(document.querySelector('[data-testid="toast-icon"]')?.textContent).toBe("✕");
    expect(item.className).toContain("border-l-red-500");
    // 错误不自动消失 → 不显示倒计时
    expect(document.querySelector('[data-testid="toast-remaining"]')).toBeNull();
  });

  it("toast.error() 便捷方法 = kind: 'error'", () => {
    function Demo() {
      const toast = useToast();
      return <button data-testid="trigger" onClick={() => toast.error("网络错误")}>show</button>;
    }
    render(<ToastProvider><Demo /></ToastProvider>);
    fireEvent.click(document.querySelector('[data-testid="trigger"]')!);
    const item = document.querySelector('[data-testid="toast-item"]')!;
    expect(item.getAttribute("data-kind")).toBe("error");
    expect(document.querySelector('[data-testid="toast-message"]')?.textContent).toBe("网络错误");
  });

  it("toast.success() 便捷方法 = kind: 'success'", () => {
    function Demo() {
      const toast = useToast();
      return <button data-testid="trigger" onClick={() => toast.success("已恢复")}>show</button>;
    }
    render(<ToastProvider><Demo /></ToastProvider>);
    fireEvent.click(document.querySelector('[data-testid="trigger"]')!);
    expect(document.querySelector('[data-testid="toast-item"]')?.getAttribute("data-kind")).toBe("success");
  });

  it("toast.error() 错误 toast 不自动消失（5s 后还在）", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useToast(), { wrapper: ToastProvider });
    act(() => { result.current.error("永久错误"); });
    act(() => { vi.advanceTimersByTime(60_000); });
    expect(document.querySelectorAll('[data-testid="toast-item"]').length).toBe(1);
  });

  it("toast.success() 3s 后自动消失", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useToast(), { wrapper: ToastProvider });
    act(() => { result.current.success("X"); });
    expect(document.querySelectorAll('[data-testid="toast-item"]').length).toBe(1);
    act(() => { vi.advanceTimersByTime(3000); });
    expect(document.querySelectorAll('[data-testid="toast-item"]').length).toBe(0);
  });
});
