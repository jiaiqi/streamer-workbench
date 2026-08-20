/// P0-2: 单一来源的 session token 注册中心。
///
/// 背景：packaged Electron 模式下，Python 后端 (server/api/handlers.py:21)
/// 强制 mutate 请求携带 X-Streamer-Session 头。
/// 渲染层不能各组件自行 fetch + 自行塞 token —— 必须从主进程统一拿到
/// {baseUrl, sessionToken} 后让 createApiClient 自动注入。
///
/// 调用方：
///   1. App 启动时（main.tsx 或 App.tsx 顶部）调 `initApiSession()` 一次；
///   2. 所有 mutate 请求走 `apiRequest` 自动带上头。
///   3. 浏览器模式 / dev mode 静默 no-op（不调 IPC），getSessionToken 永远返空串。
///
/// 设计要点：
///   - module-level 状态：避免每次 mutate 都调 IPC（IPC 是 async 的，会变慢）
///   - 失败容错：IPC 失败不抛错（不阻塞 UI），sessionToken 保持空串
///   - 不缓存 baseUrl（baseUrl 由 streamer 配置告知；createApiClient 也接受 baseUrl，
///     但 mutate 请求只依赖 sessionToken，不依赖 baseUrl）
import type { ApiClientOptions } from "./client";

let _sessionToken = "";
let _initialized = false;
let _pendingInit: Promise<void> | null = null;

/**
 * 同步读 token（给 client.ts 的 createApiClient 用）。
 * 必须同步返回，所以初始化完成前读到的就是空串。
 */
export function getSessionToken(): string {
  return _sessionToken;
}

/**
 * 异步初始化一次：拉主进程的 sessionToken 并缓存在 module 状态。
 * 安全幂等：多次调用只会触发一次 IPC。
 */
export async function initApiSession(): Promise<void> {
  if (_initialized) return;
  if (_pendingInit) return _pendingInit;
  _pendingInit = (async () => {
    try {
      const streamer = (typeof window !== "undefined" ? window.streamer : undefined);
      if (!streamer?.getApiConfig) {
        // 浏览器 / dev mode：streamer 不存在或无 getApiConfig，静默 no-op
        _initialized = true;
        return;
      }
      const cfg = await streamer.getApiConfig();
      if (cfg && typeof cfg.sessionToken === "string") {
        _sessionToken = cfg.sessionToken;
      }
    } catch {
      // IPC 失败不阻塞 UI；token 保持空串，mutate 请求会被 Python 后端拒
    } finally {
      _initialized = true;
    }
  })();
  return _pendingInit;
}

/**
 * 把 getSessionToken 注入 createApiClient 选项的便捷函数。
 * 用法：const request = createApiClient(withApiSession({ baseUrl, timeoutMs }))
 */
export function withApiSession<T extends Omit<ApiClientOptions, "getSessionToken">>(
  options: T = {} as T,
): ApiClientOptions {
  return { ...options, getSessionToken };
}

/** 测试/重置用：清空 module 状态（单测之间互不污染） */
export function _resetApiSessionForTest(): void {
  _sessionToken = "";
  _initialized = false;
  _pendingInit = null;
}
