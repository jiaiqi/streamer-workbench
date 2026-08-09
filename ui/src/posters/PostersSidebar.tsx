/// R1a.5 + M3 P0/P1 工作台左栏：海报文档区。
///
/// 新增（M3 P0）：
/// - 缩略图（200x200 后端懒生成）
/// - 搜索框（按 name 模糊匹配）
/// - 排序下拉（更新时间 / 歌数 / 名称）
/// - 右键菜单（重命名 / 复制 / 删除）
/// - inline 重命名（双击名 → input + 失焦保存 / Esc 取消）
///
/// 新增（M3 P1）：
/// - 缩略图 hover 浮层（300ms 触发，400x400 大图，右上角浮层）
/// - 多选模式（顶部「选择」按钮切换；多选后工具栏批量删除/复制/换主题）
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { PosterStore } from "./usePosterStore";
import LayoutPicker from "./LayoutPicker";
import StatusBadge from "@/components/StatusBadge";
import { useToast } from "@/components/Toast";
import { apiRequest } from "@/api/client";
import type { Theme } from "@/api/generated";

interface PostersSidebarProps {
  store: PosterStore;
  dark: boolean;
}

const STATUS_KIND: Record<PosterStore["status"], Parameters<typeof StatusBadge>[0]["kind"]> = {
  idle: "neutral",
  dirty: "dirty",
  saving: "saving",
  saved: "saved",
  error: "error",
};

const STATUS_LABEL: Record<PosterStore["status"], string> = {
  idle: "就绪",
  dirty: "编辑中…",
  saving: "保存中…",
  saved: "已保存",
  error: "保存失败",
};

type SortMode = "updated" | "name" | "songs";

const SORT_LABEL: Record<SortMode, string> = {
  updated: "最新编辑",
  name: "名称 A-Z",
  songs: "歌数最多",
};

