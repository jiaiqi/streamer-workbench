/// R4.0.10 App.tsx 拆解 — 工作台状态机 hook。
///
/// 抽离 App.tsx 中工作台视图专属的 11 个 useState + 4 个 useEffect：
///   - 资源加载：themes / layouts / paramSpecs / columnTemplates
///   - 选区：selTheme / page / avoid / canvas / zoom / params
///   - 渲染态：renderKey / lastRenderMs / loading / previewError / hasFrame
///   - 派生：previewSrc / previewKey / activeTheme / maxPage / paramsQuery
///   - 持久化：localStorage `sw-workspace`（兼容读旧 key `gp-workspace`）
///   - 防抖：params → debouncedParams（300ms）
///   - 加载守卫：previewSrc 变化时自动进入 loading
///
/// 不在本 hook：
///   - view 路由（App 级）
///   - 外观 / 暗色模式（App 级，跨视图共享）
///   - ExportDialog / LibraryDialog open 状态（App 级，跨视图）
///   - songStats（App 级，由 LibraryView / LearningView 上报）
///   - 快捷键（App 级，跨视图守卫）
///
/// 删了 v3 路线图遗留的 `selLayout` 死代码 + 修复 layout_id 跟 usePosterStore 不同步的 bug
/// （R4.1.8 一并收口）：layout_id 由父组件从 usePosterStore.current.layout_id 注入。
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import type { ColumnTemplate, Layout, ParamSpec, Settings, Theme } from "../types";
import { apiRequest } from "../api/client";

const STORAGE_KEY = "sw-workspace";
const LEGACY_STORAGE_KEY = "gp-workspace"; // 兼容 v3 时期 localStorage
const PARAMS_DEBOUNCE_MS = 300;

interface PersistedSnapshot {
  selTheme?: string;
  page?: number;
  canvas?: string;
  avoid?: boolean;
  params?: Record<string, unknown>;
}

