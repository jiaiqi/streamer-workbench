/// R4 数据统计视图 — 5 tab: 总览 / 时间线 / Top 歌曲 / 难度 / Key 分布。
///
/// 数据从 /api/stats/* 现算, 冷启动空态友好 (note 提示用户开始积累数据)。
/// R3.5 learning-report: header 右上角「导出学习报告」按钮 → 渲染 learning-report 海报。
import { useEffect, useState } from "react";
import { apiRequest } from "../api/client";
import type {
  OverviewStatsResponse,
  FeedResponse,
  TopSongsResponse,
  DistributionResponse,
} from "../api/generated";
import { toRequestFailure, type RequestFailure, useLatestRequest } from "../async/requestState";
import { Icon } from "../icons";
import { openLearningReportPoster } from "../electron-bridge";

type Tab = "overview" | "feed" | "top" | "difficulty" | "key";
type TopMetric = "request" | "perform" | "practice";

interface StatsViewProps {
  dark: boolean;
}

export default function StatsView({ dark }: StatsViewProps) {
  const [tab, setTab] = useState<Tab>("overview");
  const [posterError, setPosterError] = useState<string | null>(null);
  const [posterSuccess, setPosterSuccess] = useState<string | null>(null);
  // R4.0: 导出进度反馈（避免重复点击 + spinner 可见）
  const [posterLoading, setPosterLoading] = useState(false);
  return (
    <main className="flex-1 flex flex-col overflow-hidden">
      <header className="flex shrink-0 items-end justify-between px-8 pt-7 pb-5">
        <div>
          <h1 className={`font-serif text-[26px] font-bold tracking-wide ${dark ? "text-zinc-100" : "text-foreground"}`}>
            数据统计
          </h1>
          <p className="mt-1 text-[13px] text-muted-foreground">
            全部从 events.jsonl + 曲库现算 · 冷启动友好
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          {posterError && (
            <div
              className="rounded-lg bg-red-500/10 px-3 py-1 text-xs text-red-500"
              role="alert"
              data-testid="stats-poster-error"
            >
              {posterError}
            </div>
          )}
          {posterSuccess && (
            <div
              className={`rounded-lg px-3 py-1 text-xs ${dark ? "bg-emerald-500/15 text-emerald-300" : "bg-emerald-50 text-emerald-700"}`}
              role="status"
              data-testid="stats-poster-success"
            >
              {posterSuccess}
            </div>
          )}
          {/* R3.5 learning-report 海报导出 + R4.0 loading 反馈 */}
          <button
            type="button"
            className="secondary-action"
            data-testid="stats-export-poster"
            data-loading={posterLoading ? "true" : "false"}
            disabled={posterLoading}
            aria-busy={posterLoading}
            title="把当前数据生成为 learning-report 海报"
            onClick={async () => {
              if (posterLoading) return;
              setPosterError(null);
              setPosterSuccess(null);
              setPosterLoading(true);
              try {
                const res = await openLearningReportPoster();
                if (res.ok) {
                  setPosterSuccess(res.path ? `已保存到 ${res.path}` : "已下载海报");
                } else if (!res.cancelled) {
                  setPosterError(res.error ?? "导出失败");
                }
              } catch (err) {
                console.error("导出学习报告失败", err);
                setPosterError(err instanceof Error ? err.message : "导出失败");
              } finally {
                setPosterLoading(false);
              }
            }}
          >
            {posterLoading ? (
              <>
                <span className="inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin align-middle" />
                <span className="ml-1.5">渲染中…</span>
              </>
            ) : "导出学习报告"}
          </button>
        </div>
      </header>
      <div className="flex-1 overflow-y-auto px-8 pb-10">
        <div className="flex items-center gap-1 mb-4" role="tablist" aria-label="统计视图">
          {([
            ["overview", "总览"],
            ["feed", "时间线"],
            ["top", "Top 歌曲"],
            ["difficulty", "难度分布"],
            ["key", "Key 分布"],
          ] as [Tab, string][]).map(([k, label]) => (
            <button
              key={k}
              type="button"
              role="tab"
              aria-selected={tab === k}
              onClick={() => setTab(k)}
              data-testid={`stats-tab-${k}`}
              className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${
                tab === k
                  ? (dark ? "bg-zinc-700 text-zinc-100" : "bg-primary text-primary-foreground")
                  : (dark ? "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200" : "text-muted-foreground hover:bg-muted hover:text-foreground")
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        {tab === "overview" && <OverviewPanel dark={dark} />}
        {tab === "feed" && <FeedPanel dark={dark} />}
        {tab === "top" && <TopPanel dark={dark} />}
        {tab === "difficulty" && <DistributionPanel dark={dark} metric="difficulty" />}
        {tab === "key" && <DistributionPanel dark={dark} metric="key" />}
      </div>
    </main>
  );
}

function OverviewPanel({ dark }: { dark: boolean }) {
  const [data, setData] = useState<OverviewStatsResponse | null>(null);
  const [error, setError] = useState<RequestFailure | null>(null);
  const req = useLatestRequest<OverviewStatsResponse>({ isEmpty: d => d.total_events === 0 && !d.note });

  useEffect(() => {
    setError(null);
    void req.run(signal => apiRequest<OverviewStatsResponse>("/api/stats/overview", { signal }))
      .then(d => { if (d) setData(d); })
      .catch(reason => setError(toRequestFailure(reason)));
  }, []); // eslint-disable-line

  if (error) return <ErrorNotice message={error.message} dark={dark} />;
  if (!data) return <LoadingCard dark={dark} />;
  if (data.note) return <EmptyNotice note={data.note} dark={dark} />;

  const cards = [
    { label: "总事件", value: data.total_events, color: "primary" },
    { label: "已会", value: data.active_songs, color: "amber" },
    { label: "在学", value: data.draft_songs, color: "rose" },
    { label: "练习分钟", value: data.total_practice_minutes, color: "emerald" },
    { label: "当前连续", value: `${data.current_streak_days} 天`, color: "sky" },
    { label: "最长连续", value: `${data.longest_streak_days} 天`, color: "violet" },
    { label: "点歌数", value: data.total_queue_requests, color: "amber" },
    { label: "演唱数", value: data.total_performances, color: "rose" },
    { label: "导出海报", value: data.total_posters_exported, color: "emerald" },
  ];
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 stagger-list">
      {cards.map(c => <MetricCard key={c.label} label={c.label} value={c.value} color={c.color} dark={dark} />)}
    </div>
  );
}

function MetricCard({ label, value, color, dark }: {
  label: string; value: number | string; color: string; dark: boolean;
}) {
  const colorClass: Record<string, string> = {
    primary: "from-primary/20 to-primary/5",
    amber:   "from-amber-500/20 to-amber-500/5",
    rose:    "from-rose-500/20 to-rose-500/5",
    emerald: "from-emerald-500/20 to-emerald-500/5",
    sky:     "from-sky-500/20 to-sky-500/5",
    violet:  "from-violet-500/20 to-violet-500/5",
  };
  return (
    <div className={`rounded-2xl border p-4 bg-gradient-to-br ${colorClass[color] || colorClass.primary} ${
      dark ? "border-zinc-700/50" : "border-border"
    }`}>
      <div className={`text-[11px] uppercase tracking-wide ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
        {label}
      </div>
      <div className={`mt-1 text-2xl font-bold tabular-nums ${dark ? "text-zinc-100" : "text-foreground"}`}>
        {value}
      </div>
    </div>
  );
}

function FeedPanel({ dark }: { dark: boolean }) {
  const [data, setData] = useState<FeedResponse | null>(null);
  const [error, setError] = useState<RequestFailure | null>(null);
  const [limit, setLimit] = useState(50);
  const req = useLatestRequest<FeedResponse>({ isEmpty: d => d.items.length === 0 && !d.note });

  const load = (n: number) => {
    setError(null);
    void req.run(signal => apiRequest<FeedResponse>(`/api/stats/feed?limit=${n}`, { signal }))
      .then(d => { if (d) setData(d); })
      .catch(reason => setError(toRequestFailure(reason)));
  };

  useEffect(() => { load(limit); /* eslint-disable-next-line */ }, [limit]);

  if (error) return <ErrorNotice message={error.message} dark={dark} />;
  if (!data) return <LoadingCard dark={dark} />;
  if (data.note) return <EmptyNotice note={data.note} dark={dark} />;
  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <p className={`text-xs ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
          最近 {data.items.length} 条事件, 最新在前
        </p>
        <select
          value={limit}
          onChange={e => setLimit(Number(e.target.value))}
          aria-label="时间线条目数量"
          className={`text-xs rounded-lg px-2 py-1 outline-none ${
            dark ? "bg-zinc-800 text-zinc-200 border border-zinc-700" : "bg-card text-foreground border border-border"
          }`}
        >
          <option value={20}>20 条</option>
          <option value={50}>50 条</option>
          <option value={100}>100 条</option>
        </select>
      </div>
      <ul className="space-y-1.5 stagger-list" role="list">
        {data.items.map(item => <FeedRow key={item.event_id} item={item} dark={dark} />)}
      </ul>
    </div>
  );
}

function FeedRow({ item, dark }: { item: import("../api/generated").FeedItemResponse; dark: boolean }) {
  return (
    <li className={`flex items-start gap-3 px-3 py-2 rounded-lg ${
      dark ? "hover:bg-zinc-800/40" : "hover:bg-muted/60"
    }`}>
      <span className={`shrink-0 mt-0.5 text-[10px] font-mono tabular-nums ${
        dark ? "text-zinc-500" : "text-muted-foreground"
      }`}>
        {item.occurred_at.slice(5, 16).replace("T", " ")}
      </span>
      <span className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded uppercase font-mono ${
        dark ? "bg-zinc-700/60 text-zinc-400" : "bg-muted text-muted-foreground"
      }`}>
        {item.type.replace(/_/g, " ")}
      </span>
      <span className={`text-sm ${dark ? "text-zinc-300" : "text-foreground"}`}>
        {item.summary}
      </span>
    </li>
  );
}

function TopPanel({ dark }: { dark: boolean }) {
  const [metric, setMetric] = useState<TopMetric>("request");
  const [data, setData] = useState<TopSongsResponse | null>(null);
  const [error, setError] = useState<RequestFailure | null>(null);
  const req = useLatestRequest<TopSongsResponse>({ isEmpty: d => d.items.length === 0 && !d.note });

  useEffect(() => {
    setError(null);
    void req.run(signal => apiRequest<TopSongsResponse>(`/api/stats/top-songs?metric=${metric}&limit=10`, { signal }))
      .then(d => { if (d) setData(d); })
      .catch(reason => setError(toRequestFailure(reason)));
  }, [metric]); // eslint-disable-line

  if (error) return <ErrorNotice message={error.message} dark={dark} />;
  if (!data) return <LoadingCard dark={dark} />;
  if (data.note) return <EmptyNotice note={data.note} dark={dark} />;

  const max = data.items[0]?.count || 1;
  return (
    <div>
      <div className="flex items-center gap-1 mb-3">
        {([
          ["request", "点歌 Top"],
          ["perform", "演唱 Top"],
          ["practice", "练习 Top"],
        ] as [TopMetric, string][]).map(([m, label]) => (
          <button
            key={m}
            type="button"
            role="tab"
            aria-selected={metric === m}
            onClick={() => setMetric(m)}
            aria-label={`Top 歌曲按 ${label} 排序`}
            className={`px-3 py-1 text-xs font-medium rounded-lg transition-colors ${
              metric === m
                ? (dark ? "bg-zinc-700 text-zinc-100" : "bg-primary text-primary-foreground")
                : (dark ? "text-zinc-400 hover:bg-zinc-800/60" : "text-muted-foreground hover:bg-muted")
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      <ul className="space-y-2 stagger-list" role="list">
        {data.items.map((item, idx) => (
          <li
            key={item.song_id}
            className={`flex items-center gap-3 px-3 py-2 rounded-xl border ${
              dark ? "border-zinc-700/40" : "border-border"
            }`}
          >
            <span className={`shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
              idx === 0
                ? (dark ? "bg-amber-500/20 text-amber-300" : "bg-amber-100 text-amber-700")
                : (dark ? "bg-zinc-700/60 text-zinc-400" : "bg-muted text-muted-foreground")
            }`}>
              {idx + 1}
            </span>
            <div className="flex-1 min-w-0">
              <div className="flex items-baseline gap-2">
                <span className={`font-medium truncate ${dark ? "text-zinc-100" : "text-foreground"}`}>
                  {item.title}
                </span>
                {item.artist && (
                  <span className={`text-xs truncate ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
                    {item.artist}
                  </span>
                )}
              </div>
              <div className={`mt-1 h-1.5 rounded-full overflow-hidden ${
                dark ? "bg-zinc-800" : "bg-muted"
              }`}>
                <div
                  className="h-full rounded-full bg-primary transition-all"
                  style={{ width: `${(item.count / max) * 100}%` }}
                />
              </div>
            </div>
            <div className="shrink-0 text-right">
              <div className={`text-lg font-bold tabular-nums ${dark ? "text-zinc-100" : "text-foreground"}`}>
                {item.count}
              </div>
              {item.minutes > 0 && (
                <div className={`text-[10px] ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
                  {item.minutes} 分钟
                </div>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function DistributionPanel({ dark, metric }: { dark: boolean; metric: "difficulty" | "key" }) {
  const [data, setData] = useState<DistributionResponse | null>(null);
  const [error, setError] = useState<RequestFailure | null>(null);
  const req = useLatestRequest<DistributionResponse>({ isEmpty: d => d.buckets.length === 0 && !d.note });

  useEffect(() => {
    setError(null);
    void req.run(signal => apiRequest<DistributionResponse>(`/api/stats/distribution?metric=${metric}`, { signal }))
      .then(d => { if (d) setData(d); })
      .catch(reason => setError(toRequestFailure(reason)));
  }, [metric]); // eslint-disable-line

  if (error) return <ErrorNotice message={error.message} dark={dark} />;
  if (!data) return <LoadingCard dark={dark} />;
  if (data.note) return <EmptyNotice note={data.note} dark={dark} />;
  const max = data.buckets.reduce((m, b) => Math.max(m, b.count), 1);
  return (
    <div className="space-y-2 stagger-list" role="list">
      {data.buckets.map(b => (
        <div key={b.label} className="flex items-center gap-3" role="listitem">
          <div className={`shrink-0 w-20 text-sm text-right ${dark ? "text-zinc-400" : "text-muted-foreground"}`}>
            {b.label}
          </div>
          <div className={`flex-1 h-7 rounded-lg overflow-hidden relative ${
            dark ? "bg-zinc-800" : "bg-muted"
          }`}>
            <div
              className="h-full bg-primary/80 transition-all"
              style={{ width: `${(b.count / max) * 100}%` }}
            />
            <span className={`absolute right-2 top-1/2 -translate-y-1/2 text-xs font-semibold tabular-nums ${
              dark ? "text-zinc-100" : "text-foreground"
            }`}>
              {b.count}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

function ErrorNotice({ message, dark }: { message: string; dark: boolean }) {
  return (
    <div className={`text-sm px-4 py-6 text-center rounded-xl ${
      dark ? "bg-rose-500/10 text-rose-400" : "bg-rose-50 text-rose-700"
    }`}>
      {message}
    </div>
  );
}

function EmptyNotice({ note, dark }: { note: string; dark: boolean }) {
  return (
    <div className={`text-sm px-4 py-12 text-center rounded-xl ${
      dark ? "bg-zinc-800/40 text-zinc-400" : "bg-muted text-muted-foreground"
    }`}>
      <div className="mb-2 opacity-70 inline-block">{Icon.barChart}</div>
      <p>{note}</p>
      <p className="mt-2 text-xs opacity-60">标记学会 / 启动直播 / 打卡 让数据开始积累</p>
    </div>
  );
}

function LoadingCard({ dark }: { dark: boolean }) {
  return (
    <div className={`h-40 rounded-2xl animate-pulse ${dark ? "bg-zinc-800/60" : "bg-muted/70"}`} />
  );
}
