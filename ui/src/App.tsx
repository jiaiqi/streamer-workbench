/// R4.0.10 App.tsx 拆解后的工作台主入口。
///
/// App 现在只做 3 件事：
///   1. 路由（view 状态 + 导航）
///   2. 跨视图外观（appearance / dark / settingsSaving）
///   3. 跨视图对话框（ExportDialog / Library 对话框守卫）
///
/// 工作台视图专属的状态（themes / selTheme / page / canvas / avoid / params /
/// renderKey / loading / previewError / hasFrame / 持久化 / 防抖 / 派生）全部由
/// `useWorkspaceState` 接管。
import { useEffect, useMemo, useState, useCallback } from "react";
import { CANVAS_OPTIONS } from "./types";
import { Icon } from "./icons";
import LibraryView from "./views/LibraryView";
import LearningView from "./views/LearningView";
import LiveView from "./views/LiveView";
import StatsView from "./views/StatsView";
import SettingsView from "./views/SettingsView";
import PlayView from "./play/PlayView";
import ExportDialog from "./components/ExportDialog";
import PreviewCrossfade from "./components/PreviewCrossfade";
import ParamInspector from "./components/ParamInspector";
import ColumnTemplatePicker from "./components/ColumnTemplatePicker";
import CommandPalette, { type Command } from "./components/CommandPalette";
import { searchSongs } from "./search/globalSongSearch";
import type { Song } from "./types";
import { DEFAULT_APPEARANCE, normalizeAppearance, resolveAppearance } from "./appearance";
import { apiRequest } from "./api/client";
import { savePoster } from "./api/posters";
import type { AppearanceSettings, Settings } from "./types";
import WorkspacePosterBridge from "./posters/WorkspacePosterBridge";
import SpecialPostersPanel from "./posters/SpecialPostersPanel";
import TonightSetCard from "./components/TonightSetCard";
import { usePosterStore } from "./posters/usePosterStore";
import { openQuickView, isElectron } from "./electron-bridge";
import { useWorkspaceState } from "./workspace/useWorkspaceState";
import { PlayerProvider, usePlayer, type PlayerMode } from "./player/PlayerContext";
import MiniPlayer from "./components/MiniPlayer";
import { ToastProvider } from "./components/Toast";
import ShortcutsPanel from "./components/ShortcutsPanel";
import Onboarding, { resetOnboarded } from "./components/Onboarding";

const navItems = [
  { id: "workspace", label: "海报工作台", icon: Icon.layout },
  { id: "library", label: "歌曲库", icon: Icon.list },
  { id: "learning", label: "学歌管理", icon: Icon.book },
  { id: "live", label: "直播", icon: Icon.live },
  { id: "stats", label: "数据统计", icon: Icon.barChart },
  // 主题管理/场景预设/导出历史不作占位导航：按路线图改为工作台内资源面板时再上线
];

/* ==================== App ==================== */
// M1.3: 外层组件 — 顶层包 PlayerProvider，让 usePlayer() 在整个 App 树可用。
// M9.6b: 同层包 ToastProvider，让 useToast() 全树可用（撤销 / 通知 / 错误提示）。
// QuickView 独立窗口有自己的 store，不包 Provider（它不需要跨场景播放器状态）。
export default function App() {
  return (
    <PlayerProvider>
      <ToastProvider>
        <AppInner />
      </ToastProvider>
    </PlayerProvider>
  );
}

