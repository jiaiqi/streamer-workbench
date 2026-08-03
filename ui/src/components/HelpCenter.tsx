/// L1.7 帮助中心
///
/// 统一帮助入口：快捷键面板 / 引导重看 / 命令面板 / 加密备份 / 项目主页。
/// `Cmd+Shift+?`（实际 Cmd+Shift+/）打开。
/// 5 个入口卡片，每个 click 触发对应 action（不实际导航，新开标签）。
import { useEffect } from "react";

export interface HelpCenterProps {
  open: boolean;
  onClose: () => void;
  /** 子动作回调 —— 由 App.tsx 注入 */
  actions: {
    openShortcuts: () => void;
    reopenOnboarding: () => void;
    openCommandPalette: () => void;
  };
  dark?: boolean;
}

interface HelpItem {
  icon: string;
  title: string;
  desc: string;
  shortcut?: string;
  action: () => void;
  external?: boolean;
}

const PROJECT_HOMEPAGE = "https://github.com/jiaiqi/streamer-workbench";

export default function HelpCenter({ open, onClose, actions, dark = false }: HelpCenterProps) {
  // Esc 关闭
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const items: HelpItem[] = [
    {
      icon: "⌨",
      title: "快捷键面板",
      desc: "所有视图 / 工作台 / 弹唱的快捷键汇总",
      shortcut: "?",
      action: () => { actions.openShortcuts(); onClose(); },
    },
    {
      icon: "👋",
      title: "重看首次启动引导",
      desc: "3 步走完「载入示例 → 排版 → 弹唱」",
      action: () => { actions.reopenOnboarding(); onClose(); },
    },
    {
      icon: "🔍",
      title: "命令面板",
      desc: "Cmd+K 全局找歌 + 视图切换 + 操作",
      shortcut: "⌘K",
      action: () => { actions.openCommandPalette(); onClose(); },
    },
    {
      icon: "🌐",
      title: "项目主页",
      desc: "GitHub 仓库 · 路线图 · 提交历史",
      action: () => {
        window.open(PROJECT_HOMEPAGE, "_blank", "noopener,noreferrer");
        onClose();
      },
      external: true,
    },
    {
      icon: "💾",
      title: "加密备份",
      desc: "导出 .songworkbench（AES-256）；导入/校验/列文件",
      action: () => { onClose(); },  // 备份命令走 tools/backup.py CLI
    },
  ];

  return (
    <div
      data-testid="help-center-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label="帮助中心"
      onClick={onClose}
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
    >
      <div
        data-testid="help-center"
        onClick={e => e.stopPropagation()}
        className={`relative w-full max-w-2xl rounded-2xl border shadow-2xl overflow-hidden ${
          dark
            ? "bg-zinc-900 border-zinc-700 text-zinc-100"
            : "bg-white border-zinc-200 text-foreground"
        }`}
      >
        {/* 头部 */}
        <div className={`flex items-center justify-between border-b px-6 py-4 ${
          dark ? "border-zinc-700" : "border-zinc-200"
        }`}>
          <h2 className="font-serif text-lg font-semibold">帮助中心</h2>
          <button
            type="button"
            data-testid="help-center-close"
            onClick={onClose}
            aria-label="关闭"
            className={`rounded-md w-8 h-8 inline-flex items-center justify-center transition-colors cursor-pointer ${
              dark
                ? "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
                : "text-muted-foreground hover:bg-muted hover:text-foreground"
            }`}
          >
            ✕
          </button>
        </div>

        {/* 入口卡片网格 */}
        <div className="px-6 py-5 grid grid-cols-1 sm:grid-cols-2 gap-3" data-testid="help-center-items">
          {items.map(item => (
            <button
              key={item.title}
              type="button"
              data-testid={`help-item-${item.title}`}
              onClick={item.action}
              className={`text-left rounded-xl border p-4 transition-colors cursor-pointer ${
                dark
                  ? "border-zinc-700/60 hover:border-emerald-500/40 hover:bg-zinc-800/50"
                  : "border-zinc-200 hover:border-emerald-400/60 hover:bg-emerald-50/40"
              }`}
            >
              <div className="flex items-center gap-2 mb-1.5">
                <span className="text-xl" aria-hidden="true">{item.icon}</span>
                <span className={`font-medium text-[14px] ${dark ? "text-zinc-100" : "text-foreground"}`}>
                  {item.title}
                </span>
                {item.shortcut && (
                  <kbd className={`ml-auto rounded border px-1.5 h-5 min-w-[24px] text-[10px] font-mono leading-[18px] text-center ${
                    dark
                      ? "bg-zinc-800 border-zinc-700 text-zinc-300"
                      : "bg-muted border-border text-foreground"
                  }`}>
                    {item.shortcut}
                  </kbd>
                )}
                {item.external && !item.shortcut && (
                  <span className={`ml-auto text-[10px] tabular-nums ${
                    dark ? "text-zinc-500" : "text-muted-foreground"
                  }`}>
                    ↗
                  </span>
                )}
              </div>
              <p className={`text-[12px] leading-relaxed ${
                dark ? "text-zinc-400" : "text-muted-foreground"
              }`}>
                {item.desc}
              </p>
            </button>
          ))}
        </div>

        {/* 底部 hint */}
        <div className={`px-6 py-3 border-t text-[11px] flex items-center gap-3 ${
          dark ? "border-zinc-700 text-zinc-500" : "border-zinc-200 text-muted-foreground"
        }`}>
          <span>按 <kbd className="rounded border px-1 mx-0.5">Esc</kbd> 关闭</span>
          <span className={dark ? "text-zinc-700" : "text-zinc-300"}>·</span>
          <span>快捷键 <kbd className="rounded border px-1 mx-0.5">Cmd+Shift+?</kbd> 重新打开</span>
        </div>
      </div>
    </div>
  );
}
