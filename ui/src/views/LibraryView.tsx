import { useState, useEffect, useMemo, useRef } from "react";
import type { Song, SongsData } from "../types";
import SongEditDialog from "../components/SongEditDialog";
import TabsPanel from "../components/TabsPanel";
import AsyncStateNotice from "../components/AsyncStateNotice";
import { apiRequest } from "../api/client";
import { toRequestFailure, useLatestRequest } from "../async/requestState";

/* ================= 符号化元数据 ================= */
// 难度 → 菱形阶（◆◆◇），一瞥可读
function DifficultyMark({ value, dark }: { value: string; dark: boolean }) {
  const level = value === "简单" ? 1 : value === "中等" ? 2 : value === "困难" ? 3 : 0;
  if (level === 0) return <span className="text-muted-foreground/60">—</span>;
  return (
    <span className={`tracking-[0.15em] text-[10px] ${dark ? "text-zinc-400" : "text-muted-foreground"}`}
      title={`难度：${value}`}>
      {"◆".repeat(level)}{"◇".repeat(3 - level)}
    </span>
  );
}

// 选调 + 变调夹（等宽排版，保证列对齐）
function KeyCapo({ song }: { song: Song }) {
  if (!song.key && song.capo === null) return <span className="text-muted-foreground/60">—</span>;
  return (
    <span className="tabular-nums">
      <span className={song.key ? "" : "text-muted-foreground/60"}>{song.key || "?"}</span>
      {song.capo !== null && <span className="text-muted-foreground text-[11px]"> +{song.capo}</span>}
    </span>
  );
}

// 卡片网格：auto-fill + minmax 天然响应不同分辨率，无需断点
const GRID_CLASS = "grid gap-3 grid-cols-[repeat(auto-fill,minmax(232px,1fr))]";

