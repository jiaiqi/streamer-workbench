import { useState, useEffect, useMemo, useRef } from "react";
import type { Song, SongsData } from "./types";
import {
  LEGACY_PENDING_KEY, LEGACY_QUEUE_KEY, STORAGE_KEY, createPendingEvent, emptyStorage,
  enqueue, flushPending, loadStorageV2, migrateStorage, moveQueueItem, resolveQueueItem, toggleSung,
  type PendingEvent, type QuickEventType, type QuickViewStorageV2, type QueueItem,
} from "./quick-view/model";
import { apiRequest } from "./api/client";
import { toRequestFailure, useLatestRequest } from "./async/requestState";

/* ---- 速查小窗 Web 版（/quick）----
   场景：直播中手机开播、电脑本窗口置顶，纯键盘速查选调。
   设计语言：近黑舞台底、衬线大字歌名、等宽超大选调、单一墨绿高亮。
   交互：输入即搜（歌名/歌手/拼音首字母），↑↓ 选择，Enter 加入今晚歌单，
        Esc 清空，30s 自动刷新；歌单 localStorage 持久化，刷新不丢。
   今晚歌单：待唱按加入序，✓ 唱完沉底，重复点歌给「已唱过」提醒。
   数据：点歌/唱完双写后端事件流（/api/events/report），失败本地保序补报。
   后续 Electron 壳把本页装进 alwaysOnTop 小窗 + 全局热键。 */

const REFRESH_MS = 30_000;

/* ---- 事件上报（S2：localStorage 缓存 + 后端事件流 双写）----
   localStorage 是现场离线缓存（后端挂了直播照常进行），稳定身份仍是 Song.id；
   点歌/唱完同时上报 /api/events/report 沉淀统计数据。
   上报失败进待补队列（localStorage），下次上报成功或定时刷新时保序补报，
   occurred_at 为事件发生时刻，重试始终复用原 event_id。 */
async function postEvent(e: PendingEvent): Promise<{ ok: boolean; diagnostic?: string }> {
  try {
    await apiRequest("/api/events/report", { method: "POST", body: e });
    return { ok: true };
  } catch (error) {
    const failure = toRequestFailure(error, "事件补报失败");
    return { ok: false, diagnostic: [failure.message, failure.requestId && `请求 ${failure.requestId}`].filter(Boolean).join(" · ") };
  }
}

function DifficultyDots({ value }: { value: string }) {
  const level = value === "简单" ? 1 : value === "中等" ? 2 : value === "困难" ? 3 : 0;
  if (level === 0) return null;
  return (
    <span className="tracking-[0.2em] text-sm text-zinc-500">
      {"◆".repeat(level)}{"◇".repeat(3 - level)}
    </span>
  );
}

