/// R4.1.5 Cmd+K 跨视图命令面板。
///
/// 功能：
///   - Cmd+K / Ctrl+K 打开；Esc 关闭
///   - 搜索框（input）模糊匹配命令
///   - 命令分组：视图 / 操作 / 海报 / 速查
///   - ↑↓ 选中，Enter 执行
///   - 跨视图通用：工作台、歌曲库、学歌、直播、统计、设置都可用
///
/// M1.2 蓝图 v0.1：扩展为「全局找歌 + 命令」混合面板
///   - songResults 存在时，歌曲搜索结果显示在 commands 之前
///   - 选中歌曲 → onPickSong(song) 回调（默认进 PlayView）
///   - 歌曲分组标签 "歌曲"
///
/// 命令格式：
///   { id, title, group, shortcut?, action: () => void }
import { useEffect, useMemo, useRef, useState } from "react";
import { Icon } from "../icons";

export type CommandGroup = "视图" | "操作" | "海报" | "速查" | "歌曲" | "帮助";

export interface Command {
  id: string;
  title: string;
  group: CommandGroup;
  shortcut?: string;
  keywords?: string[];
  description?: string;
  action: () => void | Promise<void>;
  disabledReason?: string;
}

export interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  commands: Command[];
  dark?: boolean;
  /** M1.2: 歌曲搜索结果（来自 App.tsx 的 searchSongs）— 显示在 commands 之前 */
  songResults?: Array<{ id: string; title: string; artists: string[]; key?: string; status?: string }>;
  /** M1.2: 选中歌曲回调（默认进 PlayView） */
  onPickSong?: (songId: string) => void;
  /** M1.2: 当前 query（受控）— App.tsx 用它跑 searchSongs */
  query?: string;
  onQueryChange?: (q: string) => void;
}

