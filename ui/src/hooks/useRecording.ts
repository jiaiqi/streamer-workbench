/// R8.2.x 弹唱录屏 React hook。
///
/// 封装 streamer.recording.* IPC + LRC 字幕事件采集：
/// - 状态机：idle → starting → recording ⇄ paused → stopping → stopped
/// - 录音开始时记录 `recordingStartedAtRef`（performance.now()），所有 LRC 事件用相对 offset_ms
/// - 每 5s 调 appendRecordingLrc 把累积的 LRC 事件推到主进程
/// - usePlayerContext 跟踪 `isPlaying` / `currentTimeMs` 变化计算 LRC 行切换
///
/// 浏览器模式（无 `window.streamer`）静默 no-op：所有 API 调用 resolve null + state 保持 idle。
///
/// 重要：state 用 **module-level** 共享 — 这样顶栏红点和 Dialog 共享同一份
/// 录制状态（不双开 IPC 订阅）。每个组件调 useRecording() 拿到的 state 是
/// module store 的"投影"，setter 通过 store 派发。
import { useCallback, useEffect, useRef, useState } from "react";
import { useToast, type ToastApi } from "../components/Toast";
import { usePlayer } from "../player/PlayerContext";

// ── 类型 ──────────────────────────────────────────────────────────

export type RecordingStatus =
  | "idle"           // 未开始
  | "starting"       // 调 start IPC 中
  | "recording"      // 录制中
  | "paused"         // 暂停
  | "stopping"       // 停止中
  | "stopped"        // 已停止，等待用户关掉 dialog
  | "unsupported"    // 非 Electron / Linux
  | "error";         // 出错

export interface RecordingSource {
  id: string;
  name: string;
  isScreen: boolean;
  thumbnailDataUrl: string | null;
}

export interface RecordingFile {
  name: string;
  path: string;
  bytes: number;
  index: number;
  isSrt: boolean;
}

export interface RecordingState {
  status: RecordingStatus;
  id: string | null;
  startedAt: number | null;
  elapsedMs: number;
  currentBytes: number;
  totalBytes: number;
  segmentIndex: number;
  files: RecordingFile[];
  sourceName: string;
  outputDir: string;
  errorMessage: string;
}

// ── 工具 ──────────────────────────────────────────────────────────

const _isElectron = (): boolean =>
  typeof window !== "undefined" && !!(window as { streamer?: unknown }).streamer;

const _streamer = () =>
  ((window as { streamer?: {
    listRecordingSources: () => Promise<unknown>;
    startRecording: (opts: unknown) => Promise<unknown>;
    pauseRecording: (id: string) => Promise<unknown>;
    resumeRecording: (id: string) => Promise<unknown>;
    appendRecordingLrc: (id: string, events: unknown) => Promise<unknown>;
    stopRecording: (id: string) => Promise<unknown>;
    getRecordingState: (id: string | null) => Promise<unknown>;
    listRecordingFiles: (sid: string | null) => Promise<unknown>;
    deleteRecording: (sid: string) => Promise<unknown>;
  } }).streamer);

const _initialState: RecordingState = {
  status: "idle",
  id: null,
  startedAt: null,
  elapsedMs: 0,
  currentBytes: 0,
  totalBytes: 0,
  segmentIndex: 0,
  files: [],
  sourceName: "",
  outputDir: "",
  errorMessage: "",
};

// ── Module-level store（所有 hook 实例共享） ──────────────────────

let _storeState: RecordingState = { ..._initialState };
const _storeListeners = new Set<() => void>();

function _setStoreState(partial: Partial<RecordingState>) {
  _storeState = { ..._storeState, ...partial };
  _storeListeners.forEach(l => l());
}

function _resetStoreState() {
  _storeState = { ..._initialState };
  _storeListeners.forEach(l => l());
}

// module-level 计时器和 ref
const _tickerRef: { current: ReturnType<typeof setInterval> | null } = { current: null };
const _recordingStartedAtPerfRef: { current: number | null } = { current: null };
const _pendingLrcRef: { current: { offset_ms: number; text: string }[] } = { current: [] };
const _lastLrcIndexRef: { current: number | null } = { current: null };
const _lastAppendAtRef: { current: number } = { current: 0 };
const _activeLinesRef: { current: { time_ms: number; text: string }[] | null } = { current: null };

function _startTicker() {
  if (_tickerRef.current) return;
  _tickerRef.current = setInterval(() => {
    if (_storeState.startedAt && _storeState.status === "recording") {
      const elapsed = Date.now() - _storeState.startedAt;
      _setStoreState({ elapsedMs: elapsed });
    }
  }, 500);
}

