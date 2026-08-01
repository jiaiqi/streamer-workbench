/// R4.1.4 ErrorBanner 统一错误条。
///
/// 取代散落的：
///   - <AsyncStateNotice kind="error" /> 简化版
///   - <ErrorNotice message={...} /> StatsView 自写
///   - <div role="alert" className="...bg-red-500/10..."> 多处
///   - 顶部"资源异常·重试"按钮（App.tsx resourceError）
///
/// 形态：图标 + 标题 + 描述 + 可选 retry/cancel/dismiss
import { Icon } from "../icons";
import type { ReactNode } from "react";

export type ErrorSeverity = "error" | "warning";

export interface ErrorBannerProps {
  severity?: ErrorSeverity;
  /** 错误标题（默认 "出错了" / "请注意"） */
  title?: string;
  /** 错误描述（必填） */
  message: ReactNode;
  /** 重试回调（显示"重试"按钮） */
  onRetry?: () => void;
  /** 重试中状态 */
  retryPending?: boolean;
  /** 关闭回调（显示"知道了"按钮） */
  onDismiss?: () => void;
  /** 暗色模式 */
  dark?: boolean;
  /** 自定义 testid */
  "data-testid"?: string;
  /** 角色（默认 "alert"） */
  role?: "alert" | "status";
}

export default function ErrorBanner({
  severity = "error",
  title, message,
  onRetry, retryPending,
  onDismiss,
  dark,
  "data-testid": testId,
  role,
}: ErrorBannerProps) {
  const isError = severity === "error";
  const defaultTitle = isError ? "出错了" : "请注意";
  const colorClass = isError
    ? (dark ? "bg-red-500/10 text-red-300 border-red-500/20" : "bg-red-50 text-red-700 border-red-200")
    : (dark ? "bg-amber-500/10 text-amber-300 border-amber-500/20" : "bg-amber-50 text-amber-700 border-amber-200");
  const buttonClass = isError
    ? (dark ? "hover:bg-red-500/20" : "hover:bg-red-100")
    : (dark ? "hover:bg-amber-500/20" : "hover:bg-amber-100");
  return (
    <div
      role={role ?? "alert"}
      data-testid={testId}
      data-severity={severity}
      className={`error-banner flex items-start gap-2.5 rounded-lg border px-3 py-2 text-[12px] leading-relaxed ${colorClass}`}
    >
      <span className="shrink-0 mt-0.5" aria-hidden="true">
        {isError ? Icon.alertCircle : Icon.alertTriangle}
      </span>
      <div className="flex-1 min-w-0">
        <p className="font-medium">{title ?? defaultTitle}</p>
        <p className={`mt-0.5 ${dark ? "opacity-80" : "opacity-90"} break-words`}>{message}</p>
      </div>
      {(onRetry || onDismiss) && (
        <div className="flex items-center gap-1 shrink-0">
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              disabled={retryPending}
              aria-busy={retryPending}
              data-loading={retryPending ? "true" : "false"}
              className={`px-2 py-1 rounded-md text-[11px] font-medium transition-colors disabled:opacity-60 ${buttonClass}`}
            >
              {retryPending ? "重试中…" : "重试"}
            </button>
          )}
          {onDismiss && (
            <button
              type="button"
              onClick={onDismiss}
              aria-label="关闭"
              className={`p-1 rounded-md transition-colors ${buttonClass}`}
            >
              {Icon.close}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
