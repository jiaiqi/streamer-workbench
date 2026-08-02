/// R8.0 弹唱：PlayView — 弹唱主视图
///
/// 整合 LyricsPanel + TabsPanel + PlayerBar；R8.1 接 HTML5 audio 元素。
/// 父组件传入 song 数据（包含 lyrics_lrc / lyrics_plain / tabs / audio_vocal_path / audio_instrumental_path）。
///
/// 设计：
///   - 顶栏：返回按钮 + 歌名 - 歌手 + vocal/instrumental 切换 + 状态标签
///   - 中央：左歌词（60%宽）+ 右曲谱（40%宽）
///   - 底部：PlayerBar（实际 audio 元素）
///   - 数据缺失：显示 EmptyState 提示"这首歌还没歌词/曲谱"
///
/// R8.1 audio 集成：
///   - <audio ref> 真实播放；timeupdate 推 currentTimeMs → LyricsPanel/TabsPanel
///   - 切 vocal/instrumental：换 audio.src
///   - play/pause/ended 事件：本地 state + 上报 POST /api/playback/events
///
/// R8.2 直播联动：
///   - linkedSessionId / linkedRequestId / linkedRequesterName 来自 LiveView
///   - 顶栏显示「联播 · {requester_name}」标签 + 「已唱」按钮（联动模式显示）
///   - audio ended → 自动调 POST /api/live-sessions/{linkedSessionId}/record (result=sung) + 触发 onBack
///   - 联动模式下 onBack 切回 live 视图；非联动模式切回 library 视图（由 App.tsx 决定）
///
/// R9.1 联动增强：
///   - 顶栏「↻ 再唱一遍」按钮：重置 audio.currentTime + 重新 play + 重置 recordSubmittedRef
///   - 用于主播临时想从头再唱一次（间奏太长 / 观众想再听副歌）
///
/// R9.2 远观模式：
///   - 顶栏字号档位按钮 1× / 1.3× / 1.6×（影响 LyricsPanel + TabsPanel 字号）
///   - 弹唱时屏幕 1-2m 远，普通字号看不清
///
/// R9.3 Capo 标识：
///   - 顶栏大字「Capo X / 实际 Key: Y」（基于 song.key + currentCapo 反推）
///   - 升降 Capo 大按钮（− / +）；快捷键 ↑ ↓ 升降
///   - 仅影响显示 + 联动 mark sung 时把 Capo 写到 note；不真的改 audio 音高
///
/// R9.4 个人 Capo 库：
///   - 顶栏「+ 习惯」按钮：把当前 Capo 加到 song.capo_options + 设 capo_default
///   - 持久化：PATCH /api/songs/{id} 调 EDITABLE_FIELDS 白名单（capo_options/capo_default）
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiRequest } from "../api/client";
import type { Song, SongsData } from "../types";
import { parseLrc, distributePlainLyrics, findActiveLine } from "./lrc";
import { parseChordpro } from "./chordpro";
import { transposeKey, clampCapo } from "./capo";
import LyricsPanel from "./LyricsPanel";
import TabsPanel from "./TabsPanel";
import PlayerBar from "./PlayerBar";
import { Icon } from "../icons";

export interface PlayViewProps {
  dark: boolean;
  songId: string;
  onBack: () => void;
  /** R8.2: 联动 — 当前直播会话 id（来自 LiveView 弹唱按钮）。无值时为非联动模式。 */
  linkedSessionId?: string;
  /** R8.2: 联动 — 当前队列项 request id。audio ended 时调 record API。 */
  linkedRequestId?: string;
  /** R8.2: 联动 — 点歌人姓名（顶栏展示）。 */
  linkedRequesterName?: string;
  /** R8.2: 联动 — record API 返回后回调（App.tsx 用来刷新 LiveView 数据）。 */
  onLinkedRecorded?: (requestId: string) => void;
}

const DEFAULT_TOTAL_MS = 4 * 60 * 1000; // 4 分钟默认时长（无音频时用）

function pickSong(songs: Song[] | undefined, songId: string): Song | null {
  if (!Array.isArray(songs)) return null;
  return songs.find(s => s.id === songId) ?? null;
}

