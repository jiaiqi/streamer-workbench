import { useCallback, useEffect, useRef, useState } from "react";
import { ApiClientError } from "../api/client";

export type AsyncStatus = "idle" | "loading" | "success" | "empty" | "error";

export interface RequestFailure {
  message: string;
  recovery?: string;
  requestId?: string;
}

export interface AsyncRequestState<T> {
  status: AsyncStatus;
  data: T | null;
  error: RequestFailure | null;
}

export function isAbortError(reason: unknown): boolean {
  return reason instanceof DOMException && reason.name === "AbortError";
}

export function toRequestFailure(reason: unknown, fallback = "请求失败"): RequestFailure {
  if (reason instanceof ApiClientError) {
    return { message: reason.message, recovery: reason.recovery, requestId: reason.requestId };
  }
  return { message: reason instanceof Error ? reason.message : fallback };
}

export function useLatestRequest<T>(options: { isEmpty?: (data: T) => boolean } = {}) {
  const [state, setState] = useState<AsyncRequestState<T>>({ status: "idle", data: null, error: null });
  const generation = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const isEmptyRef = useRef(options.isEmpty);
  isEmptyRef.current = options.isEmpty;

  const run = useCallback(async (request: (signal: AbortSignal) => Promise<T>) => {
    const current = ++generation.current;
    controller.current?.abort();
    const nextController = new AbortController();
    controller.current = nextController;
    setState(previous => ({ status: "loading", data: previous.data, error: null }));
    try {
      const data = await request(nextController.signal);
      if (current !== generation.current || nextController.signal.aborted) return null;
      setState({ status: isEmptyRef.current?.(data) ? "empty" : "success", data, error: null });
      return data;
    } catch (reason) {
      if (current !== generation.current) return null;
      if (isAbortError(reason) || nextController.signal.aborted) {
        setState(previous => ({ ...previous, status: previous.data === null ? "idle" : "success", error: null }));
        return null;
      }
      setState(previous => ({ status: "error", data: previous.data, error: toRequestFailure(reason) }));
      return null;
    }
  }, []);

  const cancel = useCallback(() => {
    generation.current += 1;
    controller.current?.abort();
    setState(previous => ({ ...previous, status: previous.data === null ? "idle" : "success", error: null }));
  }, []);

  useEffect(() => () => {
    generation.current += 1;
    controller.current?.abort();
  }, []);
  return { ...state, run, cancel };
}
