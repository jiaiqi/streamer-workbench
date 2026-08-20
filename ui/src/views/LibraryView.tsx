import { useState, useEffect, useMemo, useRef } from "react";
import type { Song, SongsData } from "../types";
import SongEditDialog from "../components/SongEditDialog";
import TabsPanel from "../components/TabsPanel";
import AsyncStateNotice from "../components/AsyncStateNotice";
import ErrorBanner from "../components/ErrorBanner";
import TrashView from "../components/TrashView";
import PlaylistImportDialog from "../components/PlaylistImportDialog";
import ChartsBrowseDialog from "../components/ChartsBrowseDialog";
import { useToast } from "../components/Toast";
import { apiRequest } from "../api/client";
import { exportBySongIds, exportLibrary, importLibrary, listSnapshots, restoreSnapshot } from "../api/posters";
import { usePosterStore } from "../posters/usePosterStore";
import { useLatestRequest, type RequestFailure } from "../async/requestState";
import { useApiError } from "../async/useApiError";

/* ================= 符号化元数据 ================= */
// 难度 → 菱形阶（◆◆◇），一瞥可读
function DifficultyMark({ value, dark }: { value: string; dark: boolean }) {
  const level = value === "简单" ? 1 : value === "中等" ? 2 : value === "困难" ? 3 : 0;
  if (level === 0) return <span className="text-muted-foreground/60">—</span>;
  return (
    <span className={`tracking-[0.15em] text-[10px] ${dark ? "text-zinc-400" : "text-muted-foreground"}`}
      title={`难度：${value}`}>
      {"◆".repeat(level)}{"◇".repeat(3 - level)}
    </span>
  );
}

// 选调 + 变调夹（等宽排版，保证列对齐）
function KeyCapo({ song }: { song: Song }) {
  if (!song.key && song.capo === null) return <span className="text-muted-foreground/60">—</span>;
  return (
    <span className="tabular-nums">
      <span className={song.key ? "" : "text-muted-foreground/60"}>{song.key || "?"}</span>
      {song.capo !== null && <span className="text-muted-foreground text-[11px]"> +{song.capo}</span>}
    </span>
  );
}

// 卡片网格：auto-fill + minmax 天然响应不同分辨率，无需断点
const GRID_CLASS = "grid gap-3 grid-cols-[repeat(auto-fill,minmax(232px,1fr))]";

