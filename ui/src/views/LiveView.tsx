/// R2 直播管理视图。
///
/// 消费后端 /api/live-sessions* 7 端点：
/// - GET    /api/live-sessions              列表
/// - POST   /api/live-sessions              创建
/// - GET    /api/live-sessions/{id}         详情（队列 + 演唱记录）
/// - POST   /api/live-sessions/{id}/queue   入队（点歌人/权益/幂等 command_id）
/// - POST   /api/live-sessions/{id}/record  记录结果（sung/skipped/postponed/unknown/cancelled）
/// - POST   /api/live-sessions/{id}/close   关闭
/// - POST   /api/live-sessions/{id}/entitlements 授予权益
///
/// 设计：
/// - 左侧：会话列表 + 「开始一场」按钮
/// - 右侧：详情（待唱/已唱/未结）+ 入队/记录表单 + 「直播速查」链接
/// - 列表/详情独立加载，刷新只刷详情不刷整页
/// - 失败走 actionError 顶部条 + ApiClientError 还原
import { useEffect, useMemo, useState, useCallback } from "react";
import type { Song, SongsData } from "../types";
import AsyncStateNotice from "../components/AsyncStateNotice";
import { Icon } from "../icons";
import { ApiClientError, apiRequest } from "../api/client";
import type {
  LiveSessionCreateRequest,
  LiveSessionDetail,
  LiveSessionQueueRequest,
  LiveSessionQueueResponse,
  LiveSessionRecordRequest,
  LiveSessionRecordResponse,
  LiveSessionSummary,
} from "../api/generated";
import { toRequestFailure, useLatestRequest } from "../async/requestState";

/* ================== 类型 narrow helpers ================== */

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

interface PerformanceRecord {
  id: string;
  request_id: string;
  song_id: string;
  result: string;
  performed_at: string | null;
  recorded_at: string;
  reason: string;
}

function asQueueEntry(value: unknown): QueueEntry | null {
  if (!value || typeof value !== "object") return null;
  const v = value as Record<string, unknown>;
  if (typeof v.request_id !== "string" || typeof v.song_id !== "string") return null;
  return {
    request_id: v.request_id,
    song_id: v.song_id,
    position: typeof v.position === "number" ? v.position : 0,
    state: typeof v.state === "string" ? v.state : "queued",
    is_bumped: v.is_bumped === true,
    requester_name: typeof v.requester_name === "string" ? v.requester_name : "",
    entitlement_kind: typeof v.entitlement_kind === "string" ? v.entitlement_kind : "",
    inserted_at: typeof v.inserted_at === "string" ? v.inserted_at : "",
  };
}

function asPerformance(value: unknown): PerformanceRecord | null {
  if (!value || typeof value !== "object") return null;
  const v = value as Record<string, unknown>;
  if (typeof v.id !== "string" || typeof v.song_id !== "string") return null;
  return {
    id: v.id,
    request_id: typeof v.request_id === "string" ? v.request_id : "",
    song_id: v.song_id,
    result: typeof v.result === "string" ? v.result : "sung",
    performed_at: typeof v.performed_at === "string" ? v.performed_at : null,
    recorded_at: typeof v.recorded_at === "string" ? v.recorded_at : "",
    reason: typeof v.reason === "string" ? v.reason : "",
  };
}

/* ================== 状态显示 ================== */

const STATE_LABEL: Record<string, string> = {
  active: "进行中",
  closed: "已结束",
};

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

const RESULT_LABEL: Record<string, string> = {
  sung: "已唱",
  skipped: "跳过",
  postponed: "延期",
  unknown: "不会",
  cancelled: "取消",
  duplicate_merged: "合并",
};

const ENTITLEMENT_KIND_LABEL: Record<string, string> = {
  "": "普通",
  fan_join: "新粉团",
  member_daily: "会员",
  gift_exchange: "礼物",
  campaign: "活动",
  manual: "主播加歌",
  high_value_gift: "高价值",
};

function shortId(id: string): string {
  return id.length > 10 ? `${id.slice(0, 6)}…${id.slice(-3)}` : id;
}

function uuid(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  return [...bytes].map(b => b.toString(16).padStart(2, "0")).join("");
}

/* ================== 视图 ================== */

