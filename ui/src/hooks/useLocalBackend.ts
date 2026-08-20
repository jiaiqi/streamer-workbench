/// P0-4b: 区分 "navigator.onLine=false" 与 "本地后端未启动" 两种情况。
///
/// 三态网络模型：
///   - internet:    navigator.onLine 物理网络
///   - localBackend: GET /api/health 能 200
///   - onlineFeatures = internet && localBackend
///
/// 用法：
///   const { localBackend, isOnlineFeatures } = useLocalBackend();
///   渲染层：
///     - localBackend=false → "本地后端未启动" banner（与 internet 无关）
///     - localBackend=true && internet=false → "离线（在线功能不可用）" 提示
///     - 两者都 ok → 正常
///
/// 探测策略：
///   - App 启动时 1 次；
///   - 然后每 10s 一次（不频繁，避免压后端）；
///   - 收到任意 mutate 请求 401/网络错误时立刻标 localBackend=false；
///   - 恢复后下一次定时探测再标回 true。
///
/// 设计：probe 失败不抛错（fetch 抛错本地 catch），不阻塞 UI。
import { useEffect, useState, useCallback, useRef } from "react";
import { apiRequest } from "../api/client";

export type LocalBackendState = "checking" | "up" | "down";

export interface UseLocalBackendResult {
  state: LocalBackendState;
  /** 派生：online features（需要 internet + local backend） */
  isOnlineFeatures: boolean;
  /** 手动触发一次 probe */
  recheck: () => Promise<void>;
}

const PROBE_INTERVAL_MS = 10_000;
const PROBE_TIMEOUT_MS = 3_000;

export function useLocalBackend(): UseLocalBackendResult {
  const [state, setState] = useState<LocalBackendState>("checking");
  const [internetOnline, setInternetOnline] = useState<boolean>(
    typeof navigator !== "undefined" ? navigator.onLine : true,
  );
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const probe = useCallback(async (): Promise<boolean> => {
    try {
      // 用 apiRequest 走统一 transport；超时 3s；任何非 2xx 都算 down
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);
      try {
        const res = await apiRequest<{ ok: boolean }>("/api/health", {
          signal: controller.signal,
          timeoutMs: PROBE_TIMEOUT_MS,
        });
        return Boolean(res?.ok);
      } finally {
        clearTimeout(timeout);
      }
    } catch {
      return false;
    }
  }, []);

  const recheck = useCallback(async () => {
    setState("checking");
    const ok = await probe();
    setState(ok ? "up" : "down");
  }, [probe]);

  // 启动 + 定时探测
  useEffect(() => {
    void recheck();
    const tick = async () => {
      const ok = await probe();
      setState((prev) => (ok ? "up" : prev === "checking" ? "down" : "down"));
    };
    timerRef.current = setInterval(tick, PROBE_INTERVAL_MS);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [probe, recheck]);

  // 监听 internet 变化
  useEffect(() => {
    const onOnline = () => setInternetOnline(true);
    const onOffline = () => setInternetOnline(false);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, []);

  return {
    state,
    isOnlineFeatures: state === "up" && internetOnline,
    recheck,
  };
}