/* ================= 主视图 ================= */
export default function LibraryView({ dark, onStatsChange, onEditTargetChange, onPlaySong }: {
  dark: boolean;
  onStatsChange: (s: { active: number; draft: number }) => void;
  onEditTargetChange?: (open: boolean) => void;
  /** R8.0: 触发弹唱视图（点击卡片 ▶ 按钮 / 双击行） */
  onPlaySong?: (songId: string) => void;
}) {
  const [songsData, setSongsData] = useState<SongsData | null>(null);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "draft">("all");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [editTarget, setEditTarget] = useState<Song | "new" | null>(null);
  const [actionSong, setActionSong] = useState<string | null>(null);
  const [actionError, setActionError] = useState("");
  const listRequest = useLatestRequest<SongsData>({ isEmpty: data => data.total === 0 });
  const [seedPending, setSeedPending] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const rowRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const listRef = useRef<HTMLDivElement>(null);
  const probeRef = useRef<HTMLDivElement>(null);

  const refresh = async () => {
    const d = await listRequest.run(signal => apiRequest<SongsData>("/api/songs/list", { signal }));
    if (!d) return;
    setSongsData(d);
    onStatsChange({ active: d.active, draft: d.draft });
  };

  // P1 R1a.2 首用引导：空曲库 → 一键载入内置示例曲库
  const handleSeedSample = async () => {
    if (seedPending) return;
    setSeedPending(true);
    setActionError("");
    try {
      const res = await apiRequest<{ ok: boolean; added: string[] }>(
        "/api/songs/seed-sample", { method: "POST", body: {} },
      );
      if (res.added.length > 0) {
        setActionError(""); // 清空旧错误
      }
      await refresh();
    } catch (reason) {
      const failure = toRequestFailure(reason, "示例曲库载入失败");
      setActionError(failure.message);
    } finally {
      setSeedPending(false);
    }
  };

  /* 曲谱上传/删除后局部更新该曲的 tab_files（不必全量 refresh） */
  const updateTabFiles = (title: string, files: string[]) => {
    setSongsData(d => d && ({
      ...d,
      songs: d.songs.map(s => s.title === title ? { ...s, tab_files: files } : s),
    }));
  };

  useEffect(() => { refresh(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);
  useEffect(() => { onEditTargetChange?.(editTarget !== null); }, [editTarget, onEditTargetChange]);

  /* ---- 筛选：歌名 / 歌手 / 拼音首字母 ---- */
  const filtered = useMemo(() => {
    if (!songsData) return [];
    const q = query.trim().toLowerCase();
    return songsData.songs
      .filter(s => statusFilter === "all" || s.status === statusFilter)
      .filter(s => !q
        || s.title.toLowerCase().includes(q)
        || s.artists.join(" ").toLowerCase().includes(q)
        || (s.pinyin ?? "").toLowerCase().includes(q));
  }, [songsData, query, statusFilter]);

  /* ---- 按字数分类分组（1..7 + 未分类），组内保持后端序 ---- */
  const groups = useMemo(() => {
    const map = new Map<number, Song[]>();
    for (const s of filtered) {
      const sec = s.section ?? 0;
      if (!map.has(sec)) map.set(sec, []);
      map.get(sec)!.push(s);
    }
    return [...map.entries()].sort((a, b) => (a[0] === 0 ? 99 : a[0]) - (b[0] === 0 ? 99 : b[0]));
  }, [filtered]);

  const groupLabel = (sec: number) => sec === 0 ? "未分类" : sec >= 7 ? "7+ 字" : `${sec} 字`;

  /* ---- 当前网格实际列数（从隐藏探针元素的 computed style 读） ---- */
  const currentCols = () => {
    const el = probeRef.current;
    if (!el) return 1;
    const tracks = getComputedStyle(el).gridTemplateColumns;
    if (!tracks || tracks === "none") return 1;
    return tracks.split(" ").length;
  };

  /* ---- 键盘导航：←→↑↓ 光标 · Enter 展开 · X 学会了 · / 搜索 ---- */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (editTarget !== null) return;
      const tag = (e.target as HTMLElement)?.tagName;
      const typing = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";

      if (e.key === "/" && !typing) {
        e.preventDefault();
        searchRef.current?.focus();
        return;
      }
      if (typing || filtered.length === 0) return;

      const idx = cursor === null ? -1 : filtered.findIndex(s => s.title === cursor);
      const cols = currentCols();
      let next: number | null = null;
      if (e.key === "ArrowRight") next = Math.min(filtered.length - 1, idx + 1);
      else if (e.key === "ArrowLeft") next = Math.max(0, idx === -1 ? 0 : idx - 1);
      else if (e.key === "ArrowDown") next = Math.min(filtered.length - 1, (idx === -1 ? 0 : idx) + (idx === -1 ? 0 : cols));
      else if (e.key === "ArrowUp") next = Math.max(0, idx - cols);

      if (next !== null) {
        e.preventDefault();
        const title = filtered[next].title;
        setCursor(title);
        rowRefs.current.get(title)?.scrollIntoView({ block: "nearest" });
      } else if (e.key === "Enter" && cursor) {
        e.preventDefault();
        setExpanded(prev => prev === cursor ? null : cursor);
      } else if ((e.key === "x" || e.key === "X") && cursor) {
        e.preventDefault();
        const song = filtered.find(s => s.title === cursor);
        if (song) toggleStatus(song);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtered, cursor, editTarget]);

  const toggleStatus = async (song: Song) => {
    if (actionSong) return;
    const next = song.status === "active" ? "draft" : "active";
    setActionSong(song.id); setActionError("");
    try {
      await apiRequest("/api/songs/status", { method: "POST", body: { title: song.title, status: next } });
      // 本地更新该行 + 统计，避免整表重拉
      setSongsData(prev => {
        if (!prev) return prev;
        const songs = prev.songs.map(s => s.title === song.title ? { ...s, status: next } : s);
        const stats = {
          active: songs.reduce((n, s) => n + (s.status === "active" ? 1 : 0), 0),
          draft: songs.reduce((n, s) => n + (s.status === "draft" ? 1 : 0), 0),
        };
        onStatsChange(stats);
        return { ...prev, ...stats, songs };
      });
    } catch (reason) { setActionError(toRequestFailure(reason, "状态切换失败").message); }
    finally { setActionSong(null); }
  };

  const deleteSong = async (song: Song) => {
    if (!window.confirm(`确定删除「${song.title}」？此操作会立即写入 songs.json（有自动备份）。`)) return;
    if (actionSong) return;
    setActionSong(song.id); setActionError("");
    try {
      await apiRequest("/api/songs/delete", { method: "POST", body: { title: song.title } });
      if (expanded === song.title) setExpanded(null);
      await refresh();
    } catch (reason) { setActionError(toRequestFailure(reason, "删除失败").message); }
    finally { setActionSong(null); }
  };

  /* ---- 设计令牌速记 ---- */
  const hairline = dark ? "border-zinc-700/60" : "border-border";
  const label = "text-[10px] font-semibold uppercase tracking-widest text-muted-foreground";

  return (
    <main className="flex-1 flex flex-col overflow-hidden">
      {/* ===== 第一层：主工具栏 ===== */}
      <div className={`shrink-0 flex items-center gap-4 px-6 h-14 border-b ${hairline}`}>
        <h2 className={`font-serif text-[17px] font-semibold tracking-wide ${dark ? "text-zinc-100" : "text-foreground"}`}>
          歌曲库
        </h2>
        <span className={`text-xs tabular-nums ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
          {songsData ? `${songsData.total} 首 · 已会 ${songsData.active} · 未会 ${songsData.draft}` : "…"}
        </span>

        {/* 弹唱信息完整度：已填选调歌曲占比，把补数据变成有终点的进度 */}
        {songsData && (() => {
          const withKey = songsData.songs.filter(s => s.key).length;
          const pct = Math.round((withKey / (songsData.total || 1)) * 100);
          return (
            <span className="flex items-center gap-2" title={`${withKey}/${songsData.total} 首已填选调，点卡片展开 → 编辑可补`}>
              <span className={`w-16 h-1 rounded-full overflow-hidden ${dark ? "bg-zinc-700" : "bg-muted"}`}>
                <span className={`block h-full rounded-full transition-all duration-500 ${dark ? "bg-emerald-400" : "bg-emerald-600"}`}
                  style={{ width: `${pct}%` }} />
              </span>
              <span className={`text-[11px] tabular-nums ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
                弹唱完整度 {pct}%
              </span>
            </span>
          );
        })()}

        {/* 搜索：歌名 / 歌手 / 拼音首字母；按 / 聚焦 */}
        <div className={`ml-auto flex items-center gap-2 rounded-lg px-3 h-8 w-64 transition-colors ${
          dark ? "bg-zinc-800 border border-zinc-700/60 focus-within:border-emerald-500/60"
               : "bg-muted border border-border focus-within:border-primary/60"}`}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-muted-foreground shrink-0">
            <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
          </svg>
          <input ref={searchRef} type="text" placeholder="歌名 / 歌手 / 拼音首字母…" value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => { if (e.key === "Escape") { setQuery(""); searchRef.current?.blur(); } }}
            className="flex-1 bg-transparent text-[13px] outline-none placeholder:text-muted-foreground/70" />
          <kbd className={`text-[10px] px-1 rounded ${dark ? "bg-zinc-700 text-zinc-500" : "bg-background text-muted-foreground/70 border border-border"}`}>/</kbd>
        </div>

        <button onClick={() => setEditTarget("new")}
          className="flex items-center gap-1.5 rounded-lg px-3.5 h-8 text-[13px] font-medium transition-colors cursor-pointer bg-emerald-600 hover:bg-emerald-700 text-white">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M12 5v14M5 12h14"/></svg>
          新增歌曲
        </button>
      </div>

      {/* ===== 第二层：状态筛选条 ===== */}
      <div className={`shrink-0 flex items-center gap-1 px-6 h-10 border-b ${hairline} ${dark ? "bg-zinc-800/40" : "bg-muted/40"}`}>
        {([["all", "全部"], ["active", "已会"], ["draft", "未会"]] as const).map(([id, text]) => (
          <button key={id} onClick={() => setStatusFilter(id)}
            className={`rounded-md px-3 h-6.5 py-1 text-xs font-medium transition-all duration-300 ease-out cursor-pointer ${statusFilter === id
              ? (dark ? "bg-emerald-500/20 text-emerald-300" : "bg-primary-soft text-primary")
              : (dark ? "text-zinc-500 hover:text-zinc-300" : "text-muted-foreground hover:text-foreground")}`}>
            {text}
            <span className="ml-1 tabular-nums opacity-60">
              {id === "all" ? songsData?.total ?? "" : id === "active" ? songsData?.active ?? "" : songsData?.draft ?? ""}
            </span>
          </button>
        ))}
        <span className={`ml-auto text-[11px] ${dark ? "text-zinc-600" : "text-muted-foreground/70"}`}>
          ←→↑↓ 移动 · Enter 展开 · X 学会了 · / 搜索
        </span>
      </div>

      {actionError && <div className="mx-6 mt-3 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-500" role="alert">{actionError}</div>}

      {/* ===== 分组卡片网格 ===== */}
      {listRequest.status === "loading" && !songsData ? <AsyncStateNotice kind="loading" label="歌曲库" />
      : listRequest.status === "error" && !songsData ? <AsyncStateNotice kind="error" label="歌曲库" error={listRequest.error} onRetry={refresh} />
      : listRequest.status === "empty" ? <AsyncStateNotice
          kind="empty"
          label="歌曲"
          actionLabel="载入示例数据"
          onAction={handleSeedSample}
          actionPending={seedPending}
        />
      : songsData ? (
        <div ref={listRef} className="flex-1 overflow-y-auto">
          {/* 列数探针：与真实网格同 class，键盘导航据此计算 ↑↓ 步长 */}
          <div ref={probeRef} aria-hidden="true" className={`invisible h-0 overflow-hidden ${GRID_CLASS}`} />
          {groups.length === 0 && (
            <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
              没有匹配「{query}」的歌曲
            </div>
          )}
          {groups.map(([sec, songs]) => (
            <div key={sec}>
              {/* 吸顶组头：大号分类字 + 数量 */}
              <div className={`sticky top-0 z-10 flex items-baseline gap-3 px-6 py-2 border-b ${hairline} ${
                dark ? "bg-zinc-900/95 backdrop-blur-sm" : "bg-background/95 backdrop-blur-sm"}`}>
                <span className={`font-serif text-[15px] font-semibold ${dark ? "text-zinc-300" : "text-foreground"}`}>
                  {groupLabel(sec)}
                </span>
                <span className={`text-[11px] tabular-nums ${dark ? "text-zinc-600" : "text-muted-foreground"}`}>
                  {songs.length} 首
                </span>
              </div>

              <div className={`px-6 py-3 ${GRID_CLASS}`}>
                {songs.map(s => {
                  const isOpen = expanded === s.title;
                  const isCursor = cursor === s.title;
                  return (
                    <div key={s.title}
                      ref={el => { if (el) rowRefs.current.set(s.title, el); else rowRefs.current.delete(s.title); }}
                      className={isOpen ? "col-span-full" : ""}>
                      {/* ---- 卡片：点击就地展开；状态变化只用背景填充，不加边框 ---- */}
                      <div
                        onClick={() => setExpanded(isOpen ? null : s.title)}
                        className={`h-full rounded-xl px-3.5 py-3 cursor-pointer transition-colors duration-200 ${
                          isOpen
                            ? (dark ? "bg-zinc-800/80" : "bg-muted/80")
                            : isCursor
                              ? (dark ? "bg-zinc-800/70" : "bg-muted/70")
                              : (dark ? "bg-zinc-800/40 hover:bg-zinc-800/60" : "bg-muted/40 hover:bg-muted/60")}`}
                      >
                        {/* 歌名 + 展开指示 + 弹唱按钮 */}
                        <div className="flex items-start gap-1.5">
                          <span className={`flex-1 min-w-0 font-serif text-[14px] leading-snug truncate ${
                            s.status === "draft"
                              ? (dark ? "text-zinc-400" : "text-muted-foreground")
                              : (dark ? "text-zinc-100" : "text-foreground")}`}
                            title={s.title}>
                            {s.title}
                          </span>
                          {/* R8.0 弹唱按钮 */}
                          {onPlaySong && (
                            <button
                              type="button"
                              data-testid={`library-play-${s.id}`}
                              onClick={e => { e.stopPropagation(); onPlaySong(s.id); }}
                              title="弹唱这首歌（歌词 + 曲谱 + 模拟时间）"
                              aria-label={`弹唱 ${s.title}`}
                              className={`shrink-0 rounded p-1 text-xs transition-colors ${
                                dark
                                  ? "text-zinc-500 hover:bg-zinc-700 hover:text-emerald-300"
                                  : "text-muted-foreground hover:bg-muted hover:text-emerald-700"
                              }`}
                            >
                              ▶
                            </button>
                          )}
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                            className={`mt-1 shrink-0 transition-transform duration-200 ${isOpen ? "rotate-180" : ""} ${dark ? "text-zinc-600" : "text-muted-foreground/60"}`}>
                            <path d="m6 9 6 6 6-6"/>
                          </svg>
                        </div>
                        {/* 歌手 */}
                        <p className={`mt-0.5 text-[12px] truncate ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
                          {s.artists.join("、") || "—"}
                        </p>
                        {/* 元数据行：状态点 · 难度 · 选调 */}
                        <div className="mt-2.5 flex items-center gap-2.5 text-[12px]">
                          <button
                            onClick={e => { e.stopPropagation(); toggleStatus(s); }}
                            disabled={actionSong === s.id}
                            title={s.status === "active" ? "已会 · 点击标回未会" : "未会 · 点击标记学会了"}
                            className="shrink-0 w-5 h-5 -ml-1 flex items-center justify-center cursor-pointer">
                            <span className={`w-2 h-2 rounded-full transition-all duration-300 ${
                              s.status === "active"
                                ? (dark ? "bg-emerald-400" : "bg-emerald-600")
                                : `bg-transparent border ${dark ? "border-amber-400/70" : "border-amber-500/80"}`}`} />
                          </button>
                          <DifficultyMark value={s.difficulty} dark={dark} />
                          {(s.tags ?? []).length > 0 && (
                            <span className={`min-w-0 truncate text-[11px] ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
                              {s.tags.join(" · ")}
                            </span>
                          )}
                          <span className={`ml-auto shrink-0 font-mono ${dark ? "text-zinc-300" : "text-foreground"}`}>
                            <KeyCapo song={s} />
                          </span>
                        </div>

                        {/* ---- 展开面板：大字选调 + 详情网格 + 操作 ---- */}
                        {isOpen && (
                          <div className={`mt-3 pt-4 border-t ${hairline}`}
                            onClick={e => e.stopPropagation()}>
                            <div className="flex flex-wrap gap-8">
                              {/* 大字选调：主播一瞥可读；空态转为补全 CTA */}
                              <div className="shrink-0 w-36">
                                <p className={label}>选调</p>
                                {s.key ? (
                                  <p className={`font-mono text-4xl font-semibold mt-1 leading-none ${dark ? "text-zinc-100" : "text-foreground"}`}>
                                    {s.key}
                                  </p>
                                ) : (
                                  <button onClick={() => setEditTarget(s)}
                                    className={`mt-1 rounded-lg px-2.5 py-1.5 text-[12px] font-medium transition-colors cursor-pointer ${
                                      dark ? "bg-zinc-700/70 text-zinc-300 hover:bg-zinc-700" : "bg-background border border-dashed border-border text-muted-foreground hover:text-foreground hover:border-primary/50"}`}>
                                    未填 · 点我补选调 →
                                  </button>
                                )}
                                <p className={`mt-2 text-[12px] tabular-nums ${dark ? "text-zinc-400" : "text-muted-foreground"}`}>
                                  {s.capo !== null ? `变调夹 ${s.capo} 品` : "变调夹未填"}
                                </p>
                                <p className="mt-1"><DifficultyMark value={s.difficulty} dark={dark} /></p>
                              </div>

                              {/* 详情网格 */}
                              <div className="flex-1 min-w-64 grid md:grid-cols-2 gap-x-8 gap-y-3 content-start text-[13px]">
                                <div><p className={label}>作词</p><p className={`mt-0.5 ${dark ? "text-zinc-300" : ""}`}>{s.lyricist || "—"}</p></div>
                                <div><p className={label}>作曲</p><p className={`mt-0.5 ${dark ? "text-zinc-300" : ""}`}>{s.composer || "—"}</p></div>
                                <div>
                                  <p className={label}>谱子</p>
                                  <p className={`mt-0.5 break-all ${dark ? "text-zinc-300" : ""}`}>
                                    {s.tabs
                                      ? /^https?:\/\//.test(s.tabs)
                                        ? <a href={s.tabs} target="_blank" rel="noreferrer" className="underline underline-offset-2 hover:text-emerald-500">{s.tabs}</a>
                                        : s.tabs
                                      : "—"}
                                  </p>
                                </div>
                                <div><p className={label}>拼音</p><p className={`mt-0.5 font-mono ${dark ? "text-zinc-300" : ""}`}>{s.pinyin || "—"}</p></div>
                                {(s.tags ?? []).length > 0 && (
                                  <div className="md:col-span-2">
                                    <p className={label}>标签</p>
                                    <div className="mt-1 flex flex-wrap gap-1.5">
                                      {s.tags.map(t => (
                                        <span key={t} className={`rounded-md px-2 py-0.5 text-[11px] ${
                                          dark ? "bg-zinc-700/70 text-zinc-300" : "bg-background border border-border text-muted-foreground"}`}>{t}</span>
                                      ))}
                                    </div>
                                  </div>
                                )}
                                {s.notes && (
                                  <div className="md:col-span-2">
                                    <p className={label}>备注</p>
                                    <p className={`mt-0.5 leading-relaxed ${dark ? "text-zinc-300" : ""}`}>{s.notes}</p>
                                  </div>
                                )}
                                <div className="md:col-span-2">
                                  <p className={label}>曲谱附件</p>
                                  <TabsPanel title={s.title} tabFiles={s.tab_files ?? []} dark={dark}
                                    onChanged={files => updateTabFiles(s.title, files)} />
                                </div>
                              </div>

                              {/* 操作列 */}
                              <div className="shrink-0 ml-auto flex md:flex-col gap-1.5 w-full md:w-24">
                                <button onClick={() => toggleStatus(s)}
                                  disabled={actionSong === s.id}
                                  className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors cursor-pointer ${s.status === "draft"
                                    ? "bg-emerald-600 hover:bg-emerald-700 text-white"
                                    : dark ? "bg-zinc-700 text-zinc-300 hover:bg-zinc-600" : "bg-background border border-border text-muted-foreground hover:text-foreground"}`}>
                                  {s.status === "draft" ? "学会了 ✓" : "标回未会"}
                                </button>
                                <button onClick={() => setEditTarget(s)}
                                  className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors cursor-pointer ${dark ? "bg-zinc-700 text-zinc-300 hover:bg-zinc-600" : "bg-background border border-border text-foreground hover:bg-muted"}`}>
                                  编辑
                                </button>
                                <button onClick={() => deleteSong(s)}
                                  disabled={actionSong === s.id}
                                  className={`rounded-lg px-3 py-1.5 text-xs transition-colors cursor-pointer ${dark ? "text-red-400/80 hover:bg-zinc-700 hover:text-red-400" : "text-red-500/80 hover:bg-red-50 hover:text-red-500"}`}>
                                  删除
                                </button>
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      ) : null}

      {/* ===== 底栏：计数收尾 ===== */}
      <div className={`shrink-0 flex items-center px-6 h-8 border-t text-[11px] ${hairline} ${dark ? "text-zinc-600" : "text-muted-foreground"}`}>
        <span className="tabular-nums">显示 {filtered.length} / {songsData?.total ?? 0} 首</span>
        {query && <span className="ml-3">匹配：「{query}」（歌名 / 歌手 / 拼音）</span>}
      </div>

      {editTarget !== null && (
        <SongEditDialog target={editTarget}
          onClose={() => setEditTarget(null)} onSaved={refresh} />
      )}
    </main>
  );
}
