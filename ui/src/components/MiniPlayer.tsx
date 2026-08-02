/// M1.4 全局迷你播放器（蓝图 v0.1 §3.2 跨场景播放器 MVP）
///
/// 当前视图（工作台 / 学歌 / 直播 / 统计）下，若 PlayerContext 中有
/// `currentSongId`（已选歌但不在 PlayView 里），显示一个固定底栏：
///   - 左侧：歌名 + 模式徽章（直播联动 / 试听 / 练习）
///   - 中间：进度（currentTimeMs，仅展示，不控播放）
///   - 右侧：「打开弹唱 →」按钮 → 调 onOpen 切到 play 视图
///
/// 在 PlayView 自身、命令面板/对话框/垃圾桶等 modal 场景下隐藏。
///
/// MVP 范围：
///   - 只读 context（不调 audio）
///   - 真正的 audio 元素仍在 PlayView（M1.x 后续做"切视图不打断播放"）
///   - 进度条静态显示 currentTimeMs（PlayView 会通过 setCurrentTime 同步）
import { usePlayer, type PlayerMode } from "../player/PlayerContext";

const MODE_LABEL: Record<PlayerMode, string> = {
  live: "联播",
  practice: "练习",
  browse: "试听",
};

const MODE_STYLE: Record<PlayerMode, string> = {
  live: "bg-sky-500/15 text-sky-300 border-sky-500/30",
  practice: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  browse: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
};

const DARK_MODE_STYLE: Record<PlayerMode, string> = {
  live: "bg-sky-500/15 text-sky-300 border-sky-500/30",
  practice: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  browse: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
};

export interface MiniPlayerProps {
  /** 当前 song_id 对应的歌名（null = 曲库未拉到，用 fallback） */
  currentTitle: string | null;
  /** 点击「打开弹唱 →」回调（App.tsx 设 setView("play")） */
  onOpen: () => void;
  /** 关闭/退出回调（迷你栏上的 ✕），清空 PlayerContext */
  onClose: () => void;
  /** 暗色模式 */
  dark: boolean;
  /** 测试用：强制隐藏（默认不传） */
  hidden?: boolean;
}

export default function MiniPlayer({ currentTitle, onOpen, onClose, dark, hidden }: MiniPlayerProps) {
  const { currentSongId, mode, currentTimeMs } = usePlayer();
  if (hidden || !currentSongId) return null;

  const title = currentTitle ?? "未命名歌曲";
  const modeStyle = dark ? DARK_MODE_STYLE[mode] : MODE_STYLE[mode];
  // 简单进度：currentTimeMs 不带总时长，PlayView 还在跑时会持续 setCurrentTime。
  // MVP：把 currentTimeMs 格式化为 mm:ss 给用户一个"在播"的视觉反馈。
  const seconds = Math.floor(currentTimeMs / 1000);
  const mm = Math.floor(seconds / 60).toString().padStart(2, "0");
  const ss = (seconds % 60).toString().padStart(2, "0");

  return (
    <div
      data-testid="mini-player"
      data-mode={mode}
      className={`fixed bottom-0 left-0 right-0 z-30 flex items-center gap-3 px-5 h-12 backdrop-blur-md border-t transition-colors duration-300 ${
        dark
          ? "bg-zinc-900/90 border-zinc-700/60 text-zinc-200"
          : "bg-background/90 border-border text-foreground"
      }`}
    >
      {/* 左侧：模式徽章 + 歌名 */}
      <span
        data-testid="mini-player-mode"
        className={`shrink-0 rounded-md border px-2 h-6 inline-flex items-center text-[11px] font-medium tracking-wide ${modeStyle}`}
      >
        {MODE_LABEL[mode]}
      </span>
      <span
        data-testid="mini-player-title"
        className="flex-1 min-w-0 truncate text-[13px] font-medium"
        title={title}
      >
        {title}
      </span>

      {/* 中间：进度（mm:ss 静默展示；M1.x 切视图不打断时再加真实 audio 时间） */}
      <span
        data-testid="mini-player-time"
        className={`shrink-0 tabular-nums text-[11px] ${dark ? "text-zinc-500" : "text-muted-foreground"}`}
      >
        {mm}:{ss}
      </span>

      {/* 右侧：操作 */}
      <button
        type="button"
        data-testid="mini-player-open"
        onClick={onOpen}
        className={`shrink-0 inline-flex items-center gap-1 rounded-md px-2.5 h-7 text-[12px] font-medium transition-colors cursor-pointer ${
          dark
            ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-200"
            : "bg-muted hover:bg-muted/70 text-foreground"
        }`}
        aria-label={`打开弹唱 ${title}`}
      >
        打开弹唱
        <span aria-hidden="true">→</span>
      </button>
      <button
        type="button"
        data-testid="mini-player-close"
        onClick={onClose}
        title="退出弹唱（清空播放器状态）"
        aria-label="退出弹唱"
        className={`shrink-0 inline-flex items-center justify-center rounded-md w-7 h-7 text-[14px] transition-colors cursor-pointer ${
          dark
            ? "text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300"
            : "text-muted-foreground hover:bg-muted hover:text-foreground"
        }`}
      >
        ✕
      </button>
    </div>
  );
}
