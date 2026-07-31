/// R2 P2: QuickView v2 LiveSession 状态机 hook。
///
/// 用法：
///   const session = useLiveSession(sessionId);
///   await session.queueRequest(songId, requesterName, 'fan_join', entId);
///   await session.recordResult(requestId, 'sung');
///   await session.refresh();
///   await session.close();
///
/// 离线兜底：
///   - 入队/记结果失败时进 pending_commands 队列 (localStorage 临时缓存)
///   - 恢复网络后按 command_id 幂等补报
///   - 后端 record/queue 都是幂等, 重复 POST 不会产生副作用
///
/// 不依赖 LiveService: 直接调 R2 已有的 7 端点。
import { useCallback, useEffect, useRef, useState } from "react";
import { apiRequest, ApiClientError } from "../api/client";
import type {
  LiveSessionDetail,
  LiveSessionQueueResponse,
  LiveSessionRecordResponse,
  LiveSessionSummary,
} from "../api/generated";

const PENDING_KEY = "quickview-v2-pending";
const PENDING_LIMIT = 50;

export interface PendingCommand {
  /** 与后端 command_id 一致, 用于幂等补报。 */
  command_id: string;
  kind: "queue" | "record";
  /** 入队时: song_id; 记结果时: request_id */
  target_id: string;
  payload: Record<string, unknown>;
  queued_at: number;
}

export interface LiveSessionState {
  /** null = 加载中; undefined = sessionId 为空 (等待) */
  session: LiveSessionDetail | null | undefined;
  error: string | null;
  /** 待补报命令数 */
  pendingCount: number;
  /** 当前会话是否进行中 (active) */
  isActive: boolean;
  /** 当前会话标题 (供 UI 显示) */
  title: string;
}

export interface LiveSessionActions {
  refresh: () => Promise<void>;
  queueRequest: (songId: string, requesterName: string,
    entitlementKind?: string, entitlementId?: string | null) => Promise<{ ok: boolean; duplicate?: boolean; message?: string }>;
  recordResult: (requestId: string, result: string) => Promise<{ ok: boolean; refunded?: boolean; message?: string }>;
  close: () => Promise<void>;
  retryPending: () => Promise<void>;
}

export type UseLiveSession = LiveSessionState & LiveSessionActions;

