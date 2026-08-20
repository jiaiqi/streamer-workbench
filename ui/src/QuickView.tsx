/// R2 P2: QuickView v2 — 直播中置顶速查窗 (/quick?session=xxx)。
///
/// 架构 (P2 R4 重写):
/// - URL 接受 ?session=xxx → 加载 LiveSession 后端数据
/// - 队列 = LiveSession.queue (后端权威), 不再用 localStorage.queue
/// - 加歌 = POST /api/live-sessions/{id}/queue (entitlement_kind=manual 简版)
/// - 记结果 = POST /api/live-sessions/{id}/record
/// - 离线兜底: 失败的命令进 pending_commands (localStorage), 恢复后按 command_id 幂等补报
/// - 纯键盘: 搜歌 Enter 加歌, Space 已唱, U 不会, P 延期, R 跳过, T 看谱
/// - 移除了 v1 的 localStorage 队列 (与 LiveSession 二选一)
import { useState, useEffect, useMemo, useRef, useCallback } from "react";
import type { Song, SongsData } from "./types";
import { useLiveSession } from "./quick-view/useLiveSession";
import { apiRequest } from "./api/client";
import { useLatestRequest } from "./async/requestState";
import Spinner from "./components/Spinner";

/* ================== 模式解析 ================== */
// 兼容: dev 模式 (?session=) + Electron packaged 模式 (#/quick?session=)
const SESSION_ID = (() => {
  if (typeof window === "undefined") return null;
  const fromSearch = new URLSearchParams(window.location.search).get("session");
  if (fromSearch) return fromSearch;
  const hashQuery = window.location.hash.includes("?")
    ? window.location.hash.slice(window.location.hash.indexOf("?"))
    : "";
  return new URLSearchParams(hashQuery).get("session");
})();

