/// R4.2.3 导出历史面板。
///
/// 显示最近的导出记录（工作台批量 / 直播复盘 / 学歌报告三类合一）。
/// 数据源: GET /api/exports/recent（后端从 events.jsonl 读 type=poster_exported 事件）。
///
/// 嵌入位置：
///   - 工作台左栏"专用海报"区（SpecialPostersPanel）下方
///   - 工作台 ExportDialog 完成区下方
///   - LiveView 会话详情"复盘海报"按钮下
///   - StatsView 头部"导出学习报告"按钮下
///
/// 设计原则：
///   - 极简列表：kind 标签 + subject + count + 相对时间 + 文件名（hover）
///   - 自动静默刷新：mount 拉一次 + 每 30s 拉一次（5 条就够，无需交互）
///   - kind 过滤（可选）：通过 `kindFilter` 限定只显示某一类
import { useCallback, useEffect, useState } from "react";
import { listExportLog } from "../api/client";
import type { ExportLogEntryResponse } from "../api/generated";
import { Icon } from "../icons";

/* ---- 常量 ---- */
const DEFAULT_LIMIT = 5;
const POLL_INTERVAL_MS = 30_000;  // 30 秒静默拉取

/* ---- 类型 ---- */
export type ExportKind = "grid-export" | "live-poster" | "learning-report";

export interface ExportLogPanelProps {
  dark: boolean;
  /** 显示条数（1-100）。默认 5 */
  limit?: number;
  /** 类型过滤："all" | "grid-export" | "live-poster" | "learning-report"。默认 "all" */
  kindFilter?: "all" | ExportKind;
  /** 标题（默认"最近导出"） */
  title?: string;
  /** 紧凑模式（无 padding，去背景） */
  inline?: boolean;
  /** 自定义 testid */
  "data-testid"?: string;
  /** 加载完成后立即触发（不轮询） */
  once?: boolean;
}

/* ---- kind → 标签 / 图标 ---- */
const KIND_LABEL: Record<ExportKind, string> = {
  "grid-export": "工作台",
  "live-poster": "复盘海报",
  "learning-report": "学歌报告",
};

const KIND_TONE: Record<ExportKind, { light: string; dark: string }> = {
  "grid-export":      { light: "bg-sky-50 text-sky-700",         dark: "bg-sky-500/15 text-sky-300" },
  "live-poster":      { light: "bg-rose-50 text-rose-700",       dark: "bg-rose-500/15 text-rose-300" },
  "learning-report":  { light: "bg-violet-50 text-violet-700",   dark: "bg-violet-500/15 text-violet-300" },
};

function classifyKind(raw: string | undefined): ExportKind | "other" {
  if (raw === "grid-export" || raw === "live-poster" || raw === "learning-report") return raw;
  return "other";
}