export default function LiveView({ dark }: { dark: boolean }) {
  const [sessions, setSessions] = useState<LiveSessionSummary[] | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [detail, setDetail] = useState<LiveSessionDetail | null>(null);
  const [songs, setSongs] = useState<Song[]>([]);
  const [actionError, setActionError] = useState("");
  const [actionNotice, setActionNotice] = useState("");

  const listRequest = useLatestRequest<LiveSessionSummary[]>({
    isEmpty: data => data.length === 0,
  });
  const listRun = listRequest.run;

  const refreshList = useCallback(async () => {
    const data = await listRun(signal =>
      apiRequest<LiveSessionSummary[]>("/api/live-sessions", { signal }));
    if (data) setSessions(data);
  }, [listRun]);

  const loadDetail = useCallback(async (id: string) => {
    try {
      const d = await apiRequest<LiveSessionDetail>(`/api/live-sessions/${id}`);
      setDetail(d);
    } catch (reason) {
      setDetail(null);
      setActionError(toRequestFailure(reason, "加载会话详情失败").message);
    }
  }, []);

  // 启动加载：会话列表 + 曲库（用于按 song_id 解析标题）
  useEffect(() => {
    refreshList();
    apiRequest<SongsData>("/api/songs/list")
      .then(d => setSongs(d.songs))
      .catch(() => setSongs([]));
    // 只在 mount 跑一次
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 选中的会话变化 → 拉详情
  useEffect(() => {
    if (activeId) {
      void loadDetail(activeId);
    } else {
      setDetail(null);
    }
  }, [activeId, loadDetail]);

  // 已选会话变更：列表里 session 状态变了（关闭）→ 自动刷新详情
  useEffect(() => {
    if (!sessions || !activeId) return;
    const summary = sessions.find(s => s.id === activeId);
    if (summary && detail && detail.state !== summary.state) {
      void loadDetail(activeId);
    }
  }, [sessions, activeId, detail, loadDetail]);

  const songsById = useMemo(() => {
    const map = new Map<string, Song>();
    for (const s of songs) map.set(s.id, s);
    return map;
  }, [songs]);

  const songTitle = (id: string): string => songsById.get(id)?.title ?? shortId(id);

  /* ---- 创建会话 ---- */
  const handleCreate = async () => {
    setActionError("");
    const payload: LiveSessionCreateRequest = { rule_version: "rv1", title: "" };
    try {
      const created = await apiRequest<LiveSessionSummary>("/api/live-sessions", {
        method: "POST", body: payload });
      await refreshList();
      setActiveId(created.id);
    } catch (reason) {
      setActionError(toRequestFailure(reason, "创建会话失败").message);
    }
  };

  /* ---- 关闭会话 ---- */
  const handleClose = async (id: string) => {
    setActionError("");
    try {
      await apiRequest(`/api/live-sessions/${id}/close`, { method: "POST", body: {} });
      await refreshList();
      await loadDetail(id);
    } catch (reason) {
      setActionError(toRequestFailure(reason, "关闭会话失败").message);
    }
  };

  /* ---- 入队 ---- */
  const handleQueue = async (
    songId: string, requesterName: string, note: string, entitlementKind: string,
  ) => {
    if (!activeId) return;
    setActionError("");
    setActionNotice("");
    const payload: LiveSessionQueueRequest = {
      requester_name: requesterName,
      requester_id: null,
      song_id: songId,
      entitlement_id: null,
      entitlement_kind: entitlementKind,
      note,
      command_id: `cmd_${uuid().replaceAll("-", "")}`,
    };
    try {
      const res: LiveSessionQueueResponse = await apiRequest(
        `/api/live-sessions/${activeId}/queue`, { method: "POST", body: payload },
      );
      if (res.duplicate_merged) {
        setActionNotice("同一人点过同一首，合并到已有请求");
      } else {
        setActionNotice(`已加入队列，位置 #${res.position}`);
      }
      await loadDetail(activeId);
    } catch (reason) {
      setActionError(toRequestFailure(reason, "入队失败").message);
    }
  };

  /* ---- 记录结果 ---- */
  const handleRecord = async (
    requestId: string, result: string, reason: string,
  ) => {
    if (!activeId) return;
    setActionError("");
    setActionNotice("");
    const payload: LiveSessionRecordRequest = {
      request_id: requestId, result, operator: "broadcaster", reason,
    };
    try {
      const res: LiveSessionRecordResponse = await apiRequest(
        `/api/live-sessions/${activeId}/record`, { method: "POST", body: payload },
      );
      const refundMsg = res.refunded ? "（已退还权益）" : "";
      setActionNotice(`已记录：${RESULT_LABEL[result] ?? result} ${refundMsg}`.trim());
      await loadDetail(activeId);
    } catch (reason) {
      setActionError(toRequestFailure(reason, "记录失败").message);
    }
  };

  const activeSession = useMemo(
    () => sessions?.find(s => s.id === activeId) ?? null,
    [sessions, activeId],
  );

  const isActive = activeSession?.state === "active";

  const queueEntries = useMemo<QueueEntry[]>(() => {
    if (!detail?.queue) return [];
    return detail.queue
      .map(asQueueEntry)
      .filter((e): e is QueueEntry => e !== null)
      .sort((a, b) => a.position - b.position);
  }, [detail]);

  // 队列中"下一个待处理"：queued/current 状态里 position 最小的
  const nextEntry = useMemo<QueueEntry | null>(() => {
    const candidates = queueEntries.filter(
      e => e.state === "queued" || e.state === "current",
    );
    return candidates[0] ?? null;
  }, [queueEntries]);

  // 快捷键：Space = sung, U = unknown, P = postponed, R = skipped
  // 仅在 LiveView 挂载且非输入控件聚焦时生效
  useEffect(() => {
    if (!isActive || !nextEntry) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.key === " " || e.key === "Spacebar") {
        e.preventDefault();
        handleRecord(nextEntry.request_id, "sung", "");
      } else if (e.key === "u" || e.key === "U") {
        e.preventDefault();
        handleRecord(nextEntry.request_id, "unknown", "");
      } else if (e.key === "p" || e.key === "P") {
        e.preventDefault();
        handleRecord(nextEntry.request_id, "postponed", "");
      } else if (e.key === "r" || e.key === "R") {
        e.preventDefault();
        handleRecord(nextEntry.request_id, "skipped", "");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // isActive/nextEntry 变化后重新挂监听
  }, [isActive, nextEntry]);

  const performances = useMemo<PerformanceRecord[]>(() => {
    if (!detail?.performances) return [];
    return detail.performances
      .map(asPerformance)
      .filter((p): p is PerformanceRecord => p !== null)
      .sort((a, b) => (b.recorded_at > a.recorded_at ? 1 : -1));
  }, [detail]);

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* ====== LEFT: 会话列表 ====== */}
      <aside
        className={`w-72 shrink-0 border-r flex flex-col overflow-hidden ${dark ? "border-zinc-700/50" : "border-border"}`}
        data-testid="live-sessions-list"
      >
        <div className="px-5 pt-5 pb-3 flex items-center justify-between">
          <div>
            <p className="eyebrow">直播</p>
            <h2 className="panel-title">会话</h2>
          </div>
          <button
            type="button"
            className="secondary-action"
            onClick={handleCreate}
            data-testid="live-create"
          >
            + 开始一场
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-3 pb-4 space-y-2">
          {listRequest.status === "loading" && !sessions
            ? <AsyncStateNotice kind="loading" label="会话" />
            : listRequest.status === "error" && !sessions
              ? <AsyncStateNotice
                  kind="error" label="会话"
                  error={listRequest.error} onRetry={refreshList}
                />
              : listRequest.status === "empty"
                ? <div className="panel-empty">还没有会话，点上方按钮开始一场。</div>
                : sessions?.map(s => (
                    <SessionCard
                      key={s.id}
                      session={s}
                      active={s.id === activeId}
                      onSelect={() => setActiveId(s.id)}
                      dark={dark}
                    />
                  ))}
        </div>
      </aside>

      {/* ====== RIGHT: 详情 ====== */}
      <main className="flex-1 overflow-y-auto p-6" data-testid="live-detail">
        {actionError && (
          <div className="mb-4 rounded-lg bg-red-500/10 px-3 py-2 text-sm text-red-500" role="alert">
            {actionError}
          </div>
        )}
        {actionNotice && (
          <div className="mb-4 rounded-lg bg-emerald-500/10 px-3 py-2 text-sm text-emerald-600 dark:text-emerald-400" role="status">
            {actionNotice}
          </div>
        )}

        {!activeSession
          ? <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
              请在左侧选择一场直播，或开始新场。
            </div>
          : (
            <SessionDetail
              session={activeSession}
              detail={detail}
              queue={queueEntries}
              performances={performances}
              isActive={isActive}
              songTitle={songTitle}
              onClose={() => handleClose(activeSession.id)}
              onQueue={handleQueue}
              onRecord={handleRecord}
              onRefresh={() => loadDetail(activeSession.id)}
            />
          )}
      </main>
    </div>
  );
}

