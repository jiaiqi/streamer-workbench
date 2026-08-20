/// P1 R1a.5 海报文档状态机 hook。
///
/// 单一文档状态机：
///   - current: 当前正在编辑的 PosterRequest
///   - revision: 服务端 CAS 字符串
///   - status: idle | dirty | saving | saved | error
///   - lastSavedAt: 最近一次服务端确认时间戳
///   - past[]: 撤销栈 (P2 R4)
///   - future[]: 重做栈 (P2 R4)
///
/// 防抖：750ms 累积后 coalesce 一次 save。
/// 卸载前 flush（避免最后 1 秒变更丢失）。
/// 切换文档时先 flush 旧文档再切。
///
/// 撤销/重做（P2 R4）：
///   - 每次 update() 把变更前的快照入 past, 清空 future
///   - undo() 弹出 past → current, 当前 → future
///   - redo() 弹出 future → current, 当前 → past
///   - select() / newDraft() 清空两个栈 (跨文档撤销无意义)
///   - 栈深度上限 50 (防内存膨胀)
///
/// 竞态：
///   - in-flight 请求用 AbortController；切换/卸载时 abort 旧请求。
///   - inFlightRevisionRef 防旧响应回填；revision 与当前不符则丢弃。
///
/// 设计：用 ref 同步维护 current / revision 副本，保证
/// 防抖队列触发 save 时永远用最新值（不依赖 useCallback 闭包）。
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  batchPosters,
  deletePoster,
  getPoster,
  listPosters,
  savePoster,
  type PosterBatchAction,
  type PosterBatchResponse,
} from "../api/posters";
import type {
  PosterRequest,
  PosterSaveResponse,
  PosterSummaryResponse,
} from "../api/generated";
import { isAbortError, toRequestFailure, type RequestFailure } from "../async/requestState";
import { apiRequest } from "../api/client";

const AUTOSAVE_DEBOUNCE_MS = 750;
const HISTORY_LIMIT = 50;

function makeEmptyPosterRequest(): PosterRequest {
  return {
    name: "未命名海报",
    song_source: { type: "all_active", artists: [] },
    selected_song_ids: [],
    grouping: "none",
    sorting: "manual",
    layout_id: "grid-wrap",
    theme_id: "海洋柔光",
    canvas_id: "9:20",
    page_policy: { mode: "legacy-fixed-2" },
    parameters: {},
    export_settings: {
      format: "png",
      jpeg_quality: 92,
      single_page: false,
      dpi: 144,
    },
  };
}

export type PosterStatus = "idle" | "dirty" | "saving" | "saved" | "error";

export interface PosterStoreState {
  current: PosterRequest;
  revision: string;
  status: PosterStatus;
  lastSavedAt: number | null;
  error: RequestFailure | null;
  /** 撤销栈深度（UI 显示「撤销 N 次」之类）。 */
  canUndo: boolean;
  /** 重做栈深度。 */
  canRedo: boolean;
}

export interface PosterStoreActions {
  posters: PosterSummaryResponse[];
  refreshList: () => Promise<void>;
  select: (posterId: string) => Promise<void>;
  newDraft: () => void;
  update: (patch: Partial<PosterRequest>) => void;
  saveNow: () => Promise<PosterSaveResponse | null>;
  flush: () => Promise<void>;
  deleteCurrent: () => Promise<void>;
  /** M3 P0: inline 重命名（PATCH /api/posters/{id}/name）。返回新名。 */
  rename: (name: string) => Promise<string | null>;
  /** M3 P0: 复制当前海报（POST /api/posters/{id}/duplicate）。返回新 id。 */
  duplicate: () => Promise<string | null>;
  /** M3 P1: 批量操作（POST /api/posters/batch）。返回响应（含 failed 数组）。 */
  batch: (action: PosterBatchAction, ids: string[], theme?: string) => Promise<PosterBatchResponse | null>;
  cancel: () => void;
  resetError: () => void;
  /** 撤销最近一次用户修改（自动保存防抖队列会被清掉避免覆盖撤销状态）。 */
  undo: () => void;
  /** 重做最近一次撤销。 */
  redo: () => void;
  /** 当前是否处于 dirty/saving/error 任意非稳定状态（用于 UI 守卫）。 */
  isDirty: boolean;
}

