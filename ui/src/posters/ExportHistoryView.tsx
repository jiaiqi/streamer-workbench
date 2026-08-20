/// 1.2 导出历史完整列表（专家评审 P1 #1 收口）。
///
/// 设计动机：
/// R4.2.3 ExportLogPanel 已嵌入 4 处，但**只显示 5 条**；用户痛点是"找不到上次导了什么"。
/// 本组件给 SettingsView 提供一个**完整历史视图**：默认 20 条 + 完整信息列（kind / subject / count /
/// total_ms / 相对时间）+ 行点击复用 ExportLogDrawer 弹完整详情。
///
/// 不重复造轮子：内部封装 ExportLogPanel，限制 1-100 条，由用户自己调。
/// 不含缩略图（grid-export 事件没存 poster_id；future 增强需后端补字段 + 前端扩展）。
import { useEffect, useState } from "react";
import ExportLogPanel, { type ExportKind } from "./ExportLogPanel";
import { useApiError } from "@/async/useApiError";
import Spinner from "@/components/Spinner";
import ErrorBanner from "@/components/ErrorBanner";
import { apiRequest } from "@/api/client";
import type { ExportLogRecentResponse } from "@/api/generated";

/* ---- 类型过滤（all / 3 种 kind）---- */
const KIND_OPTIONS: Array<{ value: "all" | ExportKind; label: string }> = [
  { value: "all", label: "全部" },
  { value: "grid-export", label: "工作台" },
  { value: "live-poster", label: "复盘海报" },
  { value: "learning-report", label: "学歌报告" },
];

export interface ExportHistoryViewProps {
  dark: boolean;
}

export default function ExportHistoryView({ dark }: ExportHistoryViewProps) {
  const { runWithToast } = useApiError();
  const [kindFilter, setKindFilter] = useState<"all" | ExportKind>("all");
  const [totalCount, setTotalCount] = useState<number | null>(null);
  const [loadingTotal, setLoadingTotal] = useState(true);
  const [errorTotal, setErrorTotal] = useState<string | null>(null);

  // 拉一次最大集合（100 条）计算"按 kind 过滤后的总条数" + 显示"全部 N 条"
  useEffect(() => {
    let active = true;
    setLoadingTotal(true);
    setErrorTotal(null);
    runWithToast(
      () => apiRequest<ExportLogRecentResponse>("/api/exports/recent?limit=100"),
      "加载导出历史统计失败",
    )
      .then(res => {
        if (!active) return;
        if (res) setTotalCount(res.items?.length ?? 0);
      })
      .catch(failure => {
        if (!active) return;
        // runWithToast 抛 RequestFailure（plain object with .message），
        // toRequestFailure 看到 plain object 走 fallback 丢失原 message，
        // 所以直接读 .message 字段（fallback 兜底）
        const maybeMsg = (failure as { message?: unknown })?.message;
        setErrorTotal(typeof maybeMsg === "string" ? maybeMsg : "加载失败");
      })
      .finally(() => {
        if (active) setLoadingTotal(false);
      });
    return () => { active = false; };
  }, [runWithToast]);

  return (
    <section
      data-testid="export-history-view"
      aria-label="导出历史"
      className={`rounded-2xl border p-5 transition-colors duration-500 ${
        dark ? "border-zinc-800 bg-zinc-900/40" : "border-border bg-card"
      }`}
    >
      <header className="mb-4 flex items-baseline justify-between gap-3">
        <div>
          <h2 className={`text-sm font-semibold tracking-wide ${dark ? "text-zinc-100" : "text-foreground"}`}>
            导出历史
          </h2>
          <p className={`mt-1 text-[11px] leading-snug ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
            {loadingTotal
              ? "加载历史统计中…"
              : errorTotal
                ? "无法加载历史统计"
                : `共 ${totalCount ?? 0} 条导出（最多 100 条）· 数据源 events.jsonl`}
          </p>
        </div>
        {/* kind 过滤 */}
        <div
          role="tablist"
          aria-label="按类型过滤"
          className={`flex shrink-0 items-center gap-1 rounded-xl p-1 ${
            dark ? "bg-zinc-800/60" : "bg-muted"
          }`}
        >
          {KIND_OPTIONS.map(option => {
            const active = kindFilter === option.value;
            return (
              <button
                key={option.value}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setKindFilter(option.value)}
                data-testid={`export-history-filter-${option.value}`}
                className={`rounded-lg px-2.5 py-1 text-[11px] font-medium transition-colors ${
                  active
                    ? (dark ? "bg-zinc-100 text-zinc-900" : "bg-foreground text-background")
                    : (dark ? "text-zinc-400 hover:text-zinc-200" : "text-muted-foreground hover:text-foreground")
                }`}
              >
                {option.label}
              </button>
            );
          })}
        </div>
      </header>

      {/* 加载/错误占位（不动 ExportLogPanel 内部状态机） */}
      {loadingTotal && (
        <div className="flex items-center gap-2 py-2" data-testid="export-history-loading">
          <Spinner size="sm" tone="current" decorative label="加载历史统计" />
          <span className={`text-xs ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
            载入中…
          </span>
        </div>
      )}
      {!loadingTotal && errorTotal && (
        <ErrorBanner
          severity="warning"
          message={errorTotal}
          data-testid="export-history-error"
        />
      )}

      {/* 复用 ExportLogPanel：默认 20 条 + 复用现有行点击 + ExportLogDrawer */}
      <ExportLogPanel
        dark={dark}
        limit={20}
        kindFilter={kindFilter}
        title=""
        once={true}
        data-testid="export-history-list"
      />

      {/* 文档化：未来增强 */}
      <p
        className={`mt-3 text-[10px] leading-relaxed ${dark ? "text-zinc-600" : "text-muted-foreground"}`}
        data-testid="export-history-future-note"
      >
        未来增强：海报缩略图预览 + 跳转到原海报编辑（需后端 grid-export 事件补 poster_id 字段）。
      </p>
    </section>
  );
}
