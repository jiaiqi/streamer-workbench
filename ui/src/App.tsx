import { useState, useEffect, useCallback } from "react";

/* ---- types ---- */
interface Theme {
  name: string;
  prefix: string;
  watermark_fix: boolean;
  backgrounds: Record<string, string>;
  notes: string;
}
interface Layout {
  id: string;
  name: string;
  pages: number;
  supports_avoidance: boolean;
}

const CANVAS_OPTIONS = ["标准 9:16", "抖音全屏 9:20"] as const;

/* ---- inline SVG icons ---- */
const Icon = {
  music: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>,
  layout: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>,
  list: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></svg>,
  book: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>,
  palette: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M12 2a10 10 0 0 1 10 10c0 1.3-.7 2.2-2 2.2H12c-1.3 0-2-.9-2-2.2A10 10 0 0 1 12 2z"/><circle cx="8.5" cy="8.5" r="1.5" fill="currentColor"/><circle cx="15.5" cy="8.5" r="1.5" fill="currentColor"/></svg>,
  bookmark: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>,
  history: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>,
  settings: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>,
  sun: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>,
  download: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>,
  refresh: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>,
};

const navItems = [
  { id: "workspace", label: "海报工作台", icon: Icon.layout },
  { id: "library", label: "歌曲库", icon: Icon.list },
  { id: "learning", label: "学歌管理", icon: Icon.book },
  { id: "themes", label: "主题管理", icon: Icon.palette },
  { id: "presets", label: "场景预设", icon: Icon.bookmark },
  { id: "history", label: "导出历史", icon: Icon.history },
];

