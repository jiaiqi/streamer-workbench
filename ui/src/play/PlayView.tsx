/// R8.0 弹唱：PlayView — 弹唱主视图
///
/// 整合 LyricsPanel + TabsPanel + PlayerBar；v8.0 用"模拟时间"驱动（用 setInterval 模拟播放）。
/// 父组件传入 song 数据（包含 lyrics_lrc / lyrics_plain / tabs 字段）。
///
/// 设计：
///   - 顶栏：返回按钮 + 歌名 - 歌手 + 状态标签
///   - 中央：左歌词（60%宽）+ 右曲谱（40%宽）
///   - 底部：PlayerBar
///   - 数据缺失：显示 EmptyState 提示"这首歌还没歌词/曲谱"
import { useEffect, useMemo, useRef, useState } from "react";
import { apiRequest } from "../api/client";
import type { Song, SongsData } from "../types";
import { parseLrc, distributePlainLyrics } from "./lrc";
import { parseChordpro } from "./chordpro";
import LyricsPanel from "./LyricsPanel";
import TabsPanel from "./TabsPanel";
import PlayerBar from "./PlayerBar";
import { Icon } from "../icons";

export interface PlayViewProps {
  dark: boolean;
  songId: string;
  onBack: () => void;
}

const DEFAULT_TOTAL_MS = 4 * 60 * 1000; // 4 分钟默认时长（无音频时用）

function pickSong(songs: Song[] | undefined, songId: string): Song | null {
  if (!Array.isArray(songs)) return null;
  return songs.find(s => s.id === songId) ?? null;
}

export default function PlayView({ dark, songId, onBack }: PlayViewProps) {
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

  // 估算总时长：优先 audio_duration_ms；否则用歌词行数 × 8 秒（每行约 8 秒经验值）
  const totalMs = useMemo(() => {
    if (song?.audio_duration_ms && song.audio_duration_ms > 0) return song.audio_duration_ms;
    if (lyricsLines.length > 0) return lyricsLines.length * 8_000;
    return DEFAULT_TOTAL_MS;
  }, [song, lyricsLines]);

  // 模拟播放：isPlaying 时每秒推 1000ms
  useEffect(() => {
    if (!isPlaying) {
      if (timerRef.current !== null) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      return;
    }
    timerRef.current = window.setInterval(() => {
      setCurrentTimeMs(prev => {
        const next = prev + 1000;
        if (next >= totalMs) {
          setIsPlaying(false);
          return totalMs;
        }
        return next;
      });
    }, 1000);
    return () => {
      if (timerRef.current !== null) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [isPlaying, totalMs]);

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
          <LyricsPanel dark={dark} lines={lyricsLines} currentTimeMs={currentTimeMs} />
        </section>
        <section className="flex min-w-0 flex-[2] flex-col" data-region="tabs">
          <TabsPanel
            dark={dark}
            parsed={tabsParsed}
            currentTimeMs={currentTimeMs}
            totalMs={totalMs}
          />
        </section>
      </main>

      {/* 底部播放器 */}
      <PlayerBar
        dark={dark}
        isPlaying={isPlaying}
        currentTimeMs={currentTimeMs}
        totalMs={totalMs}
        hasAudio={false /* v8.0 暂不接 audio */}
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
        onSeek={setCurrentTimeMs}
      />
    </div>
  );
}
