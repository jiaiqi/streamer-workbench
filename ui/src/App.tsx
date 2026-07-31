import { useState, useEffect } from "react";
import type { Theme, Layout, SongsData, ParamSpec, Settings } from "./types";
import { CANVAS_OPTIONS } from "./types";
import { Icon } from "./icons";
import LibraryView from "./views/LibraryView";
import LearningView from "./views/LearningView";
import LiveView from "./views/LiveView";
import SettingsView from "./views/SettingsView";
import ExportDialog from "./components/ExportDialog";
import PreviewCrossfade from "./components/PreviewCrossfade";
import { DEFAULT_APPEARANCE, normalizeAppearance, resolveAppearance } from "./appearance";
import { apiRequest } from "./api/client";
import type { AppearanceSettings } from "./types";
import WorkspacePosterBridge from "./posters/WorkspacePosterBridge";

const navItems = [
  { id: "workspace", label: "海报工作台", icon: Icon.layout },
  { id: "library", label: "歌曲库", icon: Icon.list },
  { id: "learning", label: "学歌管理", icon: Icon.book },
  { id: "live", label: "直播", icon: Icon.live },
  // 主题管理/场景预设/导出历史不作占位导航：按路线图改为工作台内资源面板时再上线
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
  const [appearance, setAppearance] = useState<AppearanceSettings>(DEFAULT_APPEARANCE);
  const [savedAppearance, setSavedAppearance] = useState<AppearanceSettings>(DEFAULT_APPEARANCE);
  const [appearanceSaving, setAppearanceSaving] = useState(false);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [systemDark, setSystemDark] = useState(() => window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false);
  const [resourceError, setResourceError] = useState("");
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
  const dark = resolveAppearance(appearance.appearanceMode, systemDark) === "dark";

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const update = () => setSystemDark(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

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
    let active = true;
    const load = async () => {
      try {
        const savedWorkspace = localStorage.getItem("gp-workspace");
        const [st, themeData, layoutData, songs, specs] = await Promise.all([
          apiRequest<Settings>("/api/settings"),
          apiRequest<Theme[]>("/api/themes"),
          apiRequest<Layout[]>("/api/layouts"),
          apiRequest<SongsData>("/api/songs/list"),
          apiRequest<ParamSpec[]>("/api/layouts/grid-wrap/params"),
        ]);
        if (!active) return;
        const nextAppearance = normalizeAppearance(st);
        setAppearance(nextAppearance);
        setSavedAppearance(nextAppearance);
        if (!savedWorkspace && st.default_canvas) setCanvas(st.default_canvas);
        setThemes(themeData);
        setLayouts(layoutData);
        setSongStats({ active: songs.active, draft: songs.draft });
        if (themeData.length && !selTheme) {
          const defaultTheme = savedWorkspace ? undefined : themeData.find(theme => theme.name === st.default_theme);
          setSelTheme(defaultTheme?.name ?? themeData[0].name);
        }
        setParamSpecs(specs);
        setParams(previous => {
          const merged = { ...previous };
          for (const spec of specs) if (merged[spec.key] === undefined) merged[spec.key] = spec.default;
          return merged;
        });
        setResourceError("");
      } catch (reason) {
        if (active) setResourceError(reason instanceof Error ? reason.message : "工作台资源加载失败");
      }
    };
    load();
    return () => { active = false; };
  }, []);

  const saveAppearance = async (next: AppearanceSettings) => {
    if (appearanceSaving || settingsSaving || view === "settings") return;
    const previous = savedAppearance;
    setAppearance(next);
    setAppearanceSaving(true);
    try {
      await apiRequest("/api/settings", { method: "POST", body: next });
      setSavedAppearance(next);
      setResourceError("");
    } catch {
      setAppearance(previous);
      setResourceError("外观保存失败，已恢复为上次保存状态。");
    } finally {
      setAppearanceSaving(false);
    }
  };

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
  // P1 R1a.8 预览缓存治理：URL 仅含结构化输入；浏览器可对相同输入缓存。
  // 「强制重新渲染」的契约改为「改变结构化输入」或调用 reload()；
  // renderKey + 1 触发刷新时，通过 settings.themeIndex 之外的 useState 副作用让
  // <img> 直接重新挂载（key）实现 —— 这里我们手动用 React key 解决。
  const previewSrc = selTheme
    ? `/api/render?theme=${encodeURIComponent(selTheme)}&page=${page}&canvas=${encodeURIComponent(canvas)}&avoid=${avoid}${paramsQuery}`
    : "";
  // previewKey 在结构化输入变化时 = 0；renderKey 增加时 = renderKey（强制重挂载）。
  const previewKey = renderKey > 0 ? `k${renderKey}` : "stable";
  const activeTheme = themes.find(t => t.name === selTheme);

  // P0-1: 预览加载反馈——src 任何变化（切主题/翻页/调参/刷新）都进入 loading；
  // 失败进入错误态给出重试入口，不再静默白屏
  const [previewError, setPreviewError] = useState(false);
  // crossfade POC：是否已有可保持的旧帧（有旧帧时加载新图不再盖 spinner）
  const [hasFrame, setHasFrame] = useState(false);
  useEffect(() => {
    if (previewSrc) { setLoading(true); setPreviewError(false); }
  }, [previewSrc]);

  // Phase 2: 快捷键（设计文档 §6.8 的 Web 落地子集）
  // Ctrl/⌘+E 导出 · Ctrl/⌘+R 刷新预览 · ←→ 翻页 · Ctrl/⌘+1~7 切主题 ·
  // Ctrl/⌘+, 设置。输入控件聚焦时不拦截；Esc 由各对话框内部处理。
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (appearanceSaving || settingsSaving) return;
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
  }, [themes, view, maxPage, exportDialogOpen, libDialogOpen, appearanceSaving, settingsSaving]);

  return (
    <div className="app-shell flex h-screen w-screen overflow-hidden font-sans" data-mode={dark ? "dark" : "light"} data-accent={appearance.applicationAccentId}>
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
            aria-label={item.label}
            aria-current={item.id === view ? "page" : undefined}
            disabled={appearanceSaving || settingsSaving}
            onClick={() => setView(item.id)}
            className={`relative flex h-11 w-11 items-center justify-center rounded-xl transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-45 group ${item.id === view
              ? "bg-primary-soft text-primary"
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
          <button onClick={() => saveAppearance({ ...appearance, appearanceMode: dark ? "light" : "dark" })}
            disabled={appearanceSaving || settingsSaving || view === "settings"}
            aria-busy={appearanceSaving}
            title={view === "settings" ? "请在设置页调整外观" : dark ? "切换到画廊白" : "切换到暗色舞台"}
            className={`flex h-11 w-11 items-center justify-center rounded-xl transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-45 ${dark ? "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-700/50" : "text-muted-foreground hover:text-foreground hover:bg-muted"}`}
          >{Icon.sun}</button>
          <button onClick={() => setView("settings")} title="设置"
            disabled={appearanceSaving || settingsSaving}
            className={`flex h-11 w-11 items-center justify-center rounded-xl transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-45 ${dark ? "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-700/50" : "text-muted-foreground hover:text-foreground hover:bg-muted"}`}
          >{Icon.settings}</button>
        </div>
      </nav>

      {/* ========== MAIN AREA ========== */}
      <div className="relative z-10 flex flex-1 flex-col overflow-hidden">
        {/* header */}
        <header className={`flex h-11 shrink-0 items-center gap-5 border-b px-5 text-[13px] transition-colors duration-500 ${dark ? "border-zinc-700/50 text-zinc-500" : "border-border text-muted-foreground"}`}>
          <span className={`font-serif text-[15px] font-semibold tracking-wide whitespace-nowrap ${dark ? "text-zinc-200" : "text-foreground"}`}>主播工作台</span>
          <span className={`h-4 w-px hidden min-[800px]:block ${dark ? "bg-zinc-700/50" : "bg-border"}`}></span>
          <span className="hidden min-[800px]:inline whitespace-nowrap">{themes.length} 个主题 · {maxPage} 页</span>
          <span className={`h-4 w-px hidden min-[800px]:block ${dark ? "bg-zinc-700/50" : "bg-border"}`}></span>
          <span className="hidden min-[800px]:inline whitespace-nowrap">已会 {songStats?.active ?? "—"} · 未会 {songStats?.draft ?? "—"}</span>
          {lastRenderMs !== null && (
            <span className="ml-auto tabular-nums hidden min-[800px]:inline">渲染 {Math.round(lastRenderMs)}ms/张</span>
          )}
          {resourceError && <button className="resource-alert" type="button" onClick={() => window.location.reload()} title={resourceError}>资源异常 · 重试</button>}
        </header>

        <div className="flex flex-1 overflow-hidden">
          {/* ===== LEFT: theme list（仅工作台视图显示，<800px 隐藏） ===== */}
          {view === "workspace" && (
          <aside className={`w-64 shrink-0 border-r overflow-y-auto transition-colors duration-500 max-[800px]:hidden ${dark ? "border-zinc-700/50 bg-zinc-800/30" : "border-border"}`}>
            {/* P1 R1a.5 海报文档区 + 歌曲来源（独立 hook 状态机） */}
            <WorkspacePosterBridge
              dark={dark}
              availableThemeNames={themes.map(t => t.name)}
              onThemeSelect={(name) => { setSelTheme(name); setPage(1); }}
              onCanvasSelect={(id) => setCanvas(id)}
            />
            <div className="px-4 pt-5 pb-3">
              <p className="eyebrow">策展资源</p>
              <h2 className="panel-title">海报主题</h2>
              <p className="panel-copy">主题与布局独立组合。选择后实时更新中央展品。</p>
            </div>
            <div className="px-3 pb-4 space-y-2">
              {themes.length === 0 && !resourceError && <div className="panel-empty" aria-busy="true"><span className="spinner" />正在陈列主题…</div>}
              {themes.map(t => (
                <button
                  key={t.name}
                  onClick={() => { setSelTheme(t.name); setPage(1); }}
                  className={`w-full text-left rounded-xl overflow-hidden transition-all duration-200 group ${selTheme === t.name
                    ? "ring-2 ring-primary ring-offset-1 ring-offset-background"
                    : "hover:ring-1 hover:ring-border"
                  }`}
                >
                  <div className={`aspect-[9/16] relative overflow-hidden ${dark ? "bg-zinc-800" : "bg-muted"}`}>
                    {/* 缩略图加载失败兜底：显示主题名，不露 alt 破图 */}
                    <div className="absolute inset-0 flex items-center justify-center px-3 text-center text-xs text-muted-foreground">{t.name}</div>
                    {/* P0-2: 缩略图端点（宽 360 JPEG），不再直出多 MB 原图 */}
                    <img src={`/api/thumb/${encodeURIComponent(t.name)}`}
                      alt={t.name} className="relative w-full h-full object-cover object-bottom opacity-90 group-hover:opacity-100 transition-opacity" loading="lazy"
                      onError={(e) => { e.currentTarget.style.display = "none"; }} />
                    <div className="absolute inset-0 bg-gradient-to-t from-black/40 via-transparent to-transparent pointer-events-none" />
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

          {/* ===== CENTER: preview（<800px 隐藏，走移动端兜底面板） ===== */}
          {view === "workspace" && (
          <main className="workspace-gallery flex-1 flex flex-col items-center justify-center relative overflow-hidden max-[800px]:hidden">
            <div className="gallery-room-label" aria-hidden="true">独立海报 · 画廊策展台</div>
            {/* toolbar */}
            <div className="absolute top-4 left-4 right-4 flex items-center justify-between z-10">
              <div className={`flex items-center gap-1.5 rounded-xl px-3 py-2 shadow-sm transition-colors duration-500 ${dark ? "bg-zinc-800/80 border border-zinc-700/50" : "bg-card border border-border"}`}>
                {Array.from({ length: maxPage }, (_, i) => (
                  <button key={i} onClick={() => setPage(i + 1)}
                    className={`w-11 h-11 rounded-lg text-xs font-medium transition-all ${page === i + 1
                      ? "bg-primary text-primary-foreground"
                      : (dark ? "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700/50" : "text-muted-foreground hover:text-foreground hover:bg-muted")
                    }`}
                  >{i + 1}</button>
                ))}
                <span className={`w-px h-5 mx-1 ${dark ? "bg-zinc-700" : "bg-border"}`} />
                <label title="避开抖音右侧评论/礼物互动区（9:20 画布右下安全区）"
                  className="flex items-center gap-1.5 text-xs cursor-pointer select-none text-muted-foreground">
                  <input type="checkbox" checked={avoid} onChange={e => setAvoid(e.target.checked)}
                    className="w-3.5 h-3.5 rounded accent-primary" />
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
                    // max-width 由 max-height 和画布比例反推：让容器按比例缩小，不破坏避让线对齐
                    // (2026-07-30 修复: 旧 maxHeight+aspectRatio 组合在高 zoom 时容器被压扁)
                    maxWidth: canvas === "标准 9:16"
                      ? "calc((100vh - 120px) * 9 / 16)"
                      : "calc((100vh - 120px) * 9 / 20)",
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
                    /* §4.6 POC：旧图保持至新图完成再 crossfade，reduced-motion 直换 */
                    <PreviewCrossfade src={previewSrc}
                      alt={`${selTheme} 主题，第 ${page} 页预览`}
                      reloadKey={renderKey}
                      onLoaded={() => { setHasFrame(true); setLoading(false); }}
                      onFailed={() => { setLoading(false); setPreviewError(true); }} />
                  )}
                  {loading && !previewError && !hasFrame && (
                    <div className={`absolute inset-0 flex flex-col items-center justify-center gap-2.5 ${dark ? "bg-zinc-800/60" : "bg-background/60"}`}>
                      <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                      <p className="text-xs text-muted-foreground">渲染中…</p>
                    </div>
                  )}
                  {avoid && canvas === "抖音全屏 9:20" && (
                    <div className="absolute right-0 border-l-2 border-dashed border-red-400/60 pointer-events-none"
                      style={{
                        top: `${(1080 / 2400) * 100}%`,
                        bottom: 0,
                        width: `${((1080 - 940) / 1080) * 100}%`,
                        background: "linear-gradient(90deg, transparent, rgba(239,68,68,0.06))",
                      }} />
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
                  className="primary-action flex items-center gap-1.5 rounded-xl px-4 py-2 text-sm cursor-pointer">
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

          {/* ===== 移动端兜底（<800px）：不裁剪桌面三栏，引导去直播速查 ===== */}
          {view === "workspace" && (
          <div className="mobile-workspace flex-1 hidden max-[800px]:flex flex-col items-center gap-4 overflow-y-auto p-4 text-center">
            <div className="mobile-workspace-heading">
              <p className="eyebrow">轻量工作区</p>
              <h2>预览与导出</h2>
              <p>歌曲、布局和主题调整请在宽屏完成，移动端保留核对与导出。</p>
            </div>
            {previewSrc ? (
              <div className="mobile-preview-frame">
                {previewError ? (
                  <div className="mobile-preview-error" role="alert">
                    <span>预览渲染失败</span>
                    <button type="button" className="secondary-action" onClick={() => { setPreviewError(false); setLoading(true); setRenderKey(key => key + 1); }}>重试</button>
                  </div>
                ) : (
                  // key={previewKey}：renderKey 触发整图重挂载，模拟「强制刷新」同时不污染 URL
                  <img key={previewKey} src={previewSrc} alt={`${selTheme}主题，第 ${page} 页预览`}
                    onLoad={() => setLoading(false)}
                    onError={() => { setLoading(false); setPreviewError(true); }} />
                )}
                {loading && !previewError && <div className="mobile-preview-loading"><span className="spinner" />渲染中…</div>}
              </div>
            ) : <div className="panel-empty">尚无可预览主题</div>}
            <div className="mobile-page-picker" aria-label="选择页码">
              {Array.from({ length: maxPage }, (_, index) => <button key={index} type="button" aria-pressed={page === index + 1} onClick={() => setPage(index + 1)}>{index + 1}</button>)}
            </div>
            <div className="mobile-actions">
              {previewSrc && <a href={previewSrc} download={`${activeTheme?.prefix ?? "poster"}-p${page}.png`} className="secondary-action">下载当前页</a>}
              <button type="button" className="primary-action" onClick={() => setExportDialogOpen(true)}>批量导出</button>
              <a href="/quick" className="secondary-action">直播速查</a>
            </div>
          </div>
          )}

          {/* ===== 歌曲库视图 ===== */}
          {view === "library" && (
            <LibraryView dark={dark}
              onStatsChange={setSongStats}
              onEditTargetChange={setLibDialogOpen} />
          )}

          {/* ===== 设置视图 ===== */}
          {view === "settings" && (
            <SettingsView dark={dark} themes={themes} appearance={appearance}
              onAppearancePreview={setAppearance}
              onAppearanceSaved={next => { setAppearance(next); setSavedAppearance(next); }}
              onSavingChange={setSettingsSaving} />
          )}

          {/* ===== 学歌管理视图 ===== */}
          {view === "learning" && (
            <LearningView dark={dark}
              onStatsChange={setSongStats}
              onEditTargetChange={setLibDialogOpen} />
          )}

          {/* ===== 直播视图 ===== */}
          {view === "live" && <LiveView dark={dark} />}

          {/* ===== RIGHT: params（仅工作台视图显示，<800px 隐藏） ===== */}
          {view === "workspace" && (
          <aside className={`w-60 shrink-0 border-l overflow-y-auto transition-colors duration-500 max-[800px]:hidden ${dark ? "border-zinc-700/50 bg-zinc-800/30" : "border-border"}`}>
            <div className={`px-5 py-4 border-b ${dark ? "border-zinc-700/50" : "border-border"}`}>
              <p className="eyebrow">展品设置</p>
              <h2 className="panel-title">版式与输出</h2>
            </div>

            <div className="px-4 py-3 space-y-3">
              <section className="layout-picker" aria-label="布局">
                <p className="inspector-label">布局</p>
                <button type="button" className="layout-option active" aria-pressed="true">
                  <span className="layout-glyph" aria-hidden="true"><i /><i /><i /><i /></span>
                  <span><strong>经典网格</strong><small>grid-wrap · 固定 2 页兼容模式</small></span>
                </button>
                <button type="button" className="layout-option" disabled><span className="layout-glyph planned" aria-hidden="true" /><span><strong>自由编排</strong><small>规划中 · 暂不可用</small></span></button>
                <p className="field-note">新布局、更多比例与自动分页会按各自算法声明能力；当前不会展示无法真实导出的选项。</p>
              </section>
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
                          className="w-3.5 h-3.5 rounded accent-primary" />
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