/* ================== 子组件 ================== */

function SessionCard({ session, active, onSelect, dark }: {
  session: LiveSessionSummary;
  active: boolean;
  onSelect: () => void;
  dark: boolean;
}) {
  const stateColor = session.state === "active"
    ? "var(--color-primary)" : "var(--color-muted-foreground)";
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={active ? "true" : undefined}
      data-testid={`live-session-${session.id}`}
      className={`w-full text-left rounded-xl border px-3 py-2.5 transition-all ${active
        ? "border-primary bg-primary-soft/40"
        : (dark ? "border-zinc-700 hover:border-zinc-500" : "border-border hover:border-muted-foreground/30")
      }`}
    >
      <div className="flex items-center gap-2">
        <span className="inline-block h-2 w-2 rounded-full" style={{ background: stateColor }} />
        <span className="text-sm font-medium truncate">
          {session.title || `会话 ${shortId(session.id)}`}
        </span>
      </div>
      <div className="mt-1 flex items-center gap-2 text-[11px] text-muted-foreground">
        <span>{STATE_LABEL[session.state] ?? session.state}</span>
        <span>·</span>
        <span>队列 {session.queue_size ?? 0}</span>
        <span>·</span>
        <span>{shortId(session.id)}</span>
      </div>
    </button>
  );
}