/* ================== 工具 ================== */
function uuid(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  return [...bytes].map(b => b.toString(16).padStart(2, "0")).join("");
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

/* ================== 主组件 ================== */
export default function QuickView() {
  const live = useLiveSession(SESSION_ID);
  const [songs, setSongs] = useState<Song[]>([]);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const [tabsOpen, setTabsOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const toastTimer = useRef<number>(0);
  const selRef = useRef<Song | null>(null);
  const tabsOpenRef = useRef(false);
  const queryRef = useRef("");
  const liveRef = useRef(live);
  liveRef.current = live;
  const listRequest = useLatestRequest<SongsData>({ isEmpty: d => d.total === 0 });

  /* 加载曲库 */
  useEffect(() => {
    let active = true;
    const load = async () => {
      const d = await listRequest.run(signal => apiRequest<SongsData>("/api/songs/list", { signal }));
      if (d && active) setSongs(d.songs);
    };
    void load();
    const t = setInterval(load, 60_000);  // 1 分钟
    return () => { active = false; clearInterval(t); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 1600);
  }, []);

  /* 过滤 + 排序 */
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
  selRef.current = sel;
  tabsOpenRef.current = tabsOpen;
  queryRef.current = query;

  const songsById = useMemo(() => new Map(songs.map(s => [s.id, s])), [songs]);

  // 把 LiveSession.queue 投影为本地"队列视图"
  const queueView = useMemo(() => {
    if (!live.session?.queue) return [];
    return live.session.queue
      .map((q) => {
        const raw = q as Record<string, unknown>;
        const songId = typeof raw.song_id === "string" ? raw.song_id : "";
        const requestId = typeof raw.request_id === "string" ? raw.request_id : "";
        const state = typeof raw.state === "string" ? raw.state : "queued";
        const position = typeof raw.position === "number" ? raw.position : 0;
        return { songId, requestId, state, position, raw };
      })
      .filter(v => v.songId);
  }, [live.session]);

  const pendingItems = queueView.filter(v => v.state === "queued" || v.state === "current");
  const sungItems = queueView.filter(v => v.state === "sung");
  const pendingSongIds = new Set(pendingItems.map(v => v.songId));
  const sungSongIds = new Set(sungItems.map(v => v.songId));

  /* 队列里 "下一个待唱" = position 最小的 queued */
  const nextEntry = useMemo(() => {
    return pendingItems
      .slice()
      .sort((a, b) => a.position - b.position)[0] ?? null;
  }, [pendingItems]);

  /* 键盘：搜歌 + 标记结果 */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // 看谱弹层: 只吃 Esc/T 关闭
      if (tabsOpenRef.current) {
        if (e.key === "Escape" || e.key === "t" || e.key === "T") {
          e.preventDefault();
          setTabsOpen(false);
        }
        return;
      }
      const tag = (e.target as HTMLElement)?.tagName;
      const typing = tag === "INPUT" || tag === "TEXTAREA";
      const mod = e.ctrlKey || e.metaKey;

      // Space / U / P / R: 在所有视图, 都不在输入控件里时, 对"下一个待唱"操作
      if (!typing) {
        if (e.key === " " || e.key === "Spacebar") {
          if (nextEntry) {
            e.preventDefault();
            void handleRecord(nextEntry.requestId, "sung");
          }
          return;
        }
        if (e.key === "u" || e.key === "U") {
          if (nextEntry) {
            e.preventDefault();
            void handleRecord(nextEntry.requestId, "unknown");
          }
          return;
        }
        if (e.key === "p" || e.key === "P") {
          if (nextEntry) {
            e.preventDefault();
            void handleRecord(nextEntry.requestId, "postponed");
          }
          return;
        }
        if (e.key === "r" || e.key === "R") {
          if (nextEntry) {
            e.preventDefault();
            void handleRecord(nextEntry.requestId, "skipped");
          }
          return;
        }
      }

      // 搜索/选择
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        setCursor(c => e.key === "ArrowDown"
          ? Math.min(results.length - 1, c + 1)
          : Math.max(0, c - 1));
      } else if (e.key === "Escape") {
        if (queryRef.current) {
          setQuery("");
          searchRef.current?.focus();
        } else {
          setTabsOpen(false);
        }
      } else if (e.key === "Enter" && !mod) {
        e.preventDefault();
        const s = selRef.current;
        if (s) void handleQueue(s);
      } else if ((e.key === "t" || e.key === "T") && !typing) {
        if (queryRef.current) return;
        const s = selRef.current;
        if (!s) return;
        if ((s.tab_files ?? []).length === 0) {
          showToast(`「${s.title}」还没有曲谱附件`);
          return;
        }
        e.preventDefault();
        setTabsOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [results.length, nextEntry, live.session]);

  /* 滚到当前光标 */
  useEffect(() => {
    listRef.current?.querySelector("[data-sel='1']")?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

  /* ----- 操作 ----- */

  const handleQueue = async (song: Song) => {
    if (pendingSongIds.has(song.id)) {
      showToast(`「${song.title}」已在队列里`);
      return;
    }
    if (sungSongIds.has(song.id)) {
      showToast(`注意：「${song.title}」今晚已唱过`);
      return;
    }
    const requesterName = prompt("点歌人昵称（可空，默认「速查」）") || "速查";
    const res = await liveRef.current.queueRequest(song.id, requesterName);
    showToast(res.message ?? (res.ok ? "已加入" : "失败"));
  };

  const handleRecord = async (requestId: string, result: string) => {
    const res = await liveRef.current.recordResult(requestId, result);
    showToast(res.message ?? (res.ok ? "已记录" : "失败"));
  };

  /* 无 sessionId 时: 全屏引导 */
  if (!SESSION_ID) {
    return (
      <div className="h-screen w-screen bg-zinc-950 text-zinc-100 flex flex-col items-center justify-center gap-4 p-8 font-sans">
        <p className="text-zinc-500 uppercase tracking-[0.3em] text-[11px] font-mono">QuickView v2</p>
        <h1 className="text-2xl font-serif">需要 ?session=xxx 参数</h1>
        <p className="text-zinc-400 text-sm max-w-md text-center">
          速查窗现在绑定到具体的直播会话。请在打开时附带 session ID：
        </p>
        <code className="text-emerald-400 text-sm font-mono bg-zinc-900 px-3 py-2 rounded">
          /quick?session=live_xxxx
        </code>
        <p className="text-zinc-500 text-xs mt-2">
          可在「直播」后台管理视图中点击「直播速查」自动带上 session 参数。
        </p>
      </div>
    );
  }

  /* sessionId 但还没加载到 session */
  if (live.session === undefined) {
    return (
      <div className="h-screen w-screen bg-zinc-950 text-zinc-100 flex flex-col items-center justify-center gap-3 font-sans">
        {/* 3.1 收口：原 <span className="spinner" /> 改用 Spinner 组件 */}
        <Spinner size="md" tone="primary" decorative label={`加载会话 ${SESSION_ID}`} />
        <p className="text-zinc-400 text-sm">加载会话 {SESSION_ID}…</p>
      </div>
    );
  }

  /* sessionId 但加载失败 */
  if (live.session === null) {
    return (
      <div className="h-screen w-screen bg-zinc-950 text-zinc-100 flex flex-col items-center justify-center gap-3 p-8 font-sans">
        <p className="text-red-400 text-sm" role="alert">会话加载失败</p>
        <p className="text-zinc-500 text-xs">{live.error}</p>
        <button type="button" className="secondary-action" onClick={() => void live.refresh()}>重试</button>
      </div>
    );
  }

  return (
    <div className="h-screen w-screen bg-zinc-950 text-zinc-100 flex flex-col overflow-hidden font-sans select-none">
      {/* ===== 顶栏: 会话名 + 状态 + 离线提示 ===== */}
      <div className="shrink-0 flex items-center gap-3 px-4 h-11 border-b border-zinc-800 text-xs">
        <span className={`inline-block h-2 w-2 rounded-full ${
          live.isActive ? "bg-emerald-500" : "bg-zinc-600"}`} />
        <span className="font-serif truncate">{live.title}</span>
        <span className="text-zinc-600">
          {live.session.state === "active" ? "进行中" : "已结束"}
        </span>
        {live.pendingCount > 0 && (
          <span className="text-amber-400 ml-auto" title="离线暂存中, 恢复后自动补报">
            离线暂存 {live.pendingCount}
          </span>
        )}
        <button type="button" onClick={() => void live.retryPending()} title="重试补报"
          className="text-zinc-500 hover:text-zinc-200 cursor-pointer"
          aria-label="重试补报">
          ↻
        </button>
      </div>

      {/* ===== 搜索栏 ===== */}
      <div className="shrink-0 flex items-center gap-3 px-5 h-14 border-b border-zinc-800">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-zinc-500 shrink-0">
          <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
        </svg>
        <input ref={searchRef} type="text" autoFocus
          placeholder="歌名 / 歌手 / 拼音首字母… (Enter 加歌)"
          value={query} onChange={e => setQuery(e.target.value)}
          className="flex-1 bg-transparent text-lg outline-none placeholder:text-zinc-600" />
        <span className="text-xs tabular-nums text-zinc-600">
          {results.length ? `${Math.min(cursor + 1, results.length)} / ${results.length}` : "0"}
        </span>
      </div>

      <div className="flex flex-1 min-h-0">
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
              onDoubleClick={() => void handleQueue(s)}
              className={`px-4 py-2 cursor-pointer border-l-2 transition-colors ${
                i === cursor
                  ? "border-emerald-500 bg-zinc-900"
                  : "border-transparent hover:bg-zinc-900/50"}`}>
              <div className="flex items-center gap-1.5">
                <p className={`text-[15px] font-serif truncate ${s.status === "draft" ? "text-zinc-500" : "text-zinc-100"}`}>
                  {s.title}
                </p>
                {pendingSongIds.has(s.id) && (
                  <span className="shrink-0 rounded px-1 text-[9px] bg-emerald-950 text-emerald-400 border border-emerald-900">队列</span>
                )}
                {sungSongIds.has(s.id) && (
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

              <p className="mt-6 text-[11px] text-zinc-600 font-mono">
                Enter 加歌 · Space/U/P/R 标记 · T 看谱 · Esc 取消
              </p>
            </>
          ) : (
            <p className="text-zinc-700 text-lg">输入歌名或拼音首字母开始查</p>
          )}

          {toast && (
            <div className="absolute bottom-6 left-1/2 -translate-x-1/2 rounded-lg bg-zinc-800 border border-zinc-700 px-4 py-2 text-sm text-zinc-200 shadow-lg whitespace-nowrap">
              {toast}
            </div>
          )}

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

        {/* ===== 今晚歌单 (LiveSession 投影) ===== */}
        <div className="w-72 shrink-0 border-l border-zinc-800 flex flex-col min-h-0">
          <div className="shrink-0 px-4 h-11 flex items-center gap-2 border-b border-zinc-800">
            <span className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-mono">今晚歌单</span>
            <span className="text-[11px] tabular-nums text-zinc-500">
              待唱 {pendingItems.length} · 已唱 {sungItems.length}
            </span>
          </div>
          <div className="flex-1 overflow-y-auto">
            {queueView.length === 0 ? (
              <p className="px-4 py-6 text-sm text-zinc-600">空 (回主工作台加歌)</p>
            ) : (
              <ul>
                {[...pendingItems, ...sungItems].map(item => {
                  const song = songsById.get(item.songId);
                  const isSung = item.state === "sung";
                  return (
                    <li key={item.requestId}
                      data-testid="qv-queue-row"
                      data-state={item.state}
                      className={`group flex items-center gap-2 px-3 py-2 border-b border-zinc-900 ${
                        isSung ? "opacity-40" : ""}`}>
                      <span className="text-[10px] tabular-nums text-zinc-600 w-6 text-right">
                        #{item.position}
                      </span>
                      <div className="flex-1 min-w-0">
                        <p className={`text-sm font-serif truncate ${
                          isSung ? "line-through text-zinc-500" : "text-zinc-100"}`}>
                          {song?.title ?? item.songId}
                        </p>
                        <p className="text-[10px] text-zinc-500 truncate font-mono">
                          {song?.key ? `${song.key}${song.capo !== null ? ` · 夹${song.capo}品` : ""}` : ""}
                        </p>
                      </div>
                      {live.isActive && (
                        <div className="hidden group-hover:flex items-center gap-0.5">
                          <button
                            onClick={() => void handleRecord(item.requestId, "sung")}
                            title="已唱 (Space)"
                            className="h-6 w-6 inline-flex items-center justify-center rounded text-zinc-500 hover:text-emerald-400">
                            ✓
                          </button>
                          <button
                            onClick={() => void handleRecord(item.requestId, "postponed")}
                            title="延期 (P)"
                            className="h-6 w-6 inline-flex items-center justify-center rounded text-zinc-500 hover:text-amber-400">
                            P
                          </button>
                          <button
                            onClick={() => void handleRecord(item.requestId, "unknown")}
                            title="不会 (U)"
                            className="h-6 w-6 inline-flex items-center justify-center rounded text-zinc-500 hover:text-red-400">
                            U
                          </button>
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