function AppInner() {
  /* ---- 工作台状态（由 useWorkspaceState 接管）---- */
  const posterStore = usePosterStore();
  const ws = useWorkspaceState({ layoutId: posterStore.current.layout_id });
  /* M1.3: 跨场景播放器状态（M1.4 MiniPlayer 读这个） */
  const player = usePlayer();

  /* ---- 跨视图状态：外观 + 暗色 ---- */
  const [appearance, setAppearance] = useState<AppearanceSettings>(DEFAULT_APPEARANCE);
  const [savedAppearance, setSavedAppearance] = useState<AppearanceSettings>(DEFAULT_APPEARANCE);
  const [appearanceSaving, setAppearanceSaving] = useState(false);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [systemDark, setSystemDark] = useState(
    () => window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false,
  );

  /* ---- 跨视图状态：路由 + 对话框 ---- */
  const [view, setView] = useState<string>("workspace");
  const [exportDialogOpen, setExportDialogOpen] = useState(false);
  const [songStats, setSongStats] = useState<{ active: number; draft: number } | null>(null);
  const [libDialogOpen, setLibDialogOpen] = useState(false);
  // R8.0: 弹唱视图 - 当前播放的 song_id（null 时切回 library）
  const [playSongId, setPlaySongId] = useState<string | null>(null);
  // R8.2: 联动 — 弹唱视图进入时携带的直播会话上下文（无值表示非联动）
  const [playLink, setPlayLink] = useState<
    | { sessionId: string; requestId: string; requesterName: string }
    | null
  >(null);

  // R8.2 + M1.3: 触发弹唱。
  //   - 来自 LiveView：传 link（带会话+队列项）→ 推断 mode="live"
  //   - 来自 LibraryView/CommandPalette：不传 link，但显式传 mode="browse"
  //   - 同步写 PlayerContext，让 M1.4 MiniPlayer 知道当前在播什么
  //   - mode 显式覆盖 > link 推断 > 默认 "browse"
  const handlePlaySong = (
    songId: string,
    link?: { sessionId: string; requestId: string; requesterName: string },
    modeOverride?: PlayerMode,
  ) => {
    const mode: PlayerMode = modeOverride ?? (link ? "live" : "browse");
    setPlaySongId(songId);
    setPlayLink(link ?? null);
    setView("play");
    player.setCurrent(songId, mode);
  };
  // R8.2: 退出弹唱 — 联动模式回 live 视图；非联动模式回 library 视图。
  const handlePlayBack = () => {
    if (playLink) setView("live");
    else setView("library");
    setPlaySongId(null);
    setPlayLink(null);
    // 不清 PlayerContext —— 让 M1.4 MiniPlayer 留在底部，主播一键回弹唱
  };

  const dark = resolveAppearance(appearance.appearanceMode, systemDark) === "dark";

  /* ---- 暗色系统监听 ---- */
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const update = () => setSystemDark(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  /* ---- 外观保存 ---- */
  const saveAppearance = async (next: AppearanceSettings) => {
    if (appearanceSaving || settingsSaving || view === "settings") return;
    const previous = savedAppearance;
    setAppearance(next);
    setAppearanceSaving(true);
    try {
      await apiRequest("/api/settings", { method: "POST", body: next });
      setSavedAppearance(next);
      ws.setResourceError("");
    } catch {
      setAppearance(previous);
      ws.setResourceError("外观保存失败，已恢复为上次保存状态。");
    } finally {
      setAppearanceSaving(false);
    }
  };

  /* ---- 跨视图：加载 settings 用于 app 顶部状态（歌单统计旁） ---- */
  useEffect(() => {
    let active = true;
    apiRequest<Settings>("/api/settings")
      .then(s => {
        if (!active) return;
        const nextAppearance = normalizeAppearance(s);
        setAppearance(nextAppearance);
        setSavedAppearance(nextAppearance);
      })
      .catch(() => { /* 工作台自己的 effect 会捕获资源错误 */ });
    return () => { active = false; };
  }, []);

  /* ---- R4.2 数据反哺创作 ---- */
  const handleCreatePosterFromTop = useCallback(async (songIds: string[], metric: string) => {
    if (songIds.length === 0) throw new Error("Top 歌曲为空");
    const today = new Date();
    const stamp = `${today.getFullYear()}-${(today.getMonth() + 1).toString().padStart(2, "0")}-${today.getDate().toString().padStart(2, "0")}`;
    const metricLabel: Record<string, string> = { request: "点歌", perform: "演唱", practice: "练习" };
    const res = await savePoster({
      name: `Top ${songIds.length}（${metricLabel[metric] ?? metric}）${stamp}`,
      song_source: { type: "manual" },
      selected_song_ids: songIds,
      layout_id: posterStore.current.layout_id,
      theme_id: ws.selTheme || undefined,
      canvas_id: ws.canvas,
      page_policy: posterStore.current.layout_id === "grid-wrap"
        ? { mode: "legacy-fixed-2" }
        : { mode: "auto", min_pages: 1, max_pages: 8 },
      parameters: ws.params,
      export_settings: {
        format: "png",
        jpeg_quality: 92,
        single_page: false,
        dpi: 144,
      },
    });
    setView("workspace");
    await posterStore.select(res.id);
  }, [posterStore, ws.selTheme, ws.canvas, ws.params]);

  const handleCreatePresetFromFeed = useCallback(async (songIds: string[], name: string) => {
    if (songIds.length === 0) throw new Error("时间线歌曲 ID 为空");
    await apiRequest("/api/presets", {
      method: "POST",
      body: {
        schema_version: 2,
        id: "",
        name,
        song_query: {
          status: "active",
          classify: "manual",
          sort_by: "default",
          max_songs: 0,
          custom_ids: songIds,
          unresolved: [],
        },
        layout_id: "grid-wrap",
      },
    });
  }, []);

  /* ---- 跨视图：快捷键 ---- */
  const maxPage = ws.maxPage;
  /* ---- R4.1.5 命令面板：Cmd+K 跨视图 ---- */
  const [paletteOpen, setPaletteOpen] = useState(false);
  /* ---- L1.2 快捷键面板：? 键（Shift+/）打开 ---- */
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  /* ---- M1.2 全局找歌：所有 songs（搜索用）---- */
  const [allSongs, setAllSongs] = useState<Song[]>([]);
  useEffect(() => {
    let active = true;
    apiRequest<SongsData | Song[]>("/api/songs/list", {})
      .then(data => {
        if (!active) return;
        const list: Song[] = Array.isArray(data) ? data
          : (data && typeof data === "object" && "songs" in data && Array.isArray((data as SongsData).songs))
            ? (data as SongsData).songs : [];
        setAllSongs(list);
      })
      .catch(() => { /* 静默 — CommandPalette 仍能用命令 */ });
    return () => { active = false; };
  }, []);
  /* M1.2 实时计算搜歌结果（query 来自 CommandPalette 内部，这里只暴露 songResults） */
  const [paletteQuery, setPaletteQuery] = useState("");
  const songResults = useMemo(
    () => paletteQuery.trim() ? searchSongs(paletteQuery, allSongs, { limit: 5 }) : [],
    [paletteQuery, allSongs],
  );

  /* ---- M1.4 MiniPlayer：当前歌名查表 + 打开/关闭回调 ---- */
  const currentTitle = useMemo(
    () => player.currentSongId
      ? allSongs.find(s => s.id === player.currentSongId)?.title ?? null
      : null,
    [allSongs, player.currentSongId],
  );
  const handleMiniPlayerOpen = useCallback(() => setView("play"), []);
  const handleMiniPlayerClose = useCallback(() => {
    // 清 PlayerContext + 退出视图态：和 handlePlayBack 一致，但额外清 context
    player.setCurrent(null);
    setPlaySongId(null);
    setPlayLink(null);
    if (playLink) setView("live");
    else setView("library");
  }, [player, playLink]);

  const commands: Command[] = useMemo(() => [
    { id: "view-workspace", title: "切换到海报工作台", group: "视图", shortcut: "1", keywords: ["poster", "海报"], action: () => setView("workspace") },
    { id: "view-library", title: "切换到歌曲库", group: "视图", shortcut: "2", keywords: ["song", "歌曲"], action: () => setView("library") },
    { id: "view-learning", title: "切换到学歌管理", group: "视图", shortcut: "3", keywords: ["learn", "学歌"], action: () => setView("learning") },
    { id: "view-live", title: "切换到直播", group: "视图", shortcut: "4", keywords: ["live", "直播"], action: () => setView("live") },
    { id: "view-stats", title: "切换到数据统计", group: "视图", shortcut: "5", keywords: ["stats", "统计"], action: () => setView("stats") },
    { id: "view-settings", title: "打开设置", group: "视图", shortcut: "⌘,", keywords: ["setting", "设置"], action: () => setView("settings") },
    { id: "act-export", title: "导出当前海报", group: "操作", shortcut: "⌘E", keywords: ["export", "下载"], action: () => setExportDialogOpen(true), disabledReason: view !== "workspace" ? "切到工作台后可用" : undefined },
    { id: "act-refresh", title: "刷新预览", group: "操作", shortcut: "⌘R", keywords: ["refresh", "reload"], action: () => ws.refresh(), disabledReason: view !== "workspace" ? "切到工作台后可用" : undefined },
    { id: "act-quickview", title: "打开直播速查", group: "速查", keywords: ["quickview", "速查"], action: () => openQuickView() },
    { id: "act-shortcuts", title: "查看快捷键面板", group: "帮助", shortcut: "?", keywords: ["shortcut", "快捷键", "help", "帮助"], action: () => setShortcutsOpen(true) },
    { id: "act-onboarding", title: "重看首次启动引导", group: "帮助", keywords: ["onboard", "引导", "tutorial", "教程", "新用户"], action: () => { resetOnboarded(); window.location.reload(); } },
  ], [view, ws]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (appearanceSaving || settingsSaving) return;
      const mod = e.ctrlKey || e.metaKey;
      const tag = (e.target as HTMLElement)?.tagName;
      const typing = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";

      // R4.1.5: Cmd+K 打开命令面板（任何视图 + 输入控件聚焦时也允许）
      if (mod && (e.key === "k" || e.key === "K")) {
        e.preventDefault();
        setPaletteOpen(p => !p);
        return;
      }

      // L1.2: ?（Shift+/）打开快捷键面板
      if (e.key === "?" && !mod && !typing) {
        e.preventDefault();
        setShortcutsOpen(p => !p);
        return;
      }

      // P2 R4: undo/redo 优先级 — 输入控件聚焦让浏览器默认处理
      if (mod && !typing && view === "workspace" && !exportDialogOpen && !libDialogOpen && !paletteOpen) {
        if (e.key === "z" || e.key === "Z") {
          e.preventDefault();
          window.dispatchEvent(new CustomEvent(
            e.shiftKey ? "poster:redo" : "poster:undo",
          ));
          return;
        }
      }

      if (e.key === "Escape" || typing) return;

      if (mod && e.key === "e") {
        e.preventDefault();
        setExportDialogOpen(true);
      } else if (mod && e.key === "r") {
        e.preventDefault();
        ws.refresh();
      } else if (mod && e.key === ",") {
        e.preventDefault();
        setView("settings");
      } else if (mod && /^[1-7]$/.test(e.key)) {
        e.preventDefault();
        const t = ws.themes[parseInt(e.key, 10) - 1];
        if (t) { ws.selectTheme(t.name); }
      } else if (!mod && view === "workspace" && !exportDialogOpen && !libDialogOpen) {
        if (e.key === "ArrowLeft") ws.setPage(p => Math.max(1, p - 1));
        else if (e.key === "ArrowRight") ws.setPage(p => Math.min(maxPage, p + 1));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ws, view, maxPage, exportDialogOpen, libDialogOpen, appearanceSaving, settingsSaving]);

  /* ---- 移动端 / 桌面端分支判断 ---- */
  const inWorkspace = view === "workspace";
  const settingsBusy = appearanceSaving || settingsSaving;
  const resourceAlert = ws.resourceError;

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
            disabled={settingsBusy}
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
            disabled={settingsBusy || view === "settings"}
            aria-busy={appearanceSaving}
            title={view === "settings" ? "请在设置页调整外观" : dark ? "切换到画廊白" : "切换到暗色舞台"}
            className={`flex h-11 w-11 items-center justify-center rounded-xl transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-45 ${dark ? "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-700/50" : "text-muted-foreground hover:text-foreground hover:bg-muted"}`}
          >{Icon.sun}</button>
          <button onClick={() => setView("settings")} title="设置"
            disabled={settingsBusy}
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
          <span className="hidden min-[800px]:inline whitespace-nowrap">{ws.themes.length} 个主题 · {ws.maxPage} 页</span>
          <span className={`h-4 w-px hidden min-[800px]:block ${dark ? "bg-zinc-700/50" : "bg-border"}`}></span>
          <span className="hidden min-[800px]:inline whitespace-nowrap">已会 {songStats?.active ?? "—"} · 未会 {songStats?.draft ?? "—"}</span>
          {ws.lastRenderMs !== null && (
            <span className="ml-auto tabular-nums hidden min-[800px]:inline">渲染 {Math.round(ws.lastRenderMs)}ms/张</span>
          )}
          {resourceAlert && <button className="resource-alert" type="button" onClick={() => window.location.reload()} title={resourceAlert}>资源异常 · 重试</button>}
        </header>

        <div className="flex flex-1 overflow-hidden">
          {/* ===== LEFT: theme list（仅工作台视图显示，<800px 隐藏） ===== */}
          {inWorkspace && (
          <aside className={`w-64 shrink-0 border-r overflow-y-auto transition-colors duration-500 max-[800px]:hidden ${dark ? "border-zinc-700/50 bg-zinc-800/30" : "border-border"}`}>
            {/* R9.5 今晚歌单 — 工作台首屏运营卡片（live session Top 5 + 弹唱按钮） */}
            <TonightSetCard
              dark={dark}
              onPlaySong={handlePlaySong}
              onOpenLiveView={() => setView("live")}
            />
            {/* R1a.5 海报文档区 + 歌曲来源（独立 hook 状态机） */}
            <WorkspacePosterBridge
              dark={dark}
              availableThemeNames={ws.themes.map(t => t.name)}
              onThemeSelect={ws.selectTheme}
              onCanvasSelect={ws.setCanvas}
            />
            {/* R4.0.11 专用海报：直播复盘 + 学歌报告 */}
            <SpecialPostersPanel dark={dark} />
            <div className="px-4 pt-5 pb-3">
              <p className="eyebrow">策展资源</p>
              <h2 className="panel-title">海报主题</h2>
              <p className="panel-copy">主题与布局独立组合。选择后实时更新中央展品。</p>
            </div>
            <div className="px-3 pb-4 space-y-2">
              {ws.themes.length === 0 && !ws.resourceError && <div className="panel-empty" aria-busy="true"><span className="spinner" />正在陈列主题…</div>}
              {ws.themes.map(t => (
                <button
                  key={t.name}
                  onClick={() => ws.selectTheme(t.name)}
                  className={`w-full text-left rounded-xl overflow-hidden transition-all duration-200 group ${ws.selTheme === t.name
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
          {inWorkspace && (
          <main className="workspace-gallery flex-1 flex flex-col items-center justify-center relative overflow-hidden max-[800px]:hidden">
            <div className="gallery-room-label" aria-hidden="true">独立海报 · 画廊策展台</div>
            {/* toolbar */}
            <div className="absolute top-4 left-4 right-4 flex items-center justify-between z-10">
              <div className={`flex items-center gap-1.5 rounded-xl px-3 py-2 shadow-sm transition-colors duration-500 ${dark ? "bg-zinc-800/80 border border-zinc-700/50" : "bg-card border border-border"}`}>
                {Array.from({ length: ws.maxPage }, (_, i) => (
                  <button key={i} onClick={() => ws.setPage(i + 1)}
                    className={`w-11 h-11 rounded-lg text-xs font-medium transition-all ${ws.page === i + 1
                      ? "bg-primary text-primary-foreground"
                      : (dark ? "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700/50" : "text-muted-foreground hover:text-foreground hover:bg-muted")
                    }`}
                  >{i + 1}</button>
                ))}
                <span className={`w-px h-5 mx-1 ${dark ? "bg-zinc-700" : "bg-border"}`} />
                <label title="避开抖音右侧评论/礼物互动区（9:20 画布右下安全区）"
                  className="flex items-center gap-1.5 text-xs cursor-pointer select-none text-muted-foreground">
                  <input type="checkbox" checked={ws.avoid} onChange={e => ws.setAvoid(e.target.checked)}
                    className="w-3.5 h-3.5 rounded accent-primary" />
                  避让互动区
                </label>
              </div>

              <div className="flex items-center gap-2">
                <div className={`flex items-center gap-1 rounded-lg px-2 py-1.5 shadow-sm transition-colors duration-500 ${dark ? "bg-zinc-800/80 border border-zinc-700/50" : "bg-card border border-border"}`}>
                  <button onClick={() => ws.setZoom(z => Math.max(15, z - 10))}
                    className="w-6 h-6 rounded flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                  ><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="5" y1="12" x2="19" y2="12"/></svg></button>
                  <span className="text-[11px] text-muted-foreground w-10 text-center tabular-nums">{ws.zoom}%</span>
                  <button onClick={() => ws.setZoom(z => Math.min(150, z + 10))}
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
                  ws.setZoom(z => Math.max(15, Math.min(150, z + delta)));
                }
              }}
              style={{ touchAction: "none" }}>
              {ws.selTheme ? (
                <div className="relative rounded-2xl overflow-hidden transition-all duration-300"
                  style={{
                    width: `${(1080 * ws.zoom) / 100}px`,
                    // max-width 由 max-height 和画布比例反推：让容器按比例缩小，不破坏避让线对齐
                    maxWidth: ws.canvas === "标准 9:16"
                      ? "calc((100vh - 120px) * 9 / 16)"
                      : "calc((100vh - 120px) * 9 / 20)",
                    aspectRatio: ws.canvas === "标准 9:16" ? "9 / 16" : "9 / 20",
                    boxShadow: "0 4px 12px rgba(35,55,48,0.06), 0 24px 56px rgba(35,55,48,0.13)",
                  }}>
                  {ws.previewError ? (
                    /* P0-1: 渲染失败兜底——错误占位 + 重试，不再静默白屏 */
                    <div className={`absolute inset-0 flex flex-col items-center justify-center gap-3 ${dark ? "bg-zinc-800" : "bg-muted"}`}>
                      <p className="text-sm text-muted-foreground">预览渲染失败</p>
                      <button onClick={() => ws.refresh()}
                        className="flex items-center gap-1.5 rounded-xl px-4 py-2 text-sm bg-primary hover:bg-primary-strong text-primary-foreground font-medium transition-all active:scale-95 cursor-pointer">
                        {Icon.refresh} 重试
                      </button>
                    </div>
                  ) : (
                    /* §4.6 POC：旧图保持至新图完成再 crossfade，reduced-motion 直换 */
                    <PreviewCrossfade src={ws.previewSrc}
                      alt={`${ws.selTheme} 主题，第 ${ws.page} 页预览`}
                      reloadKey={ws.renderKey}
                      onLoaded={ws.markLoaded}
                      onFailed={ws.markFailed} />
                  )}
                  {/* M1.7 渐进式海报：相邻页预加载（hidden img 触发浏览器预取；翻页时缓存命中 → 0ms 切换） */}
                  {ws.prevPreviewSrc && (
                    <img
                      src={ws.prevPreviewSrc}
                      alt=""
                      aria-hidden="true"
                      data-testid="poster-prev-preload"
                      className="hidden"
                    />
                  )}
                  {ws.nextPreviewSrc && (
                    <img
                      src={ws.nextPreviewSrc}
                      alt=""
                      aria-hidden="true"
                      data-testid="poster-next-preload"
                      className="hidden"
                    />
                  )}
                  {ws.loading && !ws.previewError && !ws.hasFrame && (
                    <div className={`absolute inset-0 flex flex-col items-center justify-center gap-2.5 ${dark ? "bg-zinc-800/60" : "bg-background/60"}`}>
                      <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                      <p className="text-xs text-muted-foreground">渲染中…</p>
                    </div>
                  )}
                  {ws.avoid && ws.canvas === "抖音全屏 9:20" && (
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
                <span>主题：<span className={dark ? "text-zinc-300" : "text-foreground"}>{ws.selTheme || "—"}</span></span>
                <span className={`w-px h-4 ${dark ? "bg-zinc-700" : "bg-border"}`} />
                <span>画布：<span className={dark ? "text-zinc-300" : "text-foreground"}>{ws.canvas}</span></span>
                <span className={`hidden xl:inline ml-2 ${dark ? "text-zinc-600" : "text-muted-foreground/60"}`}>⌘E 导出 · ⌘R 刷新 · ←→ 翻页 · ⌘K 命令面板</span>
              </div>
              <div className="flex items-center gap-2">
                {ws.previewSrc && (
                  <a href={ws.previewSrc} download={`${ws.activeTheme?.prefix ?? "poster"}-p${ws.page}.png`}
                    className="flex items-center gap-1.5 rounded-xl px-4 py-2 text-sm transition-colors cursor-pointer no-underline text-muted-foreground hover:text-foreground hover:bg-muted">
                    {Icon.download} 下载
                  </a>
                )}
                <button onClick={() => setExportDialogOpen(true)}
                  className="primary-action flex items-center gap-1.5 rounded-xl px-4 py-2 text-sm cursor-pointer">
                  {Icon.download} 导出…
                </button>
                <button onClick={ws.refresh}
                  className="flex items-center gap-1.5 bg-primary hover:bg-primary-strong text-primary-foreground font-medium rounded-xl px-5 py-2 text-sm transition-all active:scale-95 cursor-pointer">
                  {Icon.refresh} {ws.loading ? "渲染中…" : "刷新预览"}
                </button>
              </div>
            </div>
          </main>
          )}

          {/* ===== 移动端兜底（<800px）：不裁剪桌面三栏，引导去直播速查 ===== */}
          {inWorkspace && (
          <div className="mobile-workspace flex-1 hidden max-[800px]:flex flex-col items-center gap-4 overflow-y-auto p-4 text-center">
            <div className="mobile-workspace-heading">
              <p className="eyebrow">轻量工作区</p>
              <h2>预览与导出</h2>
              <p>歌曲、布局和主题调整请在宽屏完成，移动端保留核对与导出。</p>
            </div>
            {ws.previewSrc ? (
              <div className="mobile-preview-frame">
                {ws.previewError ? (
                  <div className="mobile-preview-error" role="alert">
                    <span>预览渲染失败</span>
                    <button type="button" className="secondary-action" onClick={ws.refresh}>重试</button>
                  </div>
                ) : (
                  // key={previewKey}：renderKey 触发整图重挂载，模拟「强制刷新」同时不污染 URL
                  <img key={ws.previewKey} src={ws.previewSrc} alt={`${ws.selTheme}主题，第 ${ws.page} 页预览`}
                    onLoad={ws.markLoaded}
                    onError={ws.markFailed} />
                )}
                {ws.loading && !ws.previewError && <div className="mobile-preview-loading"><span className="spinner" />渲染中…</div>}
              </div>
            ) : <div className="panel-empty">尚无可预览主题</div>}
            <div className="mobile-page-picker" aria-label="选择页码">
              {Array.from({ length: ws.maxPage }, (_, index) => <button key={index} type="button" aria-pressed={ws.page === index + 1} onClick={() => ws.setPage(index + 1)}>{index + 1}</button>)}
            </div>
            <div className="mobile-actions">
              {ws.previewSrc && <a href={ws.previewSrc} download={`${ws.activeTheme?.prefix ?? "poster"}-p${ws.page}.png`} className="secondary-action">下载当前页</a>}
              <button type="button" className="primary-action" onClick={() => setExportDialogOpen(true)}>批量导出</button>
              <a
                href="/quick"
                target="_blank"
                rel="noreferrer"
                className="secondary-action"
                onClick={(e) => openQuickView(undefined, e)}
              >
                直播速查 {isElectron() ? "▣" : "↗"}
              </a>
            </div>
          </div>
          )}

          {/* ===== 歌曲库视图 ===== */}
          {view === "library" && (
            <LibraryView dark={dark}
              onStatsChange={setSongStats}
              onEditTargetChange={setLibDialogOpen}
              onPlaySong={(id) => handlePlaySong(id, undefined, "browse")} />
          )}

          {/* ===== 弹唱视图（R8.0 + R8.2 联动） ===== */}
          {view === "play" && playSongId && (
            <PlayView
              dark={dark}
              songId={playSongId}
              linkedSessionId={playLink?.sessionId}
              linkedRequestId={playLink?.requestId}
              linkedRequesterName={playLink?.requesterName}
              onBack={handlePlayBack}
            />
          )}

          {/* ===== 设置视图 ===== */}
          {view === "settings" && (
            <SettingsView dark={dark} themes={ws.themes} appearance={appearance}
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
          {view === "live" && <LiveView dark={dark} onPlaySong={handlePlaySong} />}

          {/* ===== 统计视图 (R4) ===== */}
          {view === "stats" && (
            <StatsView
              dark={dark}
              onCreatePosterFromTop={handleCreatePosterFromTop}
              onCreatePresetFromFeed={handleCreatePresetFromFeed}
            />
          )}

          {/* ===== RIGHT: params（仅工作台视图显示，<800px 隐藏） ===== */}
          {inWorkspace && (
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
                    <select value={ws.canvas} onChange={e => ws.setCanvas(e.target.value)}
                      className={`rounded-lg px-2 py-1 text-xs outline-none cursor-pointer ${dark ? "bg-zinc-800 border-zinc-700 text-zinc-300" : "bg-muted border-border text-foreground border"}`}>
                      {CANVAS_OPTIONS.map(c => <option key={c} value={c}>{c}</option>)}
                    </select>
                  </label>
                  <label className="flex items-center justify-between text-xs text-muted-foreground">
                    尺寸 <span className="tabular-nums text-foreground">{ws.canvas === "标准 9:16" ? "1080×1920" : "1080×2400"}</span>
                  </label>
                  <label className="flex items-center justify-between text-xs text-muted-foreground">
                    页数 <span className="tabular-nums text-foreground">{ws.maxPage}</span>
                  </label>
                </div>
              </details>

              {/* 折叠：布局参数（默认展开）—— P2 R4 通用 Inspector 接管 */}
              {/* magazine-flow 专用：栏数模板下拉 */}
              {posterStore.current.layout_id === "magazine-flow" && ws.columnTemplates.length > 0 && (
                <ColumnTemplatePicker
                  templates={ws.columnTemplates}
                  value={(ws.params.columns_per_section as Record<string, number>) || {}}
                  onChange={next => ws.setParam("columns_per_section", next)}
                  dark={dark}
                />
              )}
              <ParamInspector
                specs={ws.paramSpecs}
                values={ws.params}
                onChange={ws.setParam}
                onReset={key => {
                  const sp = ws.paramSpecs.find(p => p.key === key);
                  if (sp) ws.setParam(key, sp.default);
                }}
                dark={dark}
              />

              {/* 折叠：当前主题（默认折叠） */}
              {ws.activeTheme && (
              <details className="group">
                <summary className="flex items-center justify-between cursor-pointer py-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground select-none">
                  当前主题
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="transition-transform group-open:rotate-180"><polyline points="6 9 12 15 18 9"/></svg>
                </summary>
                <div className={`mt-2.5 rounded-xl p-3 space-y-1.5 text-xs shadow-sm ${dark ? "bg-zinc-800/80 border border-zinc-700/50" : "bg-card border border-border"}`}>
                  <p className="font-medium text-foreground">{ws.activeTheme.name}</p>
                  <p className="text-muted-foreground break-all leading-relaxed">{ws.activeTheme.notes || "无备注"}</p>
                  <p className="text-muted-foreground">水印修正：{ws.activeTheme.watermark_fix ? "是" : "否"}</p>
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
        selTheme={ws.selTheme}
        page={ws.page}
        maxPage={ws.maxPage}
        themesCount={ws.themes.length}
        canvas={ws.canvas}
        avoid={ws.avoid}
        paramsQuery={ws.paramsQuery}
        lastRenderMs={ws.lastRenderMs}
        onRendered={ws.setLastRenderMs}
      />
      {/* R4.1.5 Cmd+K 命令面板 + M1.2 全局找歌 */}
      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        commands={commands}
        dark={dark}
        songResults={songResults}
        onPickSong={(id) => { handlePlaySong(id, undefined, "browse"); setPaletteOpen(false); }}
        query={paletteQuery}
        onQueryChange={setPaletteQuery}
      />
      {/* M1.4 跨场景迷你播放器：除 PlayView 自身 + 模态场景外常驻底栏 */}
      <MiniPlayer
        currentTitle={currentTitle}
        onOpen={handleMiniPlayerOpen}
        onClose={handleMiniPlayerClose}
        dark={dark}
        hidden={view === "play" || paletteOpen || exportDialogOpen || libDialogOpen}
      />
      {/* L1.2 全局快捷键面板 — ? 键打开 */}
      <ShortcutsPanel open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} dark={dark} />
      {/* L1.3 首次启动 Onboarding（localStorage 标记控制） */}
      <Onboarding dark={dark} />
    </div>
  );
}
