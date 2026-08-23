/// P1-A1 今晚工作台 — 工作台首屏主任务中心（5 区一体化）。
///
/// 8/18 评估报告 5.1 要求把工作台从"展示面板"升级为"今日/今晚工作台"。
/// 把原先散落在 App.tsx 左栏顶部的两个独立卡片（TonightSetCard + DataQuickEntryCard）
/// 合并为一个组件，承担 5 个任务区：
///
/// - **A. 状态区**：当前 LiveSession 状态徽标（active / closed / draft / 无活跃场次）
/// - **B. 动作区**：基于状态的条件按钮（开始直播 / 打开速查 / 复盘海报 / 学习报告）
/// - **C. 今晚歌单区**：复用 TonightSetCard 拉取逻辑（活跃时显示 Top 5，未唱优先）
/// - **D. 演出准备检查区**：对今晚歌单每首歌检查 tabs / lyrics / audio / key 4 项
/// - **E. 推荐动作 + 复盘区**：复用 DataQuickEntryCard 拉取逻辑（Top 3 + 一键创建海报）
///
/// 设计原则：
/// - 5 区共享一个 section 边框 + 内部分区（避免多 section 视觉割裂）
/// - 3 个内部子组件：`<TonightQueueList>` / `<ReadinessCheck>` / `<TopActionsCard>`
/// - 复用 useApiError / useLatestRequest / toRequestFailure + Spinner / EmptyState / ErrorBanner
/// - 复用 narrow helpers（asString / asNumber / asBoolean / asRecord）
/// - 任何 fetch 失败：ErrorBanner 自带重试（onRetry）
/// - 复用 onPlaySong / onOpenLiveView / onCreatePosterFromTop / onSwitchToStats 4 个原有回调
///   + 新加 onGenerateRecap / onGenerateLearningReport / onOpenQuickView 3 个可选回调
///   （占位 toast，不强制接线）
///
/// 不触碰 core/ / server/ / 任何 Python 边界。
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiRequest } from "../api/client";
import { asString, asNumber, asBoolean, asRecord } from "../lib/narrow";
import { useLatestRequest, toRequestFailure, type RequestFailure } from "../async/requestState";
import { useApiError } from "../async/useApiError";
import Spinner from "./Spinner";
import ErrorBanner from "./ErrorBanner";
import EmptyState from "./EmptyState";
import type { TopSongsResponse } from "@/api/generated";

export interface TonightWorkbenchProps {
  dark: boolean;
  onPlaySong: (
    songId: string,
    link: { sessionId: string; requestId: string; requesterName: string },
  ) => void;
  onOpenLiveView: () => void;
  onCreatePosterFromTop: (songIds: string[]) => Promise<void>;
  onSwitchToStats: () => void;
  /** R2.5 复盘海报：传入后显示「生成复盘海报」按钮（仅 closed session 可见） */
  onGenerateRecap?: (sessionId: string) => void;
  /** R3.5 学习报告海报：传入后显示「生成学习报告」按钮 */
  onGenerateLearningReport?: () => void;
  /** R2 打开速查窗口：传入后顶部「打开速查」按钮可见 */
  onOpenQuickView?: (sessionId: string) => void;
}

/* ====================== 类型守门 ====================== */

interface LiveSessionSummary {
  id: string;
  state: string;
  title: string;
  rule_version: string;
  started_at: string;
  closed_at: string | null;
  queue_size: number;
}

interface QueueEntry {
  request_id: string;
  song_id: string;
  position: number;
  state: string;
  is_bumped: boolean;
  requester_name: string;
  entitlement_kind: string;
  inserted_at: string;
}

interface SongRecord {
  id: string;
  title: string;
  /** song tabs field — chart / chordpro 文本（"tab_files" 也是同名，但 songs/list 用 "tabs" 字符串） */
  tabs: string;
  lyrics_plain: string;
  lyrics_lrc: string;
  audio_vocal_path: string | null;
  key: string;
}

type SessionState = "active" | "closed" | "draft" | "none";

const QUEUE_STATE_LABEL: Record<string, string> = {
  pending: "待申请",
  requested: "已请求",
  queued: "待唱",
  current: "演唱中",
  sung: "已唱",
  postponed: "延期",
  unknown: "不会",
  skipped: "跳过",
  cancelled: "取消",
  duplicate_merged: "合并",
};

