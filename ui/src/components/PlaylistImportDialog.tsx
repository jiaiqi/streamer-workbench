/// M2.11 网易云/QQ 公开歌单导入对话框。
///
/// 流程：
/// 1. 输入 provider + playlist_id
/// 2. 点「预览」→ 调 /api/metadata/playlist 拉歌曲列表（Router 自动 netease/qq 回退）
/// 3. 列出歌曲 + 全选 checkbox
/// 4. 点「导入选中」→ 用 /api/songs/import (merge mode) 批量入库
/// 5. 成功后 toast + onImported + onClose
///
/// 设计要点：
/// - 不调新的专用 endpoint，复用 M2.8 /api/metadata/playlist + M2.3 /api/songs/import
/// - provider 可选 netease/qq（QQ 暂未实现 get_playlist，会通过 Router 跳 netease；后续 QQ 实现后自动可用）
/// - 默认全选已加载的歌曲
/// - 失败：M2.6 useApiError toast + 行内错误双通道
/// - 导入时不勾选的歌曲跳过（用户主动）

import { useEffect, useState } from "react";
import { apiRequest } from "../api/client";
import { useApiError } from "../async/useApiError";
import { getOnlineState } from "./OnlineStatusBadge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export interface PlaylistImportDialogProps {
  open: boolean;
  onClose: () => void;
  onImported: () => Promise<void> | void;
  /** 当前 router 注册的 providers；null = 用默认 netease/qq */
  availableProviders?: string[];
}

interface PlaylistHit {
  source: string;
  song_id: string;
  title: string;
  artist: string;
  album: string | null;
  duration_ms: number | null;
  cover_url: string | null;
}

interface PlaylistDetail {
  source: string;
  playlist_id: string;
  title: string;
  creator: string | null;
  cover_url: string | null;
  description: string | null;
  play_count: number | null;
  songs: PlaylistHit[];
}

interface ImportResult {
  ok: boolean;
  added: number;
  skipped: number;
  errors: string[];
  active: number;
  draft: number;
}

const DEFAULT_PROVIDERS = ["netease", "qq"];

