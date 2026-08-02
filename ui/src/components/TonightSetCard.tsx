/// R9.5 今晚歌单卡片
///
/// 工作台首屏左栏顶部显示：当前活跃 LiveSession 队列（Top 5） + 弹唱按钮。
/// - 拉取 /api/live-sessions 找到 state=active 的会话（取最近一个）
/// - 拉取 /api/live-sessions/{id} 拿到 queue
/// - 每项有 ▶ 弹唱按钮 → 调 onPlaySong 联动 R8.2
/// - "查看完整" 按钮 → 调 onOpenLiveView
///
/// 设计：复用 LiveView 的 asQueueEntry / QUEUE_STATE_LABEL；不重复实现。
import { useCallback, useEffect, useMemo, useState } from "react";
import { apiRequest } from "../api/client";
import { asString, asNumber, asBoolean, asRecord } from "../lib/narrow";
import { useLatestRequest, toRequestFailure } from "../async/requestState";

export interface TonightSetCardProps {
  dark: boolean;
  onPlaySong: (songId: string, link: { sessionId: string; requestId: string; requesterName: string }) => void;
  onOpenLiveView: () => void;
}

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

const TOP_N = 5;

export default function TonightSetCard({ dark, onPlaySong, onOpenLiveView }: TonightSetCardProps) {
  // 拉活跃 session 列表
  const sessionsReq = useLatestRequest<LiveSessionSummary[]>({
    isEmpty: (d) => d.length === 0,
  });
  const refreshSessions = useCallback((signal?: AbortSignal) =>
    apiRequest<LiveSessionSummary[]>("/api/live-sessions", { signal }),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  []);
  const [activeSession, setActiveSession] = useState<LiveSessionSummary | null>(null);
  const [queue, setQueue] = useState<QueueEntry[]>([]);
  const [error, setError] = useState("");
  const [songsById, setSongsById] = useState<Record<string, string>>({});

  // 拉活跃 sessions
  useEffect(() => {
    const ac = new AbortController();
    sessionsReq.run((signal) => refreshSessions(signal))
      .then((data) => {
        if (data) {
          // 找最近一个 active session
          const active = data.find((s) => s.state === "active");
          setActiveSession(active ?? null);
        }
      })
      .catch((reason) => {
        if (reason?.name !== "AbortError") {
          setError(toRequestFailure(reason, "加载会话失败").message);
        }
      });
    return () => ac.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 拉活跃 session 详情（队列）
  useEffect(() => {
    if (!activeSession) {
      setQueue([]);
      return;
    }
    let cancelled = false;
    apiRequest<{ queue?: unknown[] }>(`/api/live-sessions/${activeSession.id}`)
      .then((data) => {
        if (cancelled) return;
        const entries = (data?.queue ?? [])
          .map(asQueueEntry)
          .filter((e): e is QueueEntry => e !== null);
        // 取未唱的 Top N（按 position）
        const next = entries
          .filter((e) => !["sung", "skipped", "postponed", "cancelled", "duplicate_merged"].includes(e.state))
          .sort((a, b) => a.position - b.position)
          .slice(0, TOP_N);
        setQueue(next);
      })
      .catch(() => {
        if (!cancelled) setQueue([]);
      });
    return () => { cancelled = true; };
  }, [activeSession?.id]);

  // 拉歌曲名（用于显示）
  useEffect(() => {
    if (queue.length === 0) return;
    const songIds = Array.from(new Set(queue.map((q) => q.song_id)));
    apiRequest<{ songs: Array<{ id: string; title: string }> }>("/api/songs/list")
      .then((data) => {
        const map: Record<string, string> = {};
        for (const s of data.songs ?? []) map[s.id] = s.title;
        setSongsById(map);
      })
      .catch(() => { /* 静默 */ });
  }, [queue]);

  const isEmpty = useMemo(
    () => sessionsReq.status === "ready" && !activeSession,
    [sessionsReq.status, activeSession],
  );

  return (
    <section
      data-testid="tonight-set-card"
      data-session-id={activeSession?.id ?? ""}
      className={`px-4 py-3 border-b ${dark ? "border-zinc-700/50" : "border-border"}`}
    >
      <div className="flex items-center justify-between mb-2">
        <div>
          <p className="eyebrow">今晚</p>
          <h3 className="text-sm font-semibold">
            {activeSession ? `歌单 · ${activeSession.title || "进行中"}` : "暂无进行中场次"}
          </h3>
        </div>
        <button
          type="button"
          className="secondary-action text-[10px]"
          onClick={onOpenLiveView}
          data-testid="tonight-set-open"
        >
          {activeSession ? "完整队列 →" : "直播后台 →"}
        </button>
      </div>

      {error && (
        <p className={`text-[11px] mb-1 ${dark ? "text-red-400" : "text-red-600"}`}>{error}</p>
      )}

      {isEmpty ? (
        <p className={`text-[11px] ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
          还没有开始一场直播
        </p>
      ) : sessionsReq.status === "loading" && !activeSession ? (
        <p className={`text-[11px] ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>加载中…</p>
      ) : queue.length === 0 ? (
        <p className={`text-[11px] ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
          本场队列空 — 在直播后台点「+ 主播加歌」
        </p>
      ) : (
        <ul className="space-y-1" data-testid="tonight-set-list">
          {queue.map((q) => (
            <li
              key={q.request_id}
              data-testid="tonight-set-item"
              data-request-id={q.request_id}
              className={`flex items-center gap-2 rounded-lg px-2 py-1.5 text-[12px] ${
                dark ? "hover:bg-zinc-800/60" : "hover:bg-muted"
              }`}
            >
              <span className={`font-mono tabular-nums w-5 text-right text-[10px] ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
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
                data-testid="tonight-set-play"
                onClick={() => onPlaySong(q.song_id, {
                  sessionId: activeSession!.id,
                  requestId: q.request_id,
                  requesterName: q.requester_name,
                })}
                className="h-6 w-6 inline-flex items-center justify-center rounded-md border border-border hover:bg-muted text-[10px]"
              >▶</button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
