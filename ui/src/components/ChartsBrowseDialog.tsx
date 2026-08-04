/// M2.12 榜单浏览 + 一键入库对话框。
///
/// 流程：
/// 1. 打开自动调 /api/metadata/charts → 官方榜单卡片列表（Router 多源回退，实际 netease 提供）
/// 2. 点榜单卡片 → /api/metadata/playlist { playlist_id: chart_id } 拉榜内歌曲
/// 3. 歌曲列表默认全选 → 「导入选中」→ /api/songs/import (merge mode) 批量入库
/// 4. 成功后 toast + onImported
///
/// 设计要点：
/// - 零新增端点：复用 M2.8 /api/metadata/charts + playlist + M2.3 /api/songs/import
/// - 单面板钻取：榜单列表 ⇄ 榜内歌曲；返回榜单不重新请求（charts 缓存在 state）
/// - 每个榜单的歌曲详情缓存在 Map，返回再进同一榜单不重复请求
/// - 封面图加载失败自动降级为渐变占位（不破坏布局）
/// - 失败：M2.6 useApiError toast + 行内错误双通道

import { useEffect, useRef, useState } from "react";
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

export interface ChartsBrowseDialogProps {
  open: boolean;
  onClose: () => void;
  onImported: () => Promise<void> | void;
}

interface Chart {
  source: string;
  chart_id: string;
  title: string;
  cover_url: string | null;
  description: string | null;
}

interface ChartSong {
  source: string;
  song_id: string;
  title: string;
  artist: string;
  album: string | null;
  duration_ms: number | null;
  cover_url: string | null;
}

interface ChartDetail {
  source: string;
  playlist_id: string;
  title: string;
  creator: string | null;
  cover_url: string | null;
  description: string | null;
  play_count: number | null;
  songs: ChartSong[];
}

interface ImportResult {
  ok: boolean;
  added: number;
  skipped: number;
  errors: string[];
  active: number;
  draft: number;
}