/* ==================== App ==================== */
export default function App() {
  const [themes, setThemes] = useState<Theme[]>([]);
  const [layouts, setLayouts] = useState<Layout[]>([]);
  const [selTheme, setSelTheme] = useState<string>("");
  const [page, setPage] = useState(1);
  const [avoid, setAvoid] = useState(true);
  const [canvas, setCanvas] = useState<string>("抖音全屏 9:20");
  const [zoom, setZoom] = useState(45);
  const [loading, setLoading] = useState(false);
  const [dark, setDark] = useState(false);
  const [renderKey, setRenderKey] = useState(0);
  // P0-1: 排版参数受控
  const [params, setParams] = useState<Record<string, number>>({
    margin: 58, font_song: 36, row_h: 44, sec_gap: 26,
  });

  useEffect(() => {
    fetch("/api/themes").then(r => r.json()).then((d: Theme[]) => {
      setThemes(d);
      if (d.length && !selTheme) setSelTheme(d[0].name);
    });
    fetch("/api/layouts").then(r => r.json()).then(setLayouts);
  }, []);

  const maxPage = layouts.find(l => l.id === "grid-wrap")?.pages ?? 2;
  const paramsQuery = Object.entries(params)
    .map(([k, v]) => `&${k}=${v}`)
    .join("");
  const previewSrc = selTheme
    ? `/api/render?theme=${encodeURIComponent(selTheme)}&page=${page}&canvas=${encodeURIComponent(canvas)}&avoid=${avoid}${paramsQuery}&t=${renderKey}`
    : "";
  const activeTheme = themes.find(t => t.name === selTheme);
  const activeLayout = layouts.find(l => l.id === "grid-wrap");

  return (
    <div className={`flex h-screen w-screen overflow-hidden font-sans transition-colors duration-500 ${dark ? "bg-zinc-900 text-zinc-200" : "bg-background text-foreground"}`}>
      {/* ===== paper texture (light mode) ===== */}
      {!dark && (
        <>
          <div className="fixed inset-0 pointer-events-none z-0 opacity-[0.028]" style={{
            backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='160' height='160' filter='url(%23n)'/%3E%3C/svg%3E")`,
          }} />
          <div className="fixed inset-0 pointer-events-none z-0" style={{
            background: "radial-gradient(1200px 500px at 70% -10%, rgba(47,143,122,0.05), transparent 60%), radial-gradient(900px 420px at 10% 110%, rgba(217,118,79,0.045), transparent 60%)",
          }} />
        </>
      )}

      {/* ========== SIDE NAV ========== */}
      <nav className={`relative z-10 flex w-16 shrink-0 flex-col items-center gap-1 py-4 border-r transition-colors duration-500 ${dark ? "bg-zinc-800/50 border-zinc-700/50" : "bg-card border-border"}`}>
        <div className="mb-5 flex h-10 w-10 items-center justify-center rounded-xl shadow-md" style={{
          background: "linear-gradient(150deg, var(--color-primary), var(--color-primary-strong))",
          boxShadow: "var(--shadow-primary)",
        }}>
          <span className="text-white">{Icon.music}</span>
        </div>
        {navItems.map(item => (
          <button
            key={item.id}
            title={item.label}
            className={`relative flex h-10 w-10 items-center justify-center rounded-xl transition-all duration-200 group ${item.id === "workspace"
              ? (dark ? "bg-emerald-500/20 text-emerald-400" : "bg-primary-soft text-primary")
              : (dark ? "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-700/50" : "text-muted-foreground hover:text-foreground hover:bg-muted")
            }`}
          >
            {item.icon}
            <span className="absolute left-14 px-2.5 py-1 rounded-lg text-xs font-medium whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none shadow-md"
              style={{
                background: dark ? "rgba(39,39,42,0.95)" : "var(--color-card)",
                color: dark ? "#e4e4e7" : "var(--color-card-foreground)",
                border: `1px solid ${dark ? "rgba(255,255,255,0.08)" : "var(--color-border)"}`,
              }}
            >{item.label}</span>
          </button>
        ))}

        <div className="mt-auto flex flex-col items-center gap-1">
          <button onClick={() => setDark(d => !d)} title="切换亮/暗"
            className={`flex h-10 w-10 items-center justify-center rounded-xl transition-all duration-200 ${dark ? "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-700/50" : "text-muted-foreground hover:text-foreground hover:bg-muted"}`}
          >{Icon.sun}</button>
          <button title="设置"
            className={`flex h-10 w-10 items-center justify-center rounded-xl transition-all duration-200 ${dark ? "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-700/50" : "text-muted-foreground hover:text-foreground hover:bg-muted"}`}
          >{Icon.settings}</button>
        </div>
      </nav>

      {/* ========== MAIN AREA ========== */}
      <div className="relative z-10 flex flex-1 flex-col overflow-hidden">
        {/* header */}
        <header className={`flex h-11 shrink-0 items-center gap-5 border-b px-5 text-[13px] transition-colors duration-500 ${dark ? "border-zinc-700/50 text-zinc-500" : "border-border text-muted-foreground"}`}>
          <span className={`font-serif text-[15px] font-semibold tracking-wide ${dark ? "text-zinc-200" : "text-foreground"}`}>歌单海报</span>
          <span className={`h-4 w-px ${dark ? "bg-zinc-700/50" : "bg-border"}`}></span>
          <span>{themes.length} 个主题 · {maxPage} 页</span>
        </header>

        <div className="flex flex-1 overflow-hidden">
          {/* ===== LEFT: theme list ===== */}
          <aside className={`w-64 shrink-0 border-r overflow-y-auto transition-colors duration-500 ${dark ? "border-zinc-700/50 bg-zinc-800/30" : "border-border"}`}>
            <div className="px-4 pt-4 pb-2">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">主题 · {themes.length}</p>
            </div>
            <div className="px-3 pb-4 space-y-2">
              {themes.map(t => (
                <button
                  key={t.name}
                  onClick={() => { setSelTheme(t.name); setPage(1); }}
                  className={`w-full text-left rounded-xl overflow-hidden transition-all duration-200 group ${selTheme === t.name
                    ? (dark ? "ring-2 ring-emerald-400 ring-offset-1 ring-offset-zinc-900" : "ring-2 ring-primary ring-offset-1 ring-offset-background")
                    : "hover:ring-1 hover:ring-border"
                  }`}
                >
                  <div className={`aspect-[9/16] relative overflow-hidden ${dark ? "bg-zinc-800" : "bg-muted"}`}>
                    <img src={`/bg/${encodeURIComponent(t.name)}/${t.backgrounds["1"]}`}
                      alt={t.name} className="w-full h-full object-cover object-bottom opacity-90 group-hover:opacity-100 transition-opacity" loading="lazy" />
                    <div className="absolute inset-0 bg-gradient-to-t from-black/40 via-transparent to-transparent" />
                  </div>
                  <div className={`px-3 py-2.5 border-t ${dark ? "bg-zinc-800/80 border-zinc-700/50" : "bg-card border-border"}`}>
                    <p className={`text-[13px] font-medium truncate ${dark ? "text-zinc-200" : "text-card-foreground"}`}>{t.name}</p>
                    <p className="text-[11px] text-muted-foreground mt-0.5 truncate">{t.notes || t.prefix}</p>
                  </div>
                </button>
              ))}
            </div>
          </aside>

          {/* ===== CENTER: preview ===== */}
          <main className="flex-1 flex flex-col items-center justify-center relative overflow-hidden">
            {/* toolbar */}
            <div className="absolute top-4 left-4 right-4 flex items-center justify-between z-10">
              <div className={`flex items-center gap-1.5 rounded-xl px-3 py-2 shadow-sm transition-colors duration-500 ${dark ? "bg-zinc-800/80 border border-zinc-700/50" : "bg-card border border-border"}`}>
                {Array.from({ length: maxPage }, (_, i) => (
                  <button key={i} onClick={() => setPage(i + 1)}
                    className={`w-8 h-8 rounded-lg text-xs font-medium transition-all ${page === i + 1
                      ? (dark ? "bg-emerald-500 text-white" : "bg-primary text-primary-foreground")
                      : (dark ? "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700/50" : "text-muted-foreground hover:text-foreground hover:bg-muted")
                    }`}
                  >{i + 1}</button>
                ))}
                <span className={`w-px h-5 mx-1 ${dark ? "bg-zinc-700" : "bg-border"}`} />
                <label className="flex items-center gap-1.5 text-xs cursor-pointer select-none text-muted-foreground">
                  <input type="checkbox" checked={avoid} onChange={e => setAvoid(e.target.checked)}
                    className={`w-3.5 h-3.5 rounded ${dark ? "accent-emerald-400" : "accent-primary"}`} />
                  避让
                </label>
              </div>

              <div className="flex items-center gap-2">
                <select value={canvas} onChange={e => setCanvas(e.target.value)}
                  className={`rounded-lg px-3 py-2 text-xs outline-none appearance-none cursor-pointer transition-colors duration-500 ${dark ? "bg-zinc-800/80 border border-zinc-700/50 text-zinc-300" : "bg-card border border-border text-foreground shadow-sm"}`}>
                  {CANVAS_OPTIONS.map(c => <option key={c} value={c}>{c}</option>)}
                </select>

                <div className={`flex items-center gap-1 rounded-lg px-2 py-1.5 shadow-sm transition-colors duration-500 ${dark ? "bg-zinc-800/80 border border-zinc-700/50" : "bg-card border border-border"}`}>
                  <button onClick={() => setZoom(z => Math.max(15, z - 10))}
                    className="w-6 h-6 rounded flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                  ><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="5" y1="12" x2="19" y2="12"/></svg></button>
                  <span className="text-[11px] text-muted-foreground w-10 text-center tabular-nums">{zoom}%</span>
                  <button onClick={() => setZoom(z => Math.min(150, z + 10))}
                    className="w-6 h-6 rounded flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                  ><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg></button>
                </div>
              </div>
            </div>

            {/* preview image */}
            <div className="flex-1 w-full flex items-center justify-center p-6 pt-20">
              {selTheme ? (
                <div className="relative rounded-2xl overflow-hidden transition-all duration-300"
                  style={{
                    width: `${(1080 * zoom) / 100}px`,
                    maxHeight: "calc(100vh - 120px)",
                    boxShadow: "0 4px 12px rgba(35,55,48,0.06), 0 24px 56px rgba(35,55,48,0.13)",
                  }}>
                  <img key={`${selTheme}-${page}-${avoid}-${canvas}-${renderKey}`}
                    src={previewSrc} alt={selTheme}
                    className="w-full object-contain"
                    onLoad={() => setLoading(false)}
                    onError={() => setLoading(false)} />
                  {loading && (
                    <div className="absolute inset-0 bg-background/30 flex items-center justify-center">
                      <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                    </div>
                  )}
                  {avoid && canvas === "抖音全屏 9:20" && (
                    <div className="absolute right-0 border-l border-dashed border-red-400/30 pointer-events-none"
                      style={{ top: `${(1080 / 2400) * 100}%`, bottom: 0, width: `${((1080 - 940) / 1080) * 100}%` }} />
                  )}
                </div>
              ) : (
                <div className="text-center space-y-3">
                  <div className={`w-16 h-16 mx-auto rounded-2xl flex items-center justify-center text-2xl shadow-sm ${dark ? "bg-zinc-800" : "bg-muted"}`}>🎵</div>
                  <p className="text-sm text-muted-foreground">左侧选择一个主题开始预览</p>
                </div>
              )}
            </div>

            {/* bottom bar */}
            <div className={`absolute bottom-4 left-4 right-4 flex items-center justify-between rounded-2xl px-4 py-3 transition-colors duration-500 ${dark ? "bg-zinc-800/80 border border-zinc-700/50" : "bg-card border border-border shadow-sm"}`}>
              <div className="flex items-center gap-3 text-xs text-muted-foreground">
                <span>排版：<span className={dark ? "text-zinc-300" : "text-foreground"}>全行网格绕排版</span></span>
                <span className={`w-px h-4 ${dark ? "bg-zinc-700" : "bg-border"}`} />
                <span>主题：<span className={dark ? "text-zinc-300" : "text-foreground"}>{selTheme || "—"}</span></span>
                <span className={`w-px h-4 ${dark ? "bg-zinc-700" : "bg-border"}`} />
                <span>画布：<span className={dark ? "text-zinc-300" : "text-foreground"}>{canvas}</span></span>
              </div>
              <div className="flex items-center gap-2">
                {previewSrc && (
                  <a href={previewSrc} download={`${activeTheme?.prefix ?? "poster"}-p${page}.png`}
                    className="flex items-center gap-1.5 rounded-xl px-4 py-2 text-sm transition-colors cursor-pointer no-underline text-muted-foreground hover:text-foreground hover:bg-muted">
                    {Icon.download} 下载
                  </a>
                )}
                <button onClick={() => { setLoading(true); setRenderKey(k => k + 1); }}
                  className="flex items-center gap-1.5 bg-primary hover:bg-primary-strong text-primary-foreground font-medium rounded-xl px-5 py-2 text-sm transition-all active:scale-95 cursor-pointer">
                  {Icon.refresh} {loading ? "渲染中…" : "刷新预览"}
                </button>
              </div>
            </div>
          </main>

          {/* ===== RIGHT: params ===== */}
          <aside className={`w-60 shrink-0 border-l overflow-y-auto transition-colors duration-500 ${dark ? "border-zinc-700/50 bg-zinc-800/30" : "border-border"}`}>
            <div className={`px-5 py-4 border-b ${dark ? "border-zinc-700/50" : "border-border"}`}>
              <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">参数</h2>
            </div>

            <div className="px-4 py-3 space-y-5">
              <section>
                <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-2.5">画布</h3>
                <div className="space-y-2.5">
                  <label className="flex items-center justify-between text-xs text-muted-foreground">
                    预设
                    <select value={canvas} onChange={e => setCanvas(e.target.value)}
                      className={`rounded-lg px-2 py-1 text-xs outline-none cursor-pointer ${dark ? "bg-zinc-800 border-zinc-700 text-zinc-300" : "bg-muted border-border text-foreground border"}`}>
                      {CANVAS_OPTIONS.map(c => <option key={c} value={c}>{c}</option>)}
                    </select>
                  </label>
                  <label className="flex items-center justify-between text-xs text-muted-foreground">
                    尺寸 <span className="tabular-nums text-foreground">{canvas === "标准 9:16" ? "1080×1920" : "1080×2400"}</span>
                  </label>
                  <label className="flex items-center justify-between text-xs text-muted-foreground">
                    页数 <span className="tabular-nums text-foreground">{maxPage}</span>
                  </label>
                </div>
              </section>

              <section>
                <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-2.5">排版参数</h3>
                <div className="space-y-2.5">
                  {([{ label: "边距", key: "margin" }, { label: "歌名字号", key: "font_song" }, { label: "行高", key: "row_h" }, { label: "区块间距", key: "sec_gap" }] as const)
                    .map(p => (
                      <label key={p.key} className="flex items-center justify-between text-xs text-muted-foreground">
                        {p.label}
                        <input type="number" value={params[p.key]}
                          onChange={e => {
                            const v = parseInt(e.target.value, 10);
                            if (!isNaN(v)) setParams(prev => ({ ...prev, [p.key]: v }));
                          }}
                          className={`w-16 rounded-lg px-2 py-1 text-xs outline-none text-right ${dark ? "bg-zinc-800 border-zinc-700 text-zinc-300" : "bg-muted border-border text-foreground border"}`} />
                      </label>
                    ))}
                </div>
              </section>

              {activeTheme && (
                <section>
                  <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-2.5">当前主题</h3>
                  <div className={`rounded-xl p-3 space-y-1.5 text-xs shadow-sm ${dark ? "bg-zinc-800/80 border border-zinc-700/50" : "bg-card border border-border"}`}>
                    <p className="font-medium text-foreground">{activeTheme.name}</p>
                    <p className="text-muted-foreground break-all leading-relaxed">{activeTheme.notes || "无备注"}</p>
                    <p className="text-muted-foreground">水印修正：{activeTheme.watermark_fix ? "是" : "否"}</p>
                  </div>
                </section>
              )}
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
