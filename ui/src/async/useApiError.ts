/// M2.6 错误全局 toast 化 — 包装 fetch + 自动 toast.error + 保留 ErrorBanner 流程。
///
/// 设计动机：
/// - 各组件 catch 后仅 setXError，用户需滚动到错误位置才能看到，漏看率高。
/// - 全局 toast 系统（M9.6b）已经有 role=alert 错误通知，error 默认不自动消失。
/// - 但 ErrorBanner 仍有意义：retry 入口 + 上下文信息。
///
/// 策略：
/// - `runWithToast(fn, label)` 内部 try/catch + 失败 toast.error(label + "：" + msg)
/// - 失败时**重新抛出** RequestFailure，让上层 catch 仍能 setError → ErrorBanner
/// - AbortError 不弹 toast（用户主动取消的场景）
///
/// 用法：
/// ```ts
/// const { runWithToast } = useApiError();
/// try {
///   await runWithToast(() => apiRequest("/api/songs/delete", ...), "删除失败");
/// } catch (failure) {
///   setError(failure);  // 供 ErrorBanner 显示 + retry
/// }
/// ```
import { useCallback, useContext } from "react";
import { ToastContext, type ToastApi } from "../components/Toast";
import { isAbortError, toRequestFailure, type RequestFailure } from "./requestState";

export interface UseApiError {
  /**
   * 执行异步函数；失败时 toast.error(`${label}：${message}`) 并重新抛出 RequestFailure。
   * AbortError 不弹 toast（视为用户主动取消）。
   * 无 ToastProvider 时 no-op（仅抛出 failure，不弹 toast）— 便于测试 / 子窗口。
   */
  runWithToast: <T>(fn: () => Promise<T>, label?: string) => Promise<T>;
}

export function useApiError(): UseApiError {
  const toast: ToastApi | null = useContext(ToastContext);
  const runWithToast = useCallback(async <T,>(
    fn: () => Promise<T>,
    label?: string,
  ): Promise<T> => {
    try {
      return await fn();
    } catch (reason) {
      if (isAbortError(reason)) throw reason;
      const failure: RequestFailure = toRequestFailure(reason, label);
      if (toast) {
        toast.error(`${label ?? "操作失败"}：${failure.message}`);
      }
      throw failure;
    }
  }, [toast]);
  return { runWithToast };
}
