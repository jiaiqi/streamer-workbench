/// R2 直播后台管理视图。
///
/// 用途：**会前 + 会后** 的会话查看 / 记录 / 修正。
/// 不用于直播中点歌或记录 — 那是 QuickView (置顶速查窗) 的职责。
///
/// 范围（v1）：
/// - 会话列表 + 详情（队列 / 演唱历史）
/// - 「主播加歌」按钮：从曲库挑歌直接入队，entitlement_kind=manual
///   （不消耗权益、不需主播确认；v1 简化，其他权益类型在 QuickView 流程里）
/// - 手动覆盖 record：修正 QuickView 误操作或补录
/// - 关闭会话
///
/// R8.2 联动：队列项行尾加「弹唱」按钮 → 调 onPlaySong(songId, { sessionId, requestId, requesterName })
///   把主播带入 PlayView 联动模式；audio ended 自动 mark sung 回到 LiveView。
///
/// 不在本视图做（避免职责重复）：
/// - 搜歌入队、权益授予、断网补报 → QuickView
/// - 整体快捷键（Space/U/P/R）→ QuickView 内做
import { useEffect, useMemo, useState, useCallback, useRef } from "react";
import type { Song, SongsData } from "../types";
import AsyncStateNotice from "../components/AsyncStateNotice";
import { Icon } from "../icons";
import { apiRequest } from "../api/client";
import type {
  LiveSessionDetail,
  LiveSessionQueueResponse,
  LiveSessionRecordResponse,
  LiveSessionSummary,
} from "../api/generated";
import { useLatestRequest, type RequestFailure } from "../async/requestState";
import { useApiError } from "../async/useApiError";
import { openQuickView, openLivePoster, isElectron } from "../electron-bridge";
import { asRecord, asString, asNumber, asBoolean } from "../lib/narrow";
import StatusBadge from "../components/StatusBadge";
import ExportLogPanel from "../posters/ExportLogPanel";

/* ================== 类型 narrow helpers (R4.1.7 改用 lib/narrow) ================== */

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

