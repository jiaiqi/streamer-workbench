/// R4.1.2 Spinner 统一加载旋转器。
///
/// 取代散落的：
///   - <span className="spinner" /> 已有 CSS 类
///   - <span className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" /> LiveView/StatsView/SpecialPostersPanel
///   - <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" /> App 主预览
///
/// size: sm = 12px / md = 18px (default) / lg = 24px
/// tone: current 跟随 currentColor / primary 跟随主题主色
import type { CSSProperties } from "react";

export type SpinnerSize = "sm" | "md" | "lg";
export type SpinnerTone = "current" | "primary";

export interface SpinnerProps {
  size?: SpinnerSize;
  tone?: SpinnerTone;
  /** aria-label（默认 "加载中"） */
  label?: string;
  /** 装饰性 spin（aria-hidden=true） */
  decorative?: boolean;
  className?: string;
  style?: CSSProperties;
}

const SIZE_PX: Record<SpinnerSize, number> = { sm: 12, md: 18, lg: 24 };

export default function Spinner({
  size = "md",
  tone = "current",
  label = "加载中",
  decorative = false,
  className = "",
  style,
}: SpinnerProps) {
  const px = SIZE_PX[size];
  const styleCombined: CSSProperties = {
    width: px,
    height: px,
    ...(tone === "primary" ? { borderTopColor: "var(--color-primary)" } : {}),
    ...style,
  };
  return (
    <span
      role={decorative ? undefined : "status"}
      aria-hidden={decorative || undefined}
      aria-label={decorative ? undefined : label}
      className={`inline-block rounded-full border-2 border-current border-t-transparent animate-spin align-middle ${className}`}
      style={styleCombined}
    />
  );
}