export type PosterStore = PosterStoreState & PosterStoreActions;

export function usePosterStore(): PosterStore {
  const [posters, setPosters] = useState<PosterSummaryResponse[]>([]);
  const [current, setCurrent] = useState<PosterRequest>(() => makeEmptyPosterRequest());
  const [revision, setRevision] = useState<string>("");
  const [status, setStatus] = useState<PosterStatus>("idle");
  const [lastSavedAt, setLastSavedAt] = useState<number | null>(null);
  const [error, setError] = useState<RequestFailure | null>(null);
  // P2 R4: 撤销/重做栈
  const [past, setPast] = useState<PosterRequest[]>([]);
  const [future, setFuture] = useState<PosterRequest[]>([]);

  const abortRef = useRef<AbortController | null>(null);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  /** 最新值 ref 同步——避免 useCallback 闭包陈旧问题。 */
  const currentRef = useRef<PosterRequest>(current);
  const revisionRef = useRef<string>(revision);
  /** 当前 in-flight 请求的 expected revision；旧响应按此比对丢弃。 */
  const inFlightTokenRef = useRef<string | null>(null);
  /** true → 用户已修改但尚未成功保存（防抖队列已排队或正在 save） */
  const pendingDirtyRef = useRef<boolean>(false);
  /** 卸载标记：避免组件卸载后 setState */
  const mountedRef = useRef<boolean>(true);

  useEffect(() => { currentRef.current = current; }, [current]);
  useEffect(() => { revisionRef.current = revision; }, [revision]);

  useEffect(() => () => { mountedRef.current = false; }, []);

  const safeSetStatus = (next: PosterStatus) => {
    if (mountedRef.current) setStatus(next);
  };
  const safeSetError = (e: RequestFailure | null) => {
    if (mountedRef.current) setError(e);
  };
  const safeSetRevision = (r: string) => {
    if (mountedRef.current) {
      setRevision(r);
      revisionRef.current = r;
    }
  };
  const safeSetCurrent = (nextOrUpdater: PosterRequest | ((prev: PosterRequest) => PosterRequest)) => {
    if (mountedRef.current) {
      setCurrent(prev =>
        typeof nextOrUpdater === "function"
          ? (nextOrUpdater as (p: PosterRequest) => PosterRequest)(prev)
          : (nextOrUpdater as PosterRequest)
      );
    }
  };
  const safeSetLastSavedAt = (t: number | null) => {
    if (mountedRef.current) setLastSavedAt(t);
  };

  const cancel = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }
  }, []);

  const refreshList = useCallback(async () => {
    try {
      const items = await listPosters();
      if (mountedRef.current) setPosters(items);
    } catch (reason) {
      if (isAbortError(reason)) return;
      console.warn("poster list refresh failed:", reason);
    }
  }, []);

  const doSave = useCallback(async (
    snapshot: PosterRequest,
    expectedRevision: string,
  ): Promise<PosterSaveResponse | null> => {
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const token = expectedRevision || "__new__";
    inFlightTokenRef.current = token;
    pendingDirtyRef.current = false;

    safeSetStatus("saving");
    safeSetError(null);

    try {
      const res = await savePoster(snapshot);
      // CAS: 如果已经发起新的 save 或被切到别的文档，丢弃此结果
      if (inFlightTokenRef.current !== token) {
        safeSetStatus("dirty");
        return null;
      }
      safeSetRevision(res.revision || "");
      safeSetCurrent(prev => ({ ...prev, id: res.id }));
      safeSetLastSavedAt(Date.now());
      safeSetStatus("saved");
      void refreshList();
      return res;
    } catch (reason) {
      if (isAbortError(reason)) return null;
      // CAS 冲突（409）：本地仍 dirty，让用户决定
      const failure = toRequestFailure(reason, "保存失败");
      safeSetError(failure);
      safeSetStatus("error");
      pendingDirtyRef.current = true;
      return null;
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
    }
  }, [refreshList]);

  const scheduleAutosave = useCallback(() => {
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      debounceTimerRef.current = null;
      void doSave(currentRef.current, revisionRef.current);
    }, AUTOSAVE_DEBOUNCE_MS);
  }, [doSave]);

  const update = useCallback((patch: Partial<PosterRequest>) => {
    // P2 R4: 在变更之前把当前快照入 past 栈, 清空 future
    // 深度上限 HISTORY_LIMIT, 超长截断最早的条目
    setPast(prev => {
      const snapshot = { ...currentRef.current };
      const next = [...prev, snapshot];
      if (next.length > HISTORY_LIMIT) next.shift();
      return next;
    });
    setFuture([]);

    safeSetCurrent(prev => {
      const next: PosterRequest = {
        ...prev,
        ...patch,
        song_source: patch.song_source
          ? { ...prev.song_source, ...patch.song_source }
          : prev.song_source,
        page_policy: patch.page_policy
          ? { ...prev.page_policy, ...patch.page_policy }
          : prev.page_policy,
        export_settings: patch.export_settings
          ? { ...prev.export_settings, ...patch.export_settings }
          : prev.export_settings,
      };
      return next;
    });
    pendingDirtyRef.current = true;
    safeSetStatus("dirty");
    scheduleAutosave();
  }, [scheduleAutosave]);

  // P2 R4: 撤销 / 重做
  const undo = useCallback(() => {
    if (past.length === 0) return;
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }
    const target = past[past.length - 1];
    const newPast = past.slice(0, -1);
    const newFuture = [...future, currentRef.current];
    currentRef.current = target;
    setPast(newPast);
    setFuture(newFuture);
    if (mountedRef.current) setCurrent(target);
    safeSetStatus("dirty");
    pendingDirtyRef.current = true;
    scheduleAutosave();
    // 注意: 这里依赖 past/future state, 用 useEffect [past,future,...] 重算 deps
  }, [past, future, scheduleAutosave]);

  const redo = useCallback(() => {
    if (future.length === 0) return;
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }
    const target = future[future.length - 1];
    const newFuture = future.slice(0, -1);
    const newPast = [...past, currentRef.current];
    currentRef.current = target;
    setPast(newPast);
    setFuture(newFuture);
    if (mountedRef.current) setCurrent(target);
    safeSetStatus("dirty");
    pendingDirtyRef.current = true;
    scheduleAutosave();
  }, [past, future, scheduleAutosave]);

  const saveNow = useCallback(async () => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }
    return await doSave(currentRef.current, revisionRef.current);
  }, [doSave]);

  const flush = useCallback(async () => {
    if (pendingDirtyRef.current) {
      await saveNow();
    }
  }, [saveNow]);

  const select = useCallback(async (posterId: string) => {
    // 先 flush（避免覆盖未保存内容）
    if (pendingDirtyRef.current) {
      await saveNow();
    }
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    // P2 R4: 切换文档清空历史栈
    setPast([]);
    setFuture([]);

    safeSetStatus("dirty");
    try {
      const poster = await getPoster(posterId);
      if (controller.signal.aborted) return;
      const rev = poster.revision || "";
      safeSetCurrent({
        name: poster.name || "未命名海报",
        song_source: poster.song_source,
        selected_song_ids: poster.selected_song_ids ?? [],
        grouping: poster.grouping,
        sorting: poster.sorting,
        layout_id: poster.layout_id,
        theme_id: poster.theme_id,
        canvas_id: poster.canvas_id,
        page_policy: poster.page_policy,
        parameters: poster.parameters ?? {},
        export_settings: poster.export_settings,
        id: poster.id,
      });
      safeSetRevision(rev);
      safeSetLastSavedAt(poster.updated_at ? Date.parse(poster.updated_at) : null);
      safeSetStatus("saved");
      safeSetError(null);
    } catch (reason) {
      if (isAbortError(reason)) return;
      safeSetError(toRequestFailure(reason, "加载海报失败"));
      safeSetStatus("error");
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
    }
  }, [saveNow]);

  const newDraft = useCallback(() => {
    cancel();
    // P2 R4: 新草稿清空历史
    setPast([]);
    setFuture([]);
    safeSetCurrent(makeEmptyPosterRequest());
    safeSetRevision("");
    pendingDirtyRef.current = false;
    safeSetLastSavedAt(null);
    safeSetStatus("idle");
    safeSetError(null);
    revisionRef.current = "";
  }, [cancel]);

  const deleteCurrent = useCallback(async () => {
    const id = currentRef.current.id;
    if (!id) return;
    try {
      await deletePoster(id);
      void refreshList();
      newDraft();
    } catch (reason) {
      if (isAbortError(reason)) return;
      safeSetError(toRequestFailure(reason, "删除失败"));
    }
  }, [refreshList, newDraft]);

  // M3 P0: inline 重命名（PATCH /api/posters/{id}/name）
  const rename = useCallback(async (name: string) => {
    const id = currentRef.current.id;
    if (!id) return null;
    const trimmed = name.trim();
    if (!trimmed) {
      safeSetError(toRequestFailure(new Error("名称不能为空"), "重命名失败"));
      return null;
    }
    try {
      const res = await apiRequest<{ ok: boolean; id: string;
                                     revision: string; name: string }>(
        `/api/posters/${id}/name`,
        { method: "PATCH", body: { name: trimmed } },
      );
      // 更新列表中的 name + 当前 poster 缓存
      setPosters(prev => prev.map(p => p.id === id
        ? { ...p, name: trimmed, updated_at: new Date().toISOString() }
        : p));
      setCurrent(prev => prev ? { ...prev, name: trimmed } : prev);
      return trimmed;
    } catch (reason) {
      if (isAbortError(reason)) return null;
      safeSetError(toRequestFailure(reason, "重命名失败"));
      return null;
    }
  }, []);

  // M3 P0: 复制当前海报（POST /api/posters/{id}/duplicate）
  const duplicate = useCallback(async () => {
    const id = currentRef.current.id;
    if (!id) return null;
    try {
      const res = await apiRequest<{ ok: boolean; id: string;
                                     revision: string; updated_at: string }>(
        `/api/posters/${id}/duplicate`,
        { method: "POST" },
      );
      // 刷新列表（让新副本可见）+ 切到新副本
      await refreshList();
      await select(res.id);
      return res.id;
    } catch (reason) {
      if (isAbortError(reason)) return null;
      safeSetError(toRequestFailure(reason, "复制失败"));
      return null;
    }
  }, [refreshList, select]);

  // M3 P1: 批量操作（POST /api/posters/batch）
  const batch = useCallback(async (
    action: PosterBatchAction,
    ids: string[],
    theme?: string,
  ): Promise<PosterBatchResponse | null> => {
    if (!ids || ids.length === 0) return null;
    try {
      const res = await batchPosters({ action, ids, theme });
      // 失败明细写到 store.error 便于 UI 展示
      if (res.failed && res.failed.length > 0) {
        const ok = res.deleted ?? res.duplicated ?? res.updated ?? 0;
        if (ok === 0) {
          safeSetError(toRequestFailure(
            new Error(`${ids.length} 个全部失败：${res.failed[0]?.error}`),
            `批量${action}失败`,
          ));
        }
      }
      // 列表必刷新（删除/复制/换主题都改 list）
      await refreshList();
      // 若当前被删，切到草稿
      if (action === "delete" && currentRef.current.id &&
          ids.includes(currentRef.current.id)) {
        newDraft();
      }
      return res;
    } catch (reason) {
      if (isAbortError(reason)) return null;
      safeSetError(toRequestFailure(reason, `批量${action}失败`));
      return null;
    }
  }, [refreshList, newDraft]);

  const resetError = useCallback(() => safeSetError(null), []);

  useEffect(() => {
    void refreshList();
  }, [refreshList]);

  // 卸载前 flush
  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
        debounceTimerRef.current = null;
      }
      if (pendingDirtyRef.current && mountedRef.current === false) {
        // 组件卸载阶段；fire-and-forget（不 await）
        void doSave(currentRef.current, revisionRef.current).catch(() => undefined);
      }
    };
  }, [doSave]);

  const isDirty = status === "dirty" || status === "saving" || status === "error";
  const canUndo = past.length > 0;
  const canRedo = future.length > 0;

  return useMemo(() => ({
    current, revision, status, lastSavedAt, error,
    canUndo, canRedo,
    posters,
    refreshList, select, newDraft, update, saveNow, flush, deleteCurrent,
    rename, duplicate,  // M3 P0
    batch,              // M3 P1
    cancel, resetError, undo, redo, isDirty,
  }), [
    current, revision, status, lastSavedAt, error,
    canUndo, canRedo,
    posters, refreshList, select, newDraft, update, saveNow, flush,
    deleteCurrent, rename, duplicate, batch,
    cancel, resetError, undo, redo, isDirty,
  ]);
}
