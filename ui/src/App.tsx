import { useState, useEffect } from "react";
import type { Theme, Layout, SongsData, ParamSpec, Settings } from "./types";
import { CANVAS_OPTIONS } from "./types";
import { Icon } from "./icons";
import LibraryView from "./views/LibraryView";
import LearningView from "./views/LearningView";
import SettingsView from "./views/SettingsView";
import ExportDialog from "./components/ExportDialog";

const navItems = [
  { id: "workspace", label: "海报工作台", icon: Icon.layout },
  { id: "library", label: "歌曲库", icon: Icon.list },
  { id: "learning", label: "学歌管理", icon: Icon.book },
  { id: "themes", label: "主题管理", icon: Icon.palette, soon: true },
  { id: "presets", label: "场景预设", icon: Icon.bookmark, soon: true },
  { id: "history", label: "导出历史", icon: Icon.history, soon: true },
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
  // P0-1: 排版参数受控（初始为 grid-wrap 默认值，ParamSpec 拉取后合并）
  const [params, setParams] = useState<Record<string, number>>({
    margin: 58, font_song: 36, row_h: 44, sec_gap: 26,
  });
  // Phase 2: 参数面板动态渲染（对接 /api/layouts/{id}/params 的 ParamSpec 契约）
  const [paramSpecs, setParamSpecs] = useState<ParamSpec[]>([]);
  // Phase 2: 视图路由
  const [view, setView] = useState<string>("workspace");
  // Phase 2: 导出对话框
  const [exportDialogOpen, setExportDialogOpen] = useState(false);
  const [lastRenderMs, setLastRenderMs] = useState<number | null>(null);
  // Phase 2: 状态栏歌曲统计（LibraryView 上报）
  const [songStats, setSongStats] = useState<{ active: number; draft: number } | null>(null);
  // 歌曲编辑对话框开合状态（LibraryView 上报，用于快捷键避让）
  const [libDialogOpen, setLibDialogOpen] = useState(false);
  // Phase 2: 启动恢复
  const [restored, setRestored] = useState(false);

  // Phase 2: 启动恢复
  useEffect(() => {
    try {
      const saved = localStorage.getItem("gp-workspace");
      if (saved) {
        const s = JSON.parse(saved);
        if (s.selTheme) setSelTheme(s.selTheme);
        if (s.page) setPage(s.page);
        if (s.canvas) setCanvas(s.canvas);
        if (s.avoid !== undefined) setAvoid(s.avoid);
        if (s.params) setParams(s.params);
      }
    } catch { /* ignore */ }
    setRestored(true);
  }, []);

  // Phase 2: 持久化到 localStorage
  useEffect(() => {
    if (!restored) return;
    localStorage.setItem("gp-workspace", JSON.stringify({
      selTheme, page, canvas, avoid, params,
    }));
  }, [selTheme, page, canvas, avoid, params, restored]);

  useEffect(() => {
    // 先拉设置：无 localStorage 恢复记录时应用默认画布/默认主题
    const savedWorkspace = localStorage.getItem("gp-workspace");
    fetch("/api/settings").then(r => r.json()).then((st: Settings) => {
      if (!savedWorkspace && st.default_canvas) setCanvas(st.default_canvas);
      fetch("/api/themes").then(r => r.json()).then((d: Theme[]) => {
        setThemes(d);
        if (d.length && !selTheme) {
          const def = !savedWorkspace && d.find(t => t.name === st.default_theme);
          setSelTheme(def ? def.name : d[0].name);
        }
      });
    });
    fetch("/api/layouts").then(r => r.json()).then(setLayouts);
    // Phase 2: 状态栏歌曲统计
    fetch("/api/songs/list").then(r => r.json()).then((d: SongsData) =>
      setSongStats({ active: d.active, draft: d.draft }));
    // Phase 2: 拉取排版参数描述（ParamSpec），动态生成参数面板；
    // 已有参数值（含 localStorage 恢复的）优先，缺的用插件默认值补齐
    fetch("/api/layouts/grid-wrap/params").then(r => r.json()).then((specs: ParamSpec[]) => {
      setParamSpecs(specs);
      setParams(prev => {
        const merged = { ...prev };
        for (const s of specs) if (merged[s.key] === undefined) merged[s.key] = s.default;
        return merged;
      });
    });
  }, []);

  // Phase 2: 参数防抖（300ms）
  const [debouncedParams, setDebouncedParams] = useState(params);
  useEffect(() => {
    const t = setTimeout(() => setDebouncedParams(params), 300);
    return () => clearTimeout(t);
  }, [params]);

  const maxPage = layouts.find(l => l.id === "grid-wrap")?.pages ?? 2;
  const paramsQuery = Object.entries(debouncedParams)
    .map(([k, v]) => `&${k}=${v}`)
    .join("");
  const previewSrc = selTheme
    ? `/api/render?theme=${encodeURIComponent(selTheme)}&page=${page}&canvas=${encodeURIComponent(canvas)}&avoid=${avoid}${paramsQuery}&t=${renderKey}`
    : "";
  const activeTheme = themes.find(t => t.name === selTheme);

  // P0-1: 预览加载反馈——src 任何变化（切主题/翻页/调参/刷新）都进入 loading；
  // 失败进入错误态给出重试入口，不再静默白屏
  const [previewError, setPreviewError] = useState(false);
  useEffect(() => {
    if (previewSrc) { setLoading(true); setPreviewError(false); }
  }, [previewSrc]);

  // Phase 2: 快捷键（设计文档 §6.8 的 Web 落地子集）
  // Ctrl/⌘+E 导出 · Ctrl/⌘+R 刷新预览 · ←→ 翻页 · Ctrl/⌘+1~7 切主题 ·
  // Ctrl/⌘+, 设置。输入控件聚焦时不拦截；Esc 由各对话框内部处理。
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey;
      const tag = (e.target as HTMLElement)?.tagName;
      const typing = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
      if (e.key === "Escape" || typing) return;

      if (mod && e.key === "e") {
        e.preventDefault();
        setExportDialogOpen(true);
      } else if (mod && e.key === "r") {
        e.preventDefault();
        setLoading(true); setRenderKey(k => k + 1);
      } else if (mod && e.key === ",") {
        e.preventDefault();
        setView("settings");
      } else if (mod && /^[1-7]$/.test(e.key)) {
        e.preventDefault();
        const t = themes[parseInt(e.key, 10) - 1];
        if (t) { setSelTheme(t.name); setPage(1); }
      } else if (!mod && view === "workspace" && !exportDialogOpen && !libDialogOpen) {
        if (e.key === "ArrowLeft") setPage(p => Math.max(1, p - 1));
        else if (e.key === "ArrowRight") setPage(p => Math.min(maxPage, p + 1));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [themes, view, maxPage, exportDialogOpen, libDialogOpen]);

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
            title={item.soon ? `${item.label} · 敬请期待` : item.label}
            onClick={() => !item.soon && setView(item.id)}
            disabled={!!item.soon}
            className={`relative flex h-10 w-10 items-center justify-center rounded-xl transition-all duration-200 group ${item.id === view
              ? (dark ? "bg-emerald-500/20 text-emerald-400" : "bg-primary-soft text-primary")
              : item.soon
                ? (dark ? "text-zinc-700 cursor-not-allowed" : "text-muted-foreground/40 cursor-not-allowed")
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
            >{item.soon ? `${item.label} · 敬请期待` : item.label}</span>
          </button>
        ))}

        <div className="mt-auto flex flex-col items-center gap-1">
          <button onClick={() => setDark(d => !d)} title="切换亮/暗"
            className={`flex h-10 w-10 items-center justify-center rounded-xl transition-all duration-200 ${dark ? "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-700/50" : "text-muted-foreground hover:text-foreground hover:bg-muted"}`}
          >{Icon.sun}</button>
          <button onClick={() => setView("settings")} title="设置"
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
          <span className={`h-4 w-px ${dark ? "bg-zinc-700/50" : "bg-border"}`}></span>
          <span>已会 {songStats?.active ?? "—"} · 未会 {songStats?.draft ?? "—"}</span>
          {lastRenderMs !== null && (
            <span className="ml-auto tabular-nums">渲染 {Math.round(lastRenderMs)}ms/张</span>
          )}
        </header>

        <div className="flex flex-1 overflow-hidden">
          {/* ===== LEFT: theme list（仅工作台视图显示） ===== */}
          {view === "workspace" && (
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
                    {/* P0-2: 缩略图端点（宽 360 JPEG），不再直出多 MB 原图 */}
                    <img src={`/api/thumb/${encodeURIComponent(t.name)}`}
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
          )}

          {/* ===== CENTER: preview ===== */}
          {view === "workspace" && (
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
                <label title="避开抖音右侧评论/礼物互动区（9:20 画布右下安全区）"
                  className="flex items-center gap-1.5 text-xs cursor-pointer select-none text-muted-foreground">
                  <input type="checkbox" checked={avoid} onChange={e => setAvoid(e.target.checked)}
                    className={`w-3.5 h-3.5 rounded ${dark ? "accent-emerald-400" : "accent-primary"}`} />
                  避让互动区
                </label>
              </div>

              <div className="flex items-center gap-2">
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
            <div className="flex-1 w-full flex items-center justify-center p-6 pt-20"
              onWheel={(e) => {
                if (e.ctrlKey || e.metaKey) {
                  e.preventDefault();
                  const delta = e.deltaY > 0 ? -5 : 5;
                  setZoom(z => Math.max(15, Math.min(150, z + delta)));
                }
              }}
              style={{ touchAction: "none" }}>
              {selTheme ? (
                <div className="relative rounded-2xl overflow-hidden transition-all duration-300"
                  style={{
                    width: `${(1080 * zoom) / 100}px`,
                    maxHeight: "calc(100vh - 120px)",
                    aspectRatio: canvas === "标准 9:16" ? "9 / 16" : "9 / 20",
                    boxShadow: "0 4px 12px rgba(35,55,48,0.06), 0 24px 56px rgba(35,55,48,0.13)",
                  }}>
                  {previewError ? (
                    /* P0-1: 渲染失败兜底——错误占位 + 重试，不再静默白屏 */
                    <div className={`absolute inset-0 flex flex-col items-center justify-center gap-3 ${dark ? "bg-zinc-800" : "bg-muted"}`}>
                      <p className="text-sm text-muted-foreground">预览渲染失败</p>
                      <button onClick={() => { setPreviewError(false); setLoading(true); setRenderKey(k => k + 1); }}
                        className="flex items-center gap-1.5 rounded-xl px-4 py-2 text-sm bg-primary hover:bg-primary-strong text-primary-foreground font-medium transition-all active:scale-95 cursor-pointer">
                        {Icon.refresh} 重试
                      </button>
                    </div>
                  ) : (
                    <img key={`${selTheme}-${page}-${avoid}-${canvas}-${renderKey}`}
                      src={previewSrc} alt={selTheme}
                      className="w-full object-contain"
                      onLoad={() => setLoading(false)}
                      onError={() => { setLoading(false); setPreviewError(true); }} />
                  )}
                  {loading && !previewError && (
                    <div className={`absolute inset-0 flex flex-col items-center justify-center gap-2.5 ${dark ? "bg-zinc-800/60" : "bg-background/60"}`}>
                      <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                      <p className="text-xs text-muted-foreground">渲染中…</p>
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
                <span className={`hidden xl:inline ml-2 ${dark ? "text-zinc-600" : "text-muted-foreground/60"}`}>⌘E 导出 · ⌘R 刷新 · ←→ 翻页 · ⌘1~7 切主题</span>
              </div>
              <div className="flex items-center gap-2">
                {previewSrc && (
                  <a href={previewSrc} download={`${activeTheme?.prefix ?? "poster"}-p${page}.png`}
                    className="flex items-center gap-1.5 rounded-xl px-4 py-2 text-sm transition-colors cursor-pointer no-underline text-muted-foreground hover:text-foreground hover:bg-muted">
                    {Icon.download} 下载
                  </a>
                )}
                <button onClick={() => setExportDialogOpen(true)}
                  className="flex items-center gap-1.5 rounded-xl px-4 py-2 text-sm transition-colors cursor-pointer bg-emerald-600 hover:bg-emerald-700 text-white font-medium">
                  {Icon.download} 导出…
                </button>
                <button onClick={() => { setLoading(true); setRenderKey(k => k + 1); }}
                  className="flex items-center gap-1.5 bg-primary hover:bg-primary-strong text-primary-foreground font-medium rounded-xl px-5 py-2 text-sm transition-all active:scale-95 cursor-pointer">
                  {Icon.refresh} {loading ? "渲染中…" : "刷新预览"}
                </button>
              </div>
            </div>
          </main>
          )}

          {/* ===== 歌曲库视图 ===== */}
          {view === "library" && (
            <LibraryView dark={dark}
              onStatsChange={setSongStats}
              onEditTargetChange={setLibDialogOpen} />
          )}

          {/* ===== 设置视图 ===== */}
          {view === "settings" && (
            <SettingsView dark={dark} themes={themes} />
          )}

          {/* ===== 学歌管理视图 ===== */}
          {view === "learning" && (
            <LearningView dark={dark}
              onStatsChange={setSongStats}
              onEditTargetChange={setLibDialogOpen} />
          )}

          {/* ===== RIGHT: params（仅工作台视图显示） ===== */}
          {view === "workspace" && (
          <aside className={`w-60 shrink-0 border-l overflow-y-auto transition-colors duration-500 ${dark ? "border-zinc-700/50 bg-zinc-800/30" : "border-border"}`}>
            <div className={`px-5 py-4 border-b ${dark ? "border-zinc-700/50" : "border-border"}`}>
              <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">参数</h2>
            </div>

            <div className="px-4 py-3 space-y-3">
              {/* 折叠：输出参数（默认展开） */}
              <details open className="group">
                <summary className={`flex items-center justify-between cursor-pointer py-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground select-none`}>
                  输出参数
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="transition-transform group-open:rotate-180"><polyline points="6 9 12 15 18 9"/></svg>
                </summary>
                <div className="mt-2.5 space-y-2.5">
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
              </details>

              {/* 折叠：布局参数（默认展开） */}
              <details open className="group">
                <summary className="flex items-center justify-between cursor-pointer py-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground select-none">
                  布局参数
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="transition-transform group-open:rotate-180"><polyline points="6 9 12 15 18 9"/></svg>
                </summary>
                <div className="mt-2.5 space-y-2.5">
                  {paramSpecs.length === 0 && (
                    <p className="text-xs text-muted-foreground">参数加载中…</p>
                  )}
                  {paramSpecs.map(p => (
                    <label key={p.key} className="flex items-center justify-between text-xs text-muted-foreground">
                      {p.label}
                      {p.kind === "int" && (
                        <input type="number" value={params[p.key] ?? p.default}
                          min={p.min ?? undefined} max={p.max ?? undefined}
                          onChange={e => {
                            const v = parseInt(e.target.value, 10);
                            if (!isNaN(v)) setParams(prev => ({ ...prev, [p.key]: v }));
                          }}
                          className={`w-16 rounded-lg px-2 py-1 text-xs outline-none text-right ${dark ? "bg-zinc-800 border-zinc-700 text-zinc-300" : "bg-muted border-border text-foreground border"}`} />
                      )}
                      {p.kind === "bool" && (
                        <input type="checkbox" checked={!!params[p.key]}
                          onChange={e => setParams(prev => ({ ...prev, [p.key]: e.target.checked ? 1 : 0 }))}
                          className={`w-3.5 h-3.5 rounded ${dark ? "accent-emerald-400" : "accent-primary"}`} />
                      )}
                      {p.kind === "choice" && (
                        <select value={params[p.key] ?? p.default}
                          onChange={e => setParams(prev => ({ ...prev, [p.key]: Number(e.target.value) }))}
                          className={`rounded-lg px-2 py-1 text-xs outline-none cursor-pointer ${dark ? "bg-zinc-800 border-zinc-700 text-zinc-300" : "bg-muted border-border text-foreground border"}`}>
                          {(p.choices ?? []).map(c => <option key={c} value={c}>{c}</option>)}
                        </select>
                      )}
                    </label>
                  ))}
                </div>
              </details>

              {/* 折叠：当前主题（默认折叠） */}
              {activeTheme && (
              <details className="group">
                <summary className="flex items-center justify-between cursor-pointer py-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground select-none">
                  当前主题
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="transition-transform group-open:rotate-180"><polyline points="6 9 12 15 18 9"/></svg>
                </summary>
                <div className={`mt-2.5 rounded-xl p-3 space-y-1.5 text-xs shadow-sm ${dark ? "bg-zinc-800/80 border border-zinc-700/50" : "bg-card border border-border"}`}>
                  <p className="font-medium text-foreground">{activeTheme.name}</p>
                  <p className="text-muted-foreground break-all leading-relaxed">{activeTheme.notes || "无备注"}</p>
                  <p className="text-muted-foreground">水印修正：{activeTheme.watermark_fix ? "是" : "否"}</p>
                </div>
              </details>
              )}
            </div>
          </aside>
          )}
        </div>
      </div>

      {/* ========== 导出对话框（常挂载，open 控制显隐） ========== */}
      <ExportDialog
        dark={dark}
        open={exportDialogOpen}
        onClose={() => setExportDialogOpen(false)}
        selTheme={selTheme}
        page={page}
        maxPage={maxPage}
        themesCount={themes.length}
        canvas={canvas}
        avoid={avoid}
        paramsQuery={paramsQuery}
        lastRenderMs={lastRenderMs}
        onRendered={setLastRenderMs}
      />
    </div>
  );
}
