/// R8.0 弹唱：PlayerBar — 底部播放器条
///
/// v8.0 简化版：无 audio 元素，仅展示播放/暂停按钮 + 进度条 + 时间。
/// 父组件（PlayView）控制 currentTimeMs + isPlaying，PlayerBar 通过回调上抛。
/// v8.1 接 audio 时把 isPlaying/onSeek 接入 HTMLAudioElement 的 play/pause/seek。
import { useCallback } from "react";

export interface PlayerBarProps {
  dark: boolean;
  isPlaying: boolean;          // 当前是否"播放中"（v8.0 模拟）
  currentTimeMs: number;       // 当前时间
  totalMs: number;             // 总时长
  hasAudio: boolean;           // 是否有音频（v8.0 永远 false，UI 显示"暂无音频"）
  onPlay: () => void;
  onPause: () => void;
  onSeek: (timeMs: number) => void;
  "data-testid"?: string;
}

function formatTime(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export default function PlayerBar({
  dark, isPlaying, currentTimeMs, totalMs, hasAudio,
  onPlay, onPause, onSeek, "data-testid": testId = "player-bar",
}: PlayerBarProps) {
  const progressPct = totalMs > 0 ? Math.min(100, (currentTimeMs / totalMs) * 100) : 0;

  const handleSeek = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const v = Number(e.target.value);
    if (!Number.isNaN(v) && totalMs > 0) {
      onSeek(Math.floor((v / 100) * totalMs));
    }
  }, [onSeek, totalMs]);

  return (
    <div
      data-testid={testId}
      data-state={hasAudio ? "audio" : "no-audio"}
      data-playing={isPlaying ? "true" : "false"}
      className={`flex items-center gap-3 border-t px-4 py-2 ${dark ? "border-zinc-800 bg-zinc-900/60" : "border-border bg-background"}`}
    >
      {/* 播放/暂停 */}
      <button
        type="button"
        onClick={isPlaying ? onPause : onPlay}
        disabled={!hasAudio}
        title={hasAudio ? (isPlaying ? "暂停" : "播放") : "暂未连接音频（v8.0）"}
        data-testid={`${testId}-play`}
        className={`flex h-9 w-9 items-center justify-center rounded-full text-base transition-colors ${
          hasAudio
            ? "bg-primary text-primary-foreground hover:opacity-90"
            : dark ? "bg-zinc-800 text-zinc-500" : "bg-muted text-muted-foreground"
        }`}
      >
        {isPlaying ? "⏸" : "▶"}
      </button>

      {/* 时间 */}
      <span
        data-testid={`${testId}-time`}
        className={`min-w-[88px] tabular-nums text-xs ${dark ? "text-zinc-400" : "text-muted-foreground"}`}
      >
        {formatTime(currentTimeMs)} / {formatTime(totalMs)}
      </span>

      {/* 进度条 */}
      <input
        type="range"
        min={0}
        max={100}
        step={0.1}
        value={progressPct}
        onChange={handleSeek}
        disabled={!hasAudio}
        data-testid={`${testId}-progress`}
        aria-label="播放进度"
        className="h-1 flex-1 cursor-pointer accent-primary disabled:cursor-not-allowed disabled:opacity-50"
      />

      {/* 音频状态标签 */}
      <span
        className={`min-w-[64px] text-right text-[10px] ${dark ? "text-zinc-500" : "text-muted-foreground"}`}
      >
        {hasAudio ? (isPlaying ? "播放中" : "已暂停") : "暂无音频"}
      </span>
    </div>
  );
}
