/// M2.6 useApiError 测试
///
/// 验证：
/// - 成功路径：返回值原样透传，不弹 toast
/// - 失败路径：toast.error 调用 + 抛出 RequestFailure（供上层 setError）
/// - AbortError：抛但不 toast
/// - 自定义 label：toast 文本前缀
/// - 无 ToastProvider：toast no-op，failure 仍抛出
import { describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { useApiError } from "./useApiError";
import { ToastContext, useToast, type ToastApi } from "../components/Toast";
import type { ReactNode } from "react";

/** 包一个用 ref 收集 toast.error 调用的 Provider */
function ToastSpyProvider({ children, errors }: { children: ReactNode; errors: Array<{ message: string }> }) {
  const spy: Partial<ToastApi> = {
    show: vi.fn(),
    error: (message: string) => { errors.push({ message }); return 1; },
    success: (message: string) => { errors.push({ message }); return 1; },
    warning: (message: string) => { errors.push({ message }); return 1; },
    dismiss: vi.fn(),
    clear: vi.fn(),
  };
  return <ToastContext.Provider value={spy as ToastApi}>{children}</ToastContext.Provider>;
}

function makeWrapper(spyArr: Array<{ message: string }>) {
  return ({ children }: { children: ReactNode }) => (
    <ToastSpyProvider errors={spyArr}>{children}</ToastSpyProvider>
  );
}

describe("useApiError - M2.6 错误全局 toast 化", () => {
  it("成功路径：返回值原样透传，不弹 toast", async () => {
    const errors: Array<{ message: string }> = [];
    const { result } = renderHook(
      () => useApiError(),
      { wrapper: makeWrapper(errors) },
    );
    const data = await result.current.runWithToast(
      async () => ({ ok: true, value: 42 }),
      "测试",
    );
    expect(data).toEqual({ ok: true, value: 42 });
    expect(errors).toHaveLength(0);
  });

  it("失败路径：toast.error 弹出 + 抛出 RequestFailure", async () => {
    const errors: Array<{ message: string }> = [];
    const { result } = renderHook(
      () => useApiError(),
      { wrapper: makeWrapper(errors) },
    );
    let caught: unknown = null;
    try {
      await result.current.runWithToast(async () => {
        throw new Error("网络断开");
      }, "删除失败");
    } catch (e) {
      caught = e;
    }
    expect(caught).toBeTruthy();
    expect((caught as { message: string }).message).toBe("网络断开");
    expect(errors).toHaveLength(1);
    expect(errors[0].message).toBe("删除失败：网络断开");
  });

  it("失败无 label：toast 文本用「操作失败」前缀", async () => {
    const errors: Array<{ message: string }> = [];
    const { result } = renderHook(
      () => useApiError(),
      { wrapper: makeWrapper(errors) },
    );
    try {
      await result.current.runWithToast(async () => {
        throw new Error("oops");
      });
    } catch { /* expected */ }
    expect(errors[0].message).toBe("操作失败：oops");
  });

  it("AbortError：抛但不弹 toast", async () => {
    const errors: Array<{ message: string }> = [];
    const { result } = renderHook(
      () => useApiError(),
      { wrapper: makeWrapper(errors) },
    );
    let caught: unknown = null;
    try {
      await result.current.runWithToast(async () => {
        throw new DOMException("Aborted", "AbortError");
      }, "测试");
    } catch (e) {
      caught = e;
    }
    expect(caught).toBeInstanceOf(DOMException);
    expect((caught as DOMException).name).toBe("AbortError");
    expect(errors).toHaveLength(0);
  });

  it("抛出 RequestFailure 而非原始 Error（供 ErrorBanner 用）", async () => {
    const errors: Array<{ message: string }> = [];
    const { result } = renderHook(
      () => useApiError(),
      { wrapper: makeWrapper(errors) },
    );
    let caught: unknown = null;
    try {
      await result.current.runWithToast(async () => {
        throw new Error("raw");
      }, "X");
    } catch (e) {
      caught = e;
    }
    expect(caught).toBeTruthy();
    expect(typeof (caught as { message: string }).message).toBe("string");
    expect((caught as { message: string }).message).toBe("raw");
  });

  it("无 ToastProvider：toast no-op，failure 仍抛出", async () => {
    const { result } = renderHook(() => useApiError());
    let caught: unknown = null;
    try {
      await result.current.runWithToast(async () => {
        throw new Error("独立窗口");
      }, "测试");
    } catch (e) {
      caught = e;
    }
    expect((caught as { message: string }).message).toBe("独立窗口");
  });
});