function SessionDetail({
  session, detail, queue, performances, isActive, songTitle,
  onClose, onQueue, onRecord, onRefresh,
}: {
  session: LiveSessionSummary;
  detail: LiveSessionDetail | null;
  queue: QueueEntry[];
  performances: PerformanceRecord[];
  isActive: boolean;
  songTitle: (id: string) => string;
  onClose: () => void;
  onQueue: (songId: string, requesterName: string, note: string, entitlementKind: string) => void;
  onRecord: (requestId: string, result: string, reason: string) => void;
  onRefresh: () => void;
}) {
  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-semibold">
          {session.title || `会话 ${shortId(session.id)}`}
        </h1>
        <span className="text-xs text-muted-foreground">·</span>
        <span className="text-xs text-muted-foreground">
          {STATE_LABEL[session.state] ?? session.state} · {shortId(session.id)}
        </span>
        <div className="ml-auto flex items-center gap-2">
          <button type="button" className="secondary-action" onClick={onRefresh}>
            刷新
          </button>
          <a href="/quick" target="_blank" rel="noreferrer" className="secondary-action">
            直播速查 ↗
          </a>
          {isActive && (
            <button type="button" className="secondary-action" onClick={onClose}>
              结束场次
            </button>
          )}
        </div>
      </div>

      <QueueForm
        isActive={isActive}
        onQueue={onQueue}
        songs={detail?.queue ? extractSongOptions(detail.queue) : []}
      />

      {isActive && (
        <p className="text-[11px] text-muted-foreground">
          快捷键（仅队列有「下一个」时生效）：<kbd className="px-1.5 py-0.5 rounded border border-border bg-muted">Space</kbd> 已唱 ·
          <kbd className="px-1.5 py-0.5 rounded border border-border bg-muted">U</kbd> 不会 ·
          <kbd className="px-1.5 py-0.5 rounded border border-border bg-muted">P</kbd> 延期 ·
          <kbd className="px-1.5 py-0.5 rounded border border-border bg-muted">R</kbd> 跳过
        </p>
      )}

      <section>
        <h2 className="eyebrow mb-2">待唱 ({queue.length})</h2>
        {queue.length === 0
          ? <div className="panel-empty">队列空</div>
          : <ul className="space-y-2">
              {queue.map(q => (
                <QueueRow
                  key={q.request_id}
                  entry={q}
                  songTitle={songTitle(q.song_id)}
                  onRecord={isActive ? onRecord : undefined}
                />
              ))}
            </ul>}
      </section>

      <section>
        <h2 className="eyebrow mb-2">已唱 ({performances.length})</h2>
        {performances.length === 0
          ? <div className="panel-empty">本场暂无演唱记录</div>
          : <ul className="space-y-1.5">
              {performances.map(p => (
                <li
                  key={p.id}
                  className="flex items-center gap-3 text-sm rounded-lg border border-border/40 px-3 py-2"
                >
                  <span className="font-medium">{songTitle(p.song_id)}</span>
                  <span className="text-xs text-muted-foreground">
                    {RESULT_LABEL[p.result] ?? p.result}
                  </span>
                  {p.reason && (
                    <span className="text-xs text-muted-foreground truncate">
                      · {p.reason}
                    </span>
                  )}
                  <span className="ml-auto text-[11px] text-muted-foreground tabular-nums">
                    {p.recorded_at.slice(11, 19)}
                  </span>
                </li>
              ))}
            </ul>}
      </section>
    </div>
  );
}

function extractSongOptions(_queue: unknown[]): never[] {
  // 占位：当前从 songs 列表构造（由 LiveView 传入更好）。这里返回空。
  return [];
}

