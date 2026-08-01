/// R4.0.11 工作台左栏「专用海报」区。
///
/// 把 live-set（一场直播复盘）和 learning-report（学歌报告）
/// 两套新布局入口接到工作台，对应"日常出图"路径以外的两种海报创作来源。
///
/// 入口：工作台左栏 WorkspacePosterBridge 下方的"专用海报"折叠区。
/// 触发：openLivePoster / openLearningReportPoster（electron-bridge.ts）
///
/// 旧路径不变：LiveView 会话详情"复盘海报"按钮 + StatsView 头"导出学习报告"按钮
/// 仍可用，作为深度路径。
import { useCallback, useEffect, useMemo, useState } from "react";
import { apiRequest } from "../api/client";
import { openLivePoster, openLearningReportPoster } from "../electron-bridge";
import type { LiveSessionSummary } from "../api/generated";
import ExportLogPanel from "./ExportLogPanel";

const RECENT_SESSIONS_LIMIT = 3;

interface PresetWindow {
  days: number;
  label: string;
}

const PRESET_WINDOWS: PresetWindow[] = [
  { days: 7, label: "近 7 天" },
  { days: 30, label: "近 30 天" },
  { days: 90, label: "近 90 天" },
];

export interface SpecialPostersPanelProps {
  dark: boolean;
}

interface ExportError {
  kind: "live" | "report";
  message: string;
}