export default function PlayView({
  dark, songId, onBack,
  linkedSessionId, linkedRequestId, linkedRequesterName,
  onLinkedRecorded,
}: PlayViewProps) {
  const [song, setSong] = useState<Song | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 模拟播放状态（v8.0 简化）
  const [currentTimeMs, setCurrentTimeMs] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const timerRef = useRef<number | null>(null);

  // 拉取歌曲数据（v8.0 走 /api/songs/list 全量后前端过滤；v8.1 可加 /api/songs/{id}）
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    apiRequest<SongsData | Song[]>("/api/songs/list", {})
      .then(data => {
        if (!active) return;
        const list: Song[] = Array.isArray(data) ? data
          : (data && typeof data === "object" && "songs" in data && Array.isArray((data as SongsData).songs))
            ? (data as SongsData).songs : [];
        const found = pickSong(list, songId);
        setSong(found);
        if (!found) setError(`找不到 song_id = ${songId} 的歌曲`);
      })
      .catch(reason => {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : "加载失败");
        setSong(null);
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [songId]);

  // 解析歌词 + 曲谱
  const lyricsLines = useMemo(() => {
    if (!song) return [];
    if (song.lyrics_lrc && song.lyrics_lrc.trim()) {
      return parseLrc(song.lyrics_lrc).lines;
    }
    if (song.lyrics_plain && song.lyrics_plain.trim()) {
      const total = song.audio_duration_ms > 0 ? song.audio_duration_ms : DEFAULT_TOTAL_MS;
      return distributePlainLyrics(song.lyrics_plain, total);
    }
    return [];
  }, [song]);

  const tabsParsed = useMemo(() => {
    if (!song || !song.tabs) return { lines: [], meta: {} };
    return parseChordpro(song.tabs);
  }, [song]);

  // R8.1: 当前选中的 audio role（vocal / instrumental）
  const [audioRole, setAudioRole] = useState<"vocal" | "instrumental">("vocal");
  // R9.2: 远观模式字号档位（1 / 1.3 / 1.6）；影响 LyricsPanel + TabsPanel 字号
  const [sizeScale, setSizeScale] = useState<1 | 1.3 | 1.6>(1);
  // R9.3: 当前 Capo（0-12）；初值取 song.capo_default ?? song.capo ?? 0
  const [currentCapo, setCurrentCapo] = useState<number>(() => clampCapo(song?.capo_default ?? song?.capo ?? 0));
  // R9.4: 「+ 习惯」按钮状态
  const [saveCapoState, setSaveCapoState] = useState<"idle" | "saving" | "saved" | "error">("idle");

  // 歌曲变更时重置 Capo（从 song.capo_default 取；fallback 到 song.capo）
  useEffect(() => {
    setCurrentCapo(clampCapo(song?.capo_default ?? song?.capo ?? 0));
    setSaveCapoState("idle");
  }, [song?.id]);

  // R9.4: 「+ 习惯 Capo」— 把当前 Capo 加入 options + 设 default
  const handleSaveCapo = useCallback(async () => {
    if (!song || saveCapoState === "saving") return;
    setSaveCapoState("saving");
    const existing = Array.isArray(song.capo_options) ? song.capo_options : [];
    const nextOptions = Array.from(new Set([...existing, currentCapo])).sort((a, b) => a - b);
    try {
      await apiRequest(`/api/songs/${encodeURIComponent(song.id)}`, {
        method: "PATCH",
        body: {
          capo_options: nextOptions,
          capo_default: currentCapo,
        },
      });
      // 乐观更新本地 song（不重拉列表）
      setSong(prev => prev ? { ...prev, capo_options: nextOptions, capo_default: currentCapo } : prev);
      setSaveCapoState("saved");
      // 3 秒后回到 idle
      setTimeout(() => setSaveCapoState(s => s === "saved" ? "idle" : s), 3000);
    } catch {
      setSaveCapoState("error");
      setTimeout(() => setSaveCapoState(s => s === "error" ? "idle" : s), 3000);
    }
  }, [song, currentCapo, saveCapoState]);

  // R9.3: 当前 Capo 下的实际 Key（C + Capo 2 = D）
  const actualKey = useMemo(
    () => transposeKey(song?.key ?? "", currentCapo),
    [song?.key, currentCapo],
  );

  // R9.3: 升降 Capo 快捷键 ↑ ↓（顶栏聚焦时跳过避免重复触发）
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) {
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setCurrentCapo(c => clampCapo(c + 1));
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setCurrentCapo(c => clampCapo(c - 1));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // R8.1: 该歌可用 audio 列表（从 song 字段推断，避免额外请求）
  const hasVocal = !!song?.audio_vocal_path;
  const hasInstrumental = !!song?.audio_instrumental_path;
  const hasAudio = hasVocal || hasInstrumental;

  // R8.1: 当前选中的 audio 路径（决定 audio src）
  const audioSrc = useMemo(() => {
    if (!song || !hasAudio) return "";
    const relpath = audioRole === "vocal" ? song.audio_vocal_path : song.audio_instrumental_path;
    if (!relpath) return "";
    // relpath 是 "audio/song_xxx/vocal.mp3"，转为 /api/songs/{id}/audio/{role}/file
    const rolePath = audioRole;  // url 段
    // songId 已经在 props 里
    return `/api/songs/${encodeURIComponent(song.id)}/audio/${rolePath}/file`;
  }, [song, audioRole, hasAudio]);

  // R8.1: audio 元素引用
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // R8.1: 上报 playback 事件的辅助（fire-and-forget；失败静默）
  const reportEvent = useCallback((type: string, positionMs: number, durationMs: number = 0) => {
    if (!song) return;
    void apiRequest("/api/playback/events", {
      method: "POST",
      body: {
        type,
        song_id: song.id,
        source: audioRole,
        position_ms: Math.max(0, Math.floor(positionMs)),
        duration_ms: Math.max(0, Math.floor(durationMs)),
      },
    }).catch(() => { /* 静默：上报失败不阻塞播放 */ });
  }, [song, audioRole]);

  // R8.2: 联动模式 — 标记队列项为「已唱」（result=sung）。失败静默。
  // 重复防护：linkedRequestId 在同一会话已记录过一次，API 会返回错误；我们用 recordSubmittedRef 避免重复 POST。
  const recordSubmittedRef = useRef(false);
  const markLinkedSung = useCallback(() => {
    if (!linkedSessionId || !linkedRequestId) return;
    if (recordSubmittedRef.current) return;
    recordSubmittedRef.current = true;
    void apiRequest(
      `/api/live-sessions/${encodeURIComponent(linkedSessionId)}/record`,
      {
        method: "POST",
        body: {
          request_id: linkedRequestId,
          result: "sung",
          operator: "broadcaster",
          reason: "PlayView 弹唱联动自动标记",
        },
      },
    )
      .then(() => onLinkedRecorded?.(linkedRequestId))
      .catch(() => { /* 失败：用户可手动到 LiveView 改；不弹错避免弹唱中干扰 */ });
  }, [linkedSessionId, linkedRequestId, onLinkedRecorded]);

  // R8.1: 实际 audio 元素的事件 → state
  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    const onTimeUpdate = () => setCurrentTimeMs(Math.floor(el.currentTime * 1000));
    const onDurationChange = () => {
      if (Number.isFinite(el.duration) && el.duration > 0) {
        setDurationMs(Math.floor(el.duration * 1000));
      }
    };
    const onPlay = () => {
      setIsPlaying(true);
      reportEvent("playback_started", 0);
    };
    const onPause = () => {
      setIsPlaying(false);
      reportEvent("playback_paused", el.currentTime * 1000);
    };
    const onEnded = () => {
      setIsPlaying(false);
      reportEvent("playback_completed", el.duration * 1000, el.duration * 1000);
      // R8.2: 联动模式 — 弹唱结束自动标记「已唱」+ 回到 LiveView
      if (linkedSessionId && linkedRequestId) {
        markLinkedSung();
        onBack();
      }
    };
    el.addEventListener("timeupdate", onTimeUpdate);
    el.addEventListener("durationchange", onDurationChange);
    el.addEventListener("play", onPlay);
    el.addEventListener("pause", onPause);
    el.addEventListener("ended", onEnded);
    return () => {
      el.removeEventListener("timeupdate", onTimeUpdate);
      el.removeEventListener("durationchange", onDurationChange);
      el.removeEventListener("play", onPlay);
      el.removeEventListener("pause", onPause);
      el.removeEventListener("ended", onEnded);
    };
  }, [reportEvent, markLinkedSung, onBack, linkedSessionId, linkedRequestId]);

  // 估算总时长：优先 song.audio_duration_ms；否则用 audio 实际 duration；否则歌词行数 × 8 秒
  const [durationMs, setDurationMs] = useState(0);
  const totalMs = useMemo(() => {
    if (durationMs > 0) return durationMs;
    if (song?.audio_duration_ms && song.audio_duration_ms > 0) return song.audio_duration_ms;
    if (lyricsLines.length > 0) return lyricsLines.length * 8_000;
    return DEFAULT_TOTAL_MS;
  }, [durationMs, song, lyricsLines]);

  // 切 role 时（src 变）—— 如果在播放，先暂停（让用户手动重播以避免 auto-play 阻塞）
  const lastRoleRef = useRef(audioRole);
  useEffect(() => {
    if (lastRoleRef.current !== audioRole) {
      lastRoleRef.current = audioRole;
      // 切 role 时清空 currentTime（audio 会重新 loadedmetadata）
      setCurrentTimeMs(0);
      setIsPlaying(false);
    }
  }, [audioRole]);

  if (loading) {
    return (
      <div data-testid="play-view" data-state="loading" className="flex h-full items-center justify-center">
        <span className={`text-sm ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>加载歌曲…</span>
      </div>
    );
  }

  if (error || !song) {
    return (
      <div data-testid="play-view" data-state="error" className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
        <p className={`text-sm ${dark ? "text-red-400" : "text-red-600"}`} role="alert">
          {error || "歌曲不存在"}
        </p>
        <button
          type="button"
          onClick={onBack}
          className={`rounded-xl px-4 py-2 text-sm ${dark ? "bg-zinc-800 text-zinc-200 hover:bg-zinc-700" : "bg-muted text-foreground hover:bg-border"}`}
        >
          返回
        </button>
      </div>
    );
  }

  return (
    <div
      data-testid="play-view"
      data-state="ready"
      data-song-id={song.id}
      className={`flex h-full flex-col ${dark ? "bg-zinc-950 text-zinc-100" : "bg-background text-foreground"}`}
    >
      {/* 顶栏 */}
      <header className={`flex shrink-0 items-center gap-3 border-b px-4 py-2.5 ${dark ? "border-zinc-800" : "border-border"}`}>
        <button
          type="button"
          onClick={onBack}
          data-testid="play-view-back"
          className={`flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-sm transition-colors ${
            dark ? "text-zinc-300 hover:bg-zinc-800" : "text-foreground hover:bg-muted"
          }`}
        >
          ← 返回
        </button>
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-base font-semibold">{song.title}</h1>
          {song.artists.length > 0 && (
            <p className={`truncate text-xs ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
              {song.artists.join(" · ")}
            </p>
          )}
        </div>
        {/* R9.3: Capo 大字标识 + 升降按钮 + 实际 Key 显示 */}
        {song && (
          <div
            className="flex shrink-0 items-center gap-1 rounded-lg border px-1.5 py-0.5"
            data-testid="play-view-capo"
            data-capo={currentCapo}
            data-actual-key={actualKey}
            title="变调夹位置（↑ 升 / ↓ 降）"
          >
            <button
              type="button"
              data-testid="play-view-capo-down"
              onClick={() => setCurrentCapo(c => clampCapo(c - 1))}
              disabled={currentCapo <= 0}
              className={`h-7 w-7 inline-flex items-center justify-center rounded-md text-base font-bold transition-colors ${
                currentCapo <= 0
                  ? "cursor-not-allowed opacity-30"
                  : dark ? "hover:bg-zinc-700" : "hover:bg-muted"
              }`}
              aria-label="降 Capo"
            >
              −
            </button>
            <span
              data-testid="play-view-capo-value"
              className={`min-w-[58px] text-center text-sm font-bold tabular-nums ${
                currentCapo === 0
                  ? dark ? "text-zinc-500" : "text-muted-foreground"
                  : dark ? "text-amber-300" : "text-amber-700"
              }`}
            >
              {currentCapo === 0 ? "无 Capo" : `Capo ${currentCapo}`}
            </span>
            <button
              type="button"
              data-testid="play-view-capo-up"
              onClick={() => setCurrentCapo(c => clampCapo(c + 1))}
              disabled={currentCapo >= 12}
              className={`h-7 w-7 inline-flex items-center justify-center rounded-md text-base font-bold transition-colors ${
                currentCapo >= 12
                  ? "cursor-not-allowed opacity-30"
                  : dark ? "hover:bg-zinc-700" : "hover:bg-muted"
              }`}
              aria-label="升 Capo"
            >
              +
            </button>
            {song.key && actualKey && actualKey !== song.key && (
              <span
                className={`ml-1 text-[11px] tabular-nums ${
                  dark ? "text-zinc-400" : "text-muted-foreground"
                }`}
                data-testid="play-view-actual-key"
                title={`原 Key ${song.key} + Capo ${currentCapo} = 实际 ${actualKey}`}
              >
                → {actualKey}
              </span>
            )}
            {/* R9.4: 「+ 习惯 Capo」按钮 — 把当前 Capo 加入 options + 设 default */}
            <button
              type="button"
              data-testid="play-view-save-capo"
              data-save-state={saveCapoState}
              onClick={() => { void handleSaveCapo(); }}
              disabled={saveCapoState === "saving"}
              className={`ml-1 h-7 px-2 text-[11px] font-medium rounded-md transition-colors ${
                saveCapoState === "saved"
                  ? dark ? "bg-emerald-500/20 text-emerald-300" : "bg-emerald-100 text-emerald-700"
                  : saveCapoState === "error"
                    ? dark ? "bg-red-500/20 text-red-300" : "bg-red-100 text-red-700"
                    : dark ? "bg-zinc-800 text-zinc-200 hover:bg-zinc-700" : "bg-muted text-foreground hover:bg-border"
              }`}
              title="把当前 Capo 加入个人习惯库（capo_options + capo_default）"
            >
              {saveCapoState === "idle" && "+ 习惯"}
              {saveCapoState === "saving" && "保存中…"}
              {saveCapoState === "saved" && "✓ 已加入"}
              {saveCapoState === "error" && "失败"}
            </button>
          </div>
        )}
        {/* R9.2: 远观模式字号档位按钮 */}
        <div
          className="flex shrink-0 items-center rounded-full border px-1 py-0.5 text-[10px]"
          data-testid="play-view-size-scale"
        >
          {([1, 1.3, 1.6] as const).map(scale => (
            <button
              key={scale}
              type="button"
              data-testid={`play-view-size-${scale}`}
              data-active={sizeScale === scale ? "true" : "false"}
              onClick={() => setSizeScale(scale)}
              className={`rounded-full px-2 py-0.5 transition-colors ${
                sizeScale === scale
                  ? dark ? "bg-amber-500/20 text-amber-300" : "bg-amber-100 text-amber-700"
                  : dark ? "text-zinc-400 hover:text-zinc-200" : "text-muted-foreground hover:text-foreground"
              }`}
              title={scale === 1 ? "标准" : scale === 1.3 ? "中号" : "远观（1.5m+ 距离）"}
            >
              {scale === 1 ? "Aa" : scale === 1.3 ? "Aa" : "AA"}
            </button>
          ))}
        </div>
        {/* R8.1: vocal / instrumental 切换（仅当两轨都有时显示） */}
        {hasVocal && hasInstrumental && (
          <div className="flex shrink-0 items-center rounded-full border px-1 py-0.5 text-[10px]">
            {(["vocal", "instrumental"] as const).map(role => (
              <button
                key={role}
                type="button"
                data-testid={`play-view-role-${role}`}
                data-active={audioRole === role ? "true" : "false"}
                onClick={() => setAudioRole(role)}
                className={`rounded-full px-2 py-0.5 transition-colors ${
                  audioRole === role
                    ? dark ? "bg-emerald-500/20 text-emerald-300" : "bg-emerald-100 text-emerald-700"
                    : dark ? "text-zinc-400 hover:text-zinc-200" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {role === "vocal" ? "原声" : "伴奏"}
              </button>
            ))}
          </div>
        )}
        {/* R8.2: 联播模式标签（点了 LiveView 队列项的弹唱按钮才有） */}
        {linkedSessionId && linkedRequestId && (
          <span
            data-testid="play-view-linked"
            data-session-id={linkedSessionId}
            data-request-id={linkedRequestId}
            className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] ${
              dark ? "bg-sky-500/15 text-sky-300" : "bg-sky-100 text-sky-700"
            }`}
            title={`联播会话 ${linkedSessionId} / 队列项 ${linkedRequestId}`}
          >
            联播 · {linkedRequesterName || "主播"}
          </span>
        )}
        {/* R9.1: 联动模式下「再唱一遍」按钮 — 重置 audio + 重置 recordSubmittedRef + 重新 play */}
        {linkedSessionId && linkedRequestId && (
          <button
            type="button"
            data-testid="play-view-replay"
            onClick={() => {
              const el = audioRef.current;
              if (el) {
                el.currentTime = 0;
                void el.play().catch(() => { /* auto-play 限制或加载失败 */ });
              }
              setCurrentTimeMs(0);
              // 允许再次点「已唱」（如果已经 sung 过一次）
              recordSubmittedRef.current = false;
            }}
            className={`shrink-0 rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ${
              dark
                ? "bg-zinc-800 text-zinc-200 hover:bg-zinc-700"
                : "bg-muted text-foreground hover:bg-border"
            }`}
            title="从头重新弹唱（重置进度 + 重新播放）"
          >
            ↻ 再唱一遍
          </button>
        )}
        {/* R8.2: 联播模式下显示「已唱」按钮 — 手动标记 sung（不等 ended） */}
        {linkedSessionId && linkedRequestId && (
          <button
            type="button"
            data-testid="play-view-mark-sung"
            onClick={() => {
              markLinkedSung();
              onBack();
            }}
            className={`shrink-0 rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ${
              dark
                ? "bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30"
                : "bg-emerald-100 text-emerald-700 hover:bg-emerald-200"
            }`}
            title="标记为「已唱」并回到直播后台"
          >
            已唱 ✓
          </button>
        )}
        <span
          data-testid="play-view-state"
          className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] ${
            isPlaying
              ? dark ? "bg-emerald-500/15 text-emerald-300" : "bg-emerald-50 text-emerald-700"
              : dark ? "bg-zinc-800 text-zinc-400" : "bg-muted text-muted-foreground"
          }`}
        >
          {isPlaying ? "弹唱中" : "准备就绪"}
        </span>
      </header>

      {/* 中央：左歌词 + 右曲谱 */}
      <main className="flex min-h-0 flex-1">
        <section className="flex min-w-0 flex-[3] flex-col border-r" data-region="lyrics">
          <LyricsPanel dark={dark} lines={lyricsLines} currentTimeMs={currentTimeMs} sizeScale={sizeScale} />
        </section>
        <section className="flex min-w-0 flex-[2] flex-col" data-region="tabs">
          <TabsPanel
            dark={dark}
            parsed={tabsParsed}
            currentTimeMs={currentTimeMs}
            totalMs={totalMs}
            lyricsActiveIndex={findActiveLine(lyricsLines, currentTimeMs)}
            sizeScale={sizeScale}
          />
        </section>
      </main>

      {/* 实际 audio 元素（R8.1） */}
      {hasAudio && (
        <audio
          ref={audioRef}
          src={audioSrc}
          preload="metadata"
          data-testid="play-view-audio"
          data-role={audioRole}
          className="hidden"
        />
      )}

      {/* 底部播放器 */}
      <PlayerBar
        dark={dark}
        isPlaying={isPlaying}
        currentTimeMs={currentTimeMs}
        totalMs={totalMs}
        hasAudio={hasAudio}
        onPlay={() => {
          const el = audioRef.current;
          if (el) void el.play().catch(() => { /* 浏览器 auto-play 限制或加载失败 */ });
        }}
        onPause={() => {
          const el = audioRef.current;
          if (el) el.pause();
        }}
        onSeek={(ms) => {
          const el = audioRef.current;
          if (el) el.currentTime = ms / 1000;
          setCurrentTimeMs(ms);
        }}
      />
    </div>
  );
}
