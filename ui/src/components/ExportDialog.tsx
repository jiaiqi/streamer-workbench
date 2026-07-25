import { useState, useEffect } from "react";

/* ---- 导出对话框：范围选择 + 预估 + 进度 + 打开目录 ----
   常挂载（open 控制显隐），保证范围选择跨次打开记忆；
   每次打开时重置进度/完成态（与原 App 行为一致）。 */
export default function ExportDialog({ dark, open, onClose, selTheme, page, maxPage, themesCount, canvas, avoid, paramsQuery, lastRenderMs, onRendered }: {
  dark: boolean;
  open: boolean;
  onClose: () => void;
  selTheme: string;
  page: number;
  maxPage: number;
  themesCount: number;
  canvas: string;
  avoid: boolean;
  paramsQuery: string;
  lastRenderMs: number | null;
  onRendered: (msPerRender: number) => void;
}) {
  const [scope, setScope] = useState<"page" | "theme" | "all">("all");
  const [exporting, setExporting] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number; current: string } | null>(null);
  const [done, setDone] = useState<{ count: number; totalMs: number; outputDir: string } | null>(null);

  // 打开时重置进度/完成态
  useEffect(() => {
    if (open) { setDone(null); setProgress(null); }
  }, [open]);

  // Esc 关闭（导出中不响应）——输入框聚焦时也要生效
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !exporting) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, exporting, onClose]);

  if (!open) return null;

  const estimateCount = scope === "page" ? 1
    : scope === "theme" ? maxPage
    : themesCount * maxPage;
  const estimateMs = estimateCount * (lastRenderMs ?? 900);

  const runExport = async () => {
    setExporting(true);
    setDone(null);
    setProgress({ done: 0, total: estimateCount, current: "" });
    try {
      if (scope === "all") {
        // 批量：后端后台任务 + 300ms 轮询进度
        const res = await fetch(
          `/api/export/batch?canvas=${encodeURIComponent(canvas)}&avoid=${avoid}`,
          { method: "POST" });
        const { job_id } = await res.json();
        await new Promise<void>((resolve) => {
          const timer = setInterval(async () => {
            const j = await (await fetch(`/api/export/jobs/${job_id}`)).json();
            setProgress({ done: j.done, total: j.total, current: j.current });
            if (j.status === "done" || j.status === "error") {
              clearInterval(timer);
              if (j.status === "done") {
                setDone({ count: j.done, totalMs: j.total_ms, outputDir: j.output_dir });
                onRendered(j.total_ms / j.total);
              }
              resolve();
            }
          }, 300);
        });
      } else {
        // 单页 / 当前主题全部页：前端顺序调用单页导出
        const pages = scope === "page" ? [page]
          : Array.from({ length: maxPage }, (_, i) => i + 1);
        const t0 = performance.now();
        for (const p of pages) {
          setProgress({ done: p - pages[0], total: pages.length, current: `${selTheme} p${p}` });
          const res = await fetch(
            `/api/export?theme=${encodeURIComponent(selTheme)}&page=${p}&canvas=${encodeURIComponent(canvas)}&avoid=${avoid}${paramsQuery}`,
            { method: "POST" });
          const data = await res.json();
          onRendered(data.duration_ms);
          setProgress({ done: p - pages[0] + 1, total: pages.length, current: `${selTheme} p${p}` });
        }
        const st = await (await fetch("/api/settings")).json();
        setDone({ count: pages.length, totalMs: Math.round(performance.now() - t0), outputDir: st.output_dir });
      }
    } catch (e) {
      console.error("导出失败", e);
    }
    setExporting(false);
  };

  const openOutputDir = () => fetch("/api/export/open", { method: "POST" });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-[2px]"
      onClick={() => !exporting && onClose()}>
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
            { id: "all", label: `全部 ${themesCount} 个主题 × ${maxPage} 页`, count: themesCount * maxPage },
          ] as const).map(opt => (
            <label key={opt.id} className={`flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm cursor-pointer transition-colors ${scope === opt.id
              ? (dark ? "bg-emerald-500/15 ring-1 ring-emerald-400/50" : "bg-primary-soft ring-1 ring-primary/40")
              : (dark ? "hover:bg-zinc-700/50" : "hover:bg-muted")}`}>
              <input type="radio" name="export-scope" checked={scope === opt.id}
                onChange={() => setScope(opt.id)} disabled={exporting}
                className={dark ? "accent-emerald-400" : "accent-primary"} />
              <span className="flex-1">{opt.label}</span>
              <span className="text-xs text-muted-foreground tabular-nums">{opt.count} 张</span>
            </label>
          ))}
        </div>

        {/* 预估 */}
        {!exporting && !done && (
          <p className="text-xs text-muted-foreground mb-4">
            预估输出 <span className={dark ? "text-zinc-200" : "text-foreground"}>{estimateCount} 张</span>
            ，耗时约 <span className={dark ? "text-zinc-200" : "text-foreground"}>{(estimateMs / 1000).toFixed(1)} 秒</span>
            {lastRenderMs ? `（按实测 ${Math.round(lastRenderMs)}ms/张）` : "（按冷启动估 900ms/张）"}
          </p>
        )}

        {/* 进度条 */}
        {progress && !done && (
          <div className="mb-4">
            <div className={`h-2 rounded-full overflow-hidden ${dark ? "bg-zinc-700" : "bg-muted"}`}>
              <div className={`h-full rounded-full transition-all duration-300 ${dark ? "bg-emerald-400" : "bg-primary"}`}
                style={{ width: `${progress.total ? (progress.done / progress.total) * 100 : 0}%` }} />
            </div>
            <p className="text-xs text-muted-foreground mt-1.5 tabular-nums">
              {progress.done}/{progress.total}　{progress.current}
            </p>
          </div>
        )}

        {/* 完成状态 */}
        {done && (
          <div className={`rounded-xl px-3 py-2.5 mb-4 text-sm ${dark ? "bg-emerald-500/15 text-emerald-300" : "bg-emerald-50 text-emerald-700"}`}>
            ✅ 导出完成：{done.count} 张，耗时 {(done.totalMs / 1000).toFixed(1)} 秒
            <p className="text-xs mt-1 opacity-75 break-all">{done.outputDir}</p>
          </div>
        )}

        {/* 操作按钮 */}
        <div className="flex justify-end gap-2">
          {done && (
            <button onClick={openOutputDir}
              className={`rounded-xl px-4 py-2 text-sm transition-colors cursor-pointer ${dark ? "bg-zinc-700 hover:bg-zinc-600 text-zinc-200" : "bg-muted hover:bg-border text-foreground"}`}>
              打开目录
            </button>
          )}
          <button onClick={() => !exporting && onClose()} disabled={exporting}
            className={`rounded-xl px-4 py-2 text-sm transition-colors cursor-pointer disabled:opacity-50 ${dark ? "text-zinc-400 hover:text-zinc-200" : "text-muted-foreground hover:text-foreground"}`}>
            关闭
          </button>
          {!done && (
            <button onClick={runExport} disabled={exporting || !selTheme}
              className="rounded-xl px-5 py-2 text-sm transition-colors cursor-pointer bg-emerald-600 hover:bg-emerald-700 text-white font-medium disabled:opacity-50">
              {exporting ? "导出中…" : "开始导出"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