function formatDuration(ms: number | null | undefined): string {
  if (!ms || ms <= 0) return "—";
  const total = Math.round(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

const PLACEHOLDER_GRADIENTS = [
  "from-rose-400/70 to-orange-300/70",
  "from-violet-400/70 to-fuchsia-300/70",
  "from-sky-400/70 to-cyan-300/70",
  "from-emerald-400/70 to-lime-300/70",
  "from-amber-400/70 to-yellow-300/70",
];

/** 封面图：失败自动降级为渐变色 + 首字符占位 */
function ChartCover({ chart, index }: { chart: Chart; index: number }) {
  const [failed, setFailed] = useState(false);
  const showImg = chart.cover_url && !failed;
  if (showImg) {
    return (
      <img
        src={chart.cover_url!}
        alt={chart.title}
        loading="lazy"
        onError={() => setFailed(true)}
        className="w-full h-full object-cover rounded-t-lg"
      />
    );
  }
  return (
    <div
      className={`w-full h-full rounded-t-lg bg-gradient-to-br flex items-center justify-center text-white text-xl font-bold ${
        PLACEHOLDER_GRADIENTS[index % PLACEHOLDER_GRADIENTS.length]
      }`}
    >
      {chart.title.slice(0, 1)}
    </div>
  );
}

export default function ChartsBrowseDialog({
  open, onClose, onImported,
}: ChartsBrowseDialogProps) {
  const { runWithToast } = useApiError();
  // 榜单列表（null = 尚未加载成功）
  const [charts, setCharts] = useState<Chart[] | null>(null);
  const [loadingCharts, setLoadingCharts] = useState(false);
  const [chartsError, setChartsError] = useState("");
  // 钻取状态：null = 榜单列表视图；非 null = 榜内歌曲视图
  const [activeChart, setActiveChart] = useState<Chart | null>(null);
  const [playlist, setPlaylist] = useState<ChartDetail | null>(null);
  const [loadingSongs, setLoadingSongs] = useState(false);
  const [songsError, setSongsError] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  // 榜单 → 歌曲详情缓存（返回再进不重复请求）
  const cacheRef = useRef<Map<string, ChartDetail>>(new Map());

  const isOnline = getOnlineState() === "online";

  // 打开时重置状态 + 自动加载榜单
  useEffect(() => {
    if (open) {
      setActiveChart(null);
      setPlaylist(null);
      setImportResult(null);
      setSongsError("");
      if (charts === null) {
        void loadCharts();
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const loadCharts = async () => {
    if (!isOnline) {
      setChartsError("离线状态无法浏览榜单");
      return;
    }
    setLoadingCharts(true);
    setChartsError("");
    try {
      const data = await runWithToast(
        () => apiRequest<Chart[]>("/api/metadata/charts", {
          method: "POST",
          body: {},
        }),
        "加载榜单失败",
      );
      setCharts(data);
    } catch {
      setChartsError("加载榜单失败，请检查网络后重试");
    } finally {
      setLoadingCharts(false);
    }
  };

  const openChart = async (chart: Chart) => {
    setActiveChart(chart);
    setImportResult(null);
    setSongsError("");
    const cached = cacheRef.current.get(chart.chart_id);
    if (cached) {
      setPlaylist(cached);
      setSelected(new Set(cached.songs.map(s => `${s.source}:${s.song_id}`)));
      return;
    }
    if (!isOnline) {
      setSongsError("离线状态无法加载榜单歌曲");
      return;
    }
    setLoadingSongs(true);
    setPlaylist(null);
    try {
      const data = await runWithToast(
        () => apiRequest<ChartDetail>("/api/metadata/playlist", {
          method: "POST",
          body: { playlist_id: chart.chart_id },
        }),
        "加载榜单歌曲失败",
      );
      cacheRef.current.set(chart.chart_id, data);
      setPlaylist(data);
      // 默认全选
      setSelected(new Set(data.songs.map(s => `${s.source}:${s.song_id}`)));
    } catch {
      setSongsError("加载榜单歌曲失败，请重试");
    } finally {
      setLoadingSongs(false);
    }
  };

  const goBack = () => {
    setActiveChart(null);
    setPlaylist(null);
    setImportResult(null);
    setSongsError("");
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
    setSongsError("");
    const songsToImport = playlist.songs
      .filter(s => selected.has(`${s.source}:${s.song_id}`))
      .map(s => ({
        title: s.title,
        artists: s.artist.split(/\s*\/\s*/).filter(Boolean),
        status: "draft",  // 默认 draft（未学）；用户后续手动标记 active
        notes: `[meta:${s.source} chart=${playlist.playlist_id} song_id=${s.song_id} ${new Date().toISOString().slice(0, 10)}]`,
      }));
    try {
      const result = await runWithToast(
        () => apiRequest<ImportResult>("/api/songs/import", {
          method: "POST",
          body: { mode: "merge", songs: songsToImport },
        }),
        "导入榜单歌曲失败",
      );
      setImportResult(result);
      // 触发父组件 refresh
      await onImported();
    } catch {
      setSongsError("导入失败，已选歌曲未写入曲库");
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

  const listView = (
    <>
      <div className="flex-1 overflow-y-auto min-h-0 space-y-2">
        {loadingCharts && (
          <p className="text-sm text-muted-foreground py-6 text-center" data-testid="charts-loading">
            正在加载榜单…
          </p>
        )}

        {chartsError && (
          <div className="py-6 text-center space-y-2" data-testid="charts-error">
            <p className="text-sm text-destructive">{chartsError}</p>
            <Button type="button" variant="outline" size="sm" onClick={() => void loadCharts()}>
              重试
            </Button>
          </div>
        )}

        {!loadingCharts && !chartsError && charts !== null && charts.length === 0 && (
          <p className="text-sm text-muted-foreground py-8 text-center" data-testid="empty-charts">
            暂无可用榜单
          </p>
        )}

        {!loadingCharts && !chartsError && charts !== null && charts.length > 0 && (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2" data-testid="charts-grid">
            {charts.map((chart, i) => (
              <button
                key={chart.chart_id}
                type="button"
                onClick={() => void openChart(chart)}
                className="group rounded-lg border border-border bg-background overflow-hidden text-left hover:border-primary/60 hover:shadow-sm transition-all cursor-pointer"
                data-testid="chart-card"
              >
                <div className="aspect-square">
                  <ChartCover chart={chart} index={i} />
                </div>
                <div className="p-2">
                  <p className="text-[13px] font-medium leading-tight line-clamp-1" data-testid="chart-title">
                    {chart.title}
                  </p>
                  {chart.description && (
                    <p className="text-[11px] text-muted-foreground leading-tight line-clamp-1 mt-0.5">
                      {chart.description}
                    </p>
                  )}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      <DialogFooter className="flex-shrink-0">
        <Button type="button" variant="ghost" onClick={handleClose} disabled={importing}>
          关闭
        </Button>
      </DialogFooter>
    </>
  );

  const songsView = (
    <>
      <div className="flex items-center gap-2 flex-shrink-0">
        <button
          type="button"
          onClick={goBack}
          disabled={importing}
          className="text-xs text-primary hover:underline disabled:opacity-50"
          data-testid="back-button"
        >
          ← 榜单列表
        </button>
        <p className="text-xs text-muted-foreground truncate flex-1">
          {activeChart?.title}
        </p>
      </div>

      <div className="flex-1 overflow-y-auto min-h-0 mt-2 space-y-1.5">
        {loadingSongs && (
          <p className="text-sm text-muted-foreground py-6 text-center" data-testid="songs-loading">
            正在加载榜单歌曲…
          </p>
        )}

        {songsError && (
          <div className="py-6 text-center" data-testid="songs-error">
            <p className="text-sm text-destructive">{songsError}</p>
          </div>
        )}

        {playlist && playlist.songs.length === 0 && (
          <p className="text-sm text-muted-foreground py-8 text-center" data-testid="empty-songs">
            该榜单暂无歌曲
          </p>
        )}

        {playlist && playlist.songs.length > 0 && (
          <>
            <div className="flex items-center justify-between px-1">
              <p className="text-xs text-muted-foreground" data-testid="songs-count">
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

      {importResult && (
        <div
          className="rounded-md bg-muted/60 p-3 text-xs space-y-0.5 flex-shrink-0"
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
    </>
  );

  return (
    <Dialog open={open} onOpenChange={o => { if (!o) handleClose(); }}>
      <DialogContent
        className="sm:max-w-[640px] max-h-[85vh] overflow-hidden flex flex-col"
        data-testid="charts-browse-dialog"
      >
        <DialogHeader className="flex-shrink-0">
          <DialogTitle>{activeChart ? "榜单歌曲" : "官方榜单"}</DialogTitle>
        </DialogHeader>

        {activeChart === null ? listView : songsView}
      </DialogContent>
    </Dialog>
  );
}