export default function QuickView() {
  const [initialStorage] = useState(() => loadStorageV2(localStorage.getItem(STORAGE_KEY)));
  const [songs, setSongs] = useState<Song[]>([]);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const [storage, setStorage] = useState<QuickViewStorageV2>(initialStorage.storage ?? emptyStorage);
  const [storageReady, setStorageReady] = useState(initialStorage.storage !== null);
  const [storageError, setStorageError] = useState<string | null>(initialStorage.error);
  const [pendingDiagnostic, setPendingDiagnostic] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const [tabsOpen, setTabsOpen] = useState(false);   // T 键看谱弹层（S3）
  const searchRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const toastTimer = useRef<number>(0);
  const storageRef = useRef(storage); storageRef.current = storage;
  const storageReadyRef = useRef(storageReady); storageReadyRef.current = storageReady;
  const flushRunningRef = useRef(false);
  const listRequest = useLatestRequest<SongsData>({ isEmpty: data => data.total === 0 });

  const commitStorage = (next: QuickViewStorageV2) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    storageRef.current = next;
    setStorage(next);
  };

  const flushPendingEvents = async (events = storageRef.current.pending_events) => {
    if (flushRunningRef.current || events.length === 0) return;
    flushRunningRef.current = true;
    try {
      const result = await flushPending(events, postEvent);
      if (result.completedIds.length > 0) {
        const completed = new Set(result.completedIds);
        commitStorage({
          ...storageRef.current,
          pending_events: storageRef.current.pending_events.filter(event => !completed.has(event.event_id)),
        });
      }
      setPendingDiagnostic(result.diagnostic);
    } finally {
      flushRunningRef.current = false;
    }
  };

  const reportEvent = (type: QuickEventType, song: Song) => {
    const event = createPendingEvent(type, song);
    const next = {
      ...storageRef.current,
      pending_events: [...storageRef.current.pending_events, event],
    };
    // 先持久化再上报，刷新或网络失败都不会丢失事件。
    commitStorage(next);
    void flushPendingEvents(next.pending_events);
  };

  const refresh = async () => {
    const d = await listRequest.run(signal => apiRequest<SongsData>("/api/songs/list", { signal }));
    if (d) {
      setSongs(d.songs);
      if (!storageReadyRef.current) {
        const migrated = migrateStorage(
          localStorage.getItem(STORAGE_KEY),
          localStorage.getItem(LEGACY_QUEUE_KEY),
          localStorage.getItem(LEGACY_PENDING_KEY),
          d.songs,
          (type, song, occurredAt) => createPendingEvent(type, song, undefined, undefined, occurredAt),
        );
        if (migrated.storage) {
          commitStorage(migrated.storage);
          storageReadyRef.current = true;
          setStorageReady(true);
          setStorageError(null);
          void flushPendingEvents(migrated.storage.pending_events);
        } else {
          setStorageError(migrated.error);
        }
      } else {
        void flushPendingEvents();
      }
    }
  };
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, REFRESH_MS);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const queue = storage.queue;
  const setQueue = (updater: (queue: QueueItem[]) => QueueItem[]) => {
    commitStorage({ ...storageRef.current, queue: updater(storageRef.current.queue) });
    setConfirmClear(false);
  };

  /* 过滤 + 排序：前缀命中排前，其余按歌名 */
  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    const match = (s: Song) => !q
      || s.title.toLowerCase().includes(q)
      || s.artists.join(" ").toLowerCase().includes(q)
      || (s.pinyin ?? "").toLowerCase().includes(q);
    const prefix = (s: Song) => q && (
      s.title.toLowerCase().startsWith(q) || (s.pinyin ?? "").toLowerCase().startsWith(q));
    return songs.filter(match).sort((a, b) =>
      (prefix(b) ? 1 : 0) - (prefix(a) ? 1 : 0) || a.title.localeCompare(b.title, "zh"));
  }, [songs, query]);

  useEffect(() => { setCursor(0); }, [query]);
  const sel = results[Math.min(cursor, results.length - 1)] ?? null;

  const songsById = useMemo(() => new Map(songs.map(s => [s.id, s])), [songs]);
  const sungSet = useMemo(() => new Set(queue.filter(i => i.sung).map(i => i.song_id)), [queue]);
  const queuedSet = useMemo(() => new Set(queue.filter(i => !i.sung).map(i => i.song_id)), [queue]);

  /* 供键盘闭包读取的最新值 */
  const selRef = useRef(sel); selRef.current = sel;
  const sungRef = useRef(sungSet); sungRef.current = sungSet;
  const queuedRef = useRef(queuedSet); queuedRef.current = queuedSet;
  const tabsOpenRef = useRef(tabsOpen); tabsOpenRef.current = tabsOpen;
  const queryRef = useRef(query); queryRef.current = query;

  const showToast = (msg: string) => {
    setToast(msg);
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 1600);
  };

  const addToQueue = (song: Song) => {
    if (queuedRef.current.has(song.id)) { showToast(`「${song.title}」已在队列里`); return; }
    if (sungRef.current.has(song.id)) { showToast(`注意：「${song.title}」今晚已唱过`); return; }
    showToast(`已加入今晚歌单：${song.title}`);
    setQueue(queue => enqueue(queue, song, Date.now()));
    reportEvent("queue_added", song);
  };

  /* 键盘：↑↓ 选择 · Enter 加入歌单 · T 看谱 · Esc 清空 · 其他按键回流到搜索框 */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      /* 看谱弹层打开时：只吃 Esc / T 关闭，其余键不穿透 */
      if (tabsOpenRef.current) {
        if (e.key === "Escape" || e.key === "t" || e.key === "T") {
          e.preventDefault();
          setTabsOpen(false);
        }
        return;
      }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        setCursor(c => e.key === "ArrowDown"
          ? Math.min(results.length - 1, c + 1)
          : Math.max(0, c - 1));
      } else if (e.key === "Escape") {
        setQuery("");
        searchRef.current?.focus();
      } else if (e.key === "Enter") {
        e.preventDefault();
        const s = selRef.current;
        if (s) { addToQueue(s); setQuery(""); }
      } else if (e.key === "t" || e.key === "T") {
        /* 仅浏览态（搜索框为空）触发；搜索中 t 正常输入拼音首字母 */
        if (queryRef.current) return;
        const s = selRef.current;
        if (!s) return;
        if ((s.tab_files ?? []).length === 0) { showToast(`「${s.title}」还没有曲谱附件`); return; }
        e.preventDefault();
        setTabsOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [results.length]);

  /* 光标行滚进视野 */
  useEffect(() => {
    listRef.current?.querySelector("[data-sel='1']")
      ?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

  /* ---- 歌单操作 ---- */
  const pending = queue.filter(i => !i.sung);
  const done = queue.filter(i => i.sung);

  const moveItem = (songId: string, dir: -1 | 1) =>
    setQueue(queue => moveQueueItem(queue, songId, dir));
  const markSung = (songId: string) => {
    const item = queue.find(candidate => candidate.song_id === songId);
    const currentSong = songsById.get(songId);
    setQueue(queue => toggleSung(queue, songId));
    if (!item?.sung && currentSong) reportEvent("song_sung", currentSong);
  };
  const removeItem = (songId: string) => setQueue(queue => queue.filter(item => item.song_id !== songId));

  const popout = () => {
    window.open("/quick", "_blank", "width=560,height=780");
  };

  const queueRow = (item: QueueItem) => {
    const resolved = resolveQueueItem(item, songsById);
    const s = resolved.song;
    const meta = [
      s?.key ? `${s.key}${s.capo !== null ? ` · 夹${s.capo}品` : ""}` : "",
      s?.artists.join("、") ?? "",
    ].filter(Boolean).join(" · ");
    return (
      <div key={item.song_id}
        className={`group flex items-center gap-2 px-3 py-2 border-b border-zinc-900 ${
          item.sung ? "opacity-40" : ""}`}>
        <div className="flex-1 min-w-0">
          <p className={`text-sm font-serif truncate ${item.sung ? "line-through text-zinc-500" : "text-zinc-100"}`}>
            {resolved.title}
            {resolved.missing && <span className="ml-2 text-[9px] text-red-400">歌曲已删除</span>}
          </p>
          <p className="text-[10px] text-zinc-500 truncate font-mono">{meta || "—"}</p>
        </div>
        {!item.sung && (
          <div className="hidden group-hover:flex flex-col text-zinc-500">
            <button onClick={() => moveItem(item.song_id, -1)} className="hover:text-zinc-200 leading-none cursor-pointer">▲</button>
            <button onClick={() => moveItem(item.song_id, 1)} className="hover:text-zinc-200 leading-none cursor-pointer">▼</button>
          </div>
        )}
        <button onClick={() => markSung(item.song_id)} title={item.sung ? "撤销已唱" : "标记已唱"}
          className={`text-sm cursor-pointer ${item.sung ? "text-emerald-500" : "text-zinc-600 hover:text-emerald-400"}`}>
          {item.sung ? "✓" : "○"}
        </button>
        <button onClick={() => removeItem(item.song_id)} title="移出歌单"
          className="hidden group-hover:block text-zinc-600 hover:text-red-400 text-sm cursor-pointer">×</button>
      </div>
    );
  };

  return (
    <div className="h-screen w-screen bg-zinc-950 text-zinc-100 flex flex-col overflow-hidden font-sans select-none">
      {/* ===== 搜索栏 ===== */}
      <div className="shrink-0 flex items-center gap-3 px-5 h-14 border-b border-zinc-800">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-zinc-500 shrink-0">
          <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
        </svg>
        <input ref={searchRef} type="text" autoFocus
          placeholder="歌名 / 歌手 / 拼音首字母…"
          value={query} onChange={e => setQuery(e.target.value)}
          className="flex-1 bg-transparent text-lg outline-none placeholder:text-zinc-600" />
        <span className="text-xs tabular-nums text-zinc-600">
          {results.length ? `${Math.min(cursor + 1, results.length)} / ${results.length}` : "0"}
        </span>
        <button onClick={popout} title="弹出独立小窗（可配合系统置顶工具）"
          className="text-zinc-500 hover:text-zinc-200 transition-colors cursor-pointer text-sm px-1">⧉</button>
      </div>

      <div className="flex flex-1 min-h-0">
        {listRequest.status === "error" && (
          <div className="absolute left-1/2 top-16 z-30 -translate-x-1/2 rounded-lg border border-red-900 bg-red-950/90 px-4 py-2 text-xs text-red-300" role="alert">
            {listRequest.error?.message} {listRequest.error?.recovery && `· ${listRequest.error.recovery}`}
            <button type="button" className="ml-3 underline" onClick={refresh}>重试</button>
          </div>
        )}
        {/* ===== 结果列表 ===== */}
        <div ref={listRef} className="w-64 shrink-0 overflow-y-auto border-r border-zinc-800">
          {listRequest.status === "loading" && songs.length === 0 ? (
            <p className="px-4 py-6 text-sm text-zinc-600" role="status">正在加载歌曲…</p>
          ) : listRequest.status === "empty" ? (
            <p className="px-4 py-6 text-sm text-zinc-600">歌曲库还没有歌曲</p>
          ) : results.length === 0 && (
            <p className="px-4 py-6 text-sm text-zinc-600">无匹配</p>
          )}
          {results.map((s, i) => (
            <div key={s.id} data-sel={i === cursor ? "1" : "0"}
              onClick={() => setCursor(i)}
              onDoubleClick={() => addToQueue(s)}
              className={`px-4 py-2 cursor-pointer border-l-2 transition-colors ${
                i === cursor
                  ? "border-emerald-500 bg-zinc-900"
                  : "border-transparent hover:bg-zinc-900/50"}`}>
              <div className="flex items-center gap-1.5">
                <p className={`text-[15px] font-serif truncate ${s.status === "draft" ? "text-zinc-500" : "text-zinc-100"}`}>
                  {s.title}
                </p>
                {queuedSet.has(s.id) && (
                  <span className="shrink-0 rounded px-1 text-[9px] bg-emerald-950 text-emerald-400 border border-emerald-900">队列</span>
                )}
                {sungSet.has(s.id) && (
                  <span className="shrink-0 rounded px-1 text-[9px] bg-amber-950 text-amber-400 border border-amber-900">已唱</span>
                )}
              </div>
              <p className="text-[11px] text-zinc-500 truncate font-mono">
                {s.artists.join("、") || "—"}{s.key ? ` · ${s.key}` : ""}
              </p>
            </div>
          ))}
        </div>

        {/* ===== 大字卡片 ===== */}
        <div className="flex-1 flex flex-col justify-center px-10 min-w-0 relative">
          {sel ? (
            <>
              <p className="text-[11px] uppercase tracking-[0.3em] text-zinc-600 font-mono">
                {sel.artists.join("、") || " "}
              </p>
              <h1 className="font-serif text-6xl font-bold tracking-wide mt-2 truncate">
                {sel.title}
              </h1>

              <div className="flex items-end gap-10 mt-8">
                <div>
                  <p className="text-[11px] uppercase tracking-[0.3em] text-zinc-600 font-mono">选调</p>
                  <p className={`font-mono font-bold leading-none mt-1 tracking-tight ${
                    sel.key ? "text-emerald-400 text-[7rem]" : "text-zinc-700 text-6xl"}`}>
                    {sel.key || "未填"}
                  </p>
                </div>
                {sel.capo !== null && (
                  <div className="pb-3">
                    <p className="text-[11px] uppercase tracking-[0.3em] text-zinc-600 font-mono">变调夹</p>
                    <p className="font-mono text-5xl font-bold text-zinc-200 leading-none mt-1 tabular-nums">
                      {sel.capo}<span className="text-xl text-zinc-500 ml-1">品</span>
                    </p>
                  </div>
                )}
                <div className="pb-4"><DifficultyDots value={sel.difficulty} /></div>
              </div>

              {sel.notes && (
                <p className="mt-8 text-lg leading-relaxed text-amber-200/90 border-l-2 border-amber-400/40 pl-4">
                  {sel.notes}
                </p>
              )}
              {(sel.tags ?? []).length > 0 && (
                <div className="mt-5 flex flex-wrap gap-2">
                  {sel.tags.map(t => (
                    <span key={t} className="rounded-md px-2.5 py-1 text-xs bg-zinc-900 text-zinc-400 border border-zinc-800">{t}</span>
                  ))}
                </div>
              )}
            </>
          ) : (
            <p className="text-zinc-700 text-lg">输入歌名或拼音首字母开始查</p>
          )}

          {/* toast */}
          {toast && (
            <div className="absolute bottom-6 left-1/2 -translate-x-1/2 rounded-lg bg-zinc-800 border border-zinc-700 px-4 py-2 text-sm text-zinc-200 shadow-lg whitespace-nowrap">
              {toast}
            </div>
          )}

          {/* ===== 看谱弹层（T 键，Esc/T/点击关闭）===== */}
          {tabsOpen && sel && (
            <div onClick={() => setTabsOpen(false)}
              className="absolute inset-0 z-40 bg-zinc-950/95 overflow-y-auto p-10 cursor-zoom-out">
              <p className="text-[11px] uppercase tracking-[0.3em] text-zinc-600 font-mono mb-6">
                {sel.title} · 曲谱 · Esc 关闭
              </p>
              <div className="flex flex-col items-center gap-8">
                {(sel.tab_files ?? []).map(rel => (
                  rel.toLowerCase().endsWith(".pdf")
                    ? <iframe key={rel} src={`/${rel}`} title={rel}
                        className="w-full max-w-3xl h-[80vh] rounded-lg bg-white" />
                    : <img key={rel} src={`/${rel}`} alt={rel}
                        className="max-w-full max-h-[85vh] rounded-lg shadow-2xl object-contain bg-white p-4" />
                ))}
              </div>
            </div>
          )}
        </div>

        {/* ===== 今晚歌单 ===== */}
        <div className="w-72 shrink-0 border-l border-zinc-800 flex flex-col min-h-0">
          <div className="shrink-0 px-4 h-11 flex items-center gap-2 border-b border-zinc-800">
            <span className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-mono">今晚歌单</span>
            <span className="text-[11px] tabular-nums text-zinc-500">
              待唱 {pending.length} · 已唱 {done.length}
            </span>
            {queue.length > 0 && (
              <button
                onClick={() => confirmClear ? setQueue(() => []) : setConfirmClear(true)}
                className={`ml-auto text-[11px] transition-colors cursor-pointer ${
                  confirmClear ? "text-red-400" : "text-zinc-600 hover:text-zinc-300"}`}>
                {confirmClear ? "再点确认清空" : "清空"}
              </button>
            )}
          </div>
          {(storageError || pendingDiagnostic || storage.unresolved_queue.length > 0
              || storage.unresolved_pending_events.length > 0) && (
            <div className="shrink-0 border-b border-amber-900/50 bg-amber-950/20 px-3 py-2 text-[10px] leading-relaxed text-amber-300">
              {storageError && <p>{storageError}</p>}
              {pendingDiagnostic && <p>待补事件：{pendingDiagnostic}</p>}
              {storage.unresolved_queue.map((item, index) => (
                <p key={`queue-${index}`}>未关联队列项：「{item.title}」（{item.reason}）</p>
              ))}
              {storage.unresolved_pending_events.map((item, index) => (
                <p key={`event-${index}`}>未关联事件：{item.type} ·「{item.title}」（不会自动上报）</p>
              ))}
            </div>
          )}
          <div className="flex-1 overflow-y-auto">
            {!storageReady && !storageError ? (
              <p className="px-4 py-6 text-xs text-zinc-700">正在加载现场队列…</p>
            ) : queue.length === 0 ? (
              <p className="px-4 py-6 text-xs text-zinc-700 leading-relaxed">
                观众点歌后按 Enter<br />加入今晚队列
              </p>
            ) : (
              <>
                {pending.map(queueRow)}
                {done.length > 0 && pending.length > 0 && (
                  <p className="px-3 py-1.5 text-[10px] uppercase tracking-[0.2em] text-zinc-700 font-mono">— 已唱 —</p>
                )}
                {done.map(queueRow)}
              </>
            )}
          </div>
        </div>
      </div>

      {/* ===== 底栏 ===== */}
      <div className="shrink-0 flex items-center px-5 h-8 border-t border-zinc-800 text-[11px] text-zinc-600">
        <span>↑↓ 选择 · Enter 加入歌单 · T 看谱 · 双击同效 · Esc 清空 · 每 {REFRESH_MS / 1000}s 自动刷新</span>
        <button onClick={refresh} disabled={listRequest.status === "loading"}
          className="ml-auto hover:text-zinc-300 transition-colors cursor-pointer disabled:opacity-50">
          {listRequest.status === "loading" ? "刷新中…" : "手动刷新"}
        </button>
      </div>
    </div>
  );
}
