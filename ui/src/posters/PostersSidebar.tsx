/// R1a.5 工作台左栏：海报文档区。
///
/// 显示已保存海报列表 + 当前 Poster 名称 + 状态徽章 + 新建/删除按钮。
/// 紧凑样式；不抢主题列表的视觉位置（侧栏两段独立滚动）。
import { useCallback } from "react";
import { Button } from "@/components/ui/button";
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

function formatTime(ts: number | null): string {
  if (ts === null) return "—";
  const d = new Date(ts);
  return `${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
}

export default function PostersSidebar({ store, dark }: PostersSidebarProps) {
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

  return (
    <section aria-label="海报文档" className={`px-4 pt-5 pb-3 border-b transition-colors duration-500 ${
      dark ? "border-zinc-700/50" : "border-border"
    }`}>
      <div className="flex items-center justify-between mb-2">
        <p className="eyebrow">当前作品</p>
        <div className="flex items-center gap-1">
          {/* P2 R4: 撤销 / 重做（Cmd+Z / Cmd+Shift+Z） */}
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

      <ul className="mt-3 space-y-1 max-h-40 overflow-y-auto" role="list" aria-label="已保存海报">
        {store.posters.length === 0 && (
          <li className={`text-xs ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
            尚未保存任何海报
          </li>
        )}
        {store.posters.map(p => (
          <li key={p.id}>
            <Button
              type="button"
              variant={store.current.id === p.id ? "default" : "ghost"}
              size="sm"
              onClick={() => { void store.select(p.id); }}
              className="w-full justify-between h-auto py-1.5 px-2 text-xs"
              aria-pressed={store.current.id === p.id}
            >
              <span className="truncate font-medium">{p.name}</span>
              <span className="tabular-nums text-[10px] opacity-70">×{p.song_count}</span>
            </Button>
          </li>
        ))}
      </ul>

      {store.current.id && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="w-full mt-2 text-destructive text-xs"
          onClick={handleDelete}
        >
          删除当前
        </Button>
      )}
    </section>
  );
}
