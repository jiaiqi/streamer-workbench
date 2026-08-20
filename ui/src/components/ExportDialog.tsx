import { useState, useEffect, useCallback, useRef } from "react";
import { apiRequest } from "../api/client";
import { toRequestFailure } from "../async/requestState";
import ExportLogPanel from "../posters/ExportLogPanel";
import ErrorBanner from "./ErrorBanner";
import { useToast } from "./Toast";
import "../lib/streamer";

/* ---- M3 P0 重构后的 ExportDialog：三段式引导 ----
 *   阶段 1（未开始）：范围选择 + 预估 + [开始导出] + [关闭]
 *   阶段 2（进行中）：进度条 + 当前页 + [取消]
 *   阶段 3（完成）：  顶部 ✅ 完成反馈
 *                    中部 ExportLogPanel 近 3 条
 *                    底部 6 动作分 2 行（打开目录 / 复制剪贴板 / Finder /
 *                                    系统分享 / 再导一次 / 关闭）
 *   阶段 4（失败）：  错误提示 + [重试] + [关闭]
 *
 * 之前结构：单一按钮栏（开始 / 关闭 + 3 个分享按钮），体验差：
 *   - 导出中无法取消
 *   - 失败时只能关掉重来
 *   - 完成后用户不知道下一步做什么
 */
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
  const [error, setError] = useState("");
  // M2.16 海报分享：当前页 PNG bytes + share pending
  const [sharePng, setSharePng] = useState<ArrayBuffer | null>(null);
  const [sharePngLoading, setSharePngLoading] = useState(false);
  const [sharePending, setSharePending] = useState<"clipboard" | "finder" | "macos" | null>(null);
  // M3 P0：当前 job_id（导出中才存在）+ 取消中过渡态
  const jobIdRef = useRef<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const toast = useToast();
  const macShareSupported = !!window.streamer?.isMacOSShareSupported?.();

  // 打开 dialog 或 selTheme/page 变化时拉一张当前页 PNG 到内存备用
  useEffect(() => {
    if (!open || exporting) return;
    let cancelled = false;
    setSharePngLoading(true);
    setSharePng(null);
    const url = `/api/render?theme=${encodeURIComponent(selTheme)}&page=${page}&canvas=${encodeURIComponent(canvas)}&avoid=${avoid}${paramsQuery}`;
    fetch(url)
      .then(r => r.ok ? r.arrayBuffer() : Promise.reject(new Error(`render ${r.status}`)))
      .then(buf => { if (!cancelled) setSharePng(buf); })
      .catch(() => { if (!cancelled) setSharePng(null); })
      .finally(() => { if (!cancelled) setSharePngLoading(false); });
    return () => { cancelled = true; };
  }, [open, selTheme, page, canvas, avoid, paramsQuery, exporting]);

  const handleCopyToClipboard = useCallback(async () => {
    if (!sharePng || !window.streamer?.copyImageToClipboard) return;
    setSharePending("clipboard");
    try {
      const r = await window.streamer.copyImageToClipboard({ data: sharePng });
      if (r.ok) toast.success("已复制到剪贴板", "可粘贴到微信 / 邮件 / 任何 App");
      else toast.error("复制失败", r.error || "未知错误");
    } finally {
      setSharePending(null);
    }
  }, [sharePng, toast]);

  const handleRevealInFinder = useCallback(async () => {
    if (!done?.outputDir || !window.streamer?.revealInFinder) return;
    setSharePending("finder");
    try {
      // 拼一个示例文件路径（取第一张）
      const firstFile = done.outputDir.replace(/\/$/, "") + "/page-1.png";
      const r = await window.streamer.revealInFinder({ filePath: firstFile });
      if (!r.ok) {
        // fallback: 让后端打开目录
        try { await apiRequest("/api/export/open", { method: "POST" }); }
        catch { /* 静默 */ }
      }
    } finally {
      setSharePending(null);
    }
  }, [done, toast]);

  const handleMacShare = useCallback(async () => {
    if (!sharePng || !window.streamer?.shareToMacOS) return;
    setSharePending("macos");
    try {
      const r = await window.streamer.shareToMacOS({
        data: sharePng,
        defaultName: `${selTheme || "poster"}-${canvas.replace(/[:/]/g, "_")}-p${page}.png`,
      });
      if (r.ok) toast.success("分享面板已弹出", "选择目标 App 后导出完成");
      else if (r.code === "unsupported") toast.warn("当前平台不支持", "仅 macOS 可用");
      else toast.error("分享失败", r.error || "未知错误");
    } finally {
      setSharePending(null);
    }
  }, [sharePng, selTheme, canvas, page, toast]);

  // 打开时重置进度/完成态 + scope 回到默认
  useEffect(() => {
    if (open) { setDone(null); setProgress(null); setScope("all"); setError(""); setCancelling(false); jobIdRef.current = null; }
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

  // M3 P0：取消正在跑的批量导出
  const handleCancel = useCallback(async () => {
    const id = jobIdRef.current;
    if (!id || cancelling) return;
    setCancelling(true);
    try {
      await apiRequest(`/api/export/jobs/${id}`, { method: "DELETE" });
      // 不立即清进度，让轮询线程读到 cancelled 状态后自行收口
      toast.info("已请求取消", "等待当前页写完…");
    } catch (reason) {
      // 404 等：job 已结束，忽略
      const failure = toRequestFailure(reason, "取消失败");
      if (!/not_found|404/.test(failure.message)) {
        toast.error("取消失败", failure.message);
      }
    } finally {
      setCancelling(false);
    }
  }, [cancelling, toast]);

  const runExport = async () => {
    if (exporting) return;
    setExporting(true);
    setError("");
    setDone(null);
    setProgress({ done: 0, total: estimateCount, current: "" });
    try {
      if (scope === "all") {
        // 批量：后端后台任务 + 300ms 轮询进度
        const { job_id } = await apiRequest<{ job_id: string }>(
          `/api/export/batch?canvas=${encodeURIComponent(canvas)}&avoid=${avoid}`,
          { method: "POST" });
        jobIdRef.current = job_id;
        await new Promise<void>((resolve) => {
          const timer = setInterval(async () => {
            try {
              const j = await apiRequest<{ status: string; done: number; total: number; current: string; total_ms: number; output_dir: string; error?: string }>(`/api/export/jobs/${job_id}`);
              setProgress({ done: j.done, total: j.total, current: j.current });
              if (j.status === "done" || j.status === "error" || j.status === "cancelled") {
                clearInterval(timer);
                jobIdRef.current = null;
                if (j.status === "error") {
                  setError(j.error || "批量导出失败");
                } else if (j.status === "cancelled") {
                  setError("已取消");
                } else {
                  setDone({ count: j.done, totalMs: j.total_ms, outputDir: j.output_dir });
                  onRendered(j.total_ms / Math.max(j.total, 1));
                }
                resolve();
              }
            } catch (reason) {
              clearInterval(timer);
              jobIdRef.current = null;
              setError(toRequestFailure(reason, "批量导出失败").message);
              resolve();
            }
          }, 300);
        });
      } else {
        // 单页 / 当前主题全部页：前端顺序调用单页导出
        const pages = scope === "page" ? [page]
          : Array.from({ length: maxPage }, (_, i) => i + 1);
        const t0 = performance.now();
        let cancelled = false;
        for (const p of pages) {
          // 单页串行场景不支持取消（每个请求都很短），保持原行为
          if (cancelled) break;
          setProgress({ done: p - pages[0], total: pages.length, current: `${selTheme} p${p}` });
          try {
            const data = await apiRequest<{ duration_ms: number }>(
              `/api/export?theme=${encodeURIComponent(selTheme)}&page=${p}&canvas=${encodeURIComponent(canvas)}&avoid=${avoid}${paramsQuery}`,
              { method: "POST" });
            onRendered(data.duration_ms);
            setProgress({ done: p - pages[0] + 1, total: pages.length, current: `${selTheme} p${p}` });
          } catch (reason) {
            cancelled = true;
            setError(toRequestFailure(reason, "导出失败").message);
            break;
          }
        }
        if (!cancelled) {
          const st = await apiRequest<{ output_dir: string }>("/api/settings");
          setDone({ count: pages.length, totalMs: Math.round(performance.now() - t0), outputDir: st.output_dir });
        }
      }
    } catch (reason) {
      setError(toRequestFailure(reason, "导出失败").message);
    }
    setExporting(false);
  };

  const openOutputDir = async () => {
    try { await apiRequest("/api/export/open", { method: "POST" }); }
    catch (reason) { setError(toRequestFailure(reason, "无法打开输出目录").message); }
  };

  // ── M3 P0：阶段判定 ──
  const isStage = (s: "idle" | "running" | "done" | "error"): boolean => {
    if (s === "running") return exporting;
    if (s === "done") return !!done && !exporting;
    if (s === "error") return !!error && !exporting && !done;
    return !exporting && !done && !error;
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-[2px]"
      onClick={() => !exporting && onClose()}>
      <div className={`w-[420px] rounded-2xl p-6 shadow-2xl transition-colors ${dark ? "bg-zinc-800 border border-zinc-700 text-zinc-200" : "bg-card border border-border text-card-foreground"}`}
        onClick={e => e.stopPropagation()}
        data-testid="export-dialog"
        data-stage={isStage("running") ? "running" : isStage("done") ? "done" : isStage("error") ? "error" : "idle"}>
        <h3 className="text-base font-semibold mb-1">导出海报</h3>
        <p className="text-xs text-muted-foreground mb-4">
          排版 全行网格绕排版 · 主题 {selTheme || "—"} · 画布 {canvas} · 避让{avoid ? "开" : "关"}
        </p>

        {/* 范围选择：仅 idle / error 阶段显示 */}
        {(isStage("idle") || isStage("error")) && (
          <div className="space-y-2 mb-4">
            {([
              { id: "page", label: `当前页（${selTheme || "—"} 第 ${page} 页）`, count: 1 },
              { id: "theme", label: `当前主题全部页（${maxPage} 张）`, count: maxPage },
              { id: "all", label: `全部 ${themesCount} 个主题 × ${maxPage} 页`, count: themesCount * maxPage },
            ] as const).map(opt => (
              <label key={opt.id} className={`flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm cursor-pointer transition-colors ${scope === opt.id
                ? "bg-primary-soft ring-1 ring-primary/40"
                : (dark ? "hover:bg-zinc-700/50" : "hover:bg-muted")}`}>
                <input type="radio" name="export-scope" checked={scope === opt.id}
                  onChange={() => setScope(opt.id)} disabled={exporting}
                  className="accent-primary" />
                <span className="flex-1">{opt.label}</span>
                <span className="text-xs text-muted-foreground tabular-nums">{opt.count} 张</span>
              </label>
            ))}
          </div>
        )}

        {/* 预估：仅 idle 显示 */}
        {isStage("idle") && (
          <p className="text-xs text-muted-foreground mb-4">
            预估输出 <span className={dark ? "text-zinc-200" : "text-foreground"}>{estimateCount} 张</span>
            ，耗时约 <span className={dark ? "text-zinc-200" : "text-foreground"}>{(estimateMs / 1000).toFixed(1)} 秒</span>
            {lastRenderMs ? `（按实测 ${Math.round(lastRenderMs)}ms/张）` : "（按冷启动估 900ms/张）"}
          </p>
        )}

        {/* 进度条：仅 running 阶段 */}
        {isStage("running") && progress && (
          <div className="mb-4" data-testid="export-progress">
            <div className={`h-2 rounded-full overflow-hidden ${dark ? "bg-zinc-700" : "bg-muted"}`}>
              <div className={`h-full rounded-full transition-all duration-300 ${dark ? "bg-emerald-400" : "bg-primary"}`}
                style={{ width: `${progress.total ? (progress.done / progress.total) * 100 : 0}%` }} />
            </div>
            <p className="text-xs text-muted-foreground mt-1.5 tabular-nums">
              {progress.done}/{progress.total}　{progress.current}
            </p>
          </div>
        )}

        {/* ─── 三段式引导：完成态 ─── */}
        {isStage("done") && done && (
          <div data-testid="export-done-section">
            {/* 顶部：✅ 完成反馈 */}
            <div className={`rounded-xl px-3 py-2.5 mb-3 text-sm ${dark ? "bg-emerald-500/15 text-emerald-300" : "bg-emerald-50 text-emerald-700"}`}>
              <p>✅ 导出完成：{done.count} 张，耗时 {(done.totalMs / 1000).toFixed(1)} 秒</p>
              <p className="text-xs mt-1 opacity-75 break-all">{done.outputDir}</p>
            </div>
            {/* 中部：最近的导出（ExportLogPanel） */}
            <div className="mb-3">
              <ExportLogPanel
                dark={dark}
                limit={3}
                kindFilter="grid-export"
                title="最近 3 次导出"
                inline
                data-testid="export-recent-log"
              />
            </div>
            {/* 底部：6 动作分 2 行 */}
            <div className="space-y-2" data-testid="export-action-row">
              <div className="flex flex-wrap gap-2">
                <button onClick={openOutputDir}
                  data-testid="export-open-dir"
                  className={`flex-1 min-w-[110px] rounded-xl px-3 py-2 text-sm transition-colors cursor-pointer ${dark ? "bg-zinc-700 hover:bg-zinc-600 text-zinc-200" : "bg-muted hover:bg-border text-foreground"}`}>
                  📁 打开目录
                </button>
                <button
                  onClick={handleCopyToClipboard}
                  disabled={sharePending !== null || sharePngLoading || !sharePng}
                  data-testid="export-copy-clipboard"
                  title={sharePngLoading ? "正在加载海报…" : !sharePng ? "海报加载失败" : ""}
                  className={`flex-1 min-w-[110px] rounded-xl px-3 py-2 text-sm transition-colors cursor-pointer disabled:opacity-50 ${dark ? "bg-zinc-700 hover:bg-zinc-600 text-zinc-200" : "bg-muted hover:bg-border text-foreground"}`}>
                  {sharePending === "clipboard" ? "复制中…" : "📋 复制到剪贴板"}
                </button>
                <button
                  onClick={handleRevealInFinder}
                  disabled={sharePending !== null}
                  data-testid="export-reveal-finder"
                  title={macShareSupported ? "在 Finder 中高亮海报" : "在文件管理器中打开"}
                  className={`flex-1 min-w-[110px] rounded-xl px-3 py-2 text-sm transition-colors cursor-pointer disabled:opacity-50 ${dark ? "bg-zinc-700 hover:bg-zinc-600 text-zinc-200" : "bg-muted hover:bg-border text-foreground"}`}>
                  {sharePending === "finder" ? "打开中…" : macShareSupported ? "📁 Finder" : "📁 文件夹"}
                </button>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={handleMacShare}
                  disabled={sharePending !== null || !macShareSupported || sharePngLoading || !sharePng}
                  data-testid="export-mac-share"
                  title={!macShareSupported ? "仅 macOS 可用" : sharePngLoading ? "正在加载海报…" : !sharePng ? "海报加载失败" : "弹系统级分享面板（AirDrop / 微信 / 邮件）"}
                  className={`flex-1 min-w-[110px] rounded-xl px-3 py-2 text-sm transition-colors cursor-pointer disabled:opacity-40 ${dark ? "bg-zinc-700 hover:bg-zinc-600 text-zinc-200" : "bg-muted hover:bg-border text-foreground"}`}>
                  {sharePending === "macos" ? "分享中…" : "🪟 系统分享"}
                </button>
                <button
                  onClick={runExport}
                  data-testid="export-retry-again"
                  className="primary-action flex-1 min-w-[110px] rounded-xl px-3 py-2 text-sm cursor-pointer">
                  ↻ 再导一次
                </button>
                <button
                  onClick={onClose}
                  data-testid="export-close-done"
                  className={`flex-1 min-w-[110px] rounded-xl px-3 py-2 text-sm transition-colors cursor-pointer ${dark ? "text-zinc-400 hover:text-zinc-200" : "text-muted-foreground hover:text-foreground"}`}>
                  关闭
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ─── 错误阶段：提示 + 重试 + 关闭 ─── */}
        {isStage("error") && (
          <div data-testid="export-error-section">
            {/* 3.2 收口：原裸 div 改用 ErrorBanner（mb-4 保留外边距） */}
            <div className="mb-4" data-testid="export-error-message">
              <ErrorBanner severity="error" message={error || "导出失败"} dark={dark} />
            </div>
            <div className="flex justify-end gap-2 flex-wrap">
              <button onClick={onClose}
                data-testid="export-close-error"
                className={`rounded-xl px-4 py-2 text-sm transition-colors cursor-pointer ${dark ? "text-zinc-400 hover:text-zinc-200" : "text-muted-foreground hover:text-foreground"}`}>
                关闭
              </button>
              <button onClick={runExport} disabled={exporting || !selTheme}
                data-testid="export-retry"
                className="primary-action rounded-xl px-5 py-2 text-sm cursor-pointer disabled:opacity-50">
                重试
              </button>
            </div>
          </div>
        )}

        {/* ─── idle 阶段：开始导出 + 关闭 ─── */}
        {isStage("idle") && (
          <div className="flex justify-end gap-2 flex-wrap">
            <button onClick={onClose}
              data-testid="export-close-idle"
              className={`rounded-xl px-4 py-2 text-sm transition-colors cursor-pointer ${dark ? "text-zinc-400 hover:text-zinc-200" : "text-muted-foreground hover:text-foreground"}`}>
              关闭
            </button>
            <button onClick={runExport} disabled={exporting || !selTheme}
              data-testid="export-start"
              className="primary-action rounded-xl px-5 py-2 text-sm cursor-pointer disabled:opacity-50">
              开始导出
            </button>
          </div>
        )}

        {/* ─── running 阶段：取消按钮 ─── */}
        {isStage("running") && (
          <div className="flex justify-end gap-2 flex-wrap">
            <button
              onClick={handleCancel}
              disabled={cancelling}
              data-testid="export-cancel"
              title="终止当前批量导出任务"
              className={`rounded-xl px-4 py-2 text-sm transition-colors cursor-pointer disabled:opacity-50 ${dark ? "bg-zinc-700 hover:bg-red-500/20 text-zinc-200" : "bg-muted hover:bg-red-50 text-foreground"}`}>
              {cancelling ? "取消中…" : "取消"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
