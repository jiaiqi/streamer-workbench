/// L1.3 首次启动 Onboarding
///
/// 3 步引导 modal，首次启动时自动显示（localStorage `sw-onboarded` 未设置）。
/// 完成 / 跳过都写 localStorage；用户可以再次通过设置或命令面板重看。
///
/// 步骤：
///   1. 欢迎 + 「载入示例曲库」（178 首真实数据）
///   2. 5 套版式 + 8 套主题 + 排版参数微调
///   3. 弹唱（PlayView）+ 全局找歌（Cmd+K）+ 快捷键面板（?）
import { useEffect, useState } from "react";

const STORAGE_KEY = "sw-onboarded";
const STORAGE_VERSION = 1;  // 升级引导内容时改这个强制重看

const STEPS = [
  {
    title: "欢迎来到主播工作台",
    body: "面向吉他弹唱主播的本地化工作台。\n先点「载入示例」把 178 首真实曲库灌进来，立刻可以出图。",
    cta: "下一步",
  },
  {
    title: "排版 + 主题",
    body: "5 套版式（grid-wrap / magazine-flow / live-set / learning-report / fullscreen-flow），\n8 套主题，每套版式有独立参数（页边距 / 字号 / 行高）。\n在右侧参数面板微调，左侧预览实时刷新。",
    cta: "下一步",
  },
  {
    title: "弹唱 + 找歌 + 快捷键",
    body: "• Cmd+K — 全局找歌（按歌名/歌手/拼音/歌词/标签/调式加权排序）\n• ?      — 打开快捷键面板\n• 弹唱视图：歌词 LRC 同步 + chord 高亮 + 音频 + 直播联动",
    cta: "开始使用",
  },
];

export interface OnboardingProps {
  /** 强制显示（用于设置里手动触发） */
  forceShow?: boolean;
  /** 关闭回调（最后一页点「开始」/ 跳过时调） */
  onClose?: () => void;
  dark?: boolean;
}

export function isOnboarded(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === `v${STORAGE_VERSION}`;
  } catch {
    return false;
  }
}

export function markOnboarded(): void {
  try {
    localStorage.setItem(STORAGE_KEY, `v${STORAGE_VERSION}`);
  } catch {
    /* localStorage 不可用（隐私模式）—— 忽略 */
  }
}

export function resetOnboarded(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

export default function Onboarding({ forceShow, onClose, dark = false }: OnboardingProps) {
  const [visible, setVisible] = useState(false);
  const [step, setStep] = useState(0);

  // 决定是否显示：forceShow 永远显示；否则首次启动（localStorage 未标记）
  useEffect(() => {
    if (forceShow) {
      setVisible(true);
      setStep(0);
      return;
    }
    if (!isOnboarded()) {
      setVisible(true);
      setStep(0);
    }
  }, [forceShow]);

  if (!visible) return null;

  const isLast = step === STEPS.length - 1;
  const current = STEPS[step];

  const handleNext = () => {
    if (isLast) {
      handleFinish();
    } else {
      setStep(s => s + 1);
    }
  };

  const handleBack = () => {
    if (step > 0) setStep(s => s - 1);
  };

  const handleFinish = () => {
    markOnboarded();
    setVisible(false);
    onClose?.();
  };

  const handleSkip = () => {
    handleFinish();
  };

  return (
    <div
      data-testid="onboarding-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label="首次启动引导"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
    >
      <div
        data-testid="onboarding-panel"
        className={`relative w-full max-w-lg rounded-2xl border shadow-2xl ${
          dark
            ? "bg-zinc-900 border-zinc-700 text-zinc-100"
            : "bg-white border-zinc-200 text-foreground"
        }`}
      >
        {/* 头部：进度点 + 跳过 */}
        <div className="flex items-center justify-between px-6 pt-5">
          <div className="flex items-center gap-1.5" data-testid="onboarding-dots">
            {STEPS.map((_, i) => (
              <span
                key={i}
                data-testid={`onboarding-dot-${i}`}
                data-active={i === step ? "true" : "false"}
                className={`h-1.5 rounded-full transition-all duration-300 ${
                  i === step
                    ? "w-6 bg-emerald-500"
                    : dark
                      ? "w-1.5 bg-zinc-700"
                      : "w-1.5 bg-zinc-300"
                }`}
              />
            ))}
          </div>
          <button
            type="button"
            data-testid="onboarding-skip"
            onClick={handleSkip}
            className={`text-xs transition-colors cursor-pointer ${
              dark ? "text-zinc-500 hover:text-zinc-300" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            跳过
          </button>
        </div>

        {/* 内容 */}
        <div className="px-6 py-6 min-h-[200px]">
          <h2 className="font-serif text-xl font-semibold mb-3" data-testid="onboarding-title">
            {current.title}
          </h2>
          <p
            className={`text-sm leading-relaxed whitespace-pre-line ${
              dark ? "text-zinc-300" : "text-foreground/80"
            }`}
            data-testid="onboarding-body"
          >
            {current.body}
          </p>
        </div>

        {/* 底部：上一步 + 下一步/开始 */}
        <div className="flex items-center justify-between border-t px-6 py-4"
             style={{ borderColor: dark ? "rgb(63 63 70)" : "rgb(228 228 231)" }}>
          <button
            type="button"
            data-testid="onboarding-back"
            onClick={handleBack}
            disabled={step === 0}
            className={`text-sm transition-colors cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed ${
              dark ? "text-zinc-400 hover:text-zinc-100" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            ← 上一步
          </button>
          <span className={`text-xs tabular-nums ${
            dark ? "text-zinc-500" : "text-muted-foreground"
          }`}>
            {step + 1} / {STEPS.length}
          </span>
          <button
            type="button"
            data-testid="onboarding-next"
            onClick={handleNext}
            className="rounded-lg bg-emerald-600 hover:bg-emerald-700 px-4 h-9 text-sm font-medium text-white transition-colors cursor-pointer"
          >
            {current.cta}
          </button>
        </div>
      </div>
    </div>
  );
}
