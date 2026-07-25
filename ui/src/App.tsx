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

/* ==================== App ==================== */
export default function App() {
  const [themes, setThemes] = useState<Theme[]>([]);
  const [layouts, setLayouts] = useState<Layout[]>([]);
  const [selTheme, setSelTheme] = useState<string>("");
  const [selLayout] = useState<string>("grid-wrap");
  const [page, setPage] = useState(1);
  const [avoid, setAvoid] = useState(true);
  const [canvas, setCanvas] = useState<string>("抖音全屏 9:20");
  const [zoom, setZoom] = useState(50); // %
  const [loading, setLoading] = useState(false);

  /* ---- fetch data ---- */
  useEffect(() => {
    fetch("/api/themes").then(r => r.json()).then((d: Theme[]) => {
      setThemes(d);
      if (d.length) setSelTheme(d[0].name);
    });
    fetch("/api/layouts").then(r => r.json()).then(setLayouts);
  }, []);

  const maxPage = layouts.find(l => l.id === selLayout)?.pages ?? 2;

  /* ---- preview url ---- */
  const previewSrc = selTheme
    ? `/api/render?theme=${encodeURIComponent(selTheme)}&page=${page}&canvas=${encodeURIComponent(canvas)}&avoid=${avoid}&t=${Date.now()}`
    : "";

  /* ---- render action ---- */
  const handleRender = useCallback(async () => {
    if (!selTheme) return;
    setLoading(true);
    // trigger a fresh load by bumping time param
    setTimeout(() => setLoading(false), 800);
  }, [selTheme]);

  const activeTheme = themes.find(t => t.name === selTheme);
  const bgUrl = activeTheme
    ? `/bg/${encodeURIComponent(selTheme)}/${activeTheme.backgrounds[String(page)]}`
    : "";

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-zinc-950">
      {/* ========== LEFT PANE ========== */}
      <aside className="w-72 flex-shrink-0 flex flex-col border-r border-white/5">
        <div className="px-5 py-4 border-b border-white/5">
          <h1 className="text-sm font-semibold tracking-wide text-zinc-400 uppercase">歌单海报</h1>
          <p className="text-xs text-zinc-600 mt-0.5">梓涵吃不饱 · 点歌歌单</p>
        </div>

        {/* themes */}
        <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
          <p className="text-[11px] font-medium text-zinc-500 uppercase tracking-wider px-1">
            主题 · {themes.length}
          </p>
          {themes.map(t => (
            <button
              key={t.name}
              onClick={() => { setSelTheme(t.name); setPage(1); }}
              className={`w-full text-left rounded-xl overflow-hidden transition-all duration-200 cursor-pointer group ${
                selTheme === t.name
                  ? "ring-2 ring-accent ring-offset-1 ring-offset-zinc-950"
                  : "hover:ring-1 hover:ring-white/10"
              }`}
            >
              <div className="aspect-[9/16] bg-zinc-900 relative overflow-hidden">
                <img
                  src={`/bg/${encodeURIComponent(t.name)}/${t.backgrounds["1"]}`}
                  alt={t.name}
                  className="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity"
                  loading="lazy"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent" />
              </div>
              <div className="px-3 py-2.5 bg-surface border-t border-white/5">
                <p className="text-[13px] font-medium text-zinc-200 truncate">{t.name}</p>
                <p className="text-[11px] text-zinc-500 mt-0.5 truncate">{t.notes || t.prefix}</p>
              </div>
            </button>
          ))}
        </div>
      </aside>

      {/* ========== CENTER — preview ========== */}
      <main className="flex-1 flex flex-col items-center justify-center relative">
        {/* toolbar */}
        <div className="absolute top-4 left-4 right-4 flex items-center justify-between z-10">
          <div className="flex items-center gap-1.5 glass rounded-xl px-3 py-2">
            {Array.from({ length: maxPage }, (_, i) => (
              <button
                key={i}
                onClick={() => setPage(i + 1)}
                className={`w-8 h-8 rounded-lg text-xs font-medium transition-all ${
                  page === i + 1
                    ? "bg-accent text-zinc-900"
                    : "text-zinc-400 hover:text-zinc-200 hover:bg-white/5"
                }`}
              >
                {i + 1}
              </button>
            ))}
            <span className="w-px h-5 bg-white/10 mx-1" />
            <label className="flex items-center gap-1.5 text-xs text-zinc-400 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={avoid}
                onChange={e => setAvoid(e.target.checked)}
                className="accent-accent w-3.5 h-3.5"
              />
              避让
            </label>
          </div>

          <div className="flex items-center gap-2">
            <select
              value={canvas}
              onChange={e => setCanvas(e.target.value)}
              className="glass rounded-lg px-3 py-2 text-xs text-zinc-300 outline-none focus:ring-1 focus:ring-accent/50 appearance-none cursor-pointer"
            >
              {CANVAS_OPTIONS.map(c => (
                <option key={c} value={c} className="bg-surface text-zinc-200">{c}</option>
              ))}
            </select>

            <div className="flex items-center gap-1 glass rounded-lg px-2 py-1.5">
              <button
                onClick={() => setZoom(z => Math.max(15, z - 10))}
                className="w-6 h-6 rounded text-xs text-zinc-400 hover:text-zinc-200 hover:bg-white/5 transition-colors"
              >−</button>
              <span className="text-[11px] text-zinc-500 w-10 text-center tabular-nums">{zoom}%</span>
              <button
                onClick={() => setZoom(z => Math.min(150, z + 10))}
                className="w-6 h-6 rounded text-xs text-zinc-400 hover:text-zinc-200 hover:bg-white/5 transition-colors"
              >+</button>
            </div>
          </div>
        </div>

        {/* preview area */}
        <div className="flex-1 w-full flex items-center justify-center p-6 pt-20">
          {selTheme ? (
            <div
              className="relative rounded-2xl overflow-hidden shadow-2xl shadow-black/50 transition-all duration-300"
              style={{ width: `${(1080 * zoom) / 100}px`, maxHeight: "calc(100vh - 100px)" }}
            >
              <img
                key={`${selTheme}-${page}-${avoid}-${canvas}`}
                src={previewSrc}
                alt={selTheme}
                className="w-full object-contain"
                onLoad={() => setLoading(false)}
                onError={() => setLoading(false)}
              />
              {loading && (
                <div className="absolute inset-0 bg-black/20 flex items-center justify-center">
                  <div className="w-6 h-6 border-2 border-accent border-t-transparent rounded-full animate-spin" />
                </div>
              )}
              {/* avoid zone overlay */}
              {avoid && canvas === "抖音全屏 9:20" && (
                <div
                  className="absolute right-0 border-l border-dashed border-red-500/30 pointer-events-none"
                  style={{
                    top: `${(1080 / 2400) * 100}%`,
                    bottom: 0,
                    width: `${((1080 - 940) / 1080) * 100}%`,
                  }}
                />
              )}
            </div>
          ) : (
            <div className="text-center space-y-2">
              <div className="w-16 h-16 mx-auto rounded-2xl glass flex items-center justify-center text-2xl">
                🎵
              </div>
              <p className="text-sm text-zinc-500">左侧选择一个主题开始预览</p>
            </div>
          )}
        </div>

        {/* bottom bar */}
        <div className="absolute bottom-4 left-4 right-4 flex items-center justify-between glass rounded-2xl px-4 py-3">
          <div className="flex items-center gap-3 text-xs text-zinc-500">
            <span>排版：<span className="text-zinc-300">{layouts.find(l => l.id === selLayout)?.name ?? selLayout}</span></span>
            <span className="w-px h-4 bg-white/10" />
            <span>主题：<span className="text-zinc-300">{selTheme || "—"}</span></span>
            <span className="w-px h-4 bg-white/10" />
            <span>画布：<span className="text-zinc-300">{canvas}</span></span>
          </div>
          <div className="flex items-center gap-2">
            {/* download */}
            {previewSrc && (
              <a
                href={previewSrc}
                download={`${activeTheme?.prefix ?? "poster"}-p${page}.png`}
                className="glass-hover rounded-xl px-4 py-2 text-sm text-zinc-300 hover:text-white transition-colors cursor-pointer no-underline"
              >
                下载
              </a>
            )}
            <button
              onClick={handleRender}
              className="bg-accent hover:bg-accent/90 text-zinc-900 font-medium rounded-xl px-5 py-2 text-sm transition-all active:scale-95 cursor-pointer"
            >
              {loading ? "渲染中…" : "刷新预览"}
            </button>
          </div>
        </div>
      </main>

      {/* ========== RIGHT PANE — params ========== */}
      <aside className="w-64 flex-shrink-0 border-l border-white/5 flex flex-col overflow-y-auto">
        <div className="px-5 py-4 border-b border-white/5">
          <h2 className="text-xs font-semibold text-zinc-400 uppercase tracking-wide">参数</h2>
        </div>

        <div className="flex-1 px-4 py-3 space-y-5">
          {/* canvas section */}
          <section>
            <h3 className="text-[11px] font-medium text-zinc-500 uppercase tracking-wider mb-2">画布</h3>
            <div className="space-y-2">
              <label className="flex items-center justify-between text-xs text-zinc-400">
                预设
                <select
                  value={canvas}
                  onChange={e => setCanvas(e.target.value)}
                  className="glass rounded-lg px-2 py-1 text-xs text-zinc-300 outline-none cursor-pointer"
                >
                  {CANVAS_OPTIONS.map(c => <option key={c} value={c} className="bg-surface">{c}</option>)}
                </select>
              </label>
              <label className="flex items-center justify-between text-xs text-zinc-400">
                尺寸
                <span className="text-zinc-500 tabular-nums">
                  {canvas === "标准 9:16" ? "1080×1920" : "1080×2400"}
                </span>
              </label>
              <label className="flex items-center justify-between text-xs text-zinc-400">
                页数
                <span className="text-zinc-500 tabular-nums">{maxPage}</span>
              </label>
            </div>
          </section>

          {/* layout section */}
          <section>
            <h3 className="text-[11px] font-medium text-zinc-500 uppercase tracking-wider mb-2">排版</h3>
            <div className="space-y-2">
              <label className="flex items-center justify-between text-xs text-zinc-400">
                边距
                <input type="number" defaultValue={58} className="w-16 glass rounded-lg px-2 py-1 text-xs text-zinc-300 outline-none text-right" />
              </label>
              <label className="flex items-center justify-between text-xs text-zinc-400">
                歌名字号
                <input type="number" defaultValue={36} className="w-16 glass rounded-lg px-2 py-1 text-xs text-zinc-300 outline-none text-right" />
              </label>
              <label className="flex items-center justify-between text-xs text-zinc-400">
                行高
                <input type="number" defaultValue={44} className="w-16 glass rounded-lg px-2 py-1 text-xs text-zinc-300 outline-none text-right" />
              </label>
              <label className="flex items-center justify-between text-xs text-zinc-400">
                区块间距
                <input type="number" defaultValue={26} className="w-16 glass rounded-lg px-2 py-1 text-xs text-zinc-300 outline-none text-right" />
              </label>
            </div>
          </section>

          {/* theme info */}
          {activeTheme && (
            <section>
              <h3 className="text-[11px] font-medium text-zinc-500 uppercase tracking-wider mb-2">当前主题</h3>
              <div className="glass rounded-xl p-3 space-y-1.5 text-xs">
                <p className="text-zinc-300 font-medium">{activeTheme.name}</p>
                <p className="text-zinc-500 break-all leading-relaxed">{activeTheme.notes || "无备注"}</p>
                <p className="text-zinc-600">
                  水印修正：{activeTheme.watermark_fix ? "是" : "否"}
                </p>
              </div>
            </section>
          )}
        </div>
      </aside>
    </div>
  );
}
