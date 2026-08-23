/// P1-A3.1 LiveShell 总闸 — LiveView 顶栏 3 动作按钮 + 联动徽标
///
/// 三步走第一步：让用户进入 LiveView 后明确知道
///   1. 自己现在在哪个窗口（主控制台 / 速查窗口 / 弹唱屏）
///   2. 当前直播场次摘要（标题 + 队列长度）
///   3. 三个动作按钮（主控制台 / 速查 / 弹唱）+ 联动徽标
///
/// 设计原则：
///   - LiveShell 只消费 prop，不自己调 API；activeSession / queueSize 由 LiveView 提
///   - 弹唱联动时显示「🔗 联动中 · {requester} · 关闭」红色徽标
///   - 速查按钮在 Electron 模式下高亮可用，浏览器模式 disabled + tooltip
///   - A3.2 / A3.3 完整重构前，A3.1 只做顶栏；不重复造现有逻辑
///
/// 范围边界：
///   - 不动后端
///   - 不动 Python / core/
///   - 不动 PlayView / QuickView 内部
import { isElectron } from "../electron-bridge";

export interface LiveShellPlayLinkInfo {
  sessionId: string;
  requestId: string;
  requesterName: string;
  songId: string;
}

export interface LiveShellProps {
  /** 暗色模式 */
  dark: boolean;
  /** 当前激活 session id（null = 没在场次） */
  activeSessionId: string | null;
  /** 当前激活 session title（用于显示） */
  activeSessionTitle: string | null;
  /** 当前激活 session 队列长度（实时） */
  queueSize: number;
  /** 当前是否在 PlayView 弹唱模式 */
  isInPlayMode: boolean;
  /** 当前 PlayView 是否联动模式（linkedSessionId 存在） */
  isPlayLinked: boolean;
  /** 当前 playLink（如果用户在弹唱某首） */
  playLinkInfo?: LiveShellPlayLinkInfo | null;
  // 4 个动作回调
  /** 跳到主控制台（主窗口切到 live view） */
  onOpenLiveView: () => void;
  /** 打开速查子窗口（Electron IPC 或新窗口） */
  onOpenQuickView: () => void;
  /** 跳弹唱。可选 linked — 不传 = 非联动模式 */
  onOpenPlayView: (linked?: LiveShellPlayLinkInfo) => void;
  /** 关闭弹唱模式（清 PlayerContext） */
  onClosePlay: () => void;
}

/**
 * LiveShell — 直播壳顶栏。
 * 始终渲染（即便没活跃 session 也显示「暂无场次」+ 3 个动作入口）。
 * sticky top + z-index 保证滚动不丢失。
 */
