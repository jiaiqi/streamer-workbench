/// M3 P3：导出历史抽屉
///
/// 点 ExportLogPanel 行 → 弹右侧滑入抽屉显示完整导出信息 + 操作：
///   - 在 Finder 中显示（调 streamer.revealInFinder / shell.showItemInFolder）
///   - 复制文件路径到剪贴板（navigator.clipboard.writeText）
///   - 复制输出目录路径
///   - 关闭（Esc / 点击遮罩 / X 按钮）
///
/// 零新依赖（纯 React + 现有工具）。
import { useEffect } from "react";
import type { ExportLogEntryResponse } from "../api/generated";
import { isElectron } from "../electron-bridge";

interface ExportLogDrawerProps {
  item: ExportLogEntryResponse;
  dark: boolean;
  onClose: () => void;
  onToast: (kind: "success" | "error" | "warn" | "info", message: string) => void;
}

export default function ExportLogDrawer({
  item, dark, onClose, onToast,
}: ExportLogDrawerProps) {
  // Esc 关闭
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // 全屏文件路径（output_dir + filename 拼接；output_dir 可能为 null）
  const fullPath = item.output_dir && item.filename
    ? `${item.output_dir.replace(/\/$/, "")}/${item.filename}`
    : null;

  const handleReveal = async () => {
    if (!fullPath) {
      onToast("warn", "暂无文件路径（可能在内存中未落盘）");
      return;
    }
    if (isElectron() && window.streamer?.revealInFinder) {
      const r = await window.streamer.revealInFinder({ filePath: fullPath });
      if (r.ok) onToast("success", "已在 Finder 中高亮文件");
      else onToast("error", `Finder 定位失败：${r.error ?? "未知错误"}`);
    } else {
      onToast("warn", "Finder 定位仅 Electron 桌面端支持");
    }
  };

  const handleCopyPath = async (path: string, label: string) => {
    try {
      await navigator.clipboard.writeText(path);
      onToast("success", `${label}已复制到剪贴板`);
    } catch (err) {
      onToast("error", `复制失败：${err instanceof Error ? err.message : "未知错误"}`);
    }
  };

  const totalMs = typeof item.total_ms === "number" ? item.total_ms : null;

  return (
    <>
      {/* 遮罩 */}
      <div
        className="fixed inset-0 z-40 bg-black/30 backdrop-blur-[2px] transition-opacity"
        onClick={onClose}
        data-testid="export-log-drawer-overlay"
        aria-hidden="true"
      />
      {/* 抽屉（右滑入 400px 宽） */}
      <aside
        role="dialog"
        aria-label="导出详情"
        aria-modal="true"
        data-testid="export-log-drawer"
        className={`fixed right-0 top-0 bottom-0 z-50 w-[420px] max-w-[90vw] shadow-2xl overflow-y-auto ${
          dark ? "bg-zinc-900 text-zinc-200 border-l border-zinc-800" : "bg-card text-card-foreground border-l border-border"
        }`}
      >
        <div className={`sticky top-0 z-10 flex items-center justify-between px-4 py-3 border-b ${
          dark ? "bg-zinc-900 border-zinc-800" : "bg-card border-border"
        }`}>
          <h2 className="text-sm font-semibold">导出详情</h2>
          <button
            type="button"
            aria-label="关闭"
            onClick={onClose}
            data-testid="export-log-drawer-close"
            className={`rounded-md w-7 h-7 flex items-center justify-center text-base ${
              dark ? "hover:bg-zinc-800" : "hover:bg-muted"
            }`}
          >
            ✕
          </button>
        </div>
        <div className="p-4 space-y-3 text-xs">
          <Field label="类型" value={item.kind || "—"} dark={dark} />
          <Field label="主题" value={item.subject || "—"} dark={dark} />
          <Field label="时间" value={formatFullTime(item.occurred_at)} dark={dark} />
          {item.title && <Field label="标题" value={item.title} dark={dark} />}
          {item.session_id && <Field label="会话 ID" value={item.session_id} dark={dark} />}
          {item.period_label && <Field label="周期" value={item.period_label} dark={dark} />}
          {typeof item.days === "number" && <Field label="天数" value={String(item.days)} dark={dark} />}
          <Field label="数量" value={String(item.count)} dark={dark} />
          {totalMs !== null && (
            <Field label="耗时" value={`${(totalMs / 1000).toFixed(2)} 秒`} dark={dark} />
          )}
          {item.output_dir && (
            <div>
              <Label text="输出目录" dark={dark} />
              <PathRow path={item.output_dir} onCopy={() => handleCopyPath(item.output_dir!, "输出目录")} dark={dark} />
            </div>
          )}
          {item.filename && (
            <div>
              <Label text="文件名" dark={dark} />
              <PathRow path={item.filename} onCopy={() => handleCopyPath(item.filename!, "文件名")} dark={dark} />
            </div>
          )}
          {fullPath && (
            <div>
              <Label text="完整路径" dark={dark} />
              <PathRow path={fullPath} onCopy={() => handleCopyPath(fullPath, "完整路径")} dark={dark} />
            </div>
          )}

          {/* 操作按钮 */}
          <div className="flex flex-wrap gap-2 pt-2">
            <button
              type="button"
              onClick={handleReveal}
              disabled={!fullPath}
              data-testid="export-log-drawer-reveal"
              className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                dark
                  ? "bg-sky-600 hover:bg-sky-500 text-white disabled:bg-zinc-800 disabled:text-zinc-500"
                  : "bg-primary text-primary-foreground hover:bg-primary/90 disabled:bg-muted disabled:text-muted-foreground"
              } disabled:cursor-not-allowed`}
            >
              📁 在 Finder 中显示
            </button>
            {fullPath && (
              <button
                type="button"
                onClick={() => handleCopyPath(fullPath, "完整路径")}
                data-testid="export-log-drawer-copy-path"
                className={`rounded-md px-3 py-1.5 text-xs transition-colors ${
                  dark ? "bg-zinc-800 hover:bg-zinc-700" : "bg-muted hover:bg-border"
                }`}
              >
                📋 复制路径
              </button>
            )}
          </div>
          <p className={`text-[10px] pt-2 ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
            事件 ID：<code className="font-mono">{item.event_id}</code>
          </p>
        </div>
      </aside>
    </>
  );
}