export default function CommandPalette({ open, onClose, commands, dark, songResults, onPickSong, query: controlledQuery, onQueryChange }: CommandPaletteProps) {
  const [internalQuery, setInternalQuery] = useState("");
  // 受控/非受控：若传 query+onQueryChange 则受控
  const isControlled = controlledQuery !== undefined;
  const query = isControlled ? controlledQuery : internalQuery;
  const setQuery = (q: string) => {
    if (isControlled) onQueryChange?.(q);
    else setInternalQuery(q);
  };
  const [highlight, setHighlight] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // M1.2: 把 songResults 转成"虚拟 Command"放在 commands 之前
  const songCommands = useMemo<Command[]>(() => {
    if (!songResults || songResults.length === 0) return [];
    return songResults.map(s => ({
      id: `song-${s.id}`,
      title: s.title,
      group: "歌曲" as CommandGroup,
      keywords: [...(s.artists || []), s.key ?? ""].filter(Boolean),
      description: s.artists?.length ? s.artists.join(" · ") + (s.key ? ` · ${s.key}` : "") : s.key,
      action: () => onPickSong?.(s.id),
    }));
  }, [songResults, onPickSong]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const allCmds = [...songCommands, ...commands];
    if (!q) return allCmds;
    return allCmds.filter(cmd => {
      if (cmd.title.toLowerCase().includes(q)) return true;
      if (cmd.keywords?.some(k => k.toLowerCase().includes(q))) return true;
      if (cmd.description?.toLowerCase().includes(q)) return true;
      return false;
    });
  }, [commands, query, songCommands]);

  const grouped = useMemo(() => {
    const map = new Map<CommandGroup, Command[]>();
    for (const cmd of filtered) {
      const list = map.get(cmd.group) ?? [];
      list.push(cmd);
      map.set(cmd.group, list);
    }
    return Array.from(map.entries());
  }, [filtered]);

  const flat = useMemo(() => grouped.flatMap(([, cmds]) => cmds), [grouped]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setHighlight(0);
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); onClose(); return; }
      if (e.key === "ArrowDown") { e.preventDefault(); setHighlight(h => Math.min(flat.length - 1, h + 1)); return; }
      if (e.key === "ArrowUp") { e.preventDefault(); setHighlight(h => Math.max(0, h - 1)); return; }
      if (e.key === "Enter") {
        e.preventDefault();
        const cmd = flat[highlight];
        if (cmd && !cmd.disabledReason) { void cmd.action(); onClose(); }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, flat, highlight, onClose]);

  useEffect(() => { setHighlight(0); }, [query]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-start justify-center pt-[15vh] bg-black/30 backdrop-blur-[2px]"
      onClick={onClose}>
      <div
        role="dialog"
        aria-label="命令面板"
        aria-modal="true"
        data-testid="command-palette"
        className={`w-[520px] max-w-[92vw] rounded-2xl shadow-2xl overflow-hidden ${dark ? "bg-zinc-800 border border-zinc-700 text-zinc-200" : "bg-card border border-border text-card-foreground"}`}
        onClick={e => e.stopPropagation()}
      >
        <div className={`flex items-center gap-2 px-4 py-3 border-b ${dark ? "border-zinc-700" : "border-border"}`}>
          <span aria-hidden="true" className="text-muted-foreground">{Icon.search}</span>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="搜索命令、操作、海报…"
            aria-label="命令搜索"
            className="flex-1 bg-transparent outline-none text-sm placeholder:text-muted-foreground"
            data-testid="command-palette-input"
          />
          <kbd className={`text-[10px] px-1.5 py-0.5 rounded ${dark ? "bg-zinc-700 text-zinc-400" : "bg-muted text-muted-foreground"}`}>esc</kbd>
        </div>
        <div className="max-h-[50vh] overflow-y-auto py-1" role="listbox" aria-label="命令列表">
          {grouped.length === 0 && (
            <div className="px-4 py-8 text-center text-sm text-muted-foreground">
              没有匹配的命令
            </div>
          )}
          {grouped.map(([group, cmds], groupIdx) => {
            const startIdx = grouped.slice(0, groupIdx).reduce((acc, [, c]) => acc + c.length, 0);
            return (
              <div key={group}>
                <div className={`px-4 py-1 text-[10px] uppercase tracking-wider ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
                  {group}
                </div>
                {cmds.map((cmd, idx) => {
                  const flatIdx = startIdx + idx;
                  const isHighlight = flatIdx === highlight;
                  return (
                    <button
                      key={cmd.id}
                      type="button"
                      role="option"
                      aria-selected={isHighlight}
                      disabled={!!cmd.disabledReason}
                      data-testid={`command-${cmd.id}`}
                      onMouseEnter={() => setHighlight(flatIdx)}
                      onClick={() => {
                        if (cmd.disabledReason) return;
                        void cmd.action();
                        onClose();
                      }}
                      className={`w-full text-left px-4 py-2 flex items-center gap-3 transition-colors ${
                        cmd.disabledReason
                          ? "opacity-50 cursor-not-allowed"
                          : isHighlight
                            ? (dark ? "bg-zinc-700/60" : "bg-muted")
                            : (dark ? "hover:bg-zinc-700/40" : "hover:bg-muted/60")
                      }`}
                    >
                      <div className="flex-1 min-w-0">
                        <p className="text-sm truncate">{cmd.title}</p>
                        {cmd.description && (
                          <p className="text-[11px] text-muted-foreground truncate">{cmd.description}</p>
                        )}
                        {cmd.disabledReason && (
                          <p className="text-[11px] text-muted-foreground truncate">{cmd.disabledReason}</p>
                        )}
                      </div>
                      {cmd.shortcut && (
                        <kbd className={`text-[10px] px-1.5 py-0.5 rounded shrink-0 ${dark ? "bg-zinc-700 text-zinc-400" : "bg-muted text-muted-foreground"}`}>
                          {cmd.shortcut}
                        </kbd>
                      )}
                    </button>
                  );
                })}
              </div>
            );
          })}
        </div>
        <div className={`px-4 py-2 border-t flex items-center justify-between text-[10px] text-muted-foreground ${dark ? "border-zinc-700" : "border-border"}`}>
          <span>↑↓ 移动 · Enter 执行 · Esc 关闭</span>
          <span>主播工作台</span>
        </div>
      </div>
    </div>
  );
}
