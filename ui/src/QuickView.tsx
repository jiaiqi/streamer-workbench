import { useState, useEffect, useMemo, useRef } from "react";
import type { Song, SongsData } from "./types";

/* ---- 速查小窗 Web 版（/quick）----
   场景：直播中手机开播、电脑本窗口置顶，纯键盘速查选调。
   设计语言：近黑舞台底、衬线大字歌名、等宽超大选调、单一墨绿高亮。
   交互：输入即搜（歌名/歌手/拼音首字母），↑↓ 选择，Esc 清空，30s 自动刷新。
   后续 Electron 壳把本页装进 alwaysOnTop 小窗 + 全局热键。 */

const REFRESH_MS = 30_000;

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
  const [songs, setSongs] = useState<Song[]>([]);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const searchRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const refresh = async () => {
    try {
      const d: SongsData = await (await fetch("/api/songs/list")).json();
      setSongs(d.songs);
    } catch { /* 后端没起时保持旧数据 */ }
  };
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, REFRESH_MS);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  /* 键盘：↑↓ 选择 · Esc 清空 · 其他按键回流到搜索框 */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        setCursor(c => e.key === "ArrowDown"
          ? Math.min(results.length - 1, c + 1)
          : Math.max(0, c - 1));
      } else if (e.key === "Escape") {
        setQuery("");
        searchRef.current?.focus();
      } else if (e.key === "Enter") {
        e.preventDefault(); // 选中即大字展示，无额外动作
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [results.length]);

  /* 光标行滚进视野 */
  useEffect(() => {
    listRef.current?.querySelector("[data-sel='1']")
      ?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

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
      </div>

      <div className="flex flex-1 min-h-0">
        {/* ===== 结果列表 ===== */}
        <div ref={listRef} className="w-64 shrink-0 overflow-y-auto border-r border-zinc-800">
          {results.length === 0 && (
            <p className="px-4 py-6 text-sm text-zinc-600">无匹配</p>
          )}
          {results.map((s, i) => (
            <div key={s.title} data-sel={i === cursor ? "1" : "0"}
              onClick={() => setCursor(i)}
              className={`px-4 py-2 cursor-pointer border-l-2 transition-colors ${
                i === cursor
                  ? "border-emerald-500 bg-zinc-900"
                  : "border-transparent hover:bg-zinc-900/50"}`}>
              <p className={`text-[15px] font-serif truncate ${s.status === "draft" ? "text-zinc-500" : "text-zinc-100"}`}>
                {s.title}
              </p>
              <p className="text-[11px] text-zinc-500 truncate font-mono">
                {s.artists.join("、") || "—"}{s.key ? ` · ${s.key}` : ""}
              </p>
            </div>
          ))}
        </div>

        {/* ===== 大字卡片 ===== */}
        <div className="flex-1 flex flex-col justify-center px-10 min-w-0">
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
        </div>
      </div>

      {/* ===== 底栏 ===== */}
      <div className="shrink-0 flex items-center px-5 h-8 border-t border-zinc-800 text-[11px] text-zinc-600">
        <span>↑↓ 选择 · Esc 清空 · 每 {REFRESH_MS / 1000}s 自动刷新</span>
        <button onClick={refresh} className="ml-auto hover:text-zinc-300 transition-colors cursor-pointer">手动刷新</button>
      </div>
    </div>
  );
}