function QueueForm({
  isActive, onQueue, songs: _songs,
}: {
  isActive: boolean;
  onQueue: (songId: string, requesterName: string, note: string, entitlementKind: string) => void;
  songs: never[];
}) {
  const [songId, setSongId] = useState("");
  const [requesterName, setRequesterName] = useState("");
  const [note, setNote] = useState("");
  const [kind, setKind] = useState("");

  if (!isActive) {
    return (
      <div className="panel-empty">本场已结束；不能新增点歌。</div>
    );
  }

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!songId.trim() || !requesterName.trim()) return;
    onQueue(songId.trim(), requesterName.trim(), note.trim(), kind);
    setSongId("");
    setNote("");
  };

  return (
    <form onSubmit={submit} className="rounded-xl border border-border p-4 space-y-3">
      <p className="eyebrow">入队</p>
      <div className="grid grid-cols-2 gap-3">
        <label className="space-y-1">
          <span className="text-xs text-muted-foreground">song_id</span>
          <input
            type="text" value={songId} onChange={e => setSongId(e.target.value)}
            placeholder="例如 song_xxx"
            required
            data-testid="live-queue-song"
            className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm"
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs text-muted-foreground">点歌人</span>
          <input
            type="text" value={requesterName} onChange={e => setRequesterName(e.target.value)}
            placeholder="昵称 / 显示名" required
            data-testid="live-queue-name"
            className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm"
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs text-muted-foreground">权益</span>
          <select
            value={kind} onChange={e => setKind(e.target.value)}
            data-testid="live-queue-kind"
            className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm"
          >
            <option value="">普通（队尾）</option>
            <option value="fan_join">新粉团</option>
            <option value="member_daily">会员</option>
            <option value="gift_exchange">礼物</option>
            <option value="manual">主播加歌</option>
          </select>
        </label>
        <label className="space-y-1">
          <span className="text-xs text-muted-foreground">备注（可选）</span>
          <input
            type="text" value={note} onChange={e => setNote(e.target.value)}
            placeholder="如：要降调"
            className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm"
          />
        </label>
      </div>
      <div className="flex items-center gap-2">
        <button type="submit" className="primary-action" data-testid="live-queue-submit">
          {Icon.play} 加入队列
        </button>
        <span className="text-[11px] text-muted-foreground">
          同一 (song, requester) 自动合并，command_id 自动生成。
        </span>
      </div>
    </form>
  );
}

function QueueRow({
  entry, songTitle, onRecord,
}: {
  entry: QueueEntry;
  songTitle: string;
  onRecord?: (requestId: string, result: string, reason: string) => void;
}) {
  return (
    <li className="flex items-center gap-3 rounded-xl border border-border/60 bg-card px-3 py-2.5">
      <span className="text-sm font-mono tabular-nums w-6 text-right text-muted-foreground">
        #{entry.position}
      </span>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium truncate">{songTitle}</div>
        <div className="text-[11px] text-muted-foreground flex gap-2">
          <span>{entry.requester_name || "—"}</span>
          {entry.entitlement_kind && (
            <span className="px-1.5 rounded bg-muted">
              {ENTITLEMENT_KIND_LABEL[entry.entitlement_kind] ?? entry.entitlement_kind}
            </span>
          )}
          {entry.is_bumped && <span className="text-amber-600">插队</span>}
        </div>
      </div>
      <span className="text-[11px] text-muted-foreground">
        {QUEUE_STATE_LABEL[entry.state] ?? entry.state}
      </span>
      {onRecord && (
        <div className="flex items-center gap-1">
          <button
            type="button" title="已唱" aria-label="已唱"
            onClick={() => onRecord(entry.request_id, "sung", "")}
            className="h-7 w-7 inline-flex items-center justify-center rounded-md border border-border hover:bg-muted"
          >{Icon.check}</button>
          <button
            type="button" title="延期" aria-label="延期"
            onClick={() => onRecord(entry.request_id, "postponed", "")}
            className="h-7 w-7 inline-flex items-center justify-center rounded-md border border-border hover:bg-muted text-xs"
          >P</button>
          <button
            type="button" title="不会唱" aria-label="不会唱"
            onClick={() => onRecord(entry.request_id, "unknown", "")}
            className="h-7 w-7 inline-flex items-center justify-center rounded-md border border-border hover:bg-muted text-xs"
          >U</button>
          <button
            type="button" title="跳过" aria-label="跳过"
            onClick={() => onRecord(entry.request_id, "skipped", "")}
            className="h-7 w-7 inline-flex items-center justify-center rounded-md border border-border hover:bg-muted text-xs"
          >⤳</button>
        </div>
      )}
    </li>
  );
}