function asPerformance(value: unknown): PerformanceRecord | null {
  const v = asRecord(value);
  if (!v) return null;
  const id = asString(v, "id");
  const song_id = asString(v, "song_id");
  if (!id || !song_id) return null;
  return {
    id,
    request_id: asString(v, "request_id") ?? "",
    song_id,
    result: asString(v, "result") ?? "sung",
    performed_at: asString(v, "performed_at") ?? null,
    recorded_at: asString(v, "recorded_at") ?? "",
    reason: asString(v, "reason") ?? "",
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

export default function LiveView({
  dark,
  onPlaySong,
}: {
  dark: boolean;
  /** R8.2: 弹唱联动 — 队列项行尾「弹唱」按钮触发；App.tsx 接管路由。 */
  onPlaySong?: (songId: string, link: { sessionId: string; requestId: string; requesterName: string }) => void;
}) {
  // M2.6 错误全局 toast 化 — 失败时自动 toast.error
  const { runWithToast } = useApiError();
  const [sessions, setSessions] = useState<LiveSessionSummary[] | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [detail, setDetail] = useState<LiveSessionDetail | null>(null);
  const [songs, setSongs] = useState<Song[]>([]);
  const [actionError, setActionError] = useState("");
  const [actionNotice, setActionNotice] = useState("");
  const [manualPickerOpen, setManualPickerOpen] = useState(false);
  // R4.0: 导出复盘海报的 loading 状态（避免重复点击 + spinner 反馈）
  const [posterLoading, setPosterLoading] = useState(false);

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
      const d = await runWithToast(
        () => apiRequest<LiveSessionDetail>(`/api/live-sessions/${id}`),
        "加载会话详情失败",
      );
      setDetail(d);
    } catch (failure) {
      setDetail(null);
      setActionError((failure as RequestFailure).message);
    }
  }, [runWithToast]);

  // 启动加载：会话列表 + 曲库（手动加歌需要选歌）
  useEffect(() => {
    refreshList();
    apiRequest<SongsData>("/api/songs/list")
      .then(d => setSongs(d.songs))
      .catch(() => setSongs([]));
    // 只在 mount 跑一次（listRun 是稳定引用）
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
    try {
      const created = await runWithToast(
        () => apiRequest<LiveSessionSummary>("/api/live-sessions", {
          method: "POST", body: { rule_version: "rv1", title: "" } }),
        "创建会话失败",
      );
      await refreshList();
      setActiveId(created.id);
    } catch (failure) {
      setActionError((failure as RequestFailure).message);
    }
  };

  /* ---- 关闭会话 ---- */
  const handleClose = async (id: string) => {
    setActionError("");
    try {
      await runWithToast(
        () => apiRequest(`/api/live-sessions/${id}/close`, { method: "POST", body: {} }),
        "关闭会话失败",
      );
      await refreshList();
      await loadDetail(id);
    } catch (failure) {
      setActionError((failure as RequestFailure).message);
    }
  };

  /* ---- 主播加歌：曲库选歌 → 入队（manual 模式） ---- */
  const handleManualQueue = async (songId: string) => {
    if (!activeId) return;
    setActionError("");
    setActionNotice("");
    try {
      const res: LiveSessionQueueResponse = await runWithToast(
        () => apiRequest(
          `/api/live-sessions/${activeId}/queue`, {
            method: "POST",
            body: {
              requester_name: "主播",
              requester_id: null,
              song_id: songId,
              entitlement_id: null,
              entitlement_kind: "manual",
              note: "主播后台加歌",
              command_id: `cmd_${uuid().replaceAll("-", "")}`,
            },
          },
        ),
        "加歌失败",
      );
      setActionNotice(res.duplicate_merged
        ? "同一人点过同一首，合并到已有请求"
        : `已加入队列，位置 #${res.position}`);
      setManualPickerOpen(false);
      await loadDetail(activeId);
    } catch (failure) {
      setActionError((failure as RequestFailure).message);
    }
  };

  /* ---- 手动覆盖 record（修正 QuickView 误操作或补录） ---- */
  const handleRecord = async (requestId: string, result: string) => {
    if (!activeId) return;
    setActionError("");
    setActionNotice("");
    try {
      const res: LiveSessionRecordResponse = await runWithToast(
        () => apiRequest(
          `/api/live-sessions/${activeId}/record`, {
            method: "POST",
            body: { request_id: requestId, result, operator: "broadcaster", reason: "后台手动覆盖" },
          },
        ),
        "记录失败",
      );
      const refundMsg = res.refunded ? "（已退还权益）" : "";
      setActionNotice(`已记录：${RESULT_LABEL[result] ?? result} ${refundMsg}`.trim());
      await loadDetail(activeId);
    } catch (failure) {
      setActionError((failure as RequestFailure).message);
    }
  };

  /* ---- R4.0: 导出复盘海报（带 loading 反馈） ---- */
  const handleExportPoster = useCallback(async (sessionId: string) => {
    if (posterLoading) return;
    setPosterLoading(true);
    setActionError("");
    setActionNotice("");
    try {
      const res = await runWithToast(
        () => openLivePoster(sessionId),
        "导出复盘海报失败",
      );
      if (res.ok) {
        if (res.path) setActionNotice(`已保存到 ${res.path}`);
        else if (res.method === "download") setActionNotice("已下载海报");
      } else if (!res.cancelled) {
        setActionError(res.error ?? "导出失败");
      }
      // cancelled: 静默
    } catch (failure) {
      console.error("导出复盘海报失败", failure);
      setActionError((failure as RequestFailure).message);
    } finally {
      setPosterLoading(false);
    }
  }, [posterLoading, runWithToast]);

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

  // P0 桌面平台特性：把待唱数推到 window 供主进程 dock badge
  useEffect(() => {
    window.__liveQueueCount = queueEntries.length;
    window.dispatchEvent(new Event("live:queueCount"));
  }, [queueEntries.length]);
  }, [detail]);

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
                      dark={dark}
                      onSelect={() => setActiveId(s.id)}
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
              songs={songs}
              dark={dark}
              onClose={() => handleClose(activeSession.id)}
              onRecord={handleRecord}
              onRefresh={() => loadDetail(activeSession.id)}
              onOpenManualPicker={() => setManualPickerOpen(true)}
              onExportPoster={() => handleExportPoster(activeSession.id)}
              onPlaySong={onPlaySong}
              posterLoading={posterLoading}
            />
          )}

        {manualPickerOpen && activeId && isActive && (
          <ManualSongPicker
            songs={songs}
            onPick={handleManualQueue}
            onClose={() => setManualPickerOpen(false)}
          />
        )}
      </main>
    </div>
  );
}

/* ================== 子组件 ================== */