/* ---- helpers ---- */

function Field({ label, value, dark }: { label: string; value: string; dark: boolean }) {
  return (
    <div>
      <Label text={label} dark={dark} />
      <div
        data-testid={`export-log-drawer-field-${label}`}
        className={`text-xs ${dark ? "text-zinc-300" : "text-foreground"}`}
      >
        {value}
      </div>
    </div>
  );
}

function Label({ text, dark }: { text: string; dark: boolean }) {
  return (
    <div
      className={`text-[10px] font-medium uppercase tracking-wide mb-0.5 ${
        dark ? "text-zinc-500" : "text-muted-foreground"
      }`}
    >
      {text}
    </div>
  );
}

function PathRow({ path, onCopy, dark }: { path: string; onCopy: () => void; dark: boolean }) {
  return (
    <div className="flex items-center gap-1">
      <code
        data-testid="export-log-drawer-path"
        className={`flex-1 min-w-0 truncate font-mono text-[11px] px-2 py-1 rounded ${
          dark ? "bg-zinc-800 text-zinc-300" : "bg-muted text-foreground"
        }`}
      >
        {path}
      </code>
      <button
        type="button"
        onClick={onCopy}
        data-testid="export-log-drawer-copy-button"
        aria-label={`复制 ${path}`}
        className={`shrink-0 rounded-md w-7 h-7 flex items-center justify-center text-xs ${
          dark ? "hover:bg-zinc-800" : "hover:bg-muted"
        }`}
      >
        📋
      </button>
    </div>
  );
}

function formatFullTime(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("zh-CN", { hour12: false });
}