export default function SpecialPostersPanel({ dark }: SpecialPostersPanelProps) {
  /* ---- LiveSession 列表 ---- */
  const [sessions, setSessions] = useState<LiveSessionSummary[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [sessionsError, setSessionsError] = useState<string | null>(null);

  /* ---- 当前导出任务 ---- */
  const [exporting, setExporting] = useState<{ kind: "live" | "report"; key: string } | null>(null);
  const [exportError, setExportError] = useState<ExportError | null>(null);
  const [exportSuccess, setExportSuccess] = useState<string | null>(null);

  /* ---- 自定义弹层 ---- */
  const [showAllSessions, setShowAllSessions] = useState(false);
  const [showCustomReport, setShowCustomReport] = useState(false);

  /* ---- mount 拉取最近 LiveSession（按 started_at 降序） ---- */
  useEffect(() => {
    let active = true;
    setSessionsLoading(true);
    apiRequest<LiveSessionSummary[]>("/api/live-sessions", {})
      .then(data => {
        if (!active) return;
        // 防御：后端可能给 null 或非数组
        const list = Array.isArray(data) ? data : [];
        list.sort((a, b) => Date.parse(b.started_at) - Date.parse(a.started_at));
        setSessions(list);
        setSessionsError(null);
      })
      .catch(reason => {
        if (!active) return;
        setSessionsError(reason instanceof Error ? reason.message : "直播列表加载失败");
      })
      .finally(() => { if (active) setSessionsLoading(false); });
    return () => { active = false; };
  }, []);

  /* ---- 导出：复盘海报 ---- */
  const handleExportLive = useCallback(async (sessionId: string) => {
    if (exporting) return;
    setExportError(null);
    setExportSuccess(null);
    setExporting({ kind: "live", key: sessionId });
    try {
      const res = await openLivePoster(sessionId);
      if (res.ok) {
        setExportSuccess(res.path ? `已保存到 ${res.path}` : "已下载海报");
      } else if (!res.cancelled) {
        setExportError({ kind: "live", message: res.error ?? "复盘海报导出失败" });
      }
    } catch (reason) {
      setExportError({
        kind: "live",
        message: reason instanceof Error ? reason.message : "复盘海报导出失败",
      });
    } finally {
      setExporting(null);
    }
  }, [exporting]);

  /* ---- 导出：学歌报告（预设） ---- */
  const handleExportReportPreset = useCallback(async (window: PresetWindow) => {
    if (exporting) return;
    setExportError(null);
    setExportSuccess(null);
    setExporting({ kind: "report", key: `preset-${window.days}` });
    try {
      const res = await openLearningReportPoster({
        days: window.days,
        period_label: window.label,
      });
      if (res.ok) {
        setExportSuccess(res.path ? `已保存到 ${res.path}` : "已下载海报");
      } else if (!res.cancelled) {
        setExportError({ kind: "report", message: res.error ?? "学歌报告导出失败" });
      }
    } catch (reason) {
      setExportError({
        kind: "report",
        message: reason instanceof Error ? reason.message : "学歌报告导出失败",
      });
    } finally {
      setExporting(null);
    }
  }, [exporting]);

  /* ---- 导出：学歌报告（自定义） ---- */
  const handleExportReportCustom = useCallback(async (days: number, label: string) => {
    if (exporting) return;
    setExportError(null);
    setExportSuccess(null);
    setExporting({ kind: "report", key: `custom-${days}` });
    try {
      const res = await openLearningReportPoster({ days, period_label: label });
      if (res.ok) {
        setExportSuccess(res.path ? `已保存到 ${res.path}` : "已下载海报");
      } else if (!res.cancelled) {
        setExportError({ kind: "report", message: res.error ?? "学歌报告导出失败" });
      }
    } catch (reason) {
      setExportError({
        kind: "report",
        message: reason instanceof Error ? reason.message : "学歌报告导出失败",
      });
    } finally {
      setExporting(null);
    }
  }, [exporting]);

  const recentSessions = useMemo(
    () => sessions.slice(0, RECENT_SESSIONS_LIMIT),
    [sessions],
  );

  const liveExporting = exporting?.kind === "live" ? exporting.key : null;
  const reportExporting = exporting?.kind === "report" ? exporting.key : null;

  return (
    <section
      aria-label="专用海报"
      className={`px-4 pt-4 pb-3 border-b transition-colors duration-500 ${dark ? "border-zinc-700/50" : "border-border"}`}
    >
      <p className="eyebrow">专用海报</p>
      <h2 className="panel-title">直播复盘 · 学歌报告</h2>
      <p className="panel-copy mb-3">由事件流快照驱动，不走"选歌曲→选主题"。</p>

      {/* ===== 复盘海报 ===== */}
      <h3 className={`text-[11px] font-semibold uppercase tracking-wider mb-1.5 ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
        复盘海报
      </h3>
      {sessionsLoading && (
        <div className="text-[11px] text-muted-foreground py-2 flex items-center gap-1.5">
          <span className="spinner" /> 加载最近直播…
        </div>
      )}
      {sessionsError && !sessionsLoading && (
        <p className="text-[11px] text-destructive py-2" role="alert">
          {sessionsError}
        </p>
      )}
      {!sessionsLoading && !sessionsError && sessions.length === 0 && (
        <p className="text-[11px] text-muted-foreground py-2">
          还没有直播场次
        </p>
      )}
      <ul className="space-y-1" role="list">
        {recentSessions.map(s => {
          const isExporting = liveExporting === s.id;
          const stateLabel = s.state === "active" ? "进行中" : s.state === "closed" ? "已结束" : s.state;
          return (
            <li key={s.id}>
              <button
                type="button"
                onClick={() => void handleExportLive(s.id)}
                disabled={!!exporting}
                aria-busy={isExporting}
                data-loading={isExporting ? "true" : "false"}
                title={`把这场直播生成 live-set 复盘海报（${stateLabel}）`}
                className={`w-full text-left rounded-lg px-2.5 py-1.5 text-[12px] flex items-center gap-2 transition-colors disabled:opacity-60 disabled:cursor-not-allowed ${
                  dark
                    ? "hover:bg-zinc-700/50 text-zinc-200"
                    : "hover:bg-muted text-card-foreground"
                }`}
              >
                {isExporting ? (
                  <span className="inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin shrink-0" />
                ) : (
                  <span className="shrink-0 w-1.5 h-1.5 rounded-full"
                    style={{ background: s.state === "active" ? "var(--color-primary)" : "var(--color-muted-foreground)" }} />
                )}
                <span className="flex-1 truncate font-medium">{s.title || "未命名场次"}</span>
                <span className="text-[10px] text-muted-foreground tabular-nums shrink-0">
                  {formatStartedAt(s.started_at)}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      {sessions.length > RECENT_SESSIONS_LIMIT && (
        <button
          type="button"
          onClick={() => setShowAllSessions(true)}
          className={`text-[11px] mt-1.5 px-2.5 py-1 rounded-md transition-colors ${dark ? "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700/50" : "text-muted-foreground hover:text-foreground hover:bg-muted"}`}
        >
          查看全部 {sessions.length} 场 →
        </button>
      )}

      {/* ===== 学歌报告 ===== */}
      <h3 className={`text-[11px] font-semibold uppercase tracking-wider mt-4 mb-1.5 ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
        学歌报告
      </h3>
      <ul className="space-y-1" role="list">
        {PRESET_WINDOWS.map(w => {
          const isExporting = reportExporting === `preset-${w.days}`;
          return (
            <li key={w.days}>
              <button
                type="button"
                onClick={() => void handleExportReportPreset(w)}
                disabled={!!exporting}
                aria-busy={isExporting}
                data-loading={isExporting ? "true" : "false"}
                title={`把最近 ${w.days} 天的学歌数据生成 learning-report 海报`}
                className={`w-full text-left rounded-lg px-2.5 py-1.5 text-[12px] flex items-center gap-2 transition-colors disabled:opacity-60 disabled:cursor-not-allowed ${
                  dark
                    ? "hover:bg-zinc-700/50 text-zinc-200"
                    : "hover:bg-muted text-card-foreground"
                }`}
              >
                {isExporting ? (
                  <span className="inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin shrink-0" />
                ) : (
                  <span className="shrink-0 text-[14px]" aria-hidden="true">📈</span>
                )}
                <span className="flex-1 font-medium">{w.label}</span>
                <span className="text-[10px] text-muted-foreground tabular-nums shrink-0">
                  {w.days}d
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      <button
        type="button"
        onClick={() => setShowCustomReport(true)}
        className={`text-[11px] mt-1.5 px-2.5 py-1 rounded-md transition-colors ${dark ? "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700/50" : "text-muted-foreground hover:text-foreground hover:bg-muted"}`}
      >
        自定义时间窗口…
      </button>

      {/* 错误展示（统一在一处） */}
      {exportError && (
        <p className="text-[11px] text-destructive mt-2 px-2.5 py-1 rounded-md bg-destructive/10" role="alert">
          {exportError.message}
        </p>
      )}
      {exportSuccess && (
        <p
          className={`text-[11px] mt-2 px-2.5 py-1 rounded-md ${dark ? "bg-emerald-500/15 text-emerald-300" : "bg-emerald-50 text-emerald-700"}`}
          role="status"
          data-testid="special-poster-success"
        >
          {exportSuccess}
        </p>
      )}

      {/* ===== R4.2.3 导出历史 ===== */}
      <h3 className={`text-[11px] font-semibold uppercase tracking-wider mt-4 mb-1.5 ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
        最近导出
      </h3>
      <ExportLogPanel
        dark={dark}
        limit={5}
        title=""
        data-testid="special-posters-log"
      />

      {/* ===== 自定义弹层 ===== */}
      {showAllSessions && (
        <SessionPickerDialog
          dark={dark}
          sessions={sessions}
          exportingId={liveExporting}
          onClose={() => setShowAllSessions(false)}
          onSelect={async (id) => { setShowAllSessions(false); await handleExportLive(id); }}
        />
      )}
      {showCustomReport && (
        <LearningReportPickerDialog
          dark={dark}
          exportingKey={reportExporting}
          onClose={() => setShowCustomReport(false)}
          onConfirm={async (days, label) => {
            setShowCustomReport(false);
            await handleExportReportCustom(days, label);
          }}
        />
      )}
    </section>
  );
}

/* ---- 工具 ---- */

function formatStartedAt(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  if (sameDay) {
    return `${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
  }
  return `${(d.getMonth() + 1).toString().padStart(2, "0")}-${d.getDate().toString().padStart(2, "0")}`;
}

/* ---- 弹层 ---- */

function SessionPickerDialog({ dark, sessions, exportingId, onClose, onSelect }: {
  dark: boolean;
  sessions: LiveSessionSummary[];
  exportingId: string | null;
  onClose: () => void;
  onSelect: (id: string) => Promise<void>;
}) {
  // Esc 关闭
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-[2px]"
      onClick={onClose}>
      <div className={`w-[420px] max-w-[92vw] max-h-[80vh] flex flex-col rounded-2xl p-5 shadow-2xl ${dark ? "bg-zinc-800 border border-zinc-700 text-zinc-200" : "bg-card border border-border text-card-foreground"}`}
        onClick={e => e.stopPropagation()}>
        <h3 className="text-base font-semibold mb-1">选择直播场次</h3>
        <p className="text-xs text-muted-foreground mb-3">点选要生成复盘海报的直播（按开始时间倒序）</p>
        <ul className="flex-1 overflow-y-auto space-y-1" role="list">
          {sessions.map(s => {
            const isExporting = exportingId === s.id;
            const stateLabel = s.state === "active" ? "进行中" : s.state === "closed" ? "已结束" : s.state;
            return (
              <li key={s.id}>
                <button
                  type="button"
                  onClick={() => void onSelect(s.id)}
                  disabled={!!exportingId}
                  aria-busy={isExporting}
                  data-loading={isExporting ? "true" : "false"}
                  className={`w-full text-left rounded-lg px-3 py-2 text-sm flex items-center gap-2 transition-colors disabled:opacity-60 ${dark ? "hover:bg-zinc-700/50" : "hover:bg-muted"}`}
                >
                  {isExporting ? (
                    <span className="inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin shrink-0" />
                  ) : (
                    <span className="shrink-0 w-1.5 h-1.5 rounded-full"
                      style={{ background: s.state === "active" ? "var(--color-primary)" : "var(--color-muted-foreground)" }} />
                  )}
                  <span className="flex-1 truncate font-medium">{s.title || "未命名场次"}</span>
                  <span className="text-[11px] text-muted-foreground tabular-nums shrink-0">
                    {formatStartedAt(s.started_at)} · {stateLabel}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
        <div className="flex justify-end mt-3">
          <button
            type="button"
            onClick={onClose}
            className={`rounded-xl px-4 py-2 text-sm transition-colors ${dark ? "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700/50" : "text-muted-foreground hover:text-foreground hover:bg-muted"}`}
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}

function LearningReportPickerDialog({ dark, exportingKey, onClose, onConfirm }: {
  dark: boolean;
  exportingKey: string | null;
  onClose: () => void;
  onConfirm: (days: number, label: string) => Promise<void>;
}) {
  const [days, setDays] = useState<number>(30);
  const [label, setLabel] = useState<string>("");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !exportingKey) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, exportingKey]);

  const isExporting = !!exportingKey;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-[2px]"
      onClick={() => !isExporting && onClose()}>
      <div className={`w-[400px] max-w-[92vw] rounded-2xl p-5 shadow-2xl ${dark ? "bg-zinc-800 border border-zinc-700 text-zinc-200" : "bg-card border border-border text-card-foreground"}`}
        onClick={e => e.stopPropagation()}>
        <h3 className="text-base font-semibold mb-1">自定义学习报告</h3>
        <p className="text-xs text-muted-foreground mb-4">设置要汇总的时间窗口（1-365 天）</p>
        <div className="space-y-3">
          <label className="block">
            <span className="text-xs text-muted-foreground">天数</span>
            <input
              type="number"
              min={1}
              max={365}
              value={days}
              onChange={e => setDays(Math.max(1, Math.min(365, parseInt(e.target.value, 10) || 1)))}
              disabled={isExporting}
              className={`mt-1 w-full rounded-lg px-3 py-2 text-sm outline-none ${dark ? "bg-zinc-700 border-zinc-600 text-zinc-100" : "bg-muted border-border text-foreground border"} border`}
            />
          </label>
          <label className="block">
            <span className="text-xs text-muted-foreground">显示标签（可选）</span>
            <input
              type="text"
              maxLength={32}
              value={label}
              placeholder={`最近 ${days} 天`}
              onChange={e => setLabel(e.target.value)}
              disabled={isExporting}
              className={`mt-1 w-full rounded-lg px-3 py-2 text-sm outline-none ${dark ? "bg-zinc-700 border-zinc-600 text-zinc-100 placeholder:text-zinc-500" : "bg-muted border-border text-foreground border"} border`}
            />
          </label>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button
            type="button"
            onClick={onClose}
            disabled={isExporting}
            className={`rounded-xl px-4 py-2 text-sm transition-colors disabled:opacity-50 ${dark ? "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700/50" : "text-muted-foreground hover:text-foreground hover:bg-muted"}`}
          >
            取消
          </button>
          <button
            type="button"
            onClick={() => void onConfirm(days, label || `最近 ${days} 天`)}
            disabled={isExporting}
            aria-busy={isExporting}
            data-loading={isExporting ? "true" : "false"}
            className="primary-action rounded-xl px-5 py-2 text-sm disabled:opacity-50 flex items-center gap-1.5"
          >
            {isExporting ? (
              <>
                <span className="inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
                渲染中…
              </>
            ) : "生成海报"}
          </button>
        </div>
      </div>
    </div>
  );
}