function SessionCard({ session, active, dark, onSelect }: {
  session: LiveSessionSummary;
  dark: boolean;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={active ? "true" : undefined}
      data-testid={`live-session-${session.id}`}
      className={`w-full text-left rounded-xl border px-3 py-2.5 transition-all ${active
        ? "border-primary bg-primary-soft/40"
        : "border-border hover:border-muted-foreground/30"
      }`}
    >
      <div className="flex items-center gap-2">
        <StatusBadge
          kind={session.state === "active" ? "active" : "closed"}
          label={STATE_LABEL[session.state] ?? session.state}
          compact
          dark={dark}
        />
        <span className="text-sm font-medium truncate">
          {session.title || `会话 ${shortId(session.id)}`}
        </span>
      </div>
      <div className="mt-1 flex items-center gap-2 text-[11px] text-muted-foreground">
        <span>队列 {session.queue_size ?? 0}</span>
        <span>·</span>
        <span>{shortId(session.id)}</span>
      </div>
    </button>
  );
}

function SessionDetail({
  session, detail, queue, performances, isActive, songTitle,
  songs, dark, onClose, onRecord, onRefresh, onOpenManualPicker,
  onExportPoster, onPlaySong,
  posterLoading,
}: {
  session: LiveSessionSummary;
  dark: boolean;
  detail: LiveSessionDetail | null;
  queue: QueueEntry[];
  performances: PerformanceRecord[];
  isActive: boolean;
  songTitle: (id: string) => string;
  songs: Song[];
  onClose: () => void;
  onRecord: (requestId: string, result: string) => void;
  onRefresh: () => void;
  onOpenManualPicker: () => void;
  /** R4.0: 触发复盘海报导出；loading 状态由父组件管理。 */
  onExportPoster: () => Promise<void> | void;
  /** R8.2: 弹唱联动 — 队列项「弹唱」按钮触发。 */
  onPlaySong?: (songId: string, link: { sessionId: string; requestId: string; requesterName: string }) => void;
  /** R4.0: 导出进行中（用于 disable 按钮 + 显示 spinner）。 */
  posterLoading: boolean;
}) {
  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-semibold">
          {session.title || `会话 ${shortId(session.id)}`}
        </h1>
        <span className="text-xs text-muted-foreground">·</span>
        <span className="text-xs text-muted-foreground">
          {shortId(session.id)}
        </span>
        <div className="ml-auto flex items-center gap-2">
          <button type="button" className="secondary-action" onClick={onRefresh}>
            刷新
          </button>
          {/* R2.5: 导出直播复盘海报（live-set 布局）R4.0 加 loading 反馈 */}
          <button
            type="button"
            className="secondary-action"
            data-testid="live-export-poster"
            data-loading={posterLoading ? "true" : "false"}
            disabled={posterLoading}
            aria-busy={posterLoading}
            title="把这场直播生成 live-set 复盘海报"
            onClick={() => { void onExportPoster(); }}
          >
            {posterLoading ? (
              <>
                <span className="inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin align-middle" />
                <span className="ml-1.5">渲染中…</span>
              </>
            ) : "复盘海报"}
          </button>
          <a
            href={`/quick?session=${session.id}`}
            target="_blank"
            rel="noreferrer"
            className="secondary-action"
            data-testid="live-quickview-link"
            onClick={(e) => openQuickView(session.id, e)}
          >
            直播速查 {isElectron() ? "▣" : "↗"}
          </a>
          {isActive && (
            <>
              <button
                type="button"
                className="secondary-action"
                onClick={onOpenManualPicker}
                data-testid="live-manual-pick"
              >
                + 主播加歌
              </button>
              <button type="button" className="secondary-action" onClick={onClose}>
                结束场次
              </button>
            </>
          )}
        </div>
      </div>

      <p className="text-[11px] text-muted-foreground">
        本视图是后台管理面板。直播中的点歌 / 速查 / 快捷键请打开
        <a
          href="/quick"
          target="_blank"
          rel="noreferrer"
          className="underline"
          onClick={(e) => openQuickView(undefined, e)}
        > 直播速查 </a>。
      </p>

      {/* R4.2.3: 最近导出 — 复盘海报历史 */}
      <section>
        <h2 className="eyebrow mb-2">最近的复盘海报</h2>
        <ExportLogPanel
          dark={dark}
          limit={3}
          kindFilter="live-poster"
          title=""
        />
      </section>

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
                  onPlaySong={isActive ? onPlaySong : undefined}
                  sessionId={session.id}
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

function QueueRow({
  entry, songTitle, onRecord, onPlaySong, sessionId,
}: {
  entry: QueueEntry;
  songTitle: string;
  onRecord?: (requestId: string, result: string) => void;
  /** R8.2: 弹唱联动 — 行内 ▶ 按钮触发；传会话 id 给 PlayView 联动。 */
  onPlaySong?: (songId: string, link: { sessionId: string; requestId: string; requesterName: string }) => void;
  /** R8.2: 联动需要的 sessionId（父组件传入）。 */
  sessionId: string;
}) {
  // R8.2: 弹唱按钮仅在未唱项上可用（sung/skipped/postponed/cancelled 都不弹）
  const canPlay = !["sung", "skipped", "postponed", "cancelled", "duplicate_merged"].includes(entry.state);
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
      {/* R8.2: 弹唱按钮 — 未唱项才有 */}
      {onPlaySong && canPlay && (
        <button
          type="button"
          title="进入弹唱联动模式（弹完自动标记「已唱」）"
          aria-label="弹唱"
          data-testid="live-queue-play"
          data-request-id={entry.request_id}
          data-song-id={entry.song_id}
          onClick={() => onPlaySong(entry.song_id, {
            sessionId,
            requestId: entry.request_id,
            requesterName: entry.requester_name,
          })}
          className="h-7 w-7 inline-flex items-center justify-center rounded-md border border-border hover:bg-muted text-xs"
        >▶</button>
      )}
      {onRecord && (
        <div className="flex items-center gap-1">
          <button
            type="button" title="已唱（手动覆盖）" aria-label="已唱"
            onClick={() => onRecord(entry.request_id, "sung")}
            className="h-7 w-7 inline-flex items-center justify-center rounded-md border border-border hover:bg-muted"
          >{Icon.check}</button>
          <button
            type="button" title="延期" aria-label="延期"
            onClick={() => onRecord(entry.request_id, "postponed")}
            className="h-7 w-7 inline-flex items-center justify-center rounded-md border border-border hover:bg-muted text-xs"
          >P</button>
          <button
            type="button" title="不会唱" aria-label="不会唱"
            onClick={() => onRecord(entry.request_id, "unknown")}
            className="h-7 w-7 inline-flex items-center justify-center rounded-md border border-border hover:bg-muted text-xs"
          >U</button>
          <button
            type="button" title="跳过" aria-label="跳过"
            onClick={() => onRecord(entry.request_id, "skipped")}
            className="h-7 w-7 inline-flex items-center justify-center rounded-md border border-border hover:bg-muted text-xs"
          >⤳</button>
        </div>
      )}
    </li>
  );
}