const TOP_N = 5;

const READINESS_FIELDS_LOOKUP: Record<string, string> = {
  tabs: "曲谱",
  lyrics: "歌词",
  audio: "音频",
  key: "Key",
};

/* ====================== narrow helpers ====================== */

function asQueueEntry(value: unknown): QueueEntry | null {
  const v = asRecord(value);
  if (!v) return null;
  const request_id = asString(v, "request_id");
  const song_id = asString(v, "song_id");
  if (!request_id || !song_id) return null;
  return {
    request_id,
    song_id,
    position: asNumber(v, "position") ?? 0,
    state: asString(v, "state") ?? "queued",
    is_bumped: asBoolean(v, "is_bumped") ?? false,
    requester_name: asString(v, "requester_name") ?? "",
    entitlement_kind: asString(v, "entitlement_kind") ?? "",
    inserted_at: asString(v, "inserted_at") ?? "",
  };
}

function asSongRecord(value: unknown): SongRecord | null {
  const v = asRecord(value);
  if (!v) return null;
  const id = asString(v, "id");
  if (!id) return null;
  return {
    id,
    title: asString(v, "title") ?? id,
    tabs: asString(v, "tabs") ?? "",
    lyrics_plain: asString(v, "lyrics_plain") ?? "",
    lyrics_lrc: asString(v, "lyrics_lrc") ?? "",
    audio_vocal_path: asString(v, "audio_vocal_path") ?? null,
    key: asString(v, "key") ?? "",
  };
}

/* ====================== A + B: 状态徽标 + 动作区 ====================== */

interface StatusBadgeProps {
  dark: boolean;
  state: SessionState;
  sessionTitle: string;
  onClick: () => void;
}

