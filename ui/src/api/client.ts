export interface ApiErrorBody {
  code: string;
  message: string;
  details?: Record<string, unknown>;
  recovery?: string;
  request_id?: string;
}

// P0-2: 顶层 import session.ts 让 default apiRequest 拿得到 token getter。
// 浏览器 / dev mode 下 initApiSession 是 no-op，getSessionToken 永远返回 ""，
// 所以默认 dev 行为完全不变。
import { getSessionToken } from "./session.ts";

export interface ApiErrorEnvelope {
  error: ApiErrorBody;
}

export class ApiClientError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;
  readonly recovery?: string;
  readonly requestId?: string;

  constructor(status: number, error: ApiErrorBody) {
    super(error.message);
    this.name = "ApiClientError";
    this.status = status;
    this.code = error.code;
    this.details = error.details ?? {};
    this.recovery = error.recovery;
    this.requestId = error.request_id;
  }
}

export interface ApiClientOptions {
  baseUrl?: string;
  timeoutMs?: number;
  fetch?: typeof fetch;
  /**
   * P0-2: 每次 mutate 请求都会同步调它拿 session token。
   * 浏览器模式 / dev mode 返回空串即可（Python 后端对空 token 不强制）。
   * packaged Electron 必须返回主进程生成的随机串。
   */
  getSessionToken?: () => string;
}

function isErrorEnvelope(value: unknown): value is ApiErrorEnvelope {
  if (!value || typeof value !== "object" || !("error" in value)) return false;
  const error = (value as { error?: unknown }).error;
  return Boolean(
    error && typeof error === "object"
      && typeof (error as { code?: unknown }).code === "string"
      && typeof (error as { message?: unknown }).message === "string",
  );
}

function combineSignals(signal: AbortSignal | null | undefined, timeout: AbortSignal) {
  return signal ? AbortSignal.any([signal, timeout]) : timeout;
}

export interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  timeoutMs?: number;
}

export function createApiClient(options: ApiClientOptions = {}) {
  const baseUrl = (options.baseUrl ?? "").replace(/\/$/, "");
  const defaultTimeoutMs = options.timeoutMs ?? 15_000;

  return async function request<T>(path: string, init: RequestOptions = {}): Promise<T> {
    const fetchImpl = options.fetch ?? globalThis.fetch;
    const { body, timeoutMs = defaultTimeoutMs, headers, signal, ...requestInit } = init;
    const timeoutSignal = AbortSignal.timeout(timeoutMs);
    const isFormData = typeof FormData !== "undefined" && body instanceof FormData;

    // P0-2: mutate 请求自动注入 X-Streamer-Session。
    // 与 server/api/handlers.py:21 SESSION_TOKEN_HEADER 常量对齐。
    // token 来自 caller 注册的 getSessionToken（默认空字符串，dev mode 合法）。
    const method = (requestInit.method ?? "GET").toUpperCase();
    const isMutating = method !== "GET" && method !== "HEAD" && method !== "OPTIONS";
    const sessionToken = isMutating ? (options.getSessionToken?.() ?? "") : "";
    const authHeader = sessionToken ? { "X-Streamer-Session": sessionToken } : undefined;

    let response: Response;
    try {
      response = await fetchImpl(`${baseUrl}${path}`, {
        ...requestInit,
        body: body === undefined ? undefined : isFormData ? body : JSON.stringify(body),
        headers: body === undefined || isFormData
          ? { ...authHeader, ...headers }
          : { "Content-Type": "application/json", ...authHeader, ...headers },
        signal: combineSignals(signal, timeoutSignal),
      });
    } catch (error) {
      if (signal?.aborted) throw error;
      if (timeoutSignal.aborted) {
        throw new ApiClientError(0, {
          code: "request_timeout",
          message: "请求超时",
          recovery: "检查服务状态后重试",
        });
      }
      throw new ApiClientError(0, {
        code: "network_error",
        message: "无法连接本地服务",
        details: { reason: error instanceof Error ? error.message : String(error) },
        recovery: "确认后端已启动后重试",
      });
    }

    if (response.status === 204) return undefined as T;
    const contentType = response.headers.get("content-type") ?? "";
    const payload: unknown = contentType.includes("application/json")
      ? await response.json()
      : await response.text();
    if (!response.ok) {
      if (isErrorEnvelope(payload)) {
        throw new ApiClientError(response.status, payload.error);
      }
      throw new ApiClientError(response.status, {
        code: "http_error",
        message: `请求失败（HTTP ${response.status}）`,
        details: typeof payload === "string" && payload ? { response: payload } : {},
        recovery: "重试；若持续失败请查看日志",
      });
    }
    return payload as T;
  };
}

export const apiRequest = createApiClient({ getSessionToken });

/**
 * P0-2: 二进制请求（PNG / 音频 / 视频等）。
 * 复用 createApiClient 的 session token 注入逻辑（必须传 getSessionToken 才能在
 * Electron packaged 模式下 mutate 请求通过 X-Streamer-Session 校验），
 * 但不解析 JSON 也不走 error envelope —— binary 错误直接看 HTTP 状态码。
 * 返回 ArrayBuffer；caller 自决怎么用（saveBlob / decodeAudioData 等）。
 */
export async function apiRequestBinary(
  path: string,
  init: RequestOptions & { getSessionToken?: () => string } = {},
): Promise<ArrayBuffer> {
  const fetchImpl = (init as { fetch?: typeof fetch }).fetch ?? globalThis.fetch;
  const { body, timeoutMs = 60_000, headers, signal, getSessionToken, ...requestInit } = init;
  const timeoutSignal = AbortSignal.timeout(timeoutMs);
  const method = (requestInit.method ?? "GET").toUpperCase();
  const isMutating = method !== "GET" && method !== "HEAD" && method !== "OPTIONS";
  const sessionToken = isMutating ? (getSessionToken?.() ?? "") : "";
  const finalHeaders: Record<string, string> = {
    ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    ...(sessionToken ? { "X-Streamer-Session": sessionToken } : {}),
    ...(headers as Record<string, string> | undefined ?? {}),
  };
  const response = await fetchImpl(path, {
    ...requestInit,
    body: body === undefined ? undefined : JSON.stringify(body),
    headers: finalHeaders,
    signal: combineSignals(signal, timeoutSignal),
  });
  if (!response.ok) {
    throw new ApiClientError(response.status, {
      code: "http_error",
      message: `二进制请求失败（HTTP ${response.status}）`,
      recovery: "重试；若持续失败请查看日志",
    });
  }
  return await response.arrayBuffer();
}

/* ---- 业务方法（R4.2.3: 导出历史） ----------------------------------- */

import type { ExportLogRecentResponse } from "./generated";

/**
 * R4.2.3: 拉取最近的导出历史（工作台批量 / 直播复盘 / 学歌报告三类合一）。
 * 走 GET /api/exports/recent；后端从 events.jsonl 读 type=poster_exported 事件。
 * @param limit 1 ~ 100；默认 20
 */
export function listExportLog(limit: number = 20): Promise<ExportLogRecentResponse> {
  const safe = Math.max(1, Math.min(100, Math.floor(limit)));
  return apiRequest<ExportLogRecentResponse>(`/api/exports/recent?limit=${safe}`);
}
