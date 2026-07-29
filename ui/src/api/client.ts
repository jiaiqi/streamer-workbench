export interface ApiErrorBody {
  code: string;
  message: string;
  details?: Record<string, unknown>;
  recovery?: string;
  request_id?: string;
}

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
}

export interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  timeoutMs?: number;
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

export function createApiClient(options: ApiClientOptions = {}) {
  const baseUrl = (options.baseUrl ?? "").replace(/\/$/, "");
  const defaultTimeoutMs = options.timeoutMs ?? 15_000;

  return async function request<T>(path: string, init: RequestOptions = {}): Promise<T> {
    const fetchImpl = options.fetch ?? globalThis.fetch;
    const { body, timeoutMs = defaultTimeoutMs, headers, signal, ...requestInit } = init;
    const timeoutSignal = AbortSignal.timeout(timeoutMs);
    const isFormData = typeof FormData !== "undefined" && body instanceof FormData;
    let response: Response;
    try {
      response = await fetchImpl(`${baseUrl}${path}`, {
        ...requestInit,
        body: body === undefined ? undefined : isFormData ? body : JSON.stringify(body),
        headers: body === undefined || isFormData
          ? headers
          : { "Content-Type": "application/json", ...headers },
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

export const apiRequest = createApiClient();
