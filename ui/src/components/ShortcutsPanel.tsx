/// L1.2 全局快捷键面板
///
/// 按 `?`（实际 Shift+/）打开；Esc 关闭。
/// 列出全应用快捷键（按场景分组）。
/// 单源真值：所有快捷键都在 SHORTCUTS 常量里；新增快捷键时同步更新这里。
import { useEffect } from "react";
import { useToast } from "./Toast";

export interface ShortcutDef {
  keys: string[];          // 显示文本（例：["⌘", "K"]）
  description: string;
  /** 备选键组（多组快捷键都能触发同一动作时用） */
  keys_alt?: string[];
}

export interface ShortcutGroup {
  group: string;
  shortcuts: ShortcutDef[];
}

export const SHORTCUTS: ShortcutGroup[] = [
  {
    group: "全局",
    shortcuts: [
      { keys: ["⌘", "K"], description: "打开命令面板（找歌 + 命令）" },
      { keys: ["?"], description: "显示本快捷键面板" },
      { keys: ["⌘", ","], description: "打开设置" },
      { keys: ["Esc"], description: "关闭对话框 / 退出弹唱" },
    ],
  },
  {
    group: "视图切换（按住 ⌘）",
    shortcuts: [
      { keys: ["⌘", "1"], description: "工作台" },
      { keys: ["⌘", "2"], description: "歌曲库" },
      { keys: ["⌘", "3"], description: "学歌管理" },
      { keys: ["⌘", "4"], description: "直播" },
      { keys: ["⌘", "5"], description: "数据统计" },
    ],
  },
  {
    group: "工作台",
    shortcuts: [
      { keys: ["⌘", "E"], description: "导出当前海报" },
      { keys: ["⌘", "R"], description: "刷新预览" },
      { keys: ["⌘", "1"], description: "切换到第 1 个主题" },
      { keys: ["⌘", "7"], description: "切换到第 7 个主题" },
      { keys: ["←"], description: "上一页" },
      { keys: ["→"], description: "下一页" },
      { keys: ["⌘", "Z"], description: "撤销排版参数" },
      { keys: ["⌘", "⇧", "Z"], description: "重做" },
    ],
  },
  {
    group: "歌曲库",
    shortcuts: [
      { keys: ["/"], description: "聚焦搜索框" },
      { keys: ["↑", "↓", "←", "→"], description: "卡片导航" },
      { keys: ["Enter"], description: "展开 / 收起卡片" },
      { keys: ["X"], description: "切换已会 / 未会" },
    ],
  },
  {
    group: "弹唱（PlayView）",
    shortcuts: [
      { keys: ["Space"], description: "播放 / 暂停（v8.1 音频）" },
      { keys: ["↑"], description: "Capo 升一品" },
      { keys: ["↓"], description: "Capo 降一品" },
      { keys: ["1", "/", "1.3", "/", "1.6"], description: "远观模式字号档位" },
    ],
  },
];

export interface ShortcutsPanelProps {
  open: boolean;
  onClose: () => void;
  dark?: boolean;
}

export default function ShortcutsPanel({ open, onClose, dark = false }: ShortcutsPanelProps) {
  // Esc 关闭（仅 open 时）
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

  return (
    <div
      data-testid="shortcuts-panel-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label="快捷键面板"
      onClick={onClose}
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
    >
      <div
        data-testid="shortcuts-panel"
        onClick={e => e.stopPropagation()}
        className={`relative w-full max-w-2xl max-h-[80vh] overflow-y-auto rounded-2xl border shadow-2xl ${
          dark
            ? "bg-zinc-900 border-zinc-700 text-zinc-100"
            : "bg-white border-zinc-200 text-foreground"
        }`}
      >
        {/* 头部 */}
        <div className={`flex items-center justify-between border-b px-6 py-4 ${
          dark ? "border-zinc-700" : "border-zinc-200"
        }`}>
          <h2 className="font-serif text-lg font-semibold">
            快捷键
          </h2>
          <button
            type="button"
            data-testid="shortcuts-panel-close"
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

        {/* 内容：分组列表 */}
        <div className="px-6 py-4 space-y-5">
          {SHORTCUTS.map(group => (
            <div key={group.group} data-testid="shortcuts-group">
              <h3 className={`text-xs font-semibold uppercase tracking-widest mb-2 ${
                dark ? "text-zinc-500" : "text-muted-foreground"
              }`}>
                {group.group}
              </h3>
              <ul className="space-y-1.5">
                {group.shortcuts.map((s, si) => (
                  <li
                    key={`${group.group}-${si}`}
                    className="flex items-center justify-between gap-4 text-sm"
                  >
                    <span className={dark ? "text-zinc-300" : "text-foreground/80"}>
                      {s.description}
                    </span>
                    <span className="shrink-0 flex items-center gap-1">
                      {s.keys.map((k, ki) => (
                        <kbd
                          key={ki}
                          className={`inline-block rounded border px-1.5 h-6 min-w-[24px] text-xs font-mono leading-[22px] text-center ${
                            dark
                              ? "bg-zinc-800 border-zinc-700 text-zinc-200"
                              : "bg-muted border-border text-foreground"
                          }`}
                        >
                          {k}
                        </kbd>
                      ))}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* 底部 hint */}
        <div className={`px-6 py-3 border-t text-[11px] ${
          dark ? "border-zinc-700 text-zinc-500" : "border-zinc-200 text-muted-foreground"
        }`}>
          按 <kbd className="rounded border px-1 mx-0.5">Esc</kbd> 关闭本面板
        </div>
      </div>
    </div>
  );
}