/* ---- 相对时间（中文）："刚刚" / "5 分钟前" / "今天 12:30" / "昨天 12:30" / "08-01 12:30" / "2026-08-01 12:30" */
function formatRelative(iso: string, now: Date = new Date()): string {
  if (!iso) return "";
  const t = new Date(iso);
  if (Number.isNaN(t.getTime())) return "";
  const diffMs = now.getTime() - t.getTime();
  if (diffMs < 0) return t.toLocaleString("zh-CN", { hour12: false });
  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 30) return "刚刚";
  if (diffSec < 60) return `${diffSec} 秒前`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin} 分钟前`;
  const sameDay = t.toDateString() === now.toDateString();
  if (sameDay) {
    return `今天 ${t.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false })}`;
  }
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  if (t.toDateString() === yesterday.toDateString()) {
    return `昨天 ${t.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false })}`;
  }
  // 今年内省略年
  if (t.getFullYear() === now.getFullYear()) {
    const mm = String(t.getMonth() + 1).padStart(2, "0");
    const dd = String(t.getDate()).padStart(2, "0");
    return `${mm}-${dd} ${t.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false })}`;
  }
  return t.toLocaleString("zh-CN", { hour12: false });
}

/* ---- 主组件 ---- */
export default function ExportLogPanel({
  dark,
  limit = DEFAULT_LIMIT,
  kindFilter = "all",
  title = "最近导出",
  inline = false,
  "data-testid": testId = "export-log-panel",
  once = false,
}: ExportLogPanelProps) {
  const [items, setItems] = useState<ExportLogEntryResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);  // 触发相对时间刷新

  const fetchOnce = useCallback(async (signal?: AbortSignal) => {
    try {
      const res = await listExportLog(limit);
      if (signal?.aborted) return;
      setItems(Array.isArray(res.items) ? res.items : []);
      setError(null);
    } catch (reason) {
      if (signal?.aborted) return;
      setError(reason instanceof Error ? reason.message : "加载失败");
      setItems([]);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [limit]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    void fetchOnce(controller.signal);
    if (once) return () => controller.abort();
    const id = setInterval(() => void fetchOnce(controller.signal), POLL_INTERVAL_MS);
    return () => {
      controller.abort();
      clearInterval(id);
    };
  }, [fetchOnce, once]);

  // 相对时间每 30s 刷新（只更新显示，不重新拉数据）
  useEffect(() => {
    const id = setInterval(() => setTick(v => v + 1), 30_000);
    return () => clearInterval(id);
  }, []);
  // 引用 tick 让 ESLint 满意（实际渲染走 formatRelative(new Date()) 已经包含 now）
  void tick;

  const filtered = kindFilter === "all"
    ? items
    : items.filter(item => item.kind === kindFilter);

  // 空态 / 错误态
  if (loading) {
    return (
      <div
        data-testid={testId}
        data-state="loading"
        className={`text-xs ${dark ? "text-zinc-500" : "text-muted-foreground"} ${inline ? "px-2 py-1" : "px-3 py-2"}`}
      >
        加载导出记录…
      </div>
    );
  }
  if (error) {
    return (
      <div
        data-testid={testId}
        data-state="error"
        className={`text-xs ${dark ? "text-red-400" : "text-red-600"} ${inline ? "px-2 py-1" : "px-3 py-2"}`}
        role="alert"
      >
        导出记录加载失败：{error}
      </div>
    );
  }
  if (filtered.length === 0) {
    return (
      <div
        data-testid={testId}
        data-state="empty"
        className={`text-xs ${dark ? "text-zinc-500" : "text-muted-foreground"} ${inline ? "px-2 py-1" : "px-3 py-2"}`}
      >
        还没有导出记录
      </div>
    );
  }

  return (
    <div
      data-testid={testId}
      data-state="ready"
      className={`${inline ? "" : "rounded-xl border " + (dark ? "border-zinc-800 bg-zinc-900/30" : "border-border bg-muted/30")}`}
    >
      <div className={`flex items-center justify-between ${inline ? "px-1 py-0.5" : "px-3 pt-2 pb-1"}`}>
        {title && (
          <span className={`text-[11px] font-medium ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
            {title}
          </span>
        )}
        <span className={`text-[11px] tabular-nums ${dark ? "text-zinc-600" : "text-muted-foreground"} ${title ? "" : "ml-auto"}`}>
          最近 {filtered.length} 条
        </span>
      </div>
      <ul className={`${inline ? "space-y-0.5" : "divide-y " + (dark ? "divide-zinc-800" : "divide-border")}`}>
        {filtered.map(item => {
          const k = classifyKind(item.kind);
          const tone = k === "other"
            ? (dark ? "bg-zinc-800/60 text-zinc-400" : "bg-zinc-100 text-zinc-600")
            : (dark ? KIND_TONE[k].dark : KIND_TONE[k].light);
          const label = k === "other" ? (item.kind || "未知") : KIND_LABEL[k];
          return (
            <li
              key={item.event_id}
              data-testid={`${testId}-item`}
              data-kind={item.kind}
              className={`flex items-center gap-2 ${inline ? "px-1 py-0.5" : "px-3 py-1.5"}`}
              title={item.filename || item.subject || ""}
            >
              <span
                data-testid={`${testId}-kind`}
                className={`shrink-0 inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-medium ${tone}`}
              >
                {label}
              </span>
              <span className={`flex-1 min-w-0 truncate text-xs ${dark ? "text-zinc-300" : "text-foreground"}`}>
                {item.subject || item.filename || "（无主题）"}
                {item.count > 1 && (
                  <span className={`ml-1.5 tabular-nums text-[11px] ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
                    × {item.count}
                  </span>
                )}
              </span>
              <span className={`shrink-0 text-[10px] tabular-nums ${dark ? "text-zinc-600" : "text-muted-foreground"}`}>
                {formatRelative(item.occurred_at)}
              </span>
            </li>
          );
        })}
      </ul>
      {/* 折叠底部内边距 */}
      {!inline && <div className="h-1" aria-hidden="true" />}
    </div>
  );
}

/* 暴露给宿主组件手动调用刷新（mount 后第一个场景常需要"导出后立即看到"）*/
export async function refetchExportLog(): Promise<void> {
  // 实际刷新由组件内部控制；此函数保留作为公共 API 占位（未来如果提到 hook 可直接复用）
}

/* 暴露相对时间工具，方便测试或上层嵌入 */
export const __test = { formatRelative, classifyKind };
