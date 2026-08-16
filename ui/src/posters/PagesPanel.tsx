/// R4 退出条件 #2: 草稿/手动分页 UI V3（第一版）。
///
/// 简化 MVP：
/// - 显示当前海报的 manual_pages 列表（缩略图 + 编号）
/// - Add（追加空白页）/Delete（删当前页）/Reorder（上下箭头）
/// - 仅在 layout.supports_manual_pages=True 时启用（magazine-flow）
/// - grid-wrap / live-set / learning-report 灰显（按 capability）

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  addPosterPage,
  deletePosterPage,
  getPosterPages,
  reorderPosterPages,
  type PagePolicyMode,
} from "../api/posters";

export interface PagesPanelProps {
  posterId: string;
  layoutId: string;
  supportsManualPages: boolean;
  /** 导出成功后 refetch 信号（PosterStore.exportSuccess 变化） */
  invalidateKey?: string | number | null;
  dark: boolean;
}

const PANEL_TESTID = "pages-panel";
const ADD_BTN = "pages-add";
const THUMB_PREFIX = "pages-thumb-";
const DELETE_BTN_PREFIX = "pages-delete-";
const UP_BTN_PREFIX = "pages-up-";
const DOWN_BTN_PREFIX = "pages-down-";

export default function PagesPanel({
  posterId,
  layoutId,
  supportsManualPages,
  invalidateKey,
  dark,
}: PagesPanelProps) {
  const [items, setItems] = useState<Array<Record<string, unknown>>>([]);
  const [mode, setMode] = useState<PagePolicyMode>("auto");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    if (!supportsManualPages) return;
    setLoading(true);
    getPosterPages(posterId)
      .then(data => {
        setItems(data.items);
        setMode(data.mode);
        setError(null);
      })
      .catch(reason => {
        setError(reason instanceof Error ? reason.message : "页面列表加载失败");
      })
      .finally(() => setLoading(false));
  }, [posterId, supportsManualPages]);

  useEffect(() => {
    refresh();
  }, [refresh, invalidateKey]);

  const handleAdd = useCallback(async () => {
    setError(null);
    try {
      const data = await addPosterPage(posterId);
      setItems(data.items);
      setMode(data.mode);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "添加页面失败");
    }
  }, [posterId]);

  const handleDelete = useCallback(async (index: number) => {
    setError(null);
    try {
      const data = await deletePosterPage(posterId, index);
      setItems(data.items);
      setMode(data.mode);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "删除页面失败");
    }
  }, [posterId]);

  const handleMove = useCallback(async (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= items.length) return;
    const order = items.map((_, i) => i);
    [order[index], order[target]] = [order[target], order[index]];
    setError(null);
    try {
      const data = await reorderPosterPages(posterId, order);
      setItems(data.items);
      setMode(data.mode);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "重排页面失败");
    }
  }, [posterId, items]);

  const isDisabled = useMemo(
    () => !supportsManualPages || loading,
    [supportsManualPages, loading],
  );

  return (
    <section
      aria-label="页面编辑"
      className={`mt-3 px-3 py-2 rounded-lg border transition-colors ${
        dark
          ? "border-zinc-700/60 bg-zinc-800/30"
          : "border-border bg-muted/30"
      }`}
      data-testid={PANEL_TESTID}
    >
      <div className="flex items-center justify-between mb-1.5">
        <h3 className={`text-[11px] font-semibold uppercase tracking-wider ${
          dark ? "text-zinc-500" : "text-muted-foreground"
        }`}>
          页面 {items.length > 0 ? `（${items.length} 页）` : ""}
        </h3>
        <span className="text-[10px] text-muted-foreground tabular-nums" data-testid="pages-mode">
          {mode === "manual" ? "手动" : "自动"}
        </span>
      </div>

      {!supportsManualPages ? (
        <p className="text-[11px] text-muted-foreground py-1" data-testid="pages-disabled-hint">
          {layoutId} 不支持手动分页（切换到 magazine-flow 可启用）
        </p>
      ) : (
        <>
          {error && (
            <p className="text-[11px] text-destructive py-1" role="alert" data-testid="pages-error">
              {error}
            </p>
          )}
          {items.length === 0 ? (
            <p className="text-[11px] text-muted-foreground py-1" data-testid="pages-empty-hint">
              暂无手动页 — 点「+ 添加」开始编辑
            </p>
          ) : (
            <ul className="flex flex-wrap gap-2" role="list">
              {items.map((_, index) => {
                const isFirst = index === 0;
                const isLast = index === items.length - 1;
                return (
                  <li
                    key={index}
                    className={`relative w-[68px] rounded border ${
                      dark ? "border-zinc-700 bg-zinc-800" : "border-border bg-card"
                    }`}
                    data-testid={`${THUMB_PREFIX}${index}`}
                  >
                    <img
                      src={`/api/posters/${encodeURIComponent(posterId)}/thumb?size=200&page=${index + 1}`}
                      alt={`第 ${index + 1} 页`}
                      className="block w-full h-[68px] object-cover object-bottom rounded-t"
                      loading="lazy"
                    />
                    <div className="flex items-center justify-between px-1 py-0.5 text-[10px] tabular-nums">
                      <button
                        type="button"
                        onClick={() => void handleMove(index, -1)}
                        disabled={isDisabled || isFirst}
                        className="px-1 disabled:opacity-30 hover:underline"
                        aria-label={`上移第 ${index + 1} 页`}
                        data-testid={`${UP_BTN_PREFIX}${index}`}
                      >↑</button>
                      <span className="font-semibold">{index + 1}</span>
                      <button
                        type="button"
                        onClick={() => void handleMove(index, 1)}
                        disabled={isDisabled || isLast}
                        className="px-1 disabled:opacity-30 hover:underline"
                        aria-label={`下移第 ${index + 1} 页`}
                        data-testid={`${DOWN_BTN_PREFIX}${index}`}
                      >↓</button>
                    </div>
                    <button
                      type="button"
                      onClick={() => void handleDelete(index)}
                      disabled={isDisabled}
                      className="absolute top-0.5 right-0.5 w-4 h-4 rounded-full bg-destructive text-destructive-foreground text-[10px] flex items-center justify-center disabled:opacity-30"
                      aria-label={`删除第 ${index + 1} 页`}
                      title={`删除第 ${index + 1} 页`}
                      data-testid={`${DELETE_BTN_PREFIX}${index}`}
                    >✕</button>
                  </li>
                );
              })}
            </ul>
          )}
          <button
            type="button"
            onClick={() => void handleAdd()}
            disabled={isDisabled}
            className={`mt-2 text-[11px] px-2.5 py-1 rounded-md transition-colors disabled:opacity-40 ${
              dark
                ? "text-zinc-300 hover:bg-zinc-700/50"
                : "text-foreground hover:bg-muted"
            }`}
            data-testid={ADD_BTN}
          >+ 添加一页</button>
        </>
      )}
    </section>
  );
}
