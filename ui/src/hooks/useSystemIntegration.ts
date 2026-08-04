/// P0 桌面平台特性首批：渲染层 → 主进程 系统集成桥。
///
/// 三件事：
/// 1. 订阅 PlayerContext（isPlaying / currentSongId / currentTimeMs / durationMs）
///    节流 1Hz 推给主进程 → 菜单 enable / 系统通知 / dock badge
/// 2. 订阅主进程菜单/通知点击 → 派回 PlayerContext（让 PlayView 内的 audio 响应）
/// 3. 监听 `live:queueCount` 事件（LiveView 推送）→ 拼到 state 里给主进程
///
/// 设计要点：
/// - 单向 state 推（send，不是 invoke），主进程 diff 后自己决定
/// - 节流：1Hz（防止 progress bar 60fps IPC 把主进程卡死）
/// - 浏览器模式（无 electron）静默 no-op，不影响开发
/// - 播控指令：play/pause → setPlaying 立即翻转（让 audio 元素后续 effect 接管）
///              next/prev  → 当前没有队列上下首语义，先打 log + setView("play") 提示用户
import { useEffect, useRef } from "react";
import { usePlayer } from "../player/PlayerContext";

export interface SystemIntegrationOptions {
  /** 当前 song 的时长（ms）—— 通常 PlayView 通过 audio.duration 推 */
  durationMs?: number;
  /** 当前 song 的标题/歌手（来自当前 song 查表） */
  currentTitle?: string | null;
  currentArtist?: string | null;
  /** 切歌时是否通知主进程弹系统通知（默认 true；批量预览时关） */
  notifySongChanged?: boolean;
  /** 队列从 0→>0 时是否通知主进程弹"直播开始"（默认 false，由 LiveView 决定） */
  notifyQueueStarted?: boolean;
}

declare global {
  interface Window {
    streamer?: {
      sendPlayerState?: (state: Record<string, unknown>) => void;
      onPlayerControl?: (listener: (cmd: string) => void) => () => void;
      notify?: (opts: { title?: string; body?: string; tag?: string }) => Promise<{ ok: boolean }>;
      getPlayerState?: () => Promise<Record<string, unknown>>;
      openQuickView?: (sessionId?: string) => Promise<unknown>;
      closeQuickView?: () => Promise<unknown>;
      onQuickViewSession?: (listener: (sessionId: string) => void) => () => void;
      saveFile?: (params: { data: ArrayBuffer; defaultName: string; mimeType?: string }) => Promise<unknown>;
    };
    /** LiveView 推送的队列数（自定义事件，桥接 LiveSession → 主进程 dock badge） */
    __liveQueueCount?: number;
  }
}

const THROTTLE_MS = 1000;

export function useSystemIntegration(opts: SystemIntegrationOptions = {}): void {
  const {
    durationMs = 0,
    currentTitle = null,
    currentArtist = null,
    notifySongChanged = true,
    notifyQueueStarted = false,
  } = opts;

  const player = usePlayer();
  const lastSendAtRef = useRef(0);
  const lastStateRef = useRef<string>("");
  const lastQueueCountRef = useRef<number>(0);

  // 1) 推 state 到主进程（节流 1Hz，且仅在字段真正变化时推）
  useEffect(() => {
    const api = window.streamer;
    if (!api?.sendPlayerState) return;  // 浏览器模式 no-op
    const now = Date.now();
    const elapsed = now - lastSendAtRef.current;
    if (elapsed < THROTTLE_MS) return;
    const queueCount = window.__liveQueueCount ?? 0;
    const snapshot = {
      isPlaying: player.isPlaying,
      currentSongId: player.currentSongId,
      currentTitle,
      currentArtist,
      currentTimeMs: player.currentTimeMs,
      durationMs,
      queueCount,
      notifySongChanged,
      notifyQueueStarted,
    };
    // 去重：序列化对比，相同就跳过
    const sig = JSON.stringify(snapshot);
    if (sig === lastStateRef.current) return;
    lastStateRef.current = sig;
    lastSendAtRef.current = now;
    lastQueueCountRef.current = queueCount;
    api.sendPlayerState(snapshot);
  }, [
    player.isPlaying,
    player.currentSongId,
    player.currentTimeMs,
    durationMs,
    currentTitle,
    currentArtist,
    notifySongChanged,
    notifyQueueStarted,
  ]);

  // 1b) LiveView 推 queueCount 时主动触发一次
  useEffect(() => {
    const onQueue = () => {
      const api = window.streamer;
      if (!api?.sendPlayerState) return;
      const queueCount = window.__liveQueueCount ?? 0;
      const snapshot = {
        isPlaying: player.isPlaying,
        currentSongId: player.currentSongId,
        currentTitle,
        currentArtist,
        currentTimeMs: player.currentTimeMs,
        durationMs,
        queueCount,
        notifySongChanged,
        notifyQueueStarted,
      };
      const sig = JSON.stringify(snapshot);
      if (sig === lastStateRef.current) return;
      lastStateRef.current = sig;
      lastSendAtRef.current = Date.now();
      lastQueueCountRef.current = queueCount;
      api.sendPlayerState(snapshot);
    };
    window.addEventListener("live:queueCount", onQueue);
    return () => window.removeEventListener("live:queueCount", onQueue);
  }, [
    player.isPlaying,
    player.currentSongId,
    player.currentTimeMs,
    durationMs,
    currentTitle,
    currentArtist,
    notifySongChanged,
    notifyQueueStarted,
  ]);

  // 2) 接收主进程播控指令 → 翻译成 PlayerContext action
  useEffect(() => {
    const api = window.streamer;
    if (!api?.onPlayerControl) return;
    const off = api.onPlayerControl((cmd: string) => {
      if (cmd === "play") {
        player.setPlaying(true);
      } else if (cmd === "pause") {
        player.setPlaying(false);
      } else if (cmd === "next" || cmd === "prev") {
        // 当前 MVP：弹一个提示让用户到主窗口手动切（后续可接队列上下首）
        if (window.streamer?.notify) {
          void window.streamer.notify({
            tag: "queue-tip",
            title: cmd === "next" ? "请到直播队列切下一首" : "请到直播队列切上一首",
            body: "后续会接 LiveSession 队列自动切换",
          });
        }
      }
    });
    return off;
  }, [player]);

  // 3) 兜底 flush：卸载时强制推一次（让菜单及时 disable）
  useEffect(() => {
    const api = window.streamer;
    if (!api?.sendPlayerState) return;
    return () => {
      api.sendPlayerState({
        isPlaying: false,
        currentSongId: null,
        currentTitle: null,
        currentArtist: null,
        currentTimeMs: 0,
        durationMs: 0,
        queueCount: 0,
        notifySongChanged: false,
        notifyQueueStarted: false,
      });
    };
  }, []);
}