function loadPersisted(): PersistedSnapshot {
  if (typeof localStorage === "undefined") return {};
  try {
    const raw = localStorage.getItem(STORAGE_KEY) ?? localStorage.getItem(LEGACY_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as PersistedSnapshot;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function savePersisted(snapshot: PersistedSnapshot): void {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
  } catch {
    /* localStorage 满或被禁用时静默 */
  }
}

/** 解析首次启动时的 selTheme 候选：当前 state → 持久化 → settings 默认 → 第一个。 */
function resolveInitialTheme(
  themes: Theme[],
  settings: Settings,
  savedWorkspace: string | null,
  currentSel: string,
): string | null {
  if (currentSel && themes.some(t => t.name === currentSel)) return currentSel;
  if (savedWorkspace) {
    try {
      const s = JSON.parse(savedWorkspace) as PersistedSnapshot;
      if (s.selTheme && themes.some(t => t.name === s.selTheme)) return s.selTheme;
    } catch { /* ignore */ }
  }
  const def = themes.find(t => t.name === settings.default_theme);
  if (def) return def.name;
  return themes[0]?.name ?? null;
}

export interface UseWorkspaceStateOptions {
  /**
   * 当前海报文档的 layout_id（通常来自 usePosterStore.current.layout_id）。
   * 切换时 hook 会自动重新拉对应的 ParamSpec 和栏数模板。
   * 缺省走 "grid-wrap"（兼容未接入 store 的调用方）。
   */
  layoutId?: string;
}

export interface UseWorkspaceStateResult {
  // 资源
  themes: Theme[];
  layouts: Layout[];
  resourceError: string;
  setResourceError: (msg: string) => void;
  clearResourceError: () => void;
  /** 资源是否已尝试首次加载（用于跳过某些 effect 的初始空态）。 */
  resourcesReady: boolean;

  // 选区
  selTheme: string;
  /** 选主题并自动回到第 1 页（与 v3 行为一致）。 */
  selectTheme: (name: string) => void;
  page: number;
  setPage: Dispatch<SetStateAction<number>>;
  avoid: boolean;
  setAvoid: (a: boolean) => void;
  canvas: string;
  setCanvas: (c: string) => void;
  zoom: number;
  setZoom: Dispatch<SetStateAction<number>>;
  params: Record<string, unknown>;
  setParam: (key: string, value: unknown) => void;
  paramSpecs: ParamSpec[];
  columnTemplates: ColumnTemplate[];

  // 渲染态
  renderKey: number;
  /** 强制重挂预览（renderKey++）；同时清掉错误态。 */
  refresh: () => void;
  lastRenderMs: number | null;
  setLastRenderMs: (ms: number | null) => void;
  loading: boolean;
  setLoading: (v: boolean) => void;
  previewError: boolean;
  hasFrame: boolean;
  /** 预览图加载成功回调（清 loading + hasFrame=true）。 */
  markLoaded: () => void;
  /** 预览图加载失败回调（清 loading + 切 error 态）。 */
  markFailed: () => void;

  // 派生
  previewSrc: string;
  previewKey: string;
  activeTheme: Theme | undefined;
  maxPage: number;
  paramsQuery: string;
}

const INITIAL_PARAMS: Record<string, unknown> = {
  margin: 58, font_song: 36, row_h: 44, sec_gap: 26,
};

export function useWorkspaceState(options: UseWorkspaceStateOptions = {}): UseWorkspaceStateResult {
  const layoutId = options.layoutId ?? "grid-wrap";

  /* ---- 持久化：mount 时读一次 + 后续只在变化时回写 ---- */
  const persistedRef = useRef<PersistedSnapshot>(loadPersisted());
  const [restored, setRestored] = useState(false);

  /* ---- 资源 ---- */
  const [themes, setThemes] = useState<Theme[]>([]);
  const [layouts, setLayouts] = useState<Layout[]>([]);
  const [paramSpecs, setParamSpecs] = useState<ParamSpec[]>([]);
  const [columnTemplates, setColumnTemplates] = useState<ColumnTemplate[]>([]);
  const [resourceError, setResourceError] = useState("");
  const [resourcesReady, setResourcesReady] = useState(false);

  /* ---- 选区 ---- */
  const [selTheme, _setSelTheme] = useState<string>(persistedRef.current.selTheme ?? "");
  const [page, setPage] = useState<number>(persistedRef.current.page ?? 1);
  const [avoid, setAvoid] = useState<boolean>(persistedRef.current.avoid ?? true);
  const [canvas, setCanvas] = useState<string>(persistedRef.current.canvas ?? "抖音全屏 9:20");
  const [zoom, setZoom] = useState<number>(45);
  const [params, setParams] = useState<Record<string, unknown>>(() => {
    const merged: Record<string, unknown> = { ...INITIAL_PARAMS };
    if (persistedRef.current.params) {
      for (const [k, v] of Object.entries(persistedRef.current.params)) merged[k] = v;
    }
    return merged;
  });

  /* ---- 渲染态 ---- */
  const [renderKey, setRenderKey] = useState(0);
  const [lastRenderMs, setLastRenderMs] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [previewError, setPreviewError] = useState(false);
  const [hasFrame, setHasFrame] = useState(false);

  /* ---- 派生 ---- */
  const [debouncedParams, setDebouncedParams] = useState<Record<string, unknown>>(params);

  const selectTheme = useCallback((name: string) => {
    _setSelTheme(name);
    setPage(1);
  }, []);

  const setParam = useCallback((key: string, value: unknown) => {
    setParams(prev => (prev[key] === value ? prev : { ...prev, [key]: value }));
  }, []);

  const refresh = useCallback(() => {
    setLoading(true);
    setPreviewError(false);
    setRenderKey(k => k + 1);
  }, []);

  const clearResourceError = useCallback(() => setResourceError(""), []);

  const markLoaded = useCallback(() => {
    setLoading(false);
    setHasFrame(true);
  }, []);

  const markFailed = useCallback(() => {
    setLoading(false);
    setPreviewError(true);
  }, []);

  /* ---- 启动恢复标记 ---- */
  useEffect(() => {
    setRestored(true);
  }, []);

  /* ---- 启动：拉 themes / layouts / settings / 当前 layout 的 params ---- */
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const savedWorkspace = typeof localStorage !== "undefined"
          ? (localStorage.getItem(STORAGE_KEY) ?? localStorage.getItem(LEGACY_STORAGE_KEY))
          : null;
        const [settings, themeData, layoutData, specs] = await Promise.all([
          apiRequest<Settings>("/api/settings"),
          apiRequest<Theme[]>("/api/themes"),
          apiRequest<Layout[]>("/api/layouts"),
          apiRequest<ParamSpec[]>(`/api/layouts/${layoutId}/params`),
        ]);
        if (!active) return;
        if (!savedWorkspace && settings.default_canvas) setCanvas(settings.default_canvas);
        setThemes(themeData);
        setLayouts(layoutData);
        const nextTheme = resolveInitialTheme(themeData, settings, savedWorkspace, selTheme);
        if (themeData.length && nextTheme && nextTheme !== selTheme) {
          _setSelTheme(nextTheme);
          setPage(1);
        }
        setParamSpecs(specs);
        setParams(prev => {
          const merged = { ...prev };
          for (const spec of specs) if (merged[spec.key] === undefined) merged[spec.key] = spec.default;
          return merged;
        });
        setResourceError("");
        setResourcesReady(true);
      } catch (reason) {
        if (active) setResourceError(reason instanceof Error ? reason.message : "工作台资源加载失败");
      }
    })();
    return () => { active = false; };
    // 启动只跑一次；layout 变化走下方 effect
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ---- 切 layout：重新拉 params + （magazine-flow）栏数模板 ---- */
  useEffect(() => {
    if (!resourcesReady) return; // 等首次启动跑完
    let active = true;
    (async () => {
      try {
        const specs = await apiRequest<ParamSpec[]>(`/api/layouts/${layoutId}/params`);
        if (!active) return;
        setParamSpecs(specs);
        setParams(prev => {
          const merged = { ...prev };
          for (const spec of specs) if (merged[spec.key] === undefined) merged[spec.key] = spec.default;
          return merged;
        });
        if (layoutId === "magazine-flow") {
          const tpls = await apiRequest<ColumnTemplate[]>("/api/layouts/magazine-flow/templates");
          if (active) setColumnTemplates(tpls);
        } else {
          setColumnTemplates([]);
        }
      } catch (reason) {
        if (active) setResourceError(reason instanceof Error ? reason.message : "排版参数加载失败");
      }
    })();
    return () => { active = false; };
  }, [layoutId, resourcesReady]);

  /* ---- 持久化：选区变化时回写 ---- */
  useEffect(() => {
    if (!restored) return;
    savePersisted({ selTheme, page, canvas, avoid, params });
  }, [restored, selTheme, page, canvas, avoid, params]);

  /* ---- 防抖：params → debouncedParams ---- */
  useEffect(() => {
    const t = setTimeout(() => setDebouncedParams(params), PARAMS_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [params]);

  /* ---- 派生：previewSrc / previewKey / activeTheme / maxPage / paramsQuery ---- */
  const paramsQuery = useMemo(
    () => Object.entries(debouncedParams)
      .map(([k, v]) => `&${k}=${v}`)
      .join(""),
    [debouncedParams],
  );

  const previewSrc = useMemo(() => {
    if (!selTheme) return "";
    return `/api/render?theme=${encodeURIComponent(selTheme)}&page=${page}&canvas=${encodeURIComponent(canvas)}&avoid=${avoid}${paramsQuery}`;
  }, [selTheme, page, canvas, avoid, paramsQuery]);

  const previewKey = renderKey > 0 ? `k${renderKey}` : "stable";

  const activeTheme = useMemo(
    () => themes.find(t => t.name === selTheme),
    [themes, selTheme],
  );

  const maxPage = useMemo(
    () => layouts.find(l => l.id === "grid-wrap")?.pages ?? 2,
    [layouts],
  );

  return {
    // 资源
    themes, layouts, resourceError, setResourceError, clearResourceError, resourcesReady,
    // 选区
    selTheme, selectTheme, page, setPage, avoid, setAvoid, canvas, setCanvas,
    zoom, setZoom, params, setParam, paramSpecs, columnTemplates,
    // 渲染态
    renderKey, refresh, lastRenderMs, setLastRenderMs, loading, setLoading,
    previewError, hasFrame, markLoaded, markFailed,
    // 派生
    previewSrc, previewKey, activeTheme, maxPage, paramsQuery,
  };
}