function formatDuration(ms: number | null | undefined): string {
  if (!ms || ms <= 0) return "—";
  const total = Math.round(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export default function PlaylistImportDialog({
  open, onClose, onImported, availableProviders,
}: PlaylistImportDialogProps) {
  const { runWithToast } = useApiError();
  const [provider, setProvider] = useState<string>("netease");
  const [playlistId, setPlaylistId] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [playlist, setPlaylist] = useState<PlaylistDetail | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [inlineError, setInlineError] = useState<string>("");
  const [importResult, setImportResult] = useState<ImportResult | null>(null);

  // 打开时重置状态
  useEffect(() => {
    if (open) {
      setPlaylist(null);
      setSelected(new Set());
      setInlineError("");
      setImportResult(null);
    }
  }, [open]);

  const providers = availableProviders && availableProviders.length > 0
    ? availableProviders
    : DEFAULT_PROVIDERS;
  const isOnline = getOnlineState() === "online";

  const handlePreview = async () => {
    if (!playlistId.trim()) {
      setInlineError("请输入歌单 ID");
      return;
    }
    if (!isOnline) {
      setInlineError("离线状态无法预览");
      return;
    }
    setLoading(true);
    setInlineError("");
    setImportResult(null);
    try {
      const data = await runWithToast(
        () => apiRequest<PlaylistDetail>("/api/metadata/playlist", {
          method: "POST",
          body: {
            playlist_id: playlistId.trim(),
            preferred_provider: provider,
          },
        }),
        "拉取歌单失败",
      );
      setPlaylist(data);
      // 默认全选
      setSelected(new Set(data.songs.map(s => `${s.source}:${s.song_id}`)));
    } catch {
      setPlaylist(null);
      setInlineError("拉取歌单失败，请检查 ID 是否正确或换个 provider");
    } finally {
      setLoading(false);
    }
  };

  const toggleOne = (key: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const toggleAll = () => {
    if (!playlist) return;
    if (selected.size === playlist.songs.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(playlist.songs.map(s => `${s.source}:${s.song_id}`)));
    }
  };

  const handleImport = async () => {
    if (!playlist || selected.size === 0) return;
    setImporting(true);
    setInlineError("");
    const songsToImport = playlist.songs
      .filter(s => selected.has(`${s.source}:${s.song_id}`))
      .map(s => ({
        title: s.title,
        artists: s.artist.split(/\s*\/\s*/).filter(Boolean),
        status: "draft",  // 默认 draft（未学）；用户后续手动标记 active
        notes: `[meta:${s.source} playlist=${playlist.playlist_id} song_id=${s.song_id} ${new Date().toISOString().slice(0, 10)}]`,
      }));
    try {
      const result = await runWithToast(
        () => apiRequest<ImportResult>("/api/songs/import", {
          method: "POST",
          body: { mode: "merge", songs: songsToImport },
        }),
        "导入歌单失败",
      );
      setImportResult(result);
      // 触发父组件 refresh
      await onImported();
    } catch {
      setInlineError("导入失败，已选歌曲未写入曲库");
    } finally {
      setImporting(false);
    }
  };

  const handleClose = () => {
    if (importing) return;
    onClose();
  };

  const selectedCount = selected.size;
  const totalCount = playlist?.songs.length ?? 0;

  return (
    <Dialog open={open} onOpenChange={o => { if (!o) handleClose(); }}>
      <DialogContent
        className="sm:max-w-[640px] max-h-[85vh] overflow-hidden flex flex-col"
        data-testid="playlist-import-dialog"
      >
        <DialogHeader>
          <DialogTitle>从歌单导入</DialogTitle>
        </DialogHeader>

        <div className="space-y-3 flex-shrink-0">
          <div className="grid grid-cols-[auto_1fr] gap-3 items-end">
            <div className="grid gap-1.5">
              <Label className="text-muted-foreground text-xs font-normal">来源</Label>
              <select
                data-testid="provider-select"
                value={provider}
                onChange={e => setProvider(e.target.value)}
                disabled={loading || importing}
                className="flex h-9 rounded-md border border-input bg-transparent px-3 text-sm"
              >
                {providers.map(p => (
                  <option key={p} value={p}>
                    {p === "netease" ? "网易云" : p === "qq" ? "QQ 音乐" : p}
                  </option>
                ))}
              </select>
            </div>
            <div className="grid gap-1.5">
              <Label className="text-muted-foreground text-xs font-normal">
                歌单 ID（公开 ID，例 网易云: https://music.163.com/playlist?id=<strong>123</strong>）
              </Label>
              <div className="flex gap-2">
                <Input
                  data-testid="playlist-id-input"
                  value={playlistId}
                  onChange={e => setPlaylistId(e.target.value)}
                  placeholder="公开歌单 ID"
                  disabled={loading || importing}
                  className="flex-1"
                />
                <Button
                  type="button"
                  onClick={handlePreview}
                  disabled={loading || importing || !playlistId.trim() || !isOnline}
                  data-testid="preview-button"
                  title={!isOnline ? "离线状态不可用" : ""}
                >
                  {loading ? "加载中…" : "预览"}
                </Button>
              </div>
            </div>
          </div>

          {inlineError && (
            <p className="text-sm text-destructive" role="alert" data-testid="inline-error">
              {inlineError}
            </p>
          )}

          {importResult && (
            <div
              className="rounded-md bg-muted/60 p-3 text-xs space-y-0.5"
              data-testid="import-result"
            >
              <p className="font-medium text-foreground">
                导入完成：新增 {importResult.added} 首 / 跳过 {importResult.skipped} 首
              </p>
              <p className="text-muted-foreground">
                当前曲库：active {importResult.active} / draft {importResult.draft}
              </p>
              {importResult.errors.length > 0 && (
                <p className="text-destructive" data-testid="import-errors">
                  错误：{importResult.errors.slice(0, 3).join("；")}
                  {importResult.errors.length > 3 && ` 等 ${importResult.errors.length} 条`}
                </p>
              )}
            </div>
          )}
        </div>

        <div className="flex-1 overflow-y-auto min-h-0 mt-3 space-y-1.5">
          {!playlist && !loading && (
            <p className="text-sm text-muted-foreground py-8 text-center" data-testid="empty-state">
              输入歌单 ID 拉取预览
            </p>
          )}

          {loading && (
            <p className="text-sm text-muted-foreground py-6 text-center" data-testid="loading">
              正在拉取歌单…
            </p>
          )}

          {playlist && playlist.songs.length === 0 && (
            <p className="text-sm text-muted-foreground py-8 text-center" data-testid="empty-playlist">
              该歌单无歌曲
            </p>
          )}

          {playlist && playlist.songs.length > 0 && (
            <>
              <div className="flex items-center justify-between px-1">
                <p className="text-xs text-muted-foreground">
                  {playlist.title}
                  {playlist.creator ? ` · ${playlist.creator}` : ""}
                  {" · "}
                  共 {totalCount} 首
                </p>
                <button
                  type="button"
                  onClick={toggleAll}
                  disabled={importing}
                  className="text-xs text-primary hover:underline disabled:opacity-50"
                  data-testid="toggle-all"
                >
                  {selectedCount === totalCount ? "全不选" : "全选"}
                </button>
              </div>
              <ul className="space-y-1" data-testid="song-list">
                {playlist.songs.map(song => {
                  const key = `${song.source}:${song.song_id}`;
                  const isSelected = selected.has(key);
                  return (
                    <li key={key}>
                      <label
                        className="flex items-baseline gap-2 px-2 py-1.5 rounded hover:bg-accent cursor-pointer"
                        data-testid="song-row"
                      >
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleOne(key)}
                          disabled={importing}
                          className="shrink-0"
                          data-testid="song-checkbox"
                        />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-baseline gap-2">
                            <span className="text-sm font-medium truncate flex-1">
                              {song.title}
                            </span>
                            <span className="text-[11px] text-muted-foreground tabular-nums shrink-0">
                              {formatDuration(song.duration_ms)}
                            </span>
                          </div>
                          <p className="text-xs text-muted-foreground truncate">
                            {song.artist}
                            {song.album ? ` · ${song.album}` : ""}
                          </p>
                        </div>
                      </label>
                    </li>
                  );
                })}
              </ul>
            </>
          )}
        </div>

        <DialogFooter className="flex-shrink-0">
          <Button type="button" variant="ghost" onClick={handleClose} disabled={importing}>
            关闭
          </Button>
          <Button
            type="button"
            onClick={handleImport}
            disabled={!playlist || selectedCount === 0 || importing || importResult !== null}
            data-testid="import-button"
          >
            {importing ? "导入中…" : importResult ? "已导入" : `导入选中（${selectedCount}）`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