export function useLiveSession(sessionId: string | null): UseLiveSession {
  const [session, setSession] = useState<LiveSessionDetail | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [pendingCount, setPendingCount] = useState(() => loadPending().length);

  const pendingRef = useRef<PendingCommand[]>(loadPending());
  pendingRef.current = pendingRef.current; // keep ref in sync
  const sessionRef = useRef<LiveSessionDetail | null>(null);
  const retryingRef = useRef(false);

  const updatePending = (next: PendingCommand[]) => {
    pendingRef.current = next.slice(-PENDING_LIMIT);
    localStorage.setItem(PENDING_KEY, JSON.stringify(pendingRef.current));
    setPendingCount(pendingRef.current.length);
  };

  const refresh = useCallback(async () => {
    if (!sessionId) {
      setSession(undefined);
      return;
    }
    try {
      const data = await apiRequest<LiveSessionDetail>(`/api/live-sessions/${sessionId}`);
      setSession(data);
      setError(null);
      sessionRef.current = data;
    } catch (reason) {
      const msg = reason instanceof ApiClientError
        ? `${reason.code}: ${reason.message}`
        : (reason instanceof Error ? reason.message : String(reason));
      setError(msg);
      setSession(null);
      sessionRef.current = null;
    }
  }, [sessionId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // 30s 自动重试 pending + refresh 会话
  useEffect(() => {
    const t = setInterval(() => {
      void retryPending();
      void refresh();
    }, 30_000);
    return () => clearInterval(t);
  }, [refresh]);

  const retryPending = useCallback(async () => {
    if (retryingRef.current || pendingRef.current.length === 0 || !sessionId) return;
    retryingRef.current = true;
    const remaining: PendingCommand[] = [];
    for (const cmd of pendingRef.current) {
      try {
        if (cmd.kind === "queue") {
          await apiRequest(`/api/live-sessions/${sessionId}/queue`, {
            method: "POST", body: cmd.payload,
          });
        } else if (cmd.kind === "record") {
          await apiRequest(`/api/live-sessions/${sessionId}/record`, {
            method: "POST", body: cmd.payload,
          });
        }
      } catch {
        // 仍然失败: 保留在队列里下次再试
        remaining.push(cmd);
      }
    }
    updatePending(remaining);
    await refresh();
    retryingRef.current = false;
  }, [sessionId, refresh]);

  const enqueuePending = (cmd: PendingCommand) => {
    updatePending([...pendingRef.current, cmd]);
  };

  const queueRequest = useCallback(async (
    songId: string, requesterName: string,
    entitlementKind: string = "", entitlementId: string | null = null,
  ) => {
    if (!sessionId) return { ok: false, message: "未指定会话" };
    const command_id = `cmd_${uuid().replaceAll("-", "")}`;
    const payload = {
      requester_name: requesterName,
      requester_id: null,
      song_id: songId,
      entitlement_id: entitlementId,
      entitlement_kind: entitlementKind,
      note: "速查窗加歌",
      command_id,
    };
    try {
      const res = await apiRequest<LiveSessionQueueResponse>(
        `/api/live-sessions/${sessionId}/queue`,
        { method: "POST", body: payload },
      );
      await refresh();
      return {
        ok: true,
        duplicate: res.duplicate_merged ?? false,
        message: res.duplicate_merged ? "已在队列中" : `位置 #${res.position}`,
      };
    } catch (reason) {
      // 网络/服务器错误: 入 pending 队列后续补报
      enqueuePending({
        command_id, kind: "queue", target_id: songId, payload, queued_at: Date.now(),
      });
      const msg = reason instanceof ApiClientError
        ? reason.message
        : (reason instanceof Error ? reason.message : String(reason));
      return { ok: false, message: `已离线暂存 (${msg})` };
    }
  }, [sessionId, refresh]);

  const recordResult = useCallback(async (requestId: string, result: string) => {
    if (!sessionId) return { ok: false, message: "未指定会话" };
    const command_id = `cmd_${uuid().replaceAll("-", "")}`;
    const payload = {
      request_id: requestId,
      result,
      operator: "broadcaster",
      reason: "速查窗记录",
      command_id,
    };
    try {
      const res = await apiRequest<LiveSessionRecordResponse>(
        `/api/live-sessions/${sessionId}/record`,
        { method: "POST", body: payload },
      );
      await refresh();
      return {
        ok: true,
        refunded: res.refunded ?? false,
        message: res.refunded ? `已记录: ${result} (已退还权益)` : `已记录: ${result}`,
      };
    } catch (reason) {
      enqueuePending({
        command_id, kind: "record", target_id: requestId, payload, queued_at: Date.now(),
      });
      const msg = reason instanceof ApiClientError
        ? reason.message
        : (reason instanceof Error ? reason.message : String(reason));
      return { ok: false, message: `已离线暂存 (${msg})` };
    }
  }, [sessionId, refresh]);

  const close = useCallback(async () => {
    if (!sessionId) return;
    try {
      await apiRequest(`/api/live-sessions/${sessionId}/close`, { method: "POST", body: {} });
    } catch {
      // 关闭失败不强提示
    }
    await refresh();
  }, [sessionId, refresh]);

  const isActive = session?.state === "active";
  const title = session?.title || (sessionId ? `会话 ${shortId(sessionId)}` : "未选择会话");

  return {
    session, error, pendingCount, isActive, title,
    refresh, queueRequest, recordResult, close, retryPending,
  };
}

/* ===== helpers ===== */

function loadPending(): PendingCommand[] {
  try {
    const raw = localStorage.getItem(PENDING_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr : [];
  } catch {
    return [];
  }
}

function uuid(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  return [...bytes].map(b => b.toString(16).padStart(2, "0")).join("");
}

function shortId(id: string): string {
  return id.length > 10 ? `${id.slice(0, 6)}…${id.slice(-3)}` : id;
}