function StatusBadge({ dark, state, sessionTitle, onClick }: StatusBadgeProps) {
  const config = (() => {
    switch (state) {
      case "active":
        return { dot: "bg-emerald-500", label: "进行中", tone: dark ? "text-emerald-300" : "text-emerald-700" };
      case "closed":
        return { dot: "bg-zinc-400", label: "已结束", tone: dark ? "text-zinc-300" : "text-zinc-600" };
      case "draft":
        return { dot: "bg-amber-500", label: "未开始", tone: dark ? "text-amber-300" : "text-amber-700" };
      case "none":
      default:
        return { dot: "bg-zinc-500", label: "无活跃场次", tone: dark ? "text-zinc-400" : "text-zinc-500" };
    }
  })();
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid="tw-status-badge"
      data-session-state={state}
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium transition-colors ${
        dark ? "hover:bg-zinc-700/50" : "hover:bg-muted"
      } ${config.tone}`}
      title="切到直播视图"
    >
      <span className={`inline-block w-2 h-2 rounded-full ${config.dot}`} aria-hidden="true" />
      {sessionTitle ? `${config.label} · ${sessionTitle}` : config.label}
    </button>
  );
}

interface ActionBarProps {
  dark: boolean;
  state: SessionState;
  sessionId: string | null;
  onOpenLiveView: () => void;
  onOpenQuickView?: (sessionId: string) => void;
  onGenerateRecap?: (sessionId: string) => void;
  onGenerateLearningReport?: () => void;
}

function ActionBar({
  dark, state, sessionId,
  onOpenLiveView, onOpenQuickView, onGenerateRecap, onGenerateLearningReport,
}: ActionBarProps) {
  const baseBtn = (primary: boolean) =>
    `inline-flex items-center justify-center gap-1 rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-colors cursor-pointer ${
      primary
        ? dark
          ? "bg-zinc-100 text-zinc-900 hover:bg-white"
          : "bg-foreground text-background hover:opacity-90"
        : dark
          ? "border border-zinc-700/60 text-zinc-300 hover:bg-zinc-700/40"
          : "border border-border text-foreground hover:bg-muted"
    }`;

  if (state === "none") {
    return (
      <div className="flex items-center gap-1.5" data-testid="tw-actions-none">
        <button
          type="button"
          className={baseBtn(true)}
          onClick={onOpenLiveView}
          data-testid="tw-action-start-live"
        >
          开始直播
        </button>
        {onOpenQuickView && (
          <button
            type="button"
            className={baseBtn(false)}
            onClick={() => onOpenQuickView("")}
            data-testid="tw-action-open-quickview"
            disabled
            title="无活跃场次时不可用"
          >
            打开速查
          </button>
        )}
      </div>
    );
  }

  if (state === "active") {
    return (
      <div className="flex items-center gap-1.5 flex-wrap" data-testid="tw-actions-active">
        {onOpenQuickView && sessionId && (
          <button
            type="button"
            className={baseBtn(true)}
            onClick={() => onOpenQuickView(sessionId)}
            data-testid="tw-action-open-quickview"
          >
            打开速查 ▶
          </button>
        )}
        <button
          type="button"
          className={baseBtn(false)}
          onClick={onOpenLiveView}
          data-testid="tw-action-open-full-queue"
        >
          查看完整队列 →
        </button>
      </div>
    );
  }

  // closed / draft
  return (
    <div className="flex items-center gap-1.5 flex-wrap" data-testid="tw-actions-closed">
      {state === "closed" && onGenerateRecap && sessionId && (
        <button
          type="button"
          className={baseBtn(true)}
          onClick={() => onGenerateRecap(sessionId)}
          data-testid="tw-action-recap"
        >
          生成复盘海报 🎨
        </button>
      )}
      {onGenerateLearningReport && (
        <button
          type="button"
          className={baseBtn(false)}
          onClick={onGenerateLearningReport}
          data-testid="tw-action-learning-report"
        >
          生成学习报告 📊
        </button>
      )}
      <button
        type="button"
        className={baseBtn(false)}
        onClick={onOpenLiveView}
        data-testid="tw-action-open-liveview"
      >
        打开 LiveView
      </button>
    </div>
  );
}

/* ====================== C: 今晚歌单（子组件） ====================== */

interface TonightQueueListProps {
  dark: boolean;
  /** active session id；为 null 时显示空态 */
  activeSession: LiveSessionSummary | null;
  onPlaySong: (
    songId: string,
    link: { sessionId: string; requestId: string; requesterName: string },
  ) => void;
}

function TonightQueueList({ dark, activeSession, onPlaySong }: TonightQueueListProps) {
  const { runWithToast } = useApiError();
  const [queue, setQueue] = useState<QueueEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<RequestFailure | null>(null);
  const [songsById, setSongsById] = useState<Record<string, string>>({});
  const [retryNonce, setRetryNonce] = useState(0);
  const cancelledRef = useRef(false);

  // 拉队列详情
  useEffect(() => {
    if (!activeSession) {
      setQueue([]);
      setError(null);
      setLoading(false);
      return;
    }
    cancelledRef.current = false;
    setLoading(true);
    setError(null);
    runWithToast(
      () => apiRequest<{ queue?: unknown[] }>(`/api/live-sessions/${activeSession.id}`),
      "今晚歌单加载失败",
    )
      .then((data) => {
        if (cancelledRef.current) return;
        const entries = (data?.queue ?? [])
          .map(asQueueEntry)
          .filter((e): e is QueueEntry => e !== null);
        const next = entries
          .filter((e) => !["sung", "skipped", "postponed", "cancelled", "duplicate_merged"].includes(e.state))
          .sort((a, b) => a.position - b.position)
          .slice(0, TOP_N);
        setQueue(next);
      })
      .catch((failure: RequestFailure | unknown) => {
        if (cancelledRef.current) return;
        setQueue([]);
        setError(toRequestFailure(failure));
      })
      .finally(() => {
        if (!cancelledRef.current) setLoading(false);
      });
    return () => {
      cancelledRef.current = true;
    };
  }, [activeSession?.id, retryNonce, runWithToast]);

  const handleRetry = useCallback(() => {
    setRetryNonce((n) => n + 1);
  }, []);

  // 拉歌名映射
  useEffect(() => {
    if (queue.length === 0) return;
    let cancelled = false;
    apiRequest<{ songs?: Array<{ id: string; title: string }> }>("/api/songs/list")
      .then((data) => {
        if (cancelled) return;
        const map: Record<string, string> = {};
        for (const s of data.songs ?? []) map[s.id] = s.title;
        setSongsById(map);
      })
      .catch(() => { /* 静默 */ });
    return () => { cancelled = true; };
  }, [queue]);

  if (!activeSession) {
    return (
      <p
        data-testid="tw-queue-empty"
        className={`text-[11px] ${dark ? "text-zinc-500" : "text-muted-foreground"}`}
      >
        还没有开始一场直播
      </p>
    );
  }
  if (loading) {
    return (
      <div className="flex items-center gap-2 py-1" data-testid="tw-queue-loading">
        <Spinner size="sm" tone="current" decorative label="加载今晚歌单" />
        <span className={`text-[11px] ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>加载中…</span>
      </div>
    );
  }
  if (error) {
    return (
      <ErrorBanner
        severity="warning"
        message={error.message}
        onRetry={handleRetry}
        data-testid="tw-queue-error"
      />
    );
  }
  if (queue.length === 0) {
    return (
      <p
        data-testid="tw-queue-empty-after-load"
        className={`text-[11px] ${dark ? "text-zinc-500" : "text-muted-foreground"}`}
      >
        本场队列空 — 在直播后台点「+ 主播加歌」
      </p>
    );
  }
  return (
    <ul className="space-y-1" data-testid="tw-queue-list">
      {queue.map((q) => (
        <li
          key={q.request_id}
          data-testid="tw-queue-item"
          data-request-id={q.request_id}
          className={`flex items-center gap-2 rounded-lg px-2 py-1.5 text-[12px] ${
            dark ? "hover:bg-zinc-800/60" : "hover:bg-muted"
          }`}
        >
          <span
            className={`font-mono tabular-nums w-5 text-right text-[10px] ${
              dark ? "text-zinc-500" : "text-muted-foreground"
            }`}
          >
            #{q.position}
          </span>
          <span className="flex-1 min-w-0 truncate" title={songsById[q.song_id] ?? q.song_id}>
            {songsById[q.song_id] ?? "…"}
          </span>
          <span className={`text-[10px] ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
            {QUEUE_STATE_LABEL[q.state] ?? q.state}
          </span>
          <button
            type="button"
            title="进入弹唱联动模式"
            aria-label="弹唱"
            data-testid="tw-queue-play"
            onClick={() =>
              onPlaySong(q.song_id, {
                sessionId: activeSession.id,
                requestId: q.request_id,
                requesterName: q.requester_name,
              })
            }
            className={`h-6 w-6 inline-flex items-center justify-center rounded-md border text-[10px] ${
              dark ? "border-zinc-700 hover:bg-zinc-700/40" : "border-border hover:bg-muted"
            }`}
          >▶</button>
        </li>
      ))}
    </ul>
  );
}

/* ====================== D: 演出准备检查（子组件） ====================== */

interface ReadinessCheckProps {
  dark: boolean;
  /** 今晚歌单里有意义参与检查的 song id 列表（去重 + 排除无效） */
  songIds: string[];
}

interface ReadinessReport {
  ready: number;
  total: number;
  /** 缺失项 song_id → 缺失字段数组 */
  missing: Array<{ songId: string; title: string; missing: string[] }>;
  /** 全部 4 项都齐的歌曲 id 集合（不必渲染） */
}

function evaluateReadiness(song: SongRecord): string[] {
  const missing: string[] = [];
  if (!song.tabs || song.tabs.trim() === "") missing.push("tabs");
  if ((!song.lyrics_plain || song.lyrics_plain.trim() === "") && (!song.lyrics_lrc || song.lyrics_lrc.trim() === "")) {
    missing.push("lyrics");
  }
  if (!song.audio_vocal_path) missing.push("audio");
  if (!song.key || song.key.trim() === "") missing.push("key");
  return missing;
}

function ReadinessCheck({ dark, songIds }: ReadinessCheckProps) {
  const [report, setReport] = useState<ReadinessReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<RequestFailure | null>(null);

  const fetchSongs = useCallback((signal?: AbortSignal) => {
    if (songIds.length === 0) {
      setReport({ ready: 0, total: 0, missing: [] });
      return Promise.resolve();
    }
    setLoading(true);
    setError(null);
    return apiRequest<{ songs?: unknown[] }>("/api/songs/list", { signal })
      .then((data) => {
        const all = (data.songs ?? []).map(asSongRecord).filter((s): s is SongRecord => s !== null);
        const target = all.filter((s) => songIds.includes(s.id));
        const missing: ReadinessReport["missing"] = [];
        let ready = 0;
        for (const s of target) {
          const m = evaluateReadiness(s);
          if (m.length === 0) ready += 1;
          else missing.push({ songId: s.id, title: s.title, missing: m });
        }
        setReport({ ready, total: target.length, missing });
      })
      .catch((reason: unknown) => {
        // 静默：失败时不显示 ErrorBanner，避免和 E 区竞争注意力（设计: 没数据时静默 no-op）
        if (reason && (reason as { name?: string }).name === "AbortError") return;
        setError(toRequestFailure(reason));
        setReport(null);
      })
      .finally(() => setLoading(false));
  }, [songIds]);

  useEffect(() => {
    const ac = new AbortController();
    void fetchSongs(ac.signal);
    return () => ac.abort();
  }, [fetchSongs]);

  // 没歌单时直接 no-op
  if (songIds.length === 0) {
    return (
      <p
        data-testid="tw-readiness-no-songs"
        className={`text-[11px] ${dark ? "text-zinc-500" : "text-muted-foreground"}`}
      >
        今晚没有歌可检查
      </p>
    );
  }

  if (loading && !report) {
    return (
      <div className="flex items-center gap-2 py-1" data-testid="tw-readiness-loading">
        <Spinner size="sm" tone="current" decorative label="检查准备" />
        <span className={`text-[11px] ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>检查准备中…</span>
      </div>
    );
  }

  if (error && !report) {
    return (
      <ErrorBanner
        severity="warning"
        message={error.message}
        onRetry={() => void fetchSongs()}
        data-testid="tw-readiness-error"
      />
    );
  }

  if (!report) return null;

  return (
    <div className="space-y-1.5" data-testid="tw-readiness">
      <p
        data-testid="tw-readiness-summary"
        data-ready={report.ready}
        data-total={report.total}
        className={`text-[11px] font-medium ${dark ? "text-zinc-300" : "text-foreground"}`}
      >
        <span className={report.ready === report.total ? "text-emerald-500" : "text-amber-500"}>
          {report.ready}/{report.total}
        </span>{" "}
        项就绪
        <span className={`ml-1 ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
          （曲谱 / 歌词 / 音频 / Key）
        </span>
      </p>
      {report.missing.length > 0 && (
        <ul className="space-y-0.5" data-testid="tw-readiness-missing">
          {report.missing.slice(0, 5).map((m) => (
            <li
              key={m.songId}
              data-testid="tw-readiness-missing-item"
              data-song-id={m.songId}
              className={`text-[11px] flex items-baseline gap-1.5 ${dark ? "text-zinc-400" : "text-muted-foreground"}`}
            >
              <span className="truncate flex-1" title={m.title}>{m.title}</span>
              <span className="text-[10px] tabular-nums">
                {m.missing.map((f) => READINESS_FIELDS_LOOKUP[f] ?? f).join(" / ")}
              </span>
            </li>
          ))}
          {report.missing.length > 5 && (
            <li className={`text-[10px] ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
              等 {report.missing.length - 5} 项…
            </li>
          )}
        </ul>
      )}
    </div>
  );
}

