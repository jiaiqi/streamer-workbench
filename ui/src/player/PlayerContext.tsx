/// M1.3 蓝图 v0.1：PlayerContext — 跨场景播放器状态共享
///
/// 三个场景（蓝图 §3.2）：
///   - live: 直播弹唱（PlayView + 联动 LiveView）
///   - practice: 练习对拍（PlayView + Learning）
///   - browse: 曲库试听与校对（PlayView + Library）
///
/// MVP 范围（M1.3）：
///   - Context 存：currentSongId / mode / isPlaying / currentTimeMs
///   - actions: setCurrent / setMode / setPlaying / setCurrentTime
///   - 真正的 audio 元素仍在 PlayView（context 同步状态，不直接管 audio）
///   - M1.4 迷你栏读这个 context 显示 + 跳转 PlayView
///
/// 后续（M1.x）：如要"切视图不打断播放"，把 audio ref 提升到 App.tsx 顶层
import { createContext, useCallback, useContext, useMemo, useState } from "react";

export type PlayerMode = "live" | "practice" | "browse";

export interface PlayerState {
  currentSongId: string | null;
  mode: PlayerMode;
  isPlaying: boolean;
  currentTimeMs: number;
}

export interface PlayerActions {
  setCurrent: (songId: string | null, mode?: PlayerMode) => void;
  setMode: (mode: PlayerMode) => void;
  setPlaying: (playing: boolean) => void;
  setCurrentTime: (ms: number) => void;
}

const PlayerContext = createContext<(PlayerState & PlayerActions) | null>(null);

export function PlayerProvider({ children }: { children: React.ReactNode }) {
  const [currentSongId, setCurrentSongId] = useState<string | null>(null);
  const [mode, setMode] = useState<PlayerMode>("browse");
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTimeMs, setCurrentTimeMs] = useState(0);

  const setCurrent = useCallback((songId: string | null, nextMode?: PlayerMode) => {
    setCurrentSongId(songId);
    setIsPlaying(false);
    setCurrentTimeMs(0);
    if (nextMode) setMode(nextMode);
  }, []);
  const setModeFn = useCallback((next: PlayerMode) => setMode(next), []);
  const setPlayingFn = useCallback((p: boolean) => setIsPlaying(p), []);
  const setCurrentTimeFn = useCallback((ms: number) => setCurrentTimeMs(ms), []);

  const value = useMemo(
    () => ({ currentSongId, mode, isPlaying, currentTimeMs,
             setCurrent, setMode: setModeFn, setPlaying: setPlayingFn, setCurrentTime: setCurrentTimeFn }),
    [currentSongId, mode, isPlaying, currentTimeMs, setCurrent, setModeFn, setPlayingFn, setCurrentTimeFn],
  );
  return <PlayerContext.Provider value={value}>{children}</PlayerContext.Provider>;
}

export function usePlayer(): PlayerState & PlayerActions {
  const ctx = useContext(PlayerContext);
  if (ctx) return ctx;
  // 未包 PlayerProvider 的场景（如 PlayView 单测）→ 返回 no-op 默认值，
  // 避免把 Provider 强绑到每个使用点。生产环境 App 顶层已包，这里只是降级。
  // 注意：此分支下 setCurrent 等不会真正驱动全局状态。
  return NOOP_PLAYER;
}

const NOOP_PLAYER: PlayerState & PlayerActions = {
  currentSongId: null,
  mode: "browse",
  isPlaying: false,
  currentTimeMs: 0,
  setCurrent: () => {},
  setMode: () => {},
  setPlaying: () => {},
  setCurrentTime: () => {},
};