function _stopTicker() {
  if (_tickerRef.current) {
    clearInterval(_tickerRef.current);
    _tickerRef.current = null;
  }
}

function _checkLrcChange(currentAudioMs?: number) {
  if (_storeState.status !== "recording") return;
  if (_recordingStartedAtPerfRef.current == null) return;
  const lines = _activeLinesRef.current;
  if (!lines || lines.length === 0) return;
  // 用音频 currentTimeMs（来自 PlayView timeupdate → PlayerContext）
  // fallback：录制 elapsedMs（不推荐，可能跟音频时间不一致）
  const currentTimeMs = typeof currentAudioMs === "number"
    ? currentAudioMs
    : _storeState.elapsedMs;
  let activeIdx = -1;
  for (let i = 0; i < lines.length; i++) {
    const start = lines[i]?.time_ms ?? 0;
    if (start <= currentTimeMs) activeIdx = i;
    else break;
  }
  if (activeIdx < 0) return;
  if (_lastLrcIndexRef.current === activeIdx) return;
  const offset = Date.now() - _recordingStartedAtPerfRef.current;
  const text = (lines[activeIdx]?.text ?? "").trim();
  if (text) {
    _pendingLrcRef.current.push({ offset_ms: offset, text });
  }
  _lastLrcIndexRef.current = activeIdx;
  // 限流推
  const now = Date.now();
  if (now - _lastAppendAtRef.current >= 5_000 && _storeState.id) {
    const toSend = _pendingLrcRef.current.splice(0);
    if (toSend.length > 0) {
      _streamer()?.appendRecordingLrc(_storeState.id, toSend)?.catch(() => { /* noop */ });
      _lastAppendAtRef.current = now;
    }
  }
}

// ── Hook ──────────────────────────────────────────────────────────

export interface UseRecordingOptions {
  /** 关联到 LiveView 直播 session id（用于文件夹归类） */
  linkedSessionId?: string | null;
  /** 队列项 id（仅用于 SRT 文件名前缀） */
  linkedRequestId?: string | null;
  /** LRC 行（不传则不采集字幕；PlayView 传自己的 lyricsLines） */
  lines?: { time_ms: number; text: string }[] | null;
}

export interface UseRecordingResult extends RecordingState {
  // 源
  sources: RecordingSource[];
  sourcesLoading: boolean;
  sourcesError: string;
  refreshSources: () => Promise<void>;
  // 操作
  start: (opts: { sourceId: string; includeAudio: boolean; sourceName?: string }) => Promise<boolean>;
  pause: () => Promise<void>;
  resume: () => Promise<void>;
  stop: () => Promise<RecordingFile[]>;
  reset: () => void;
  // 录制历史（completed 后可拉）
  history: RecordingFile[];
  historyDir: string;
  refreshHistory: () => Promise<void>;
  deleteHistory: (sessionId: string) => Promise<void>;
  isElectron: boolean;
}

function useStoreState(): RecordingState {
  // 首次 render 同步反映环境：浏览器模式直接 unsupported（不依赖 useEffect）
  const [s, setS] = useState<RecordingState>(() => {
    if (!_isElectron() && _storeState.status === "idle") {
      _storeState = { ..._storeState, status: "unsupported" };
    }
    return { ..._storeState };
  });
  useEffect(() => {
    const l = () => setS({ ..._storeState });
    _storeListeners.add(l);
    // 立即同步一次（防止 hook 挂载时 store 已有数据）
    l();
    return () => { _storeListeners.delete(l); };
  }, []);
  return s;
}