function ManualSongPicker({
  songs, onPick, onClose,
}: {
  songs: Song[];
  onPick: (songId: string) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { inputRef.current?.focus(); }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return songs.slice(0, 50);
    return songs.filter(s =>
      s.title.toLowerCase().includes(q) ||
      s.artists.join(" ").toLowerCase().includes(q) ||
      (s.pinyin ?? "").toLowerCase().includes(q),
    ).slice(0, 50);
  }, [songs, query]);

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-label="主播加歌"
      data-testid="live-manual-picker"
      onClick={onClose}
    >
      <div
        className="bg-background rounded-2xl shadow-2xl w-full max-w-md max-h-[80vh] flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        <div className="p-4 border-b border-border">
          <p className="eyebrow">主播加歌</p>
          <h3 className="text-base font-semibold">从曲库选歌</h3>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="按歌名 / 歌手 / 拼音首字母搜索"
            className="mt-3 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm"
            data-testid="live-manual-search"
          />
          <p className="mt-2 text-[11px] text-muted-foreground">
            走 manual 模式入队，不消耗权益。
          </p>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {filtered.length === 0
            ? <div className="panel-empty">没有匹配</div>
            : <ul className="space-y-1">
                {filtered.map(s => (
                  <li key={s.id}>
                    <button
                      type="button"
                      onClick={() => onPick(s.id)}
                      className="w-full text-left rounded-lg px-3 py-2 hover:bg-muted"
                    >
                      <div className="text-sm font-medium">{s.title}</div>
                      <div className="text-[11px] text-muted-foreground">
                        {s.artists.join(" / ") || "—"} · {s.key || "?"}
                      </div>
                    </button>
                  </li>
                ))}
              </ul>}
        </div>
        <div className="p-3 border-t border-border flex justify-end">
          <button type="button" className="secondary-action" onClick={onClose}>
            取消
          </button>
        </div>
      </div>
    </div>
  );
}
