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
interface Song {
  title: string;
  status: string;
  section: number | null;
  artists: string[];
  lyricist: string;
  composer: string;
  key: string;
  capo: number | null;
  difficulty: string;
  tabs: string;
  tags: string[];
  pinyin: string;
  added_at: string;
  notes: string;
}
interface SongsData {
  total: number;
  active: number;
  draft: number;
  songs: Song[];
}
interface ParamSpec {
  key: string;
  label: string;
  kind: string;            // "int" | "color" | "bool" | "choice"
  default: number;
  min: number | null;
  max: number | null;
  choices: string[] | null;
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
  // P0-1: 排版参数受控（初始为 grid-wrap 默认值，ParamSpec 拉取后合并）
  const [params, setParams] = useState<Record<string, number>>({
    margin: 58, font_song: 36, row_h: 44, sec_gap: 26,
  });
  // Phase 2: 参数面板动态渲染（对接 /api/layouts/{id}/params 的 ParamSpec 契约）
  const [paramSpecs, setParamSpecs] = useState<ParamSpec[]>([]);
  // Phase 2: 视图路由
  const [view, setView] = useState<string>("workspace");
  // Phase 2: 歌曲库数据
  const [songsData, setSongsData] = useState<SongsData | null>(null);
  const [songFilter, setSongFilter] = useState<string>("");
  const [songStatusFilter, setSongStatusFilter] = useState<string>("all");
  // Phase 2: 导出对话框（范围选择 + 预估 + 进度 + 打开目录）
  const [exportDialogOpen, setExportDialogOpen] = useState(false);
  const [exportScope, setExportScope] = useState<"page" | "theme" | "all">("all");
  const [exporting, setExporting] = useState(false);
  const [exportProgress, setExportProgress] = useState<{ done: number; total: number; current: string } | null>(null);
  const [exportDone, setExportDone] = useState<{ count: number; totalMs: number; outputDir: string } | null>(null);
  const [lastRenderMs, setLastRenderMs] = useState<number | null>(null);
  // Phase 2: 状态栏歌曲统计
  const [songStats, setSongStats] = useState<{ active: number; draft: number } | null>(null);
  // Phase 2.5: 歌曲编辑（增删改）
  const [editTarget, setEditTarget] = useState<Song | "new" | null>(null);
  const [editForm, setEditForm] = useState<Record<string, string>>({});
  const [editError, setEditError] = useState<string>("");
  const [saving, setSaving] = useState(false);
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
    fetch("/api/themes").then(r => r.json()).then((d: Theme[]) => {
      setThemes(d);
      if (d.length && !selTheme) setSelTheme(d[0].name);
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

  // Phase 2: 歌曲库数据加载
  useEffect(() => {
    if (view === "library") {
      fetch("/api/songs/list").then(r => r.json()).then(setSongsData);
    }
  }, [view]);

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
  const activeLayout = layouts.find(l => l.id === "grid-wrap");

  // Phase 2: 导出对话框逻辑
  const estimateCount = exportScope === "page" ? 1
    : exportScope === "theme" ? maxPage
    : themes.length * maxPage;
  const estimateMs = estimateCount * (lastRenderMs ?? 900);

  const runExport = async () => {
    setExporting(true);
    setExportDone(null);
    setExportProgress({ done: 0, total: estimateCount, current: "" });
    try {
      if (exportScope === "all") {
        // 批量：后端后台任务 + 300ms 轮询进度
        const res = await fetch(
          `/api/export/batch?canvas=${encodeURIComponent(canvas)}&avoid=${avoid}`,
          { method: "POST" });
        const { job_id } = await res.json();
        await new Promise<void>((resolve) => {
          const timer = setInterval(async () => {
            const j = await (await fetch(`/api/export/jobs/${job_id}`)).json();
            setExportProgress({ done: j.done, total: j.total, current: j.current });
            if (j.status === "done" || j.status === "error") {
              clearInterval(timer);
              if (j.status === "done") {
                setExportDone({ count: j.done, totalMs: j.total_ms, outputDir: j.output_dir });
                setLastRenderMs(j.total_ms / j.total);
              }
              resolve();
            }
          }, 300);
        });
      } else {
        // 单页 / 当前主题全部页：前端顺序调用单页导出
        const pages = exportScope === "page" ? [page]
          : Array.from({ length: maxPage }, (_, i) => i + 1);
        const t0 = performance.now();
        for (const p of pages) {
          setExportProgress({ done: p - pages[0], total: pages.length, current: `${selTheme} p${p}` });
          const res = await fetch(
            `/api/export?theme=${encodeURIComponent(selTheme)}&page=${p}&canvas=${encodeURIComponent(canvas)}&avoid=${avoid}${paramsQuery}`,
            { method: "POST" });
          const data = await res.json();
          setLastRenderMs(data.duration_ms);
          setExportProgress({ done: p - pages[0] + 1, total: pages.length, current: `${selTheme} p${p}` });
        }
        const st = await (await fetch("/api/settings")).json();
        setExportDone({ count: pages.length, totalMs: Math.round(performance.now() - t0), outputDir: st.output_dir });
      }
    } catch (e) {
      console.error("导出失败", e);
    }
    setExporting(false);
  };

  const openOutputDir = () => fetch("/api/export/open", { method: "POST" });

  // Phase 2.5: 歌曲编辑（增删改）
  const refreshSongs = async () => {
    const d: SongsData = await (await fetch("/api/songs/list")).json();
    setSongsData(d);
    setSongStats({ active: d.active, draft: d.draft });
  };

  const openEdit = (target: Song | "new") => {
    setEditTarget(target);
    setEditError("");
    if (target === "new") {
      setEditForm({ title: "", artists: "", key: "", capo: "", difficulty: "", section: "", lyricist: "", composer: "", tabs: "", tags: "", pinyin: "", notes: "" });
    } else {
      setEditForm({
        title: target.title, artists: target.artists.join("，"),
        key: target.key, capo: target.capo === null ? "" : String(target.capo),
        difficulty: target.difficulty, section: target.section === null ? "" : String(target.section),
        lyricist: target.lyricist, composer: target.composer, tabs: target.tabs,
        tags: target.tags.join("，"), pinyin: target.pinyin, notes: target.notes,
      });
    }
  };

  const saveEdit = async () => {
    if (!editForm.title?.trim()) { setEditError("歌名不能为空"); return; }
    setSaving(true);
    setEditError("");
    const fields: Record<string, unknown> = {
      title: editForm.title.trim(),
      artists: editForm.artists.split(/[，,]/).map(s => s.trim()).filter(Boolean),
      key: editForm.key, difficulty: editForm.difficulty,
      lyricist: editForm.lyricist, composer: editForm.composer,
      tabs: editForm.tabs, notes: editForm.notes, pinyin: editForm.pinyin,
      tags: editForm.tags.split(/[，,]/).map(s => s.trim()).filter(Boolean),
      capo: editForm.capo === "" ? null : parseInt(editForm.capo, 10),
      section: editForm.section === "" ? null : parseInt(editForm.section, 10),
    };
    try {
      const res = editTarget === "new"
        ? await fetch("/api/songs/add", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(fields) })
        : await fetch("/api/songs/update", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title: (editTarget as Song).title, fields }) });
      if (!res.ok) { setEditError(await res.text()); setSaving(false); return; }
      await refreshSongs();
      setEditTarget(null);
    } catch (e) {
      setEditError("保存失败：" + e);
    }
    setSaving(false);
  };

  const deleteSong = async (song: Song) => {
    if (!window.confirm(`确定删除「${song.title}」？此操作会立即写入 songs.json（有自动备份）。`)) return;
    try {
      const res = await fetch("/api/songs/delete", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: song.title }),
      });
      if (!res.ok) { console.error("删除失败", await res.text()); return; }
      await refreshSongs();
    } catch (e) {
      console.error("删除失败", e);
    }
  };

  // Phase 2: 学会了 ⇄ 标回未会
  const handleToggleStatus = async (song: Song) => {
    const next = song.status === "active" ? "draft" : "active";
    try {
      const res = await fetch("/api/songs/status", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: song.title, status: next }),
      });
      if (!res.ok) {
        console.error("状态切换失败", await res.text());
        return;
      }
      // 本地更新该行 + 顶部统计，避免整表重拉
      setSongStats(prev => prev && (next === "active"
        ? { active: prev.active + 1, draft: prev.draft - 1 }
        : { active: prev.active - 1, draft: prev.draft + 1 }));
      setSongsData(prev => prev && {
        ...prev,
        active: prev.songs.reduce((n, s) => n + ((s.title === song.title ? next : s.status) === "active" ? 1 : 0), 0),
        draft: prev.songs.reduce((n, s) => n + ((s.title === song.title ? next : s.status) === "draft" ? 1 : 0), 0),
        songs: prev.songs.map(s => s.title === song.title ? { ...s, status: next } : s),
      });
    } catch (e) {
      console.error("状态切换失败", e);
    }
  };

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
            onClick={() => setView(item.id)}
            className={`relative flex h-10 w-10 items-center justify-center rounded-xl transition-all duration-200 group ${item.id === view
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
          <span className={`h-4 w-px ${dark ? "bg-zinc-700/50" : "bg-border"}`}></span>
          <span>已会 {songStats?.active ?? "—"} · 未会 {songStats?.draft ?? "—"}</span>
          {lastRenderMs !== null && (
            <span className="ml-auto tabular-nums">渲染 {Math.round(lastRenderMs)}ms/张</span>
          )}
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
                <button onClick={() => { setExportDialogOpen(true); setExportDone(null); setExportProgress(null); }}
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
          <main className="flex-1 flex flex-col overflow-hidden p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className={`text-lg font-semibold ${dark ? "text-zinc-200" : "text-foreground"}`}>歌曲库</h2>
              <div className="flex items-center gap-2">
                <input type="text" placeholder="搜索歌名…" value={songFilter}
                  onChange={e => setSongFilter(e.target.value)}
                  className={`rounded-lg px-3 py-1.5 text-sm outline-none ${dark ? "bg-zinc-800 border-zinc-700 text-zinc-300" : "bg-muted border-border text-foreground border"}`} />
                <select value={songStatusFilter} onChange={e => setSongStatusFilter(e.target.value)}
                  className={`rounded-lg px-3 py-1.5 text-sm outline-none ${dark ? "bg-zinc-800 border-zinc-700 text-zinc-300" : "bg-muted border-border text-foreground border"}`}>
                  <option value="all">全部</option>
                  <option value="active">已会</option>
                  <option value="draft">未会</option>
                </select>
                <button onClick={() => openEdit("new")}
                  className="rounded-lg px-3 py-1.5 text-sm font-medium transition-colors cursor-pointer bg-emerald-600 hover:bg-emerald-700 text-white">
                  + 新增歌曲
                </button>
              </div>
            </div>
            {songsData ? (
              <div className={`flex-1 overflow-auto rounded-xl border ${dark ? "border-zinc-700/50" : "border-border"}`}>
                <table className="w-full text-sm">
                  <thead className={`sticky top-0 ${dark ? "bg-zinc-800" : "bg-muted"}`}>
                    <tr>
                      <th className="text-left px-4 py-2 font-medium">歌名</th>
                      <th className="text-left px-4 py-2 font-medium">歌手</th>
                      <th className="text-left px-4 py-2 font-medium">弹唱</th>
                      <th className="text-left px-4 py-2 font-medium">状态</th>
                      <th className="text-left px-4 py-2 font-medium">分类</th>
                      <th className="text-left px-4 py-2 font-medium">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {songsData.songs
                      .filter(s => songStatusFilter === "all" || s.status === songStatusFilter)
                      .filter(s => !songFilter || s.title.includes(songFilter))
                      .map(s => (
                        <tr key={s.title} className={`border-t ${dark ? "border-zinc-700/50 hover:bg-zinc-800/50" : "border-border hover:bg-muted/50"}`}>
                          <td className="px-4 py-2">{s.title}</td>
                          <td className="px-4 py-2 text-muted-foreground">{s.artists.join("、") || "—"}</td>
                          <td className="px-4 py-2 text-muted-foreground tabular-nums">
                            {s.key || s.capo !== null
                              ? `${s.key || "?"}${s.capo !== null ? ` · capo${s.capo}` : ""}`
                              : "—"}
                          </td>
                          <td className="px-4 py-2">
                            <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${s.status === "active" ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300" : "bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300"}`}>
                              {s.status === "active" ? "已会" : "未会"}
                            </span>
                          </td>
                          <td className="px-4 py-2 text-muted-foreground">{s.section ? `${s.section}字` : "—"}</td>
                          <td className="px-4 py-2">
                            <div className="flex items-center gap-1.5">
                              <button onClick={() => handleToggleStatus(s)}
                                className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-colors cursor-pointer ${s.status === "draft"
                                  ? "bg-emerald-100 text-emerald-700 hover:bg-emerald-200 dark:bg-emerald-900 dark:text-emerald-300"
                                  : "bg-amber-100 text-amber-700 hover:bg-amber-200 dark:bg-amber-900 dark:text-amber-300"}`}>
                                {s.status === "draft" ? "学会了 ✓" : "标回未会"}
                              </button>
                              <button onClick={() => openEdit(s)}
                                className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-colors cursor-pointer ${dark ? "bg-zinc-700 text-zinc-300 hover:bg-zinc-600" : "bg-muted text-foreground hover:bg-border"}`}>
                                编辑
                              </button>
                              <button onClick={() => deleteSong(s)}
                                className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-colors cursor-pointer ${dark ? "text-red-400 hover:bg-zinc-700" : "text-red-500 hover:bg-red-50"}`}>
                                删除
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="flex-1 flex items-center justify-center text-muted-foreground">加载中…</div>
            )}
            <div className={`mt-3 text-xs ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
              共 {songsData?.total ?? 0} 首 · 已会 {songsData?.active ?? 0} · 未会 {songsData?.draft ?? 0}
            </div>
          </main>
          )}

          {/* ===== 其他视图占位 ===== */}
          {["learning", "themes", "presets", "history", "settings"].includes(view) && (
          <main className="flex-1 flex items-center justify-center">
            <div className="text-center space-y-3">
              <div className={`w-16 h-16 mx-auto rounded-2xl flex items-center justify-center text-2xl shadow-sm ${dark ? "bg-zinc-800" : "bg-muted"}`}>
                {navItems.find(n => n.id === view)?.icon}
              </div>
              <p className="text-sm text-muted-foreground">{navItems.find(n => n.id === view)?.label} — 二期功能</p>
            </div>
          </main>
          )}

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

      {/* ========== 导出对话框 ========== */}
      {exportDialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-[2px]"
          onClick={() => !exporting && setExportDialogOpen(false)}>
          <div className={`w-[420px] rounded-2xl p-6 shadow-2xl transition-colors ${dark ? "bg-zinc-800 border border-zinc-700 text-zinc-200" : "bg-card border border-border text-card-foreground"}`}
            onClick={e => e.stopPropagation()}>
            <h3 className="text-base font-semibold mb-1">导出海报</h3>
            <p className="text-xs text-muted-foreground mb-4">
              排版 全行网格绕排版 · 主题 {selTheme || "—"} · 画布 {canvas} · 避让{avoid ? "开" : "关"}
            </p>

            {/* 范围选择 */}
            <div className="space-y-2 mb-4">
              {([
                { id: "page", label: `当前页（${selTheme || "—"} 第 ${page} 页）`, count: 1 },
                { id: "theme", label: `当前主题全部页（${maxPage} 张）`, count: maxPage },
                { id: "all", label: `全部 ${themes.length} 个主题 × ${maxPage} 页`, count: themes.length * maxPage },
              ] as const).map(opt => (
                <label key={opt.id} className={`flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm cursor-pointer transition-colors ${exportScope === opt.id
                  ? (dark ? "bg-emerald-500/15 ring-1 ring-emerald-400/50" : "bg-primary-soft ring-1 ring-primary/40")
                  : (dark ? "hover:bg-zinc-700/50" : "hover:bg-muted")}`}>
                  <input type="radio" name="export-scope" checked={exportScope === opt.id}
                    onChange={() => setExportScope(opt.id)} disabled={exporting}
                    className={dark ? "accent-emerald-400" : "accent-primary"} />
                  <span className="flex-1">{opt.label}</span>
                  <span className="text-xs text-muted-foreground tabular-nums">{opt.count} 张</span>
                </label>
              ))}
            </div>

            {/* 预估 */}
            {!exporting && !exportDone && (
              <p className="text-xs text-muted-foreground mb-4">
                预估输出 <span className={dark ? "text-zinc-200" : "text-foreground"}>{estimateCount} 张</span>
                ，耗时约 <span className={dark ? "text-zinc-200" : "text-foreground"}>{(estimateMs / 1000).toFixed(1)} 秒</span>
                {lastRenderMs ? `（按实测 ${Math.round(lastRenderMs)}ms/张）` : "（按冷启动估 900ms/张）"}
              </p>
            )}

            {/* 进度条 */}
            {exportProgress && !exportDone && (
              <div className="mb-4">
                <div className={`h-2 rounded-full overflow-hidden ${dark ? "bg-zinc-700" : "bg-muted"}`}>
                  <div className={`h-full rounded-full transition-all duration-300 ${dark ? "bg-emerald-400" : "bg-primary"}`}
                    style={{ width: `${exportProgress.total ? (exportProgress.done / exportProgress.total) * 100 : 0}%` }} />
                </div>
                <p className="text-xs text-muted-foreground mt-1.5 tabular-nums">
                  {exportProgress.done}/{exportProgress.total}　{exportProgress.current}
                </p>
              </div>
            )}

            {/* 完成状态 */}
            {exportDone && (
              <div className={`rounded-xl px-3 py-2.5 mb-4 text-sm ${dark ? "bg-emerald-500/15 text-emerald-300" : "bg-emerald-50 text-emerald-700"}`}>
                ✅ 导出完成：{exportDone.count} 张，耗时 {(exportDone.totalMs / 1000).toFixed(1)} 秒
                <p className="text-xs mt-1 opacity-75 break-all">{exportDone.outputDir}</p>
              </div>
            )}

            {/* 操作按钮 */}
            <div className="flex justify-end gap-2">
              {exportDone && (
                <button onClick={openOutputDir}
                  className={`rounded-xl px-4 py-2 text-sm transition-colors cursor-pointer ${dark ? "bg-zinc-700 hover:bg-zinc-600 text-zinc-200" : "bg-muted hover:bg-border text-foreground"}`}>
                  打开目录
                </button>
              )}
              <button onClick={() => !exporting && setExportDialogOpen(false)} disabled={exporting}
                className={`rounded-xl px-4 py-2 text-sm transition-colors cursor-pointer disabled:opacity-50 ${dark ? "text-zinc-400 hover:text-zinc-200" : "text-muted-foreground hover:text-foreground"}`}>
                关闭
              </button>
              {!exportDone && (
                <button onClick={runExport} disabled={exporting || !selTheme}
                  className="rounded-xl px-5 py-2 text-sm transition-colors cursor-pointer bg-emerald-600 hover:bg-emerald-700 text-white font-medium disabled:opacity-50">
                  {exporting ? "导出中…" : "开始导出"}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ========== 歌曲编辑对话框 ========== */}
      {editTarget !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-[2px]"
          onClick={() => !saving && setEditTarget(null)}>
          <div className={`w-[460px] max-h-[85vh] overflow-y-auto rounded-2xl p-6 shadow-2xl transition-colors ${dark ? "bg-zinc-800 border border-zinc-700 text-zinc-200" : "bg-card border border-border text-card-foreground"}`}
            onClick={e => e.stopPropagation()}>
            <h3 className="text-base font-semibold mb-4">
              {editTarget === "new" ? "新增歌曲" : `编辑「${(editTarget as Song).title}」`}
            </h3>

            <div className="space-y-3">
              {/* 歌名 */}
              <label className="block text-xs text-muted-foreground">
                歌名 <span className="text-red-400">*</span>
                <input type="text" value={editForm.title ?? ""} onChange={e => setEditForm(f => ({ ...f, title: e.target.value }))}
                  className={`mt-1 w-full rounded-lg px-3 py-2 text-sm outline-none ${dark ? "bg-zinc-700 text-zinc-200" : "bg-muted border border-border text-foreground"}`} />
              </label>

              <div className="grid grid-cols-2 gap-3">
                <label className="block text-xs text-muted-foreground">
                  歌手（逗号分隔）
                  <input type="text" value={editForm.artists ?? ""} onChange={e => setEditForm(f => ({ ...f, artists: e.target.value }))}
                    className={`mt-1 w-full rounded-lg px-3 py-2 text-sm outline-none ${dark ? "bg-zinc-700 text-zinc-200" : "bg-muted border border-border text-foreground"}`} />
                </label>
                <label className="block text-xs text-muted-foreground">
                  分类
                  <select value={editForm.section ?? ""} onChange={e => setEditForm(f => ({ ...f, section: e.target.value }))}
                    className={`mt-1 w-full rounded-lg px-3 py-2 text-sm outline-none ${dark ? "bg-zinc-700 text-zinc-200" : "bg-muted border border-border text-foreground"}`}>
                    <option value="">自动（按字数）</option>
                    {[1, 2, 3, 4, 5, 6, 7].map(n => <option key={n} value={n}>{n === 7 ? "7+（长歌名/英文）" : `${n} 字`}</option>)}
                  </select>
                </label>
              </div>

              {/* 弹唱信息 */}
              <div className={`rounded-xl p-3 space-y-3 ${dark ? "bg-zinc-700/40" : "bg-muted/60"}`}>
                <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">弹唱信息</p>
                <div className="grid grid-cols-3 gap-3">
                  <label className="block text-xs text-muted-foreground">
                    选调
                    <input type="text" placeholder="如 G" value={editForm.key ?? ""} onChange={e => setEditForm(f => ({ ...f, key: e.target.value }))}
                      className={`mt-1 w-full rounded-lg px-3 py-2 text-sm outline-none ${dark ? "bg-zinc-700 text-zinc-200" : "bg-card border border-border text-foreground"}`} />
                  </label>
                  <label className="block text-xs text-muted-foreground">
                    变调夹（品）
                    <input type="number" min={0} max={12} placeholder="空=未填" value={editForm.capo ?? ""} onChange={e => setEditForm(f => ({ ...f, capo: e.target.value }))}
                      className={`mt-1 w-full rounded-lg px-3 py-2 text-sm outline-none ${dark ? "bg-zinc-700 text-zinc-200" : "bg-card border border-border text-foreground"}`} />
                  </label>
                  <label className="block text-xs text-muted-foreground">
                    难度
                    <select value={editForm.difficulty ?? ""} onChange={e => setEditForm(f => ({ ...f, difficulty: e.target.value }))}
                      className={`mt-1 w-full rounded-lg px-3 py-2 text-sm outline-none ${dark ? "bg-zinc-700 text-zinc-200" : "bg-card border border-border text-foreground"}`}>
                      <option value="">未标</option>
                      <option value="简单">简单</option>
                      <option value="中等">中等</option>
                      <option value="困难">困难</option>
                    </select>
                  </label>
                </div>
                <label className="block text-xs text-muted-foreground">
                  谱子（链接或来源）
                  <input type="text" value={editForm.tabs ?? ""} onChange={e => setEditForm(f => ({ ...f, tabs: e.target.value }))}
                    className={`mt-1 w-full rounded-lg px-3 py-2 text-sm outline-none ${dark ? "bg-zinc-700 text-zinc-200" : "bg-card border border-border text-foreground"}`} />
                </label>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <label className="block text-xs text-muted-foreground">
                  作词
                  <input type="text" value={editForm.lyricist ?? ""} onChange={e => setEditForm(f => ({ ...f, lyricist: e.target.value }))}
                    className={`mt-1 w-full rounded-lg px-3 py-2 text-sm outline-none ${dark ? "bg-zinc-700 text-zinc-200" : "bg-muted border border-border text-foreground"}`} />
                </label>
                <label className="block text-xs text-muted-foreground">
                  作曲
                  <input type="text" value={editForm.composer ?? ""} onChange={e => setEditForm(f => ({ ...f, composer: e.target.value }))}
                    className={`mt-1 w-full rounded-lg px-3 py-2 text-sm outline-none ${dark ? "bg-zinc-700 text-zinc-200" : "bg-muted border border-border text-foreground"}`} />
                </label>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <label className="block text-xs text-muted-foreground">
                  标签（逗号分隔）
                  <input type="text" placeholder="如：小甜歌，苦情" value={editForm.tags ?? ""} onChange={e => setEditForm(f => ({ ...f, tags: e.target.value }))}
                    className={`mt-1 w-full rounded-lg px-3 py-2 text-sm outline-none ${dark ? "bg-zinc-700 text-zinc-200" : "bg-muted border border-border text-foreground"}`} />
                </label>
                <label className="block text-xs text-muted-foreground">
                  拼音首字母
                  <input type="text" placeholder="空=自动生成" value={editForm.pinyin ?? ""} onChange={e => setEditForm(f => ({ ...f, pinyin: e.target.value }))}
                    className={`mt-1 w-full rounded-lg px-3 py-2 text-sm outline-none ${dark ? "bg-zinc-700 text-zinc-200" : "bg-muted border border-border text-foreground"}`} />
                </label>
              </div>

              <label className="block text-xs text-muted-foreground">
                备注
                <textarea rows={2} placeholder="如：副歌高音要降 key" value={editForm.notes ?? ""} onChange={e => setEditForm(f => ({ ...f, notes: e.target.value }))}
                  className={`mt-1 w-full rounded-lg px-3 py-2 text-sm outline-none resize-none ${dark ? "bg-zinc-700 text-zinc-200" : "bg-muted border border-border text-foreground"}`} />
              </label>
            </div>

            {editError && (
              <p className="mt-3 text-sm text-red-500">{editError}</p>
            )}

            <div className="flex justify-end gap-2 mt-5">
              <button onClick={() => !saving && setEditTarget(null)} disabled={saving}
                className={`rounded-xl px-4 py-2 text-sm transition-colors cursor-pointer disabled:opacity-50 ${dark ? "text-zinc-400 hover:text-zinc-200" : "text-muted-foreground hover:text-foreground"}`}>
                取消
              </button>
              <button onClick={saveEdit} disabled={saving}
                className="rounded-xl px-5 py-2 text-sm transition-colors cursor-pointer bg-emerald-600 hover:bg-emerald-700 text-white font-medium disabled:opacity-50">
                {saving ? "保存中…" : "保存"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