/* ====================== E: 推荐动作 + 复盘（子组件） ====================== */

interface TopActionsCardProps {
  dark: boolean;
  onCreatePosterFromTop: (songIds: string[]) => Promise<void>;
  onSwitchToStats: () => void;
}

function TopActionsCard({
  dark, onCreatePosterFromTop, onSwitchToStats,
}: TopActionsCardProps) {
  const [data, setData] = useState<TopSongsResponse | null>(null);
  const [error, setError] = useState<RequestFailure | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);

  const fetchTop = useCallback(() => {
    setLoading(true);
    setError(null);
    apiRequest<TopSongsResponse>(`/api/stats/top-songs?metric=request&limit=${3}`)
      .then((res) => {
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
      const songIds = (data.items ?? []).map((item) => item.song_id);
      await onCreatePosterFromTop(songIds);
    } finally {
      setCreating(false);
    }
  }, [data, onCreatePosterFromTop]);

  return (
    <div data-testid="tw-top-actions">
      {loading && (
        <div className="flex items-center gap-2 py-1" data-testid="tw-top-loading">
          <Spinner size="sm" tone="current" decorative label="加载 Top 歌曲" />
          <span className={`text-[11px] ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
            加载点歌热度中…
          </span>
        </div>
      )}

      {!loading && error && (
        <ErrorBanner
          severity="warning"
          message={error.message}
          onRetry={fetchTop}
          data-testid="tw-top-error"
        />
      )}

      {!loading && !error && data && (data.items?.length ?? 0) === 0 && (
        <EmptyState
          icon={<span aria-hidden="true">📊</span>}
          title="还没有点歌记录"
          description={data.note || "记录点歌后会出现在这里；点歌可在直播现场速查完成。"}
          secondaryLabel="去看统计"
          onSecondary={onSwitchToStats}
          inline
          dark={dark}
          data-testid="tw-top-empty"
        />
      )}

      {!loading && !error && data && (data.items?.length ?? 0) > 0 && (
        <div className="space-y-2" data-testid="tw-top-list">
          <ol className="space-y-1">
            {data.items!.map((item, idx) => (
              <li
                key={item.song_id}
                className={`flex items-baseline gap-2 text-[12px] leading-snug ${
                  dark ? "text-zinc-300" : "text-foreground"
                }`}
                data-testid="tw-top-item"
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
              data-testid="tw-top-create"
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
              data-testid="tw-top-stats-link"
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
    </div>
  );
}

/* ====================== 主组件 ====================== */

/**
 * 今晚工作台 — 工作台首屏主任务中心。
 *
 * 5 区结构：
 * - A. 状态区（StatusBadge + ActionBar）
 * - C. 今晚歌单（TonightQueueList）
 * - D. 演出准备检查（ReadinessCheck）
 * - E. 推荐动作 + 复盘（TopActionsCard）
 */
export default function TonightWorkbench({
  dark,
  onPlaySong,
  onOpenLiveView,
  onCreatePosterFromTop,
  onSwitchToStats,
  onGenerateRecap,
  onGenerateLearningReport,
  onOpenQuickView,
}: TonightWorkbenchProps) {
  // 拉 sessions
  // isEmpty 必须对任何返回值（null / undefined / 非数组）安全 — 防御 mock 测试 + 旧版本后端
  const sessionsReq = useLatestRequest<LiveSessionSummary[]>({
    isEmpty: (d) => !Array.isArray(d) || d.length === 0,
  });
  const { runWithToast } = useApiError();

  const refreshSessions = useCallback(
    (signal?: AbortSignal) =>
      apiRequest<LiveSessionSummary[]>("/api/live-sessions", { signal }),
    [],
  );

  useEffect(() => {
    void sessionsReq.run((signal) =>
      runWithToast(() => refreshSessions(signal), "今晚场次加载失败"),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // sessionsReq.data 在 mock 或异常路径下可能是非数组；统一 narrow 到 LiveSessionSummary[]
  const sessions: LiveSessionSummary[] = useMemo(() => {
    const data = sessionsReq.data;
    if (!Array.isArray(data)) return [];
    return data;
  }, [sessionsReq.data]);
  const sessionState: SessionState = useMemo(() => {
    if (sessionsReq.status === "loading" || sessionsReq.status === "idle") {
      // 仍在加载 — 不显示"无活跃"以免误报；直接返回 active 或 none
      // 这里取第一项的 state（如果有）；否则 none
      const first = sessions.find((s) => s.state === "active")
        ?? sessions.find((s) => s.state === "closed")
        ?? sessions.find((s) => s.state === "draft");
      if (first) {
        if (first.state === "active") return "active";
        if (first.state === "closed") return "closed";
        if (first.state === "draft") return "draft";
      }
      return "none";
    }
    const active = sessions.find((s) => s.state === "active");
    if (active) return "active";
    const closed = sessions.find((s) => s.state === "closed");
    if (closed) return "closed";
    const draft = sessions.find((s) => s.state === "draft");
    if (draft) return "draft";
    return "none";
  }, [sessionsReq.status, sessions]);

  const currentSession = useMemo(() => {
    if (sessionState === "active") return sessions.find((s) => s.state === "active") ?? null;
    if (sessionState === "closed") return sessions.find((s) => s.state === "closed") ?? null;
    if (sessionState === "draft") return sessions.find((s) => s.state === "draft") ?? null;
    return null;
  }, [sessionState, sessions]);

  // 用于 E 区 readiness 检查的 songId 列表
  // 目前简化：仅在 active session 时把当前 session queue 之外的"今晚点歌热度 top N"也加入；
  // 主信号仍是 currentSession.id 触发子组件内部去 /api/live-sessions/{id} 拿 queue。
  // 这里先不重复拉 queue；D 区用一种轻量方案：active 时由调用方传入目标歌单
  // — 此 prop 没在 spec 里。简化：把 sessionsReq 的所有 id 也算进来（不可行，没有 song id）。
  // 决策：D 区只对"本场未唱 queue"做检查；queue 的数据由 E 区处理：
  //  - 本组件通过 useEffect 拉一次本场 queue 拿到 songIds，传给 ReadinessCheck。
  const [readinessSongIds, setReadinessSongIds] = useState<string[]>([]);

  useEffect(() => {
    if (sessionState !== "active" || !currentSession) {
      setReadinessSongIds([]);
      return;
    }
    let cancelled = false;
    apiRequest<{ queue?: unknown[] }>(`/api/live-sessions/${currentSession.id}`)
      .then((data) => {
        if (cancelled) return;
        const ids = (data?.queue ?? [])
          .map(asQueueEntry)
          .filter((e): e is QueueEntry => e !== null)
          .map((e) => e.song_id);
        setReadinessSongIds(Array.from(new Set(ids)));
      })
      .catch(() => {
        if (!cancelled) setReadinessSongIds([]);
      });
    return () => { cancelled = true; };
  }, [sessionState, currentSession?.id]);

  return (
    <section
      data-testid="tonight-workbench"
      data-session-state={sessionState}
      className={`px-4 py-3 border-b ${dark ? "border-zinc-700/50" : "border-border"}`}
    >
      {/* ===== A: 状态徽标 + B: 动作区（同一行 wrap） ===== */}
      <div className="flex items-center justify-between gap-2 mb-2.5 flex-wrap">
        <StatusBadge
          dark={dark}
          state={sessionState}
          sessionTitle={currentSession?.title ?? ""}
          onClick={onOpenLiveView}
        />
        <ActionBar
          dark={dark}
          state={sessionState}
          sessionId={currentSession?.id ?? null}
          onOpenLiveView={onOpenLiveView}
          onOpenQuickView={onOpenQuickView}
          onGenerateRecap={onGenerateRecap}
          onGenerateLearningReport={onGenerateLearningReport}
        />
      </div>

      {/* sessions 整体错误（不会盖住子区） */}
      {sessionsReq.error && (
        <ErrorBanner
          severity="warning"
          message={sessionsReq.error.message}
          onRetry={() => void sessionsReq.run((signal) =>
            runWithToast(() => refreshSessions(signal), "今晚场次加载失败"))}
          data-testid="tw-sessions-error"
        />
      )}

      {/* ===== C: 今晚歌单区 ===== */}
      <div className="mt-2">
        <p className="eyebrow">今晚</p>
        <h3 className="text-sm font-semibold mb-1.5">
          {currentSession ? `歌单 · ${currentSession.title || "进行中"}` : "暂无进行中场次"}
        </h3>
        <TonightQueueList dark={dark} activeSession={currentSession} onPlaySong={onPlaySong} />
      </div>

      {/* ===== D: 演出准备检查区 ===== */}
      <div className="mt-3">
        <p className="eyebrow">演出准备</p>
        <h3 className="text-sm font-semibold mb-1.5">今晚歌单就绪度</h3>
        <ReadinessCheck dark={dark} songIds={readinessSongIds} />
      </div>

      {/* ===== E: 推荐动作 + 复盘区 ===== */}
      <div className="mt-3">
        <p className="eyebrow">基于数据</p>
        <h3 className="text-sm font-semibold mb-1.5">最常被点歌的 3 首 · 一键成海报</h3>
        <TopActionsCard
          dark={dark}
          onCreatePosterFromTop={onCreatePosterFromTop}
          onSwitchToStats={onSwitchToStats}
        />
      </div>
    </section>
  );
}
