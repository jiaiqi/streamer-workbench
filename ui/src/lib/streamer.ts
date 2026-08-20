/// Electron preload 暴露的 window.streamer API 类型 —— 单一来源。
///
/// 浏览器中 window.streamer 不存在 → 走 <a download> / 降级路径。
/// Electron 中 window.streamer 存在 → IPC 调主进程原生能力。
///
/// 所有需要调用 Electron 能力的模块必须从这里 import 类型，
/// 不再各文件 declare global 重复声明。
///
/// 主进程 + preload 实际暴露的方法以 electron/preload/*.js 为准。

export interface SaveFileParams {
  data: ArrayBuffer;
  defaultName: string;
  mimeType?: string;
}

export interface SaveFileResult {
  ok: boolean;
  path?: string;
  cancelled?: boolean;
  error?: string;
}

export interface QuickLookParams {
  data: ArrayBuffer;
  posterId?: string;
}

export interface QuickLookResult {
  ok: boolean;
  code?: string;
  error?: string;
  path?: string;
}

export interface RevealInFinderParams {
  filePath: string;
}

export interface RevealInFinderResult {
  ok: boolean;
  error?: string;
}

export interface ShareToMacOSParams {
  data: ArrayBuffer;
  defaultName?: string;
}

export interface ShareToMacOSResult {
  ok: boolean;
  code?: string;
  error?: string;
}

export interface CopyImageToClipboardParams {
  data: ArrayBuffer;
}

export interface CopyImageToClipboardResult {
  ok: boolean;
  error?: string;
}

export interface NotifyParams {
  title?: string;
  body?: string;
  tag?: string;
}

export interface NotifyResult {
  ok: boolean;
}

export interface RecordingSource {
  id: string;
  name: string;
  thumbnail?: string;
}

export interface RecordingStartOpts {
  sourceId: string;
  includeAudio: boolean;
  /** 会话 ID；缺省 = 直播场次 id；纯弹唱 = null */
  sessionId?: string | null;
  /** LRC 行变化事件队列（来自 LRC 解析） */
  lrcEvents?: Array<{ timeMs: number; text: string }>;
}

export interface RecordingLrcEvent {
  timeMs: number;
  text: string;
}

export interface RecordingFileInfo {
  filename: string;
  size: number;
  startedAt: number;
  durationMs: number;
  hasSrt: boolean;
}

export interface RecordingSession {
  sessionId: string | null;
  files: RecordingFileInfo[];
}

export interface RecordingState {
  status: "idle" | "starting" | "recording" | "paused" | "stopping" | "stopped" | "unsupported" | "error";
  id: string | null;
  startedAt: number | null;
  pausedAt: number | null;
  elapsedMs: number;
  currentBytes: number;
  totalBytes: number;
  segmentIndex: number;
  errorMessage?: string;
  permissionDenied?: boolean;
}

/**
 * P0-2: 主进程返回的 API 配置。
 * - baseUrl：Python 后端完整 origin（http://localhost:8765 等）；
 * - sessionToken：packaged mode 必填；dev mode 为空字符串（origin 白名单兜底）。
 * 渲染层 mutate 请求走 client.ts，由它统一注入 X-Streamer-Session；
 * 组件自身不要用 fetch() + 自行塞 token。
 */
export interface ApiConfig {
  baseUrl: string;
  sessionToken: string;
}

/**
 * 主进程实际暴露的 IPC 能力集合。全部可选（浏览器模式 streamer 不存在）。
 * 各模块按需取用对应字段，不要假定全有。
 */
export interface StreamerApi {
  // 速查窗口
  openQuickView?(sessionId?: string): Promise<{ ok: boolean }>;
  closeQuickView?(): Promise<{ ok: boolean }>;
  onQuickViewSession?(listener: (sessionId: string) => void): () => void;

  // 文件保存 / Finder / Quick Look
  saveFile?(params: SaveFileParams): Promise<SaveFileResult>;
  revealInFinder?(params: RevealInFinderParams): Promise<RevealInFinderResult>;
  quickLookPoster?(params: QuickLookParams): Promise<QuickLookResult>;
  isQuickLookSupported?(): boolean;

  // 海报分享（M2.16）
  copyImageToClipboard?(params: CopyImageToClipboardParams): Promise<CopyImageToClipboardResult>;
  shareToMacOS?(params: ShareToMacOSParams): Promise<ShareToMacOSResult>;
  isMacOSShareSupported?(): boolean;

  // 系统通知 / 媒体控制（M2.13）
  sendPlayerState?(state: Record<string, unknown>): void;
  onPlayerControl?(listener: (cmd: string) => void): () => void;
  notify?(opts: NotifyParams): Promise<NotifyResult>;
  getPlayerState?(): Promise<Record<string, unknown>>;

  // P0-2: API 配置（baseUrl + sessionToken）
  getApiConfig?(): Promise<ApiConfig>;

  // 录屏（R8.2.x）
  listRecordingSources?(): Promise<RecordingSource[]>;
  startRecording?(opts: RecordingStartOpts): Promise<RecordingState>;
  pauseRecording?(id: string): Promise<RecordingState>;
  resumeRecording?(id: string): Promise<RecordingState>;
  appendRecordingLrc?(id: string, events: RecordingLrcEvent[]): Promise<{ ok: boolean; appended: number }>;
  stopRecording?(id: string): Promise<RecordingState>;
  getRecordingState?(id: string | null): Promise<RecordingState>;
  listRecordingFiles?(sessionId: string | null): Promise<RecordingFileInfo[]>;
  listRecordingSessions?(): Promise<RecordingSession[]>;
  deleteRecording?(sessionId: string): Promise<{ ok: boolean; deleted: number }>;
}

declare global {
  interface Window {
    streamer?: StreamerApi;
    /** LiveView 推送的队列数（M2.13 dock badge 桥接） */
    __liveQueueCount?: number;
  }
}

export {};
