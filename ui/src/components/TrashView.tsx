/// R9.6 垃圾桶视图：列出 deleted_at 距今 ≤ 30 天的歌曲。
/// - 恢复（POST /api/songs/{id}/restore）
/// - 永久删除（DELETE /api/songs/{id}?permanent=true）
/// - 30 天后自动清理（cleanup_expired 在 list 端点触发）
import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../api/client";
import { asString, asRecord, asStringArray } from "../lib/narrow";
import { useApiError } from "../async/useApiError";
import { type RequestFailure } from "../async/requestState";

interface TrashSong {
  id: string;
  title: string;
  artists: string[];
  status: string;
  deleted_at: string;
}

interface TrashViewProps {
  dark: boolean;
  onChanged: () => void; // 通知父组件库可能变更
}

function asTrashSong(value: unknown): TrashSong | null {
  const v = asRecord(value);
  if (!v) return null;
  const id = asString(v, "id");
  const title = asString(v, "title");
  const deleted_at = asString(v, "deleted_at");
  if (!id || !title) return null;
  const artists = asStringArray(v, "artists") ?? [];
  return {
    id,
    title,
    artists,
    status: asString(v, "status") ?? "active",
    deleted_at,
  };
}

function formatDeletedAt(iso: string): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

function daysSince(iso: string): number {
  if (!iso) return 0;
  const d = new Date(iso).getTime();
  if (Number.isNaN(d)) return 0;
  return Math.floor((Date.now() - d) / 86_400_000);
}

export default function TrashView({ dark, onChanged }: TrashViewProps) {
  // M2.6 错误全局 toast 化
  const { runWithToast } = useApiError();
  const [songs, setSongs] = useState<TrashSong[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await runWithToast(
        () => apiRequest<{ songs?: unknown[] }>("/api/songs/trash"),
        "加载垃圾桶失败",
      );
      const list = (data?.songs ?? []).map(asTrashSong).filter((s): s is TrashSong => s !== null);
      list.sort((a, b) => b.deleted_at.localeCompare(a.deleted_at));
      setSongs(list);
    } catch (failure) {
      setError((failure as RequestFailure).message);
    } finally {
      setLoading(false);
    }
  }, [runWithToast]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleRestore = useCallback(async (song: TrashSong) => {
    if (busyId) return;
    setBusyId(song.id);
    try {
      await runWithToast(
        () => apiRequest(`/api/songs/${encodeURIComponent(song.id)}/restore`, { method: "POST" }),
        "恢复失败",
      );
      setSongs(prev => prev.filter(s => s.id !== song.id));
      onChanged();
    } catch (failure) {
      setError((failure as RequestFailure).message);
    } finally {
      setBusyId(null);
    }
  }, [busyId, onChanged, runWithToast]);

  const handlePurge = useCallback(async (song: TrashSong) => {
    if (busyId) return;
    if (!window.confirm(`确定永久删除「${song.title}」？此操作不可恢复。`)) return;
    setBusyId(song.id);
    try {
      await runWithToast(
        () => apiRequest(`/api/songs/${encodeURIComponent(song.id)}?permanent=true`, { method: "DELETE" }),
        "永久删除失败",
      );
      setSongs(prev => prev.filter(s => s.id !== song.id));
      onChanged();
    } catch (failure) {
      setError((failure as RequestFailure).message);
    } finally {
      setBusyId(null);
    }
  }, [busyId, onChanged, runWithToast]);

  if (loading) {
    return (
      <div className="px-6 py-8 text-center text-sm text-muted-foreground">加载垃圾桶…</div>
    );
  }

  if (error) {
    return (
      <div className="px-6 py-4">
        <p className="text-sm text-red-600" role="alert">{error}</p>
      </div>
    );
  }

  if (songs.length === 0) {
    return (
      <div className="px-6 py-12 text-center">
        <p className="text-sm text-muted-foreground">垃圾桶是空的</p>
        <p className="mt-1 text-[11px] text-muted-foreground/70">
          删歌后会在此保留 30 天，30 天后自动清理。
        </p>
      </div>
    );
  }

  return (
    <div className="px-6 py-4 max-w-3xl mx-auto">
      <div className="mb-4">
        <h2 className="text-base font-semibold">垃圾桶</h2>
        <p className="text-[11px] text-muted-foreground">
          共 {songs.length} 首 · 30 天后自动清理 · 恢复后回到曲库
        </p>
      </div>
      <ul className="space-y-2" data-testid="trash-list">
        {songs.map(song => {
          const days = daysSince(song.deleted_at);
          const willExpire = 30 - days;
          return (
            <li
              key={song.id}
              data-testid="trash-item"
              data-song-id={song.id}
              className={`flex items-center gap-3 rounded-xl border px-3 py-2.5 ${
                dark ? "border-zinc-700/60 bg-zinc-900/40" : "border-border bg-card"
              }`}
            >
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium truncate">{song.title}</div>
                <div className={`text-[11px] ${dark ? "text-zinc-500" : "text-muted-foreground"} flex gap-2`}>
                  {song.artists.length > 0 && <span>{song.artists.join(" · ")}</span>}
                  <span>· 删除于 {formatDeletedAt(song.deleted_at)}</span>
                  <span className={willExpire <= 3 ? "text-red-600" : ""}>
                    · {willExpire} 天后清掉
                  </span>
                </div>
              </div>
              <button
                type="button"
                data-testid="trash-restore"
                disabled={busyId === song.id}
                onClick={() => { void handleRestore(song); }}
                className={`text-xs rounded-lg px-2.5 py-1 font-medium transition-colors ${
                  dark
                    ? "bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30"
                    : "bg-emerald-100 text-emerald-700 hover:bg-emerald-200"
                }`}
              >
                {busyId === song.id ? "处理中…" : "恢复"}
              </button>
              <button
                type="button"
                data-testid="trash-purge"
                disabled={busyId === song.id}
                onClick={() => { void handlePurge(song); }}
                className={`text-xs rounded-lg px-2.5 py-1 font-medium transition-colors ${
                  dark
                    ? "bg-red-500/15 text-red-300 hover:bg-red-500/25"
                    : "bg-red-100 text-red-700 hover:bg-red-200"
                }`}
              >
                永久删除
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
