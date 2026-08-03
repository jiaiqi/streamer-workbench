/// L1.6 全局状态栏（底部）
///
/// 显示 5 个分块：
///   1. 当前视图（工作台 / 歌曲库 / 学歌 / 直播 / 统计 / 弹唱 / 设置）
///   2. 当前操作状态（空闲 / 渲染中 / 保存中 / 加载中）
///   3. 渲染耗时（仅工作台视图且有数据时）
///   4. 上次保存时间（来自 events.jsonl 最近一条）
///   5. 资源错误（红色 badge + 重试按钮）
///
/// 设计原则：
///   - 固定底栏（不与 MiniPlayer 冲突：StatusBar bottom-0，MiniPlayer 视情况）
///   - 暗色 backdrop-blur，不抢眼但一直可见
///   - 各分块小图标 + 文字 + 颜色提示（绿/红/灰/蓝）
///   - 视图切换时小动效
import { useEffect, useState } from "react";

export type StatusView = "workspace" | "library" | "learning" | "live" | "stats" | "play" | "settings" | "preview";

const VIEW_LABEL: Record<StatusView, string> = {
  workspace: "工作台",
  library: "歌曲库",
  learning: "学歌管理",
  live: "直播",
  stats: "数据统计",
  play: "弹唱",
  settings: "设置",
  preview: "海报预览",
};

export type StatusOp = "idle" | "rendering" | "saving" | "loading";

const OP_LABEL: Record<StatusOp, string> = {
  idle: "空闲",
  rendering: "渲染中…",
  saving: "保存中…",
  loading: "加载中…",
};

const OP_COLOR: Record<StatusOp, string> = {
  idle: "text-emerald-500",
  rendering: "text-amber-500",
  saving: "text-sky-500",
  loading: "text-sky-500",
};

export interface StatusBarProps {
  view: StatusView;
  op?: StatusOp;
  lastRenderMs?: number | null;
  lastSaveTime?: string | null;        // ISO 字符串
  errorMessage?: string | null;        // 资源错误时显示红 badge
  onRetry?: () => void;
  dark?: boolean;
  /** 隐藏条件：弹唱视图时 MiniPlayer 已占底栏 */
  hidden?: boolean;
}

export default function StatusBar({
  view,
  op = "idle",
  lastRenderMs = null,
  lastSaveTime = null,
  errorMessage = null,
  onRetry,
  dark = false,
  hidden = false,
}: StatusBarProps) {
  // 渲染耗时显示用 1s 刷新（让数字滚动更平滑）
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!lastSaveTime) return;
    const id = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(id);
  }, [lastSaveTime]);

  if (hidden) return null;

  const lastSaveAgo = lastSaveTime ? formatTimeAgo(new Date(lastSaveTime), now) : null;

  return (
    <div
      data-testid="status-bar"
      data-view={view}
      data-op={op}
      className={`fixed bottom-0 left-0 right-0 z-20 flex items-center gap-4 px-4 h-7 backdrop-blur-md border-t text-[11px] tabular-nums transition-colors duration-300 ${
        dark
          ? "bg-zinc-900/80 border-zinc-700/60 text-zinc-400"
          : "bg-background/80 border-border text-muted-foreground"
      }`}
    >
      {/* 1. 当前视图 */}
      <span data-testid="status-bar-view" className="flex items-center gap-1">
        <span className={dark ? "text-zinc-600" : "text-zinc-400"}>视图</span>
        <span className={`font-medium ${dark ? "text-zinc-200" : "text-foreground"}`}>
          {VIEW_LABEL[view] ?? view}
        </span>
      </span>

      {/* 分隔 */}
      <span className={dark ? "text-zinc-700" : "text-zinc-300"}>·</span>

      {/* 2. 当前操作状态 */}
      <span data-testid="status-bar-op" className="flex items-center gap-1.5">
        <span
          data-testid="status-bar-op-dot"
          className={`inline-block h-1.5 w-1.5 rounded-full ${
            op === "idle" ? "bg-emerald-500"
              : op === "rendering" ? "bg-amber-500 animate-pulse"
              : "bg-sky-500 animate-pulse"
          }`}
        />
        <span className={OP_COLOR[op]}>{OP_LABEL[op]}</span>
      </span>

      {/* 3. 渲染耗时（仅 lastRenderMs > 0） */}
      {lastRenderMs !== null && lastRenderMs > 0 && (
        <>
          <span className={dark ? "text-zinc-700" : "text-zinc-300"}>·</span>
          <span data-testid="status-bar-render" className="flex items-center gap-1">
            <span className={dark ? "text-zinc-600" : "text-zinc-400"}>渲染</span>
            <span className={dark ? "text-zinc-300" : "text-foreground/80"}>
              {Math.round(lastRenderMs)}ms
            </span>
          </span>
        </>
      )}

      {/* 4. 上次保存时间 */}
      {lastSaveAgo && (
        <>
          <span className={dark ? "text-zinc-700" : "text-zinc-300"}>·</span>
          <span data-testid="status-bar-save" className="flex items-center gap-1" title={lastSaveTime ?? undefined}>
            <span className={dark ? "text-zinc-600" : "text-zinc-400"}>保存</span>
            <span className={dark ? "text-zinc-300" : "text-foreground/80"}>
              {lastSaveAgo}
            </span>
          </span>
        </>
      )}

      {/* 5. 错误重试（红色 badge） */}
      {errorMessage && (
        <>
          <span className={`flex-1 ${dark ? "text-zinc-700" : "text-zinc-300"}`} />
          <button
            type="button"
            data-testid="status-bar-error"
            onClick={onRetry}
            className="flex items-center gap-1 rounded px-1.5 h-5 bg-red-500/15 text-red-500 hover:bg-red-500/25 transition-colors cursor-pointer"
            title={errorMessage}
          >
            <span className="font-medium">⚠ 错误 · 重试</span>
          </button>
        </>
      )}
    </div>
  );
}

function formatTimeAgo(date: Date, now: number): string {
  const diff = Math.max(0, now - date.getTime());
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return `${sec}s 前`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m 前`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h 前`;
  const day = Math.floor(hr / 24);
  return `${day}d 前`;
}