export default function LiveShell(props: LiveShellProps) {
  const {
    dark,
    activeSessionId,
    activeSessionTitle,
    queueSize,
    isInPlayMode,
    isPlayLinked,
    playLinkInfo,
    onOpenLiveView,
    onOpenQuickView,
    onOpenPlayView,
    onClosePlay,
  } = props;

  const hasSession = activeSessionId !== null;
  const electron = isElectron();

  return (
    <div
      data-testid="live-shell"
      className={`sticky top-0 z-20 flex items-center gap-3 px-5 h-12 border-b backdrop-blur-md transition-colors duration-300 ${
        dark
          ? "bg-zinc-900/90 border-zinc-700/60 text-zinc-200"
          : "bg-background/90 border-border text-foreground"
      }`}
    >
      {/* ===== 位置指示 ===== */}
      <div className="flex items-center gap-2 shrink-0">
        <span
          aria-hidden="true"
          className={`inline-block w-2 h-2 rounded-full ${
            isInPlayMode
              ? "bg-emerald-500"
              : hasSession
                ? "bg-amber-500"
                : "bg-zinc-400"
          }`}
          data-testid="live-shell-position-dot"
        />
        <span
          data-testid="live-shell-position"
          className={`text-[12px] font-medium whitespace-nowrap ${
            dark ? "text-zinc-300" : "text-foreground"
          }`}
        >
          你现在在：
          <span className="ml-1">
            {isInPlayMode ? (
              <span className="text-emerald-500" data-testid="live-shell-pos-play">弹唱屏</span>
            ) : (
              <span className="text-amber-500" data-testid="live-shell-pos-live">主控制台</span>
            )}
          </span>
        </span>
      </div>

      {/* 分隔 */}
      <span className={`h-5 w-px ${dark ? "bg-zinc-700" : "bg-border"}`} />

      {/* ===== Session 摘要 ===== */}
      {hasSession ? (
        <div
          data-testid="live-shell-session"
          className="flex items-center gap-2 min-w-0"
        >
          <span
            aria-hidden="true"
            className="inline-block w-2 h-2 rounded-full bg-emerald-500 shrink-0"
          />
          <span
            data-testid="live-shell-session-title"
            className={`text-[12px] font-medium truncate max-w-[180px] ${
              dark ? "text-zinc-100" : "text-foreground"
            }`}
            title={activeSessionTitle ?? ""}
          >
            {activeSessionTitle || `会话 ${activeSessionId.slice(0, 8)}`}
          </span>
          <span
            data-testid="live-shell-queue-badge"
            className={`shrink-0 inline-flex items-center justify-center min-w-[24px] h-5 px-1.5 rounded-md text-[11px] font-semibold tabular-nums ${
              dark
                ? "bg-amber-500/15 text-amber-300 border border-amber-500/30"
                : "bg-amber-50 text-amber-700 border border-amber-200"
            }`}
            title="当前队列待唱数"
          >
            队列 {queueSize}
          </span>
        </div>
      ) : (
        <span
          data-testid="live-shell-empty"
          className={`text-[12px] ${dark ? "text-zinc-500" : "text-muted-foreground"}`}
        >
          暂无场次 — 点「主控制台」开始一场直播
        </span>
      )}

      {/* 联动徽标（弹唱 + 联动模式才显示） */}
      {isInPlayMode && isPlayLinked && playLinkInfo && (
        <span
          data-testid="live-shell-link-badge"
          className={`shrink-0 inline-flex items-center gap-1.5 rounded-md px-2 h-6 text-[11px] font-medium border ${
            dark
              ? "bg-rose-500/15 text-rose-300 border-rose-500/30"
              : "bg-rose-50 text-rose-700 border-rose-200"
          }`}
        >
          <span aria-hidden="true">🔗</span>
          <span>联动中 · {playLinkInfo.requesterName}</span>
          <button
            type="button"
            data-testid="live-shell-link-close"
            onClick={onClosePlay}
            className={`ml-1 -mr-1 inline-flex items-center justify-center w-4 h-4 rounded text-[10px] transition-colors ${
              dark
                ? "hover:bg-rose-500/20"
                : "hover:bg-rose-100"
            }`}
            title="关闭联动（清空弹唱状态）"
            aria-label="关闭联动"
          >
            ✕
          </button>
        </span>
      )}

      {/* spacer */}
      <div className="flex-1" />

      {/* ===== 3 个动作按钮 ===== */}
      <button
        type="button"
        data-testid="live-shell-btn-live"
        onClick={onOpenLiveView}
        className={`shrink-0 inline-flex items-center gap-1 rounded-md px-3 h-8 text-[12px] font-medium transition-colors cursor-pointer ${
          !isInPlayMode
            ? "bg-sky-500 text-white hover:bg-sky-600"
            : dark
              ? "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
              : "bg-muted text-foreground hover:bg-muted/70"
        }`}
        aria-label="切到主控制台"
      >
        <span aria-hidden="true">📺</span>
        <span>主控制台</span>
      </button>

      <button
        type="button"
        data-testid="live-shell-btn-quick"
        onClick={onOpenQuickView}
        disabled={!electron}
        title={electron ? "打开速查子窗口" : "仅 Electron 桌面端支持"}
        className={`shrink-0 inline-flex items-center gap-1 rounded-md px-3 h-8 text-[12px] font-medium transition-colors cursor-pointer disabled:cursor-not-allowed disabled:opacity-50 ${
          electron
            ? "bg-amber-500 text-white hover:bg-amber-600"
            : dark
              ? "bg-zinc-800 text-zinc-500"
              : "bg-muted text-muted-foreground"
        }`}
        aria-label="打开速查窗口"
      >
        <span aria-hidden="true">⚡</span>
        <span>速查窗口</span>
        {!electron && <span className="text-[10px] ml-0.5" aria-hidden="true">▣</span>}
      </button>

      <button
        type="button"
        data-testid="live-shell-btn-play"
        onClick={() => onOpenPlayView()}
        className={`shrink-0 inline-flex items-center gap-1 rounded-md px-3 h-8 text-[12px] font-medium transition-colors cursor-pointer ${
          isInPlayMode
            ? "bg-emerald-500 text-white hover:bg-emerald-600"
            : dark
              ? "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
              : "bg-muted text-foreground hover:bg-muted/70"
        }`}
        aria-label="进入弹唱屏"
      >
        <span aria-hidden="true">🎤</span>
        <span>弹唱屏</span>
      </button>
    </div>
  );
}
