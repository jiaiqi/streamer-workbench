/// P1 R1a.5 海报文档状态机 hook。
///
/// 单一文档状态机：
///   - current: 当前正在编辑的 PosterRequest
///   - revision: 服务端 CAS 字符串
///   - status: idle | dirty | saving | saved | error
///   - lastSavedAt: 最近一次服务端确认时间戳
///
/// 防抖：750ms 累积后 coalesce 一次 save。
/// 卸载前 flush（避免最后 1 秒变更丢失）。
/// 切换文档时先 flush 旧文档再切。
///
/// 竞态：
///   - in-flight 请求用 AbortController；切换/卸载时 abort 旧请求。
///   - inFlightRevisionRef 防旧响应回填；revision 与当前不符则丢弃。
///
/// 设计：用 ref 同步维护 current / revision 副本，保证
/// 防抖队列触发 save 时永远用最新值（不依赖 useCallback 闭包）。
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  deletePoster,
  getPoster,
  listPosters,
  savePoster,
} from "../api/posters";
import type {
  PosterRequest,
  PosterSaveResponse,
  PosterSummaryResponse,
} from "../api/generated";
import { isAbortError, toRequestFailure, type RequestFailure } from "../async/requestState";

const AUTOSAVE_DEBOUNCE_MS = 750;

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
  cancel: () => void;
  resetError: () => void;
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

  return useMemo(() => ({
    current, revision, status, lastSavedAt, error,
    posters,
    refreshList, select, newDraft, update, saveNow, flush, deleteCurrent,
    cancel, resetError, isDirty,
  }), [
    current, revision, status, lastSavedAt, error,
    posters, refreshList, select, newDraft, update, saveNow, flush,
    deleteCurrent, cancel, resetError, isDirty,
  ]);
}
