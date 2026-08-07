/// R1a.5 + M3 P0 工作台左栏：海报文档区。
///
/// 新增（M3 P0）：
/// - 缩略图（200x200 后端懒生成）
/// - 搜索框（按 name 模糊匹配）
/// - 排序下拉（更新时间 / 歌数 / 名称）
/// - 右键菜单（重命名 / 复制 / 删除）
/// - inline 重命名（双击名 → input + 失焦保存 / Esc 取消）
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { PosterStore } from "./usePosterStore";
import LayoutPicker from "./LayoutPicker";
import StatusBadge from "@/components/StatusBadge";

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

  // ── 过滤 + 排序 ──
  const visiblePosters = useMemo(() => {
    const term = search.trim().toLowerCase();
    const filtered = term
      ? store.posters.filter(p => p.name.toLowerCase().includes(term))
      : store.posters;
    const sorted = [...filtered].sort((a, b) => {
      if (sortBy === "name") return a.name.localeCompare(b.name, "zh-CN");
      if (sortBy === "songs") return b.song_count - a.song_count;
      // 默认 updated：后端 PosterSummary 暂无 updated_at 字段，按 name 倒序做 fallback
      return a.name.localeCompare(b.name);
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

      {/* 搜索 + 排序（M3 P0） */}
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
      </div>

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
          return (
            <li key={p.id} className="group" data-testid={`poster-item-${p.id}`}>
              <div
                role="button"
                tabIndex={0}
                aria-pressed={isCurrent}
                onClick={() => { if (!isRenaming) void store.select(p.id); }}
                onContextMenu={(e) => {
                  e.preventDefault();
                  setContextMenu({ x: e.clientX, y: e.clientY, id: p.id });
                }}
                onDoubleClick={() => startRename(p.id, p.name)}
                className={`w-full text-left rounded-lg px-1.5 py-1.5 text-xs flex items-center gap-2 transition-colors cursor-pointer ${
                  isCurrent
                    ? (dark ? "bg-emerald-500/15 ring-1 ring-emerald-500/40" : "bg-emerald-50 ring-1 ring-emerald-200")
                    : (dark ? "hover:bg-zinc-800/50" : "hover:bg-muted")
                }`}
                data-current={isCurrent ? "true" : "false"}
              >
                {/* 缩略图（M3 P0） */}
                <div className={`shrink-0 w-10 h-10 rounded overflow-hidden ${dark ? "bg-zinc-800" : "bg-muted"}`}>
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