/* ================= 主视图 ================= */
function SnapshotsView({ dark, onChanged }: { dark: boolean; onChanged: () => void }) {
  const [items, setItems] = useState<Array<{ filename: string; size_bytes: number; modified_at: string }>>([]);
  const [loading, setLoading] = useState(true);
  const [restoring, setRestoring] = useState<string | null>(null);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listSnapshots();
      setItems(res.items);
    } catch { /* ignore — toast 由 useApiError 处理 */ }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const handleRestore = async (filename: string) => {
    if (!window.confirm(`确定从快照「${filename}」恢复？
恢复后当前曲库内容会被覆盖（不会丢失，备份仍在 backups/songs/）。`)) return;
    setRestoring(filename);
    try {
      await restoreSnapshot(filename);
      onChanged();
      await load();
    } finally {
      setRestoring(null);
    }
  };
  if (loading) {
    return <div className="px-6 py-8 text-center text-sm text-muted-foreground">加载快照…</div>;
  }
  if (items.length === 0) {
    return (
      <div className="px-6 py-8 text-center">
        <p className="text-sm text-muted-foreground">暂无快照。每次曲库变更（新增/编辑/状态切换/删除/导入）会自动备份到 <code className="font-mono text-[12px]">backups/songs/</code>。</p>
      </div>
    );
  }
  return (
    <div className="px-6 py-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className={`text-[14px] font-semibold ${dark ? "text-zinc-200" : "text-foreground"}`}>
          曲库快照（共 {items.length} 个，保留最近 20 个）
        </h3>
        <button
          type="button"
          onClick={load}
          className={`text-[12px] px-2 h-7 rounded transition-colors ${
            dark ? "text-zinc-400 hover:bg-zinc-800" : "text-muted-foreground hover:bg-muted"
          }`}>
          刷新
        </button>
      </div>
      <ul className="space-y-1.5">
        {items.map(it => (
          <li
            key={it.filename}
            data-testid={`snapshot-item-${it.filename}`}
            className={`flex items-center gap-3 rounded-lg px-3 py-2 text-[13px] ${
              dark ? "bg-zinc-800/50 hover:bg-zinc-800" : "bg-muted/50 hover:bg-muted"
            }`}>
            <span className={`flex-1 font-mono text-[12px] ${dark ? "text-zinc-300" : "text-foreground"}`}>
              {it.filename}
            </span>
            <span className={`text-[11px] tabular-nums ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
              {(it.size_bytes / 1024).toFixed(1)} KB
            </span>
            <span className={`text-[11px] tabular-nums ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
              {it.modified_at}
            </span>
            <button
              type="button"
              onClick={() => handleRestore(it.filename)}
              disabled={restoring === it.filename}
              data-testid={`snapshot-restore-${it.filename}`}
              className="rounded-md px-2.5 h-7 text-[12px] font-medium transition-colors cursor-pointer disabled:opacity-40 bg-blue-600 hover:bg-blue-700 text-white">
              {restoring === it.filename ? "恢复中…" : "恢复"}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function LibraryView({ dark, onStatsChange, onEditTargetChange, onPlaySong }: {
  dark: boolean;
  onStatsChange: (s: { active: number; draft: number }) => void;
  onEditTargetChange?: (open: boolean) => void;
  /** R8.0: 触发弹唱视图（点击卡片 ▶ 按钮 / 双击行） */
  onPlaySong?: (songId: string) => void;
}) {
  const [songsData, setSongsData] = useState<SongsData | null>(null);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "draft" | "trash">("all");
  // L2.2 批量导出：当前工作台 layout/theme/canvas
  const posterStore = usePosterStore();
  const [expanded, setExpanded] = useState<string | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [editTarget, setEditTarget] = useState<Song | "new" | null>(null);
  // M2.11 从歌单导入对话框
  const [playlistImportOpen, setPlaylistImportOpen] = useState(false);
  // M2.12 榜单浏览对话框
  const [chartsBrowseOpen, setChartsBrowseOpen] = useState(false);
  const [actionSong, setActionSong] = useState<string | null>(null);
  const [actionError, setActionError] = useState("");
  const listRequest = useLatestRequest<SongsData>({ isEmpty: data => data.total === 0 });
  const [seedPending, setSeedPending] = useState(false);
  /* L2.1 批量操作：多选模式 + 已选标题集合 */
  const [selectMode, setSelectMode] = useState(false);
  const [selectedTitles, setSelectedTitles] = useState<Set<string>>(() => new Set());
  const [batchPending, setBatchPending] = useState(false);
  const [exportPending, setExportPending] = useState(false);
  const [importPending, setImportPending] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const rowRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const listRef = useRef<HTMLDivElement>(null);
  const probeRef = useRef<HTMLDivElement>(null);
  // M9.6b 全局 toast — 删除成功显示 5s 撤销按钮
  const toast = useToast();
  // M2.6 错误全局 toast 化 — 失败时自动 toast.error，上层 catch 仍可 setError
  const { runWithToast } = useApiError();

  const refresh = async () => {
    const d = await listRequest.run(signal => apiRequest<SongsData>("/api/songs/list", { signal }));
    if (!d) return;
    setSongsData(d);
    onStatsChange({ active: d.active, draft: d.draft });
  };

  // P1 R1a.2 首用引导：空曲库 → 一键载入内置示例曲库
  const handleSeedSample = async () => {
    if (seedPending) return;
    setSeedPending(true);
    setActionError("");
    try {
      const res = await runWithToast(
        () => apiRequest<{ ok: boolean; added: string[] }>(
          "/api/songs/seed-sample", { method: "POST", body: {} },
        ),
        "示例曲库载入失败",
      );
      if (res.added.length > 0) {
        setActionError(""); // 清空旧错误
      }
      await refresh();
    } catch (failure) {
      setActionError((failure as RequestFailure).message);
    } finally {
      setSeedPending(false);
    }
  };

  /* 曲谱上传/删除后局部更新该曲的 tab_files（不必全量 refresh） */
  const updateTabFiles = (title: string, files: string[]) => {
    setSongsData(d => d && ({
      ...d,
      songs: d.songs.map(s => s.title === title ? { ...s, tab_files: files } : s),
    }));
  };

  useEffect(() => { refresh(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);
  useEffect(() => { onEditTargetChange?.(editTarget !== null); }, [editTarget, onEditTargetChange]);

  /* ---- 筛选：歌名 / 歌手 / 拼音首字母 ---- */
  const filtered = useMemo(() => {
    if (!songsData) return [];
    const q = query.trim().toLowerCase();
    return songsData.songs
      .filter(s => statusFilter === "all" || s.status === statusFilter)
      .filter(s => !q
        || s.title.toLowerCase().includes(q)
        || s.artists.join(" ").toLowerCase().includes(q)
        || (s.pinyin ?? "").toLowerCase().includes(q));
  }, [songsData, query, statusFilter]);

  /* ---- 按字数分类分组（1..7 + 未分类），组内保持后端序 ---- */
  const groups = useMemo(() => {
    const map = new Map<number, Song[]>();
    for (const s of filtered) {
      const sec = s.section ?? 0;
      if (!map.has(sec)) map.set(sec, []);
      map.get(sec)!.push(s);
    }
    return [...map.entries()].sort((a, b) => (a[0] === 0 ? 99 : a[0]) - (b[0] === 0 ? 99 : b[0]));
  }, [filtered]);

  const groupLabel = (sec: number) => sec === 0 ? "未分类" : sec >= 7 ? "7+ 字" : `${sec} 字`;

  /* ---- 当前网格实际列数（从隐藏探针元素的 computed style 读） ---- */
  const currentCols = () => {
    const el = probeRef.current;
    if (!el) return 1;
    const tracks = getComputedStyle(el).gridTemplateColumns;
    if (!tracks || tracks === "none") return 1;
    return tracks.split(" ").length;
  };

  /* ---- 键盘导航：←→↑↓ 光标 · Enter 展开 · X 学会了 · / 搜索 ---- */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (editTarget !== null) return;
      const tag = (e.target as HTMLElement)?.tagName;
      const typing = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";

      if (e.key === "/" && !typing) {
        e.preventDefault();
        searchRef.current?.focus();
        return;
      }
      if (typing || filtered.length === 0) return;

      const idx = cursor === null ? -1 : filtered.findIndex(s => s.title === cursor);
      const cols = currentCols();
      let next: number | null = null;
      if (e.key === "ArrowRight") next = Math.min(filtered.length - 1, idx + 1);
      else if (e.key === "ArrowLeft") next = Math.max(0, idx === -1 ? 0 : idx - 1);
      else if (e.key === "ArrowDown") next = Math.min(filtered.length - 1, (idx === -1 ? 0 : idx) + (idx === -1 ? 0 : cols));
      else if (e.key === "ArrowUp") next = Math.max(0, idx - cols);

      if (next !== null) {
        e.preventDefault();
        const title = filtered[next].title;
        setCursor(title);
        rowRefs.current.get(title)?.scrollIntoView({ block: "nearest" });
      } else if (e.key === "Enter" && cursor) {
        e.preventDefault();
        setExpanded(prev => prev === cursor ? null : cursor);
      } else if ((e.key === "x" || e.key === "X") && cursor) {
        e.preventDefault();
        const song = filtered.find(s => s.title === cursor);
        if (song) toggleStatus(song);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtered, cursor, editTarget]);

  const toggleStatus = async (song: Song) => {
    if (actionSong) return;
    const next = song.status === "active" ? "draft" : "active";
    setActionSong(song.id); setActionError("");
    try {
      await runWithToast(
        () => apiRequest("/api/songs/status", { method: "POST", body: { title: song.title, status: next } }),
        "状态切换失败",
      );
      // 本地更新该行 + 统计，避免整表重拉
      setSongsData(prev => {
        if (!prev) return prev;
        const songs = prev.songs.map(s => s.title === song.title ? { ...s, status: next } : s);
        const stats = {
          active: songs.reduce((n, s) => n + (s.status === "active" ? 1 : 0), 0),
          draft: songs.reduce((n, s) => n + (s.status === "draft" ? 1 : 0), 0),
        };
        onStatsChange(stats);
        return { ...prev, ...stats, songs };
      });
    } catch (failure) {
      setActionError((failure as RequestFailure).message);
    }
    finally { setActionSong(null); }
  };

  const deleteSong = async (song: Song) => {
    if (!window.confirm(`确定删除「${song.title}」？R9.6 软删除：30 天内可在垃圾桶恢复。`)) return;
    if (actionSong) return;
    setActionSong(song.id); setActionError("");
    try {
      await runWithToast(
        () => apiRequest("/api/songs/delete", { method: "POST", body: { title: song.title } }),
        "删除失败",
      );
      if (expanded === song.title) setExpanded(null);
      await refresh();
      // M9.6b: 5s 撤销窗口 — 点撤销调 POST /api/songs/{id}/restore
      toast.show({
        message: `已删除「${song.title}」`,
        action: {
          label: "撤销",
          onClick: async () => {
            await runWithToast(
              () => apiRequest(`/api/songs/${song.id}/restore`, { method: "POST" }),
              "恢复失败",
            );
            await refresh();
            toast.show({ message: `已恢复「${song.title}」`, durationMs: 3000 });
          },
        },
        durationMs: 5000,
      });
    } catch (failure) {
      setActionError((failure as RequestFailure).message);
    }
    finally { setActionSong(null); }
  };

  /* ---- L2.1 批量操作：多选 helper ---- */
  const toggleSelectTitle = (title: string) => {
    setSelectedTitles(prev => {
      const next = new Set(prev);
      if (next.has(title)) next.delete(title);
      else next.add(title);
      return next;
    });
  };
  const selectAllVisible = () => {
    setSelectedTitles(prev => {
      const next = new Set(prev);
      for (const s of filtered) next.add(s.title);
      return next;
    });
  };
  const clearSelection = () => setSelectedTitles(new Set());
  const exitSelectMode = () => { setSelectMode(false); clearSelection(); };
  /* ---- L2.1 批量删除：循环调 /api/songs/delete + 聚合 toast + 单条撤销 ---- */
  const handleBatchDelete = async () => {
    if (batchPending || selectedTitles.size === 0) return;
    if (!window.confirm(`确定删除 ${selectedTitles.size} 首？R9.6 软删除：30 天内可在垃圾桶恢复。`)) return;
    setBatchPending(true);
    setActionError("");
    const titles = Array.from(selectedTitles);
    let succeeded = 0;
    const failed: string[] = [];
    const deletedIds: Array<{ id: string; title: string }> = [];
    for (const title of titles) {
      const song = songsData?.songs.find(s => s.title === title);
      if (!song) continue;
      try {
        await runWithToast(
          () => apiRequest("/api/songs/delete", { method: "POST", body: { title } }),
          "批量删除失败",
        );
        succeeded++;
        deletedIds.push({ id: song.id, title: song.title });
      } catch (failure) {
        failed.push(`${title}：${(failure as RequestFailure).message}`);
      }
    }
    setBatchPending(false);
    if (succeeded > 0) {
      await refresh();
      exitSelectMode();
      if (failed.length === 0 && deletedIds.length === 1) {
        // 单条走 M9.6b 撤销
        const only = deletedIds[0];
        toast.show({
          message: `已删除「${only.title}」`,
          action: {
            label: "撤销",
            onClick: async () => {
              try {
                await runWithToast(
                  () => apiRequest(`/api/songs/${only.id}/restore`, { method: "POST" }),
                  "恢复失败",
                );
                await refresh();
                toast.show({ message: `已恢复「${only.title}」`, durationMs: 3000 });
              } catch { /* toast 已弹 */ }
            },
          },
          durationMs: 5000,
        });
      } else {
        // 多条：聚合 toast（"已删除 N 首" + 失败列表附注）
        const summary = failed.length > 0
          ? `已删除 ${succeeded} 首，${failed.length} 首失败：${failed[0]}${failed.length > 1 ? ` 等 ${failed.length} 首` : ""}`
          : `已删除 ${succeeded} 首`;
        toast.show({ message: summary, durationMs: failed.length > 0 ? 6000 : 3000 });
      }
    } else if (failed.length > 0) {
      toast.error(`批量删除全部失败：${failed[0]}${failed.length > 1 ? ` 等 ${failed.length} 首` : ""}`);
    }
  };
  /* ---- L2.1 批量改状态：循环调 /api/songs/status + 聚合 toast ---- */
  const handleBatchStatus = async (next: "active" | "draft") => {
    if (batchPending || selectedTitles.size === 0) return;
    setBatchPending(true);
    setActionError("");
    const titles = Array.from(selectedTitles);
    let succeeded = 0;
    const failed: string[] = [];
    for (const title of titles) {
      try {
        await runWithToast(
          () => apiRequest("/api/songs/status", { method: "POST", body: { title, status: next } }),
          `批量改状态失败`,
        );
        succeeded++;
      } catch (failure) {
        failed.push(`${title}：${(failure as RequestFailure).message}`);
      }
    }
    setBatchPending(false);
    if (succeeded > 0) {
      await refresh();
      exitSelectMode();
      const verb = next === "active" ? "已会" : "未会";
      const summary = failed.length > 0
        ? `已标记 ${succeeded} 首为${verb}，${failed.length} 首失败`
        : `已标记 ${succeeded} 首为${verb}`;
      toast.show({ message: summary, durationMs: 3000 });
    } else if (failed.length > 0) {
      toast.error(`批量改状态全部失败：${failed[0]}${failed.length > 1 ? ` 等 ${failed.length} 首` : ""}`);
    }
  };

  /* ---- L2.2 批量导出：每首选中歌曲渲染成 1 张 PNG 存盘 ---- */
  const handleBatchExport = async () => {
    if (exportPending || selectedTitles.size === 0) return;
    setExportPending(true);
    setActionError("");
    const titles = Array.from(selectedTitles);
    const ids = titles
      .map(t => songsData?.songs.find(s => s.title === t)?.id)
      .filter((id): id is string => !!id);
    if (ids.length === 0) {
      toast.error("未能解析选中歌曲的 ID");
      setExportPending(false);
      return;
    }
    try {
      const result = await runWithToast(
        () => exportBySongIds({
          theme: posterStore.current.theme_id,
          song_ids: ids,
          layout: posterStore.current.layout_id,
          canvas: posterStore.current.canvas_id,
        }),
        "批量导出失败",
      );
      const summary = result.total === ids.length
        ? `已导出 ${result.total} 张海报到输出目录`
        : `已导出 ${result.total} 张（跳过 ${ids.length - result.total} 首）`;
      toast.show({ message: summary, durationMs: 4000 });
      exitSelectMode();
    } catch (failure) {
      setActionError((failure as RequestFailure).message);
    } finally {
      setExportPending(false);
    }
  };

  /* ---- L2.3 导出：把整个曲库存为 JSON 文件下载 ---- */
  const handleExportLibrary = async () => {
    setActionError("");
    try {
      const data = await runWithToast(
        () => exportLibrary(),
        "导出曲库失败",
      );
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `streamer-workbench-library-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast.show({ message: `已导出 ${data.songs.length} 首到 JSON 文件`, durationMs: 3000 });
    } catch (failure) {
      setActionError((failure as RequestFailure).message);
    }
  };

  /* ---- L2.3 导入：选 JSON 文件 → POST /api/songs/import (merge) ---- */
  const fileInputRef = useRef<HTMLInputElement>(null);
  const handleImportLibrary = () => {
    fileInputRef.current?.click();
  };
  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";  // 重置 input 以便下次还能选同一文件
    if (!file) return;
    setImportPending(true);
    setActionError("");
    let parsed: unknown;
    try {
      parsed = JSON.parse(await file.text());
    } catch {
      toast.error("文件不是合法 JSON");
      setImportPending(false);
      return;
    }
    const songs = (parsed && typeof parsed === "object" && "songs" in parsed
      ? (parsed as { songs: unknown[] }).songs
      : null);
    if (!Array.isArray(songs)) {
      toast.error("文件缺少 songs 数组字段");
      setImportPending(false);
      return;
    }
    try {
      const result = await runWithToast(
        () => importLibrary({ mode: "merge", songs: songs as Array<{ title: string }> }),
        "导入曲库失败",
      );
      toast.show({
        message: `已导入 ${result.added} 首（跳过 ${result.skipped} 首重复）`,
        durationMs: 4000,
      });
    } catch (failure) {
      setActionError((failure as RequestFailure).message);
    } finally {
      setImportPending(false);
    }
  };

  /* ---- 设计令牌速记 ---- */
  const hairline = dark ? "border-zinc-700/60" : "border-border";
  const label = "text-[10px] font-semibold uppercase tracking-widest text-muted-foreground";

  return (
    <main className="flex-1 flex flex-col overflow-hidden">
      {/* ===== 第一层：主工具栏 ===== */}
      <div className={`shrink-0 flex items-center gap-4 px-6 h-14 border-b ${hairline}`}>
        <h2 className={`font-serif text-[17px] font-semibold tracking-wide ${dark ? "text-zinc-100" : "text-foreground"}`}>
          歌曲库
        </h2>
        <span className={`text-xs tabular-nums ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
          {songsData ? `${songsData.total} 首 · 已会 ${songsData.active} · 未会 ${songsData.draft}` : "…"}
        </span>

        {/* 弹唱信息完整度：已填选调歌曲占比，把补数据变成有终点的进度 */}
        {songsData && (() => {
          const withKey = songsData.songs.filter(s => s.key).length;
          const pct = Math.round((withKey / (songsData.total || 1)) * 100);
          return (
            <span className="flex items-center gap-2" title={`${withKey}/${songsData.total} 首已填选调，点卡片展开 → 编辑可补`}>
              <span className={`w-16 h-1 rounded-full overflow-hidden ${dark ? "bg-zinc-700" : "bg-muted"}`}>
                <span className={`block h-full rounded-full transition-all duration-500 ${dark ? "bg-emerald-400" : "bg-emerald-600"}`}
                  style={{ width: `${pct}%` }} />
              </span>
              <span className={`text-[11px] tabular-nums ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
                弹唱完整度 {pct}%
              </span>
            </span>
          );
        })()}

        {/* 搜索：歌名 / 歌手 / 拼音首字母；按 / 聚焦 */}
        <div className={`ml-auto flex items-center gap-2 rounded-lg px-3 h-8 w-64 transition-colors ${
          dark ? "bg-zinc-800 border border-zinc-700/60 focus-within:border-emerald-500/60"
               : "bg-muted border border-border focus-within:border-primary/60"}`}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-muted-foreground shrink-0">
            <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
          </svg>
          <input ref={searchRef} type="text" placeholder="歌名 / 歌手 / 拼音首字母…" value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => { if (e.key === "Escape") { setQuery(""); searchRef.current?.blur(); } }}
            className="flex-1 bg-transparent text-[13px] outline-none placeholder:text-muted-foreground/70" />
          <kbd className={`text-[10px] px-1 rounded ${dark ? "bg-zinc-700 text-zinc-500" : "bg-background text-muted-foreground/70 border border-border"}`}>/</kbd>
        </div>

        {/* L2.3 导入导出：曲库 JSON 备份恢复 */}
        <input
          ref={fileInputRef}
          type="file"
          accept="application/json"
          data-testid="library-import-file-input"
          onChange={handleFileChange}
          className="hidden"
        />
        <button
          onClick={handleImportLibrary}
          disabled={importPending || statusFilter === "trash"}
          data-testid="library-import-button"
          className={`flex items-center gap-1.5 rounded-lg px-3 h-8 text-[13px] font-medium transition-colors cursor-pointer disabled:opacity-40 ${
            dark ? "bg-zinc-800 text-zinc-300 border border-zinc-700/60 hover:bg-zinc-700" : "bg-background text-foreground border border-border hover:bg-muted"
          }`}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>
          </svg>
          {importPending ? "导入中…" : "导入"}
        </button>
        {/* M2.11 从在线歌单导入 */}
        <button
          onClick={() => setPlaylistImportOpen(true)}
          disabled={statusFilter === "trash"}
          data-testid="library-playlist-import-button"
          className={`flex items-center gap-1.5 rounded-lg px-3 h-8 text-[13px] font-medium transition-colors cursor-pointer disabled:opacity-40 ${
            dark ? "bg-zinc-800 text-zinc-300 border border-zinc-700/60 hover:bg-zinc-700" : "bg-background text-foreground border border-border hover:bg-muted"
          }`}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M3 6h18M3 12h18M3 18h12"/>
          </svg>
          从歌单导入
        </button>
        {/* M2.12 榜单浏览 + 一键入库 */}
        <button
          onClick={() => setChartsBrowseOpen(true)}
          disabled={statusFilter === "trash"}
          data-testid="library-charts-browse-button"
          className={`flex items-center gap-1.5 rounded-lg px-3 h-8 text-[13px] font-medium transition-colors cursor-pointer disabled:opacity-40 ${
            dark ? "bg-zinc-800 text-zinc-300 border border-zinc-700/60 hover:bg-zinc-700" : "bg-background text-foreground border border-border hover:bg-muted"
          }`}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M8 21h8M12 17v4M7 4h10v4a5 5 0 0 1-10 0V4z"/>
          </svg>
          榜单浏览
        </button>
        <button
          onClick={handleExportLibrary}
          data-testid="library-export-button"
          className={`flex items-center gap-1.5 rounded-lg px-3 h-8 text-[13px] font-medium transition-colors cursor-pointer ${
            dark ? "bg-zinc-800 text-zinc-300 border border-zinc-700/60 hover:bg-zinc-700" : "bg-background text-foreground border border-border hover:bg-muted"
          }`}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5-5 5 5M12 15V3" transform="rotate(180 12 12)"/>
          </svg>
          导出
        </button>

        {/* L2.1 批量操作：选择模式切换 */}
        <button
          onClick={() => selectMode ? exitSelectMode() : setSelectMode(true)}
          data-testid="library-select-toggle"
          aria-pressed={selectMode}
          className={`flex items-center gap-1.5 rounded-lg px-3 h-8 text-[13px] font-medium transition-colors cursor-pointer ${
            selectMode
              ? (dark ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40" : "bg-emerald-50 text-emerald-700 border border-emerald-200")
              : (dark ? "bg-zinc-800 text-zinc-300 border border-zinc-700/60 hover:bg-zinc-700" : "bg-background text-foreground border border-border hover:bg-muted")
          }`}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="3" width="18" height="18" rx="2"/>
            <path d="m9 12 2 2 4-4"/>
          </svg>
          {selectMode ? "退出选择" : "选择"}
        </button>

        <button onClick={() => setEditTarget("new")}
          className="flex items-center gap-1.5 rounded-lg px-3.5 h-8 text-[13px] font-medium transition-colors cursor-pointer bg-emerald-600 hover:bg-emerald-700 text-white">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M12 5v14M5 12h14"/></svg>
          新增歌曲
        </button>
      </div>

      {/* ===== 第二层：状态筛选条 ===== */}
      <div className={`shrink-0 flex items-center gap-1 px-6 h-10 border-b ${hairline} ${dark ? "bg-zinc-800/40" : "bg-muted/40"}`}>
        {([
          ["all", "全部"],
          ["active", "已会"],
          ["draft", "未会"],
          ["trash", "垃圾桶"],
        ] as const).map(([id, text]) => (
          <button
            key={id}
            data-testid={`library-tab-${id}`}
            onClick={() => setStatusFilter(id)}
            className={`rounded-md px-3 h-6.5 py-1 text-xs font-medium transition-all duration-300 ease-out cursor-pointer ${statusFilter === id
              ? (dark ? "bg-emerald-500/20 text-emerald-300" : "bg-primary-soft text-primary")
              : (dark ? "text-zinc-500 hover:text-zinc-300" : "text-muted-foreground hover:text-foreground")}`}
          >
            {text}
            {id !== "trash" && id !== "snapshots" && (
              <span className="ml-1 tabular-nums opacity-60">
                {id === "all" ? songsData?.total ?? "" : id === "active" ? songsData?.active ?? "" : songsData?.draft ?? ""}
              </span>
            )}
          </button>
        ))}
        <span className={`ml-auto text-[11px] ${dark ? "text-zinc-600" : "text-muted-foreground/70"}`}>
          ←→↑↓ 移动 · Enter 展开 · X 学会了 · / 搜索
        </span>
      </div>

      {/* ===== 垃圾桶视图（R9.6） ===== */}
      {statusFilter === "trash" && (
        <TrashView dark={dark} onChanged={() => { void refresh(); }} />
      )}

      {/* ===== 快照视图（L2.3） ===== */}
      {statusFilter === "snapshots" && (
        <SnapshotsView dark={dark} onChanged={() => { void refresh(); }} />
      )}

      {actionError && (
        // 3.2 收口：原裸 div 改用 ErrorBanner
        <div className="mx-6 mt-3">
          <ErrorBanner severity="error" message={actionError} dark={dark} />
        </div>
      )}

      {/* ===== 分组卡片网格 ===== */}
      {listRequest.status === "loading" && !songsData ? <AsyncStateNotice kind="loading" label="歌曲库" />
      : listRequest.status === "error" && !songsData ? <AsyncStateNotice kind="error" label="歌曲库" error={listRequest.error} onRetry={refresh} />
      : listRequest.status === "empty" ? <AsyncStateNotice
          kind="empty"
          label="歌曲"
          actionLabel="载入示例数据"
          onAction={handleSeedSample}
          actionPending={seedPending}
        />
      : songsData ? (
        <div ref={listRef} className="flex-1 overflow-y-auto">
          {/* 列数探针：与真实网格同 class，键盘导航据此计算 ↑↓ 步长 */}
          <div ref={probeRef} aria-hidden="true" className={`invisible h-0 overflow-hidden ${GRID_CLASS}`} />
          {groups.length === 0 && (
            <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
              没有匹配「{query}」的歌曲
            </div>
          )}
          {groups.map(([sec, songs]) => (
            <div key={sec}>
              {/* 吸顶组头：大号分类字 + 数量 */}
              <div className={`sticky top-0 z-10 flex items-baseline gap-3 px-6 py-2 border-b ${hairline} ${
                dark ? "bg-zinc-900/95 backdrop-blur-sm" : "bg-background/95 backdrop-blur-sm"}`}>
                <span className={`font-serif text-[15px] font-semibold ${dark ? "text-zinc-300" : "text-foreground"}`}>
                  {groupLabel(sec)}
                </span>
                <span className={`text-[11px] tabular-nums ${dark ? "text-zinc-600" : "text-muted-foreground"}`}>
                  {songs.length} 首
                </span>
              </div>

              <div className={`px-6 py-3 ${GRID_CLASS}`}>
                {songs.map(s => {
                  const isOpen = expanded === s.title;
                  const isCursor = cursor === s.title;
                  const isSelected = selectedTitles.has(s.title);
                  return (
                    <div key={s.title}
                      ref={el => { if (el) rowRefs.current.set(s.title, el); else rowRefs.current.delete(s.title); }}
                      className={isOpen ? "col-span-full" : ""}>
                      {/* ---- 卡片：点击就地展开；状态变化只用背景填充，不加边框 ---- */}
                      <div
                        onClick={() => {
                          if (selectMode) toggleSelectTitle(s.title);
                          else setExpanded(isOpen ? null : s.title);
                        }}
                        data-testid={`library-card-${s.id}`}
                        data-selected={isSelected ? "true" : "false"}
                        className={`h-full rounded-xl px-3.5 py-3 cursor-pointer transition-colors duration-200 ${
                          isSelected
                            ? (dark ? "bg-emerald-500/15 ring-2 ring-emerald-500/50" : "bg-emerald-50 ring-2 ring-emerald-400")
                            : isOpen
                              ? (dark ? "bg-zinc-800/80" : "bg-muted/80")
                              : isCursor
                              ? (dark ? "bg-zinc-800/70" : "bg-muted/70")
                              : (dark ? "bg-zinc-800/40 hover:bg-zinc-800/60" : "bg-muted/40 hover:bg-muted/60")}`}
                      >
                        {/* 歌名 + 展开指示 + 弹唱按钮 */}
                        <div className="flex items-start gap-1.5">
                          {/* L2.1 批量操作：select 模式下显示 checkbox */}
                          {selectMode && (
                            <span
                              data-testid={`library-card-checkbox-${s.id}`}
                              data-checked={isSelected ? "true" : "false"}
                              className={`shrink-0 mt-0.5 w-4 h-4 rounded border-2 flex items-center justify-center transition-colors ${
                                isSelected
                                  ? "bg-emerald-500 border-emerald-500 text-white"
                                  : (dark ? "border-zinc-600" : "border-gray-300")
                              }`}>
                              {isSelected && (
                                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                                  <path d="m5 12 5 5L20 7"/>
                                </svg>
                              )}
                            </span>
                          )}
                          <span className={`flex-1 min-w-0 font-serif text-[14px] leading-snug truncate ${
                            s.status === "draft"
                              ? (dark ? "text-zinc-400" : "text-muted-foreground")
                              : (dark ? "text-zinc-100" : "text-foreground")}`}
                            title={s.title}>
                            {s.title}
                          </span>
                          {/* R8.0 弹唱按钮 */}
                          {onPlaySong && (
                            <button
                              type="button"
                              data-testid={`library-play-${s.id}`}
                              onClick={e => { e.stopPropagation(); onPlaySong(s.id); }}
                              title="弹唱这首歌（歌词 + 曲谱 + 模拟时间）"
                              aria-label={`弹唱 ${s.title}`}
                              className={`shrink-0 rounded p-1 text-xs transition-colors ${
                                dark
                                  ? "text-zinc-500 hover:bg-zinc-700 hover:text-emerald-300"
                                  : "text-muted-foreground hover:bg-muted hover:text-emerald-700"
                              }`}
                            >
                              ▶
                            </button>
                          )}
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                            className={`mt-1 shrink-0 transition-transform duration-200 ${isOpen ? "rotate-180" : ""} ${dark ? "text-zinc-600" : "text-muted-foreground/60"}`}>
                            <path d="m6 9 6 6 6-6"/>
                          </svg>
                        </div>
                        {/* 歌手 */}
                        <p className={`mt-0.5 text-[12px] truncate ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
                          {s.artists.join("、") || "—"}
                        </p>
                        {/* 元数据行：状态点 · 难度 · 选调 */}
                        <div className="mt-2.5 flex items-center gap-2.5 text-[12px]">
                          <button
                            onClick={e => { e.stopPropagation(); toggleStatus(s); }}
                            disabled={actionSong === s.id}
                            title={s.status === "active" ? "已会 · 点击标回未会" : "未会 · 点击标记学会了"}
                            className="shrink-0 w-5 h-5 -ml-1 flex items-center justify-center cursor-pointer">
                            <span className={`w-2 h-2 rounded-full transition-all duration-300 ${
                              s.status === "active"
                                ? (dark ? "bg-emerald-400" : "bg-emerald-600")
                                : `bg-transparent border ${dark ? "border-amber-400/70" : "border-amber-500/80"}`}`} />
                          </button>
                          <DifficultyMark value={s.difficulty} dark={dark} />
                          {(s.tags ?? []).length > 0 && (
                            <span className={`min-w-0 truncate text-[11px] ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
                              {s.tags.join(" · ")}
                            </span>
                          )}
                          <span className={`ml-auto shrink-0 font-mono ${dark ? "text-zinc-300" : "text-foreground"}`}>
                            <KeyCapo song={s} />
                          </span>
                        </div>

                        {/* ---- 展开面板：大字选调 + 详情网格 + 操作 ---- */}
                        {isOpen && (
                          <div className={`mt-3 pt-4 border-t ${hairline}`}
                            onClick={e => e.stopPropagation()}>
                            <div className="flex flex-wrap gap-8">
                              {/* 大字选调：主播一瞥可读；空态转为补全 CTA */}
                              <div className="shrink-0 w-36">
                                <p className={label}>选调</p>
                                {s.key ? (
                                  <p className={`font-mono text-4xl font-semibold mt-1 leading-none ${dark ? "text-zinc-100" : "text-foreground"}`}>
                                    {s.key}
                                  </p>
                                ) : (
                                  <button onClick={() => setEditTarget(s)}
                                    className={`mt-1 rounded-lg px-2.5 py-1.5 text-[12px] font-medium transition-colors cursor-pointer ${
                                      dark ? "bg-zinc-700/70 text-zinc-300 hover:bg-zinc-700" : "bg-background border border-dashed border-border text-muted-foreground hover:text-foreground hover:border-primary/50"}`}>
                                    未填 · 点我补选调 →
                                  </button>
                                )}
                                <p className={`mt-2 text-[12px] tabular-nums ${dark ? "text-zinc-400" : "text-muted-foreground"}`}>
                                  {s.capo !== null ? `变调夹 ${s.capo} 品` : "变调夹未填"}
                                </p>
                                <p className="mt-1"><DifficultyMark value={s.difficulty} dark={dark} /></p>
                              </div>

                              {/* 详情网格 */}
                              <div className="flex-1 min-w-64 grid md:grid-cols-2 gap-x-8 gap-y-3 content-start text-[13px]">
                                <div><p className={label}>作词</p><p className={`mt-0.5 ${dark ? "text-zinc-300" : ""}`}>{s.lyricist || "—"}</p></div>
                                <div><p className={label}>作曲</p><p className={`mt-0.5 ${dark ? "text-zinc-300" : ""}`}>{s.composer || "—"}</p></div>
                                <div>
                                  <p className={label}>谱子</p>
                                  <p className={`mt-0.5 break-all ${dark ? "text-zinc-300" : ""}`}>
                                    {s.tabs
                                      ? /^https?:\/\//.test(s.tabs)
                                        ? <a href={s.tabs} target="_blank" rel="noreferrer" className="underline underline-offset-2 hover:text-emerald-500">{s.tabs}</a>
                                        : s.tabs
                                      : "—"}
                                  </p>
                                </div>
                                <div><p className={label}>拼音</p><p className={`mt-0.5 font-mono ${dark ? "text-zinc-300" : ""}`}>{s.pinyin || "—"}</p></div>
                                {(s.tags ?? []).length > 0 && (
                                  <div className="md:col-span-2">
                                    <p className={label}>标签</p>
                                    <div className="mt-1 flex flex-wrap gap-1.5">
                                      {s.tags.map(t => (
                                        <span key={t} className={`rounded-md px-2 py-0.5 text-[11px] ${
                                          dark ? "bg-zinc-700/70 text-zinc-300" : "bg-background border border-border text-muted-foreground"}`}>{t}</span>
                                      ))}
                                    </div>
                                  </div>
                                )}
                                {s.notes && (
                                  <div className="md:col-span-2">
                                    <p className={label}>备注</p>
                                    <p className={`mt-0.5 leading-relaxed ${dark ? "text-zinc-300" : ""}`}>{s.notes}</p>
                                  </div>
                                )}
                                <div className="md:col-span-2">
                                  <p className={label}>曲谱附件</p>
                                  <TabsPanel title={s.title} tabFiles={s.tab_files ?? []} dark={dark}
                                    onChanged={files => updateTabFiles(s.title, files)} />
                                </div>
                              </div>

                              {/* 操作列 */}
                              <div className="shrink-0 ml-auto flex md:flex-col gap-1.5 w-full md:w-24">
                                {/* M1.5 试听入口：与卡片小 ▶ 图标互补，展开后更醒目；不传 link 即 browse 模式 */}
                                {onPlaySong && (
                                  <button
                                    type="button"
                                    data-testid={`library-preview-${s.id}`}
                                    onClick={() => onPlaySong(s.id)}
                                    title="试听：歌词 + 曲谱同步（不联动直播）"
                                    aria-label={`试听 ${s.title}`}
                                    className={`flex items-center justify-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors cursor-pointer ${
                                      dark
                                        ? "bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25 border border-emerald-500/30"
                                        : "bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border border-emerald-200/60"
                                    }`}
                                  >
                                    <span aria-hidden="true">▶</span>
                                    试听
                                  </button>
                                )}
                                <button onClick={() => toggleStatus(s)}
                                  disabled={actionSong === s.id}
                                  className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors cursor-pointer ${s.status === "draft"
                                    ? "bg-emerald-600 hover:bg-emerald-700 text-white"
                                    : dark ? "bg-zinc-700 text-zinc-300 hover:bg-zinc-600" : "bg-background border border-border text-muted-foreground hover:text-foreground"}`}>
                                  {s.status === "draft" ? "学会了 ✓" : "标回未会"}
                                </button>
                                <button onClick={() => setEditTarget(s)}
                                  className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors cursor-pointer ${dark ? "bg-zinc-700 text-zinc-300 hover:bg-zinc-600" : "bg-background border border-border text-foreground hover:bg-muted"}`}>
                                  编辑
                                </button>
                                <button onClick={() => deleteSong(s)}
                                  disabled={actionSong === s.id}
                                  className={`rounded-lg px-3 py-1.5 text-xs transition-colors cursor-pointer ${dark ? "text-red-400/80 hover:bg-zinc-700 hover:text-red-400" : "text-red-500/80 hover:bg-red-50 hover:text-red-500"}`}>
                                  删除
                                </button>
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      ) : null}

      {/* ===== 底栏：计数收尾 ===== */}
      <div className={`shrink-0 flex items-center px-6 h-8 border-t text-[11px] ${hairline} ${dark ? "text-zinc-600" : "text-muted-foreground"}`}>
        <span className="tabular-nums">显示 {filtered.length} / {songsData?.total ?? 0} 首</span>
        {query && <span className="ml-3">匹配：「{query}」（歌名 / 歌手 / 拼音）</span>}
      </div>

      {editTarget !== null && (
        <SongEditDialog target={editTarget}
          onClose={() => setEditTarget(null)} onSaved={refresh} />
      )}

      {/* M2.11 从在线歌单导入 */}
      <PlaylistImportDialog
        open={playlistImportOpen}
        onClose={() => setPlaylistImportOpen(false)}
        onImported={refresh}
      />

      {/* M2.12 榜单浏览 + 一键入库 */}
      <ChartsBrowseDialog
        open={chartsBrowseOpen}
        onClose={() => setChartsBrowseOpen(false)}
        onImported={refresh}
      />

      {/* L2.1 批量操作：底部 action bar（select 模式 + 至少选中 1 首时显示） */}
      {selectMode && statusFilter !== "trash" && (
        <div
          data-testid="library-batch-bar"
          className={`shrink-0 z-20 flex items-center gap-2 px-6 h-14 border-t ${
            dark ? "bg-zinc-900/95 border-zinc-700 backdrop-blur-sm" : "bg-background/95 border-border backdrop-blur-sm"
          }`}>
          <span className={`text-[13px] font-medium tabular-nums ${
            dark ? "text-zinc-200" : "text-foreground"
          }`}>
            已选 <span data-testid="library-batch-count" className="text-emerald-500">{selectedTitles.size}</span> 首
          </span>
          <button
            type="button"
            onClick={selectAllVisible}
            data-testid="library-batch-select-all"
            className={`text-[12px] px-2 h-7 rounded transition-colors ${
              dark ? "text-zinc-400 hover:bg-zinc-800" : "text-muted-foreground hover:bg-muted"
            }`}>
            全选当前筛选
          </button>
          <button
            type="button"
            onClick={clearSelection}
            data-testid="library-batch-clear"
            disabled={selectedTitles.size === 0}
            className={`text-[12px] px-2 h-7 rounded transition-colors disabled:opacity-40 ${
              dark ? "text-zinc-400 hover:bg-zinc-800" : "text-muted-foreground hover:bg-muted"
            }`}>
            清空
          </button>
          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              onClick={() => handleBatchStatus("active")}
              data-testid="library-batch-mark-active"
              disabled={selectedTitles.size === 0 || batchPending}
              className="flex items-center gap-1.5 rounded-lg px-3 h-8 text-[12px] font-medium transition-colors cursor-pointer disabled:opacity-40 bg-emerald-600 hover:bg-emerald-700 text-white">
              ✓ 标记已会
            </button>
            <button
              type="button"
              onClick={() => handleBatchStatus("draft")}
              data-testid="library-batch-mark-draft"
              disabled={selectedTitles.size === 0 || batchPending}
              className={`flex items-center gap-1.5 rounded-lg px-3 h-8 text-[12px] font-medium transition-colors cursor-pointer disabled:opacity-40 ${
                dark ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700" : "bg-background hover:bg-muted text-foreground border border-border"
              }`}>
              ◯ 标记未会
            </button>
            <button
              type="button"
              onClick={handleBatchDelete}
              data-testid="library-batch-delete"
              disabled={selectedTitles.size === 0 || batchPending}
              className="flex items-center gap-1.5 rounded-lg px-3 h-8 text-[12px] font-medium transition-colors cursor-pointer disabled:opacity-40 bg-red-600 hover:bg-red-700 text-white">
              🗑 批量删除
            </button>
            <button
              type="button"
              onClick={handleBatchExport}
              data-testid="library-batch-export"
              disabled={selectedTitles.size === 0 || batchPending || exportPending}
              className="flex items-center gap-1.5 rounded-lg px-3 h-8 text-[12px] font-medium transition-colors cursor-pointer disabled:opacity-40 bg-blue-600 hover:bg-blue-700 text-white">
              📤 批量导出
            </button>
            <button
              type="button"
              onClick={exitSelectMode}
              data-testid="library-batch-cancel"
              className={`ml-2 text-[12px] px-2 h-7 rounded transition-colors ${
                dark ? "text-zinc-500 hover:text-zinc-300" : "text-muted-foreground hover:text-foreground"
              }`}>
              取消
            </button>
          </div>
        </div>
      )}
    </main>
  );
}