export function useRecording(opts: UseRecordingOptions = {}): UseRecordingResult {
  // 兼容无 Provider 的环境（单测 / 裸环境）
  // 类型用宽松形态：usePlayer() 返回 PlayerState & PlayerActions（含 PlayerMode 联合类型），
  // 但内部不调用 player.setMode / setCurrent 等敏感方法，仅读 currentTimeMs/isPlaying，
  // 所以这里用 unknown-ish 兜底 + 类型断言
  let player: {
    currentSongId?: string | null; mode?: string; isPlaying?: boolean;
    currentTimeMs?: number;
    setCurrent?: (id: string | null) => void;
    setMode?: (m: string) => void;
    setPlaying?: (b: boolean) => void;
    setCurrentTime?: (ms: number) => void;
    lines?: { time_ms: number; text: string }[] | null;
  };
  try {
    player = usePlayer() as typeof player;
  } catch {
    player = { currentTimeMs: 0, isPlaying: false, lines: [] };
  }
  let toast: ToastApi;
  try {
    toast = useToast();
  } catch {
    const noop = (): string => "";
    toast = {
      show: noop,
      error: noop,
      success: noop,
      warn: noop,
      warning: noop,
      info: noop,
      dismiss: () => undefined,
      clear: () => undefined,
    };
  }

  const state = useStoreState();
  const [sources, setSources] = useState<RecordingSource[]>([]);
  const [sourcesLoading, setSourcesLoading] = useState(false);
  const [sourcesError, setSourcesError] = useState("");
  const [history, setHistory] = useState<RecordingFile[]>([]);
  const [historyDir, setHistoryDir] = useState("");

  // 同步 LRC 行（供 LRC 切换检测用）
  useEffect(() => {
    _activeLinesRef.current = opts.lines ?? null;
  }, [opts.lines]);

  // 启动时拉当前活跃录制（如果之前窗口没关还在录）
  useEffect(() => {
    if (!_isElectron()) {
      _setStoreState({ status: "unsupported" });
      return;
    }
    void _streamer()?.getRecordingState(null)?.then((res: unknown) => {
      const r = res as { ok?: boolean; active?: null; id?: string;
        startedAt?: number; status?: string;
        elapsedMs?: number; totalBytes?: number; segmentIndex?: number;
        files?: { name: string; path: string; bytes: number;
          index: number; isSrt: boolean }[];
        sourceName?: string; outputDir?: string } | null;
      if (r?.ok && r.id) {
        _setStoreState({
          status: (r.status as RecordingStatus) || "recording",
          id: r.id,
          startedAt: r.startedAt ?? null,
          elapsedMs: r.elapsedMs ?? 0,
          totalBytes: r.totalBytes ?? 0,
          segmentIndex: r.segmentIndex ?? 0,
          files: r.files || [],
          sourceName: r.sourceName ?? "",
          outputDir: r.outputDir ?? "",
          errorMessage: "",
        });
        if (r.startedAt) {
          _recordingStartedAtPerfRef.current = Date.now() - (r.elapsedMs ?? 0);
        }
        _startTicker();
      }
    }).catch(() => { /* noop */ });
    return () => { _stopTicker(); };
  }, []);

  // 监听 player 行变化 → 触发 LRC 切换检测
  useEffect(() => {
    if (opts.lines) {
      _activeLinesRef.current = opts.lines;
    } else if (player && Array.isArray((player as { lines?: unknown }).lines)) {
      _activeLinesRef.current = (player as {
        lines: { time_ms: number; text: string }[] | null;
      }).lines;
    }
  }, [player, opts.lines]);

  // LRC 行变化时记录事件（订阅 player.currentTimeMs）
  useEffect(() => {
    if (state.status !== "recording") return;
    _checkLrcChange(player.currentTimeMs);
  }, [player.currentTimeMs, state.status]);

  const refreshSources = useCallback(async () => {
    if (!_isElectron()) {
      setSources([]);
      setSourcesError("非 Electron 模式");
      return;
    }
    setSourcesLoading(true);
    setSourcesError("");
    try {
      const res = (await _streamer()?.listRecordingSources()) as
        { ok: boolean; platform?: string; sources?: RecordingSource[];
          code?: string; error?: string } | null;
      if (res?.ok) {
        setSources(res.sources || []);
      } else {
        setSourcesError(res?.error || res?.code || "列出源失败");
        setSources([]);
      }
    } catch (err) {
      setSourcesError(err instanceof Error ? err.message : String(err));
      setSources([]);
    } finally {
      setSourcesLoading(false);
    }
  }, []);

  const start = useCallback(async (startOpts: {
    sourceId: string; includeAudio: boolean; sourceName?: string;
  }): Promise<boolean> => {
    if (!_isElectron()) {
      toast.error("当前不在 Electron 桌面模式", "请用 desktop shell 启动才能录屏");
      return false;
    }
    _setStoreState({ status: "starting", errorMessage: "" });
    try {
      const res = (await _streamer()?.startRecording({
        sourceId: startOpts.sourceId,
        sourceName: startOpts.sourceName,
        includeAudio: startOpts.includeAudio,
        sessionId: opts.linkedSessionId || undefined,
      })) as { ok: boolean; id?: string; startedAt?: number; outputDir?: string;
        code?: string; error?: string } | null;
      if (res?.ok && res.id) {
        const perfNow = Date.now();
        _recordingStartedAtPerfRef.current = perfNow;
        _pendingLrcRef.current = [];
        _lastLrcIndexRef.current = null;
        _lastAppendAtRef.current = perfNow;
        _setStoreState({
          status: "recording",
          id: res.id,
          startedAt: res.startedAt ?? perfNow,
          elapsedMs: 0,
          currentBytes: 0,
          totalBytes: 0,
          segmentIndex: 0,
          files: [],
          sourceName: startOpts.sourceName ?? "",
          outputDir: res.outputDir ?? "",
          errorMessage: "",
        });
        _startTicker();
        toast.success("开始录制", "● 顶栏红点 + 计时器已启动");
        return true;
      } else {
        const code = res?.code || "internal";
        const msg = res?.error || "启动失败";
        _setStoreState({ status: "error", errorMessage: `${code}: ${msg}` });
        toast.error("启动录制失败", msg);
        return false;
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      _setStoreState({ status: "error", errorMessage: msg });
      toast.error("启动录制异常", msg);
      return false;
    }
  }, [toast, opts.linkedSessionId]);

  const pause = useCallback(async () => {
    if (!state.id) return;
    await _streamer()?.pauseRecording(state.id)?.catch(() => { /* noop */ });
    _setStoreState({ status: "paused" });
  }, [state.id]);

  const resume = useCallback(async () => {
    if (!state.id) return;
    await _streamer()?.resumeRecording(state.id).catch(() => { /* noop */ });
    _setStoreState({ status: "recording" });
  }, [state.id]);

  const stop = useCallback(async (): Promise<RecordingFile[]> => {
    if (!state.id) return [];
    _setStoreState({ status: "stopping" });
    if (_pendingLrcRef.current.length > 0) {
      await _streamer()?.appendRecordingLrc(
        state.id, _pendingLrcRef.current.splice(0),
      ).catch(() => { /* noop */ });
    }
    try {
      const res = (await _streamer()?.stopRecording(state.id)) as
        { ok: boolean; files?: RecordingFile[]; code?: string; error?: string } | null;
      if (res?.ok) {
        const files = res.files || [];
        _setStoreState({ status: "stopped", files });
        _recordingStartedAtPerfRef.current = null;
        _stopTicker();
        toast.success("录制已停止", `${files.length} 个文件`);
        return files;
      } else {
        toast.error("停止失败", res?.error || res?.code || "");
        _setStoreState({ status: "error",
          errorMessage: res?.error || res?.code || "" });
        return [];
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error("停止异常", msg);
      _setStoreState({ status: "error", errorMessage: msg });
      return [];
    }
  }, [state.id, toast]);

  const reset = useCallback(() => {
    _resetStoreState();
    _recordingStartedAtPerfRef.current = null;
    _pendingLrcRef.current = [];
    _lastLrcIndexRef.current = null;
    _stopTicker();
  }, []);

  const refreshHistory = useCallback(async () => {
    if (!_isElectron()) return;
    const sid = opts.linkedSessionId || null;
    const res = (await _streamer()?.listRecordingFiles(sid)) as
      { ok: boolean; files?: RecordingFile[]; dir?: string;
        code?: string; error?: string } | null;
    if (res?.ok) {
      setHistory(res.files || []);
      setHistoryDir(res.dir || "");
    }
  }, [opts.linkedSessionId]);

  const deleteHistory = useCallback(async (sessionId: string) => {
    await _streamer()?.deleteRecording(sessionId).catch(() => { /* noop */ });
    await refreshHistory();
  }, [refreshHistory]);

  return {
    ...state,
    sources,
    sourcesLoading,
    sourcesError,
    refreshSources,
    start,
    pause,
    resume,
    stop,
    reset,
    history,
    historyDir,
    refreshHistory,
    deleteHistory,
    isElectron: _isElectron(),
  };
}

// ── helper: 格式化 ms 为 mm:ss / hh:mm:ss ──

/** 测试用：重置 module-level store + 所有 ref。 */
export function __resetRecordingStore() {
  _resetStoreState();
  _recordingStartedAtPerfRef.current = null;
  _pendingLrcRef.current = [];
  _lastLrcIndexRef.current = null;
  _lastAppendAtRef.current = 0;
  _activeLinesRef.current = null;
  _stopTicker();
}

/// 轻量级「只读」hook：只取 store state，不开 IPC、不接 Player。
/// 用于顶栏红点按钮（PlayView 渲染时显示当前录制状态）。
export function useRecordingIndicator(): {
  status: RecordingStatus;
  elapsedMs: number;
  isElectron: boolean;
} {
  const state = useStoreState();
  return {
    status: state.status,
    elapsedMs: state.elapsedMs,
    isElectron: _isElectron(),
  };
}

export function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