function formatTime(ts: number | null): string {
  if (ts === null) return "—";
  const d = new Date(ts);
  return `${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
}

function formatDateTime(iso: string): string {
  // "2026-08-04T12:34:56" → "08-04 12:34"
  if (!iso) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso);
  if (!m) return iso.slice(0, 16);
  return `${m[2]}-${m[3]} ${m[4]}:${m[5]}`;
}

export default function PostersSidebar({ store, dark }: PostersSidebarProps) {
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<SortMode>("updated");
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; id: string } | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const renameInputRef = useRef<HTMLInputElement>(null);
  // M3 P1: hover 浮层 + 多选模式
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [previewPos, setPreviewPos] = useState<{ x: number; y: number } | null>(null);
  const [multiSelectMode, setMultiSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const [themes, setThemes] = useState<Theme[]>([]);
  const [themePickerOpen, setThemePickerOpen] = useState(false);
  // M3 P2: 拖拽排序状态
  const [dragId, setDragId] = useState<string | null>(null);
  const [dropTarget, setDropTarget] = useState<{ id: string; pos: "before" | "after" } | null>(null);
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLElement>(null);
  const toast = useToast();

  // M3 P1: 拉 themes 一次（多选批量改主题用）
  useEffect(() => {
    let cancelled = false;
    apiRequest<Theme[]>("/api/themes")
      .then(items => { if (!cancelled) setThemes(items); })
      .catch(() => { /* 静默 — 批量改主题按钮降级为 disabled */ });
    return () => { cancelled = true; };
  }, []);

  const handleNew = useCallback(() => {
    void store.flush();
    store.newDraft();
  }, [store]);

  const handleDelete = useCallback(async () => {
    if (!store.current.id) return;
    if (!window.confirm(`删除「${store.current.name || "未命名海报"}」？此操作不可撤销。`)) {
      return;
    }
    await store.deleteCurrent();
  }, [store]);

  // ── M3 P1: hover 浮层（300ms 触发） ──
  const handleThumbEnter = useCallback((id: string, target: HTMLElement) => {
    if (renamingId) return;
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
    hoverTimerRef.current = setTimeout(() => {
      // 计算浮层位置：相对 viewport
      const rect = target.getBoundingClientRect();
      setPreviewPos({
        x: Math.min(window.innerWidth - 420, rect.right + 8),
        y: Math.max(8, rect.top - 8),
      });
      setHoverId(id);
    }, 300);
  }, [renamingId]);

  const handleThumbLeave = useCallback(() => {
    if (hoverTimerRef.current) {
      clearTimeout(hoverTimerRef.current);
      hoverTimerRef.current = null;
    }
    setHoverId(null);
    setPreviewPos(null);
  }, []);

  useEffect(() => () => {
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
  }, []);

  // ── M3 P1: 多选模式 ──
  const toggleMultiSelect = useCallback(() => {
    setMultiSelectMode(v => {
      if (v) setSelectedIds(new Set());
      return !v;
    });
  }, []);

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);

  const selectAll = useCallback(() => {
    // visiblePosters 在下面定义（useMemo）；通过 ref 闭包拿到
    const all = store.posters
      .filter(p => {
        const term = search.trim().toLowerCase();
        return term ? p.name.toLowerCase().includes(term) : true;
      })
      .sort((a, b) => {
        if (sortBy === "name") return a.name.localeCompare(b.name, "zh-CN");
        if (sortBy === "songs") return b.song_count - a.song_count;
        return a.name.localeCompare(b.name);
      })
      .map(p => p.id);
    setSelectedIds(new Set(all));
  }, [store.posters, search, sortBy]);

  const clearSelection = useCallback(() => {
    setSelectedIds(new Set());
  }, []);

  // ── M3 P1: 批量操作 handlers ──
  const handleBatchDelete = useCallback(async () => {
    if (selectedIds.size === 0) return;
    if (!window.confirm(`删除选中的 ${selectedIds.size} 张海报？此操作不可撤销。`)) return;
    const res = await store.batch("delete", Array.from(selectedIds));
    if (res) {
      toast.success(`已删除 ${res.deleted ?? 0} 张`,
        res.failed?.length ? `${res.failed.length} 张失败` : undefined);
      setSelectedIds(new Set());
    }
  }, [selectedIds, store, toast]);

  const handleBatchDuplicate = useCallback(async () => {
    if (selectedIds.size === 0) return;
    const res = await store.batch("duplicate", Array.from(selectedIds));
    if (res) {
      toast.success(`已复制 ${res.duplicated ?? 0} 张`,
        res.failed?.length ? `${res.failed.length} 张失败` : undefined);
      setSelectedIds(new Set());
    }
  }, [selectedIds, store, toast]);

  // ── M3 P2 拖拽排序 handlers ──
  const handleDragStart = useCallback((e: React.DragEvent<HTMLDivElement>, id: string) => {
    if (multiSelectMode) {
      // 多选模式不参与拖拽
      e.preventDefault();
      return;
    }
    setDragId(id);
    try { e.dataTransfer.effectAllowed = "move"; } catch { /* jsdom stub */ }
    try { e.dataTransfer.setData("text/plain", id); } catch { /* jsdom stub */ }
  }, [multiSelectMode]);

  const handleDragOver = useCallback((e: React.DragEvent<HTMLLIElement>, targetId: string) => {
    // 从 dataTransfer.types 兜底（jsdom 不传 dataTransfer 时 types 为空）
    const types = (() => { try { return e.dataTransfer.types; } catch { return [] as unknown[]; } })();
    const isDragging = Array.isArray(types) ? types.length > 0
      : (types as { contains?: (s: string) => boolean })?.contains?.("text/plain");
    if (!isDragging) return;
    const sourceId = (() => {
      try { return e.dataTransfer.getData("text/plain"); } catch { return ""; }
    })() || dragId;
    if (!sourceId || sourceId === targetId) return;
    e.preventDefault();
    try { e.dataTransfer.dropEffect = "move"; } catch { /* jsdom stub */ }
    const rect = e.currentTarget.getBoundingClientRect();
    const midY = rect.top + rect.height / 2;
    const pos: "before" | "after" = e.clientY < midY ? "before" : "after";
    console.log("DBG setDropTarget", { targetId, pos, dragId, sourceId, midY, clientY: e.clientY, rect });
    setDropTarget((prev) =>
      prev && prev.id === targetId && prev.pos === pos ? prev : { id: targetId, pos }
    );
  }, [dragId]);

  const handleDragLeave = useCallback((e: React.DragEvent<HTMLLIElement>, targetId: string) => {
    // 只在离开整个 li 时清除；进入子元素不算 leave
    const related = e.relatedTarget as Node | null;
    if (related && e.currentTarget.contains(related)) return;
    setDropTarget((prev) => (prev?.id === targetId ? null : prev));
  }, []);

  const handleDragEnd = useCallback(() => {
    setDragId(null);
    setDropTarget(null);
  }, []);

  const handleDrop = useCallback(async (e: React.DragEvent<HTMLLIElement>, targetId: string) => {
    e.preventDefault();
    const sourceId = e.dataTransfer.getData("text/plain") || dragId;
    if (!sourceId || sourceId === targetId) {
      setDragId(null);
      setDropTarget(null);
      return;
    }
    // 用当前 store.posters（保留后端顺序 — sortBy=name/songs 也用同基线）作为提交基准
    const term = search.trim().toLowerCase();
    const baseList = term
      ? store.posters.filter(p => p.name.toLowerCase().includes(term))
      : store.posters;
    const currentOrder = baseList.map(p => p.id);
    const fromIdx = currentOrder.indexOf(sourceId);
    const toIdxRaw = currentOrder.indexOf(targetId);
    if (fromIdx < 0 || toIdxRaw < 0) {
      setDragId(null);
      setDropTarget(null);
      return;
    }
    // 移除被拖项
    currentOrder.splice(fromIdx, 1);
    // 计算 drop 后插入位置
    const pos = dropTarget?.id === targetId ? dropTarget.pos : "after";
    let insertIdx = currentOrder.indexOf(targetId);
    if (pos === "after") insertIdx += 1;
    currentOrder.splice(insertIdx, 0, sourceId);
    setDragId(null);
    setDropTarget(null);
    const res = await store.batch("reorder", currentOrder);
    if (res) {
      toast.success(`已重排 ${res.reordered ?? 0} 张`, undefined);
    }
  }, [dragId, dropTarget, search, store, toast]);

  const handleBatchSetTheme = useCallback(async (theme: string) => {
    if (selectedIds.size === 0) return;
    const res = await store.batch("set_theme", Array.from(selectedIds), theme);
    if (res) {
      toast.success(`已改主题 ${res.updated ?? 0} 张`,
        res.failed?.length ? `${res.failed.length} 张失败` : undefined);
      setSelectedIds(new Set());
    }
  }, [selectedIds, store, toast]);

  // ── 过滤 + 排序 ──
  const visiblePosters = useMemo(() => {
    const term = search.trim().toLowerCase();
    const filtered = term
      ? store.posters.filter(p => p.name.toLowerCase().includes(term))
      : store.posters;
    if (sortBy === "updated") {
      // 默认：直接用后端顺序（order_index asc，None 排到末尾，再按 updated_at desc）
      return filtered;
    }
    const sorted = [...filtered].sort((a, b) => {
      if (sortBy === "name") return a.name.localeCompare(b.name, "zh-CN");
      if (sortBy === "songs") return b.song_count - a.song_count;
      return 0;
    });
    return sorted;
  }, [store.posters, search, sortBy]);

  // ── 右键菜单 ──
  useEffect(() => {
    if (!contextMenu) return;
    const close = () => setContextMenu(null);
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    window.addEventListener("click", close);
    window.addEventListener("contextmenu", close);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("contextmenu", close);
      window.removeEventListener("keydown", onKey);
    };
  }, [contextMenu]);

  const startRename = (id: string, currentName: string) => {
    setRenamingId(id);
    setRenameValue(currentName);
    setContextMenu(null);
    setTimeout(() => {
      renameInputRef.current?.focus();
      renameInputRef.current?.select();
    }, 30);
  };

  const commitRename = async () => {
    if (!renamingId) return;
    const id = renamingId;
    const newName = renameValue.trim();
    setRenamingId(null);
    if (!newName) return;
    // 当前海报重命名：走 store.rename
    if (id === store.current.id) {
      await store.rename(newName);
      return;
    }
    // 非当前海报：走独立 PATCH
    try {
      const { apiRequest } = await import("../api/client");
      await apiRequest(`/api/posters/${id}/name`,
        { method: "PATCH", body: { name: newName } });
      void store.refreshList();
    } catch {
      /* useApiError 兜底；忽略 */
    }
  };

  const cancelRename = () => {
    setRenamingId(null);
    setRenameValue("");
  };

  return (
    <section aria-label="海报文档" className={`px-4 pt-5 pb-3 border-b transition-colors duration-500 ${
      dark ? "border-zinc-700/50" : "border-border"
    }`}>
      <div className="flex items-center justify-between mb-2">
        <p className="eyebrow">当前作品</p>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            onClick={store.undo}
            disabled={!store.canUndo}
            title="撤销 (⌘Z)"
            data-testid="poster-undo"
            aria-label="撤销"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 7v6h6" /><path d="M21 17a9 9 0 0 0-15-6.7L3 13" />
            </svg>
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            onClick={store.redo}
            disabled={!store.canRedo}
            title="重做 (⌘⇧Z)"
            data-testid="poster-redo"
            aria-label="重做"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 7v6h-6" /><path d="M3 17a9 9 0 0 1 15-6.7L21 13" />
            </svg>
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-7 px-2 text-xs"
            onClick={handleNew}
            disabled={store.isDirty && store.status === "saving"}
            title="新建草稿（自动保存当前编辑）"
            data-testid="poster-new"
          >
            + 新建
          </Button>
        </div>
      </div>

      <h2 className="panel-title truncate" title={store.current.name}>
        {store.current.name || "未命名海报"}
      </h2>

      <LayoutPicker store={store} />

      <div className="flex items-center gap-2 mt-1">
        <StatusBadge
          kind={STATUS_KIND[store.status]}
          label={STATUS_LABEL[store.status]}
          compact
          dark={dark}
        />
        {store.status === "saved" && store.lastSavedAt && (
          <span className={`text-[11px] tabular-nums ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
            {formatTime(store.lastSavedAt)}
          </span>
        )}
        {store.status === "error" && store.error && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-6 px-1.5 text-[11px] text-destructive"
            onClick={() => store.saveNow()}
            title={store.error.message}
          >
            重试
          </Button>
        )}
      </div>

      {/* 搜索 + 排序 + 多选切换（M3 P0/P1） */}
      <div className="mt-3 flex items-center gap-1.5">
        <Input
          placeholder="搜索海报…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="h-7 text-xs flex-1 min-w-0"
          data-testid="poster-search-input"
        />
        <select
          aria-label="排序"
          value={sortBy}
          onChange={e => setSortBy(e.target.value as SortMode)}
          className={`h-7 text-[11px] rounded-md border px-1.5 ${dark ? "bg-zinc-800 border-zinc-700" : "bg-background border-border"}`}
          data-testid="poster-sort-select"
        >
          {(Object.keys(SORT_LABEL) as SortMode[]).map(m => (
            <option key={m} value={m}>{SORT_LABEL[m]}</option>
          ))}
        </select>
        <Button
          type="button"
          variant={multiSelectMode ? "default" : "outline"}
          size="sm"
          className="h-7 px-2 text-[11px]"
          onClick={toggleMultiSelect}
          data-testid="poster-multiselect-toggle"
          title={multiSelectMode ? "退出多选" : "进入多选"}
        >
          {multiSelectMode ? "✕ 退出" : "☐ 选择"}
        </Button>
      </div>

      {/* M3 P1: 多选模式工具栏 */}
      {multiSelectMode && (
        <div
          className={`mt-2 flex items-center gap-1 rounded-lg p-1.5 text-[11px] ${dark ? "bg-zinc-800/60" : "bg-muted"}`}
          data-testid="poster-multiselect-toolbar"
        >
          <span className="tabular-nums px-1">{selectedIds.size} 项已选</span>
          <Button type="button" variant="ghost" size="sm" className="h-6 px-1.5 text-[11px]"
            onClick={selectAll} data-testid="poster-multiselect-all">全选</Button>
          <Button type="button" variant="ghost" size="sm" className="h-6 px-1.5 text-[11px]"
            onClick={clearSelection} disabled={selectedIds.size === 0}
            data-testid="poster-multiselect-clear">清空</Button>
          <span className="flex-1" />
          <Button type="button" variant="ghost" size="sm" className="h-6 px-1.5 text-[11px]"
            onClick={handleBatchDuplicate} disabled={selectedIds.size === 0}
            data-testid="poster-multiselect-duplicate"
            title="复制选中为副本">⎘ 复制</Button>
          <div className="relative">
            <Button type="button" variant="ghost" size="sm" className="h-6 px-1.5 text-[11px]"
              onClick={() => setThemePickerOpen(v => !v)} disabled={selectedIds.size === 0 || themes.length === 0}
              data-testid="poster-multiselect-theme"
              title="批量改主题">🎨 主题</Button>
            {themePickerOpen && (
              <div
                className={`absolute right-0 top-7 z-30 max-h-56 overflow-y-auto rounded-md border shadow-lg py-1 text-xs min-w-[140px] ${dark ? "bg-zinc-800 border-zinc-700" : "bg-popover border-border"}`}
                onClick={e => e.stopPropagation()}
              >
                {themes.map(t => (
                  <button key={t.id} type="button"
                    className={`w-full text-left px-2 py-1 ${dark ? "hover:bg-zinc-700" : "hover:bg-muted"}`}
                    onClick={() => { setThemePickerOpen(false); void handleBatchSetTheme(t.id); }}
                    data-testid={`poster-multiselect-theme-${t.id}`}
                  >{t.name}</button>
                ))}
              </div>
            )}
          </div>
          <Button type="button" variant="ghost" size="sm" className="h-6 px-1.5 text-[11px] text-destructive"
            onClick={handleBatchDelete} disabled={selectedIds.size === 0}
            data-testid="poster-multiselect-delete"
            title="批量删除">🗑 删除</Button>
        </div>
      )}

      <ul className="mt-2 space-y-1 max-h-56 overflow-y-auto" role="list" aria-label="已保存海报"
        data-testid="poster-list">
        {visiblePosters.length === 0 && (
          <li className={`text-xs py-2 text-center ${dark ? "text-zinc-500" : "text-muted-foreground"}`}
            data-testid="poster-empty">
            {search.trim() ? `没有匹配「${search.trim()}」的海报` : "尚未保存任何海报"}
          </li>
        )}
        {visiblePosters.map(p => {
          const isCurrent = store.current.id === p.id;
          const isRenaming = renamingId === p.id;
          const isSelected = selectedIds.has(p.id);
          return (
            <li
              key={p.id}
              className="group relative"
              data-testid={`poster-item-${p.id}`}
              onDragOver={(e) => handleDragOver(e, p.id)}
              onDragLeave={(e) => handleDragLeave(e, p.id)}
              onDrop={(e) => void handleDrop(e, p.id)}
            >
              {/* M3 P2 拖拽插入线指示 */}
              {dropTarget?.id === p.id && dropTarget.pos === "before" && (
                <div
                  className="absolute left-0 right-0 -top-px h-0.5 bg-sky-500 pointer-events-none"
                  data-testid={`drop-indicator-before-${p.id}`}
                />
              )}
              {dropTarget?.id === p.id && dropTarget.pos === "after" && (
                <div
                  className="absolute left-0 right-0 -bottom-px h-0.5 bg-sky-500 pointer-events-none"
                  data-testid={`drop-indicator-after-${p.id}`}
                />
              )}
              <div
                role="button"
                tabIndex={0}
                aria-pressed={isCurrent}
                draggable={!multiSelectMode && !isRenaming}
                onDragStart={(e) => handleDragStart(e, p.id)}
                onDragEnd={handleDragEnd}
                onClick={() => {
                  if (isRenaming) return;
                  if (multiSelectMode) { toggleSelect(p.id); return; }
                  void store.select(p.id);
                }}
                onContextMenu={(e) => {
                  e.preventDefault();
                  setContextMenu({ x: e.clientX, y: e.clientY, id: p.id });
                }}
                onDoubleClick={() => {
                  if (multiSelectMode) { toggleSelect(p.id); return; }
                  startRename(p.id, p.name);
                }}
                className={`w-full text-left rounded-lg px-1.5 py-1.5 text-xs flex items-center gap-2 transition-colors cursor-pointer ${
                  isSelected
                    ? (dark ? "bg-sky-500/15 ring-1 ring-sky-500/40" : "bg-sky-50 ring-1 ring-sky-200")
                    : isCurrent
                    ? (dark ? "bg-emerald-500/15 ring-1 ring-emerald-500/40" : "bg-emerald-50 ring-1 ring-emerald-200")
                    : (dark ? "hover:bg-zinc-800/50" : "hover:bg-muted")
                } ${
                  dragId === p.id ? "opacity-50" : ""
                }`}
                data-current={isCurrent ? "true" : "false"}
              >
                {/* M3 P1: 多选 checkbox */}
                {multiSelectMode && (
                  <input
                    type="checkbox"
                    aria-label={`选择「${p.name}」`}
                    checked={isSelected}
                    onChange={() => toggleSelect(p.id)}
                    onClick={e => e.stopPropagation()}
                    className="shrink-0 accent-sky-500"
                    data-testid={`poster-checkbox-${p.id}`}
                  />
                )}
                {/* 缩略图（M3 P0 + P1 hover 浮层） */}
                <div
                  className={`shrink-0 w-10 h-10 rounded overflow-hidden ${dark ? "bg-zinc-800" : "bg-muted"}`}
                  onMouseEnter={(e) => handleThumbEnter(p.id, e.currentTarget)}
                  onMouseLeave={handleThumbLeave}
                >
                  <img
                    src={`/api/posters/${p.id}/thumb`}
                    alt=""
                    width={40}
                    height={40}
                    className="w-full h-full object-cover"
                    loading="lazy"
                    onError={(e) => {
                      // 缩略图失败 → fallback 显示首字符
                      const el = e.currentTarget;
                      el.style.display = "none";
                      const fallback = el.nextElementSibling as HTMLElement | null;
                      if (fallback) fallback.style.display = "flex";
                    }}
                    data-testid={`poster-thumb-${p.id}`}
                  />
                  <div
                    aria-hidden="true"
                    className={`w-full h-full items-center justify-center text-sm font-medium ${dark ? "bg-zinc-800 text-zinc-400" : "bg-muted text-muted-foreground"}`}
                    style={{ display: "none" }}
                  >
                    {(p.name || "?").charAt(0).toUpperCase()}
                  </div>
                </div>
                <div className="flex-1 min-w-0 grid gap-0.5">
                  {isRenaming ? (
                    <input
                      ref={renameInputRef}
                      value={renameValue}
                      onChange={e => setRenameValue(e.target.value)}
                      onBlur={commitRename}
                      onKeyDown={e => {
                        if (e.key === "Enter") commitRename();
                        if (e.key === "Escape") cancelRename();
                      }}
                      className={`text-xs px-1 py-0.5 rounded border w-full ${dark ? "bg-zinc-900 border-zinc-700" : "bg-background border-input"}`}
                      data-testid={`poster-rename-input-${p.id}`}
                      onClick={e => e.stopPropagation()}
                    />
                  ) : (
                    <span className="truncate font-medium" title={p.name}>
                      {p.name}
                    </span>
                  )}
                  <span className={`text-[10px] tabular-nums flex items-center gap-1.5 ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
                    <span>×{p.song_count} 首</span>
                    {p.updated_at && (
                      <>
                        <span aria-hidden="true">·</span>
                        <span>{formatDateTime(p.updated_at)}</span>
                      </>
                    )}
                  </span>
                </div>
              </div>
            </li>
          );
        })}
      </ul>

      {/* M3 P1: hover 浮层（400x400 大图，右上角） */}
      {hoverId && previewPos && (
        <div
          role="dialog"
          aria-label="海报预览"
          className={`fixed z-50 rounded-lg overflow-hidden border shadow-2xl ${dark ? "bg-zinc-900 border-zinc-700" : "bg-card border-border"}`}
          style={{
            left: previewPos.x,
            top: previewPos.y,
            width: 400,
            height: 400,
          }}
          data-testid="poster-preview-overlay"
        >
          <img
            src={`/api/posters/${hoverId}/thumb?size=400`}
            alt=""
            width={400}
            height={400}
            className="w-full h-full object-contain"
            onError={(e) => { e.currentTarget.style.display = "none"; }}
          />
        </div>
      )}

      {/* 右键菜单 */}
      {contextMenu && (
        <div
          role="menu"
          data-testid="poster-context-menu"
          className={`fixed z-50 rounded-md border shadow-lg py-1 text-xs min-w-[120px] ${
            dark ? "bg-zinc-800 border-zinc-700 text-zinc-200" : "bg-popover border-border text-popover-foreground"
          }`}
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onClick={(e) => e.stopPropagation()}
        >
          <button
            type="button" role="menuitem"
            className={`w-full text-left px-3 py-1.5 ${dark ? "hover:bg-zinc-700" : "hover:bg-muted"}`}
            onClick={() => {
              const target = visiblePosters.find(p => p.id === contextMenu.id);
              if (target) startRename(target.id, target.name);
            }}
            data-testid="poster-context-rename"
          >
            ✎ 重命名
          </button>
          <button
            type="button" role="menuitem"
            className={`w-full text-left px-3 py-1.5 ${dark ? "hover:bg-zinc-700" : "hover:bg-muted"}`}
            onClick={async () => {
              const id = contextMenu.id;
              setContextMenu(null);
              if (id === store.current.id) {
                await store.duplicate();
              } else {
                // 非当前海报：切换 → 复制 → 切回原
                const prev = store.current.id;
                await store.select(id);
                const newId = await store.duplicate();
                if (newId && prev) await store.select(prev);
              }
            }}
            data-testid="poster-context-duplicate"
          >
            ⎘ 复制副本
          </button>
          <div className={`my-0.5 border-t ${dark ? "border-zinc-700" : "border-border"}`} />
          <button
            type="button" role="menuitem"
            className={`w-full text-left px-3 py-1.5 text-destructive ${dark ? "hover:bg-red-500/20" : "hover:bg-red-50"}`}
            onClick={async () => {
              const id = contextMenu.id;
              setContextMenu(null);
              if (!id) return;
              const target = visiblePosters.find(p => p.id === id);
              if (!target) return;
              if (!window.confirm(`删除「${target.name}」？此操作不可撤销。`)) return;
              const prev = store.current.id;
              await store.select(id);
              await store.deleteCurrent();
              if (prev && prev !== id) await store.select(prev);
            }}
            data-testid="poster-context-delete"
          >
            🗑 删除
          </button>
        </div>
      )}

      {store.current.id && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="w-full mt-2 text-destructive text-xs"
          onClick={handleDelete}
          data-testid="poster-delete-current"
        >
          删除当前
        </Button>
      )}
    </section>
  );
}
