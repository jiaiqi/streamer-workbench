/// R4.2.4 数据反哺创作 — 工作台左栏"基于数据"快入口卡片（1.1 收口）
///
/// 设计动机：
/// R4.2.1 / R4.2.2 已实现 StatsView Top / Feed tab 里的"据此创建海报 / Preset"按钮，
/// 但能力藏在二级菜单里，工作台用户不主动切到 StatsView 看不到。
///
/// 本组件把这条路径**主动塞到工作台首屏左栏顶部**：
/// 1. 拉 `/api/stats/top-songs?metric=request&limit=3`（点歌热度 top 3）
/// 2. 4 态：loading（Spinner）/ error（ErrorBanner）/ empty（EmptyState）/ data（列表 + 按钮）
/// 3. 按钮"用 Top 3 创建海报" → 调 onCreatePosterFromTop，复用 App.tsx:222-248 回调
/// 4. 次按钮"去统计页看更多" → 调 onSwitchToStats
///
/// 不存任何状态到父组件（pure component）；失败时 ErrorBanner 自带重试按钮。
import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "@/api/client";
import type { TopSongsResponse } from "@/api/generated";
import Spinner from "@/components/Spinner";
import ErrorBanner from "@/components/ErrorBanner";
import EmptyState from "@/components/EmptyState";
import { toRequestFailure, type RequestFailure } from "@/async/requestState";

export interface DataQuickEntryCardProps {
  dark: boolean;
  /** App.tsx handleCreatePosterFromTop：接受 songIds，metric 固定 request */
  onCreatePosterFromTop: (songIds: string[]) => Promise<void>;
  /** 切到 StatsView（App.tsx 的 setView("stats")） */
  onSwitchToStats: () => void;
}

const TOP_LIMIT = 3;

export default function DataQuickEntryCard({
  dark, onCreatePosterFromTop, onSwitchToStats,
}: DataQuickEntryCardProps) {
  const [data, setData] = useState<TopSongsResponse | null>(null);
  const [error, setError] = useState<RequestFailure | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);

  const fetchTop = useCallback(() => {
    setLoading(true);
    setError(null);
    apiRequest<TopSongsResponse>(`/api/stats/top-songs?metric=request&limit=${TOP_LIMIT}`)
      .then(res => {
        if (res) setData(res);
      })
      .catch((failure: unknown) => {
        setError(toRequestFailure(failure));
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchTop();
  }, [fetchTop]);

  const handleCreate = useCallback(async () => {
    if (!data || (data.items?.length ?? 0) === 0) return;
    setCreating(true);
    try {
      const songIds = (data.items ?? []).map(item => item.song_id);
      await onCreatePosterFromTop(songIds);
    } finally {
      setCreating(false);
    }
  }, [data, onCreatePosterFromTop]);

  return (
    <section
      aria-label="基于数据"
      data-testid="data-quick-entry"
      className={`px-4 pt-5 pb-4 border-b transition-colors duration-500 ${
        dark ? "border-zinc-700/50" : "border-border"
      }`}
    >
      <header className="mb-2.5 flex items-baseline justify-between">
        <div>
          <h2 className={`text-[13px] font-semibold tracking-wide ${dark ? "text-zinc-100" : "text-foreground"}`}>
            基于数据
          </h2>
          <p className={`mt-0.5 text-[11px] leading-snug ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
            最常被点歌的 {TOP_LIMIT} 首 · 一键成海报
          </p>
        </div>
      </header>

      {/* loading 态 */}
      {loading && (
        <div className="flex items-center gap-2 py-3" data-testid="data-quick-loading">
          <Spinner size="sm" tone="current" decorative label="加载 Top 歌曲" />
          <span className={`text-xs ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
            加载点歌热度中…
          </span>
        </div>
      )}

      {/* error 态 */}
      {!loading && error && (
        <ErrorBanner
          severity="warning"
          message={error.message}
          onRetry={fetchTop}
          data-testid="data-quick-error"
        />
      )}

      {/* empty 态：note 字段后端会在数据不足时填冷启动说明 */}
      {!loading && !error && data && (data.items?.length ?? 0) === 0 && (
        <EmptyState
          icon={<span aria-hidden="true">📊</span>}
          title="还没有点歌记录"
          description={data.note || "记录点歌后会出现在这里；点歌可在直播现场速查完成。"}
          secondaryLabel="去看统计"
          onSecondary={onSwitchToStats}
          inline
          dark={dark}
          data-testid="data-quick-empty"
        />
      )}

      {/* data 态 */}
      {!loading && !error && data && (data.items?.length ?? 0) > 0 && (
        <div className="space-y-2.5" data-testid="data-quick-list">
          <ol className="space-y-1.5">
            {data.items!.map((item, idx) => (
              <li
                key={item.song_id}
                className={`flex items-baseline gap-2 text-[12px] leading-snug ${
                  dark ? "text-zinc-300" : "text-foreground"
                }`}
                data-testid="data-quick-item"
                data-song-id={item.song_id}
              >
                <span
                  className={`shrink-0 font-mono text-[11px] tabular-nums ${
                    dark ? "text-zinc-500" : "text-muted-foreground"
                  }`}
                >
                  {idx + 1}.
                </span>
                <span className="truncate flex-1">
                  <span className="font-medium">{item.title}</span>
                  {item.artist && (
                    <span className={dark ? "text-zinc-500 ml-1" : "text-muted-foreground ml-1"}>
                      · {item.artist}
                    </span>
                  )}
                </span>
                <span
                  className={`shrink-0 font-mono text-[11px] tabular-nums ${
                    dark ? "text-zinc-500" : "text-muted-foreground"
                  }`}
                  title={`${item.count ?? 0} 次点歌`}
                >
                  ×{item.count ?? 0}
                </span>
              </li>
            ))}
          </ol>
          <div className="flex items-center gap-2 pt-1">
            <button
              type="button"
              onClick={handleCreate}
              disabled={creating}
              aria-busy={creating}
              data-loading={creating ? "true" : "false"}
              data-testid="data-quick-create"
              className={`flex-1 inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-medium transition-all active:scale-95 cursor-pointer disabled:opacity-50 ${
                dark
                  ? "bg-zinc-100 text-zinc-900 hover:bg-white"
                  : "bg-foreground text-background hover:opacity-90"
              }`}
            >
              {creating && <Spinner size="sm" tone="current" decorative />}
              {creating ? "创建中…" : `用 Top ${data.items?.length ?? 0} 创建海报`}
            </button>
            <button
              type="button"
              onClick={onSwitchToStats}
              data-testid="data-quick-stats-link"
              className={`shrink-0 rounded-lg px-2.5 py-1.5 text-[12px] transition-colors cursor-pointer ${
                dark
                  ? "text-zinc-400 hover:text-zinc-200"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              更多 →
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
