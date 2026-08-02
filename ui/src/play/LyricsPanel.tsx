/// R8.0 弹唱：LyricsPanel — 歌词面板
///
/// 显示已解析的 LrcLine 列表；当前行高亮 + 居中（CSS scrollIntoView 模拟）。
/// 当前行由外部传入 currentTimeMs 决定（不依赖 audio；v8.1 接 audio 后直接传 currentTime）。
///
/// 设计要点：
///   - 列表项平铺，不带行号（弹唱是卡拉 OK 风格，不是文本编辑器）
///   - 当前行：放大字号 + 高亮背景 + 强制居中滚动
///   - 空状态：友好提示"还没有歌词" / "未发现 [mm:ss.xx] 时间戳"
///   - 大列表（200+ 行）：浏览器原生滚动足够；v8.x 可加虚拟滚动
import { useEffect, useRef } from "react";
import { findActiveLine, type LrcLine } from "./lrc";

export interface LyricsPanelProps {
  dark: boolean;
  lines: LrcLine[];          // 已解析的歌词行（已按 timeMs 升序）
  currentTimeMs: number;     // 当前时间（毫秒）
  /** R9.2: 字号倍数（1 / 1.3 / 1.6），远观模式用 */
  sizeScale?: 1 | 1.3 | 1.6;
  /** 测试 id */
  "data-testid"?: string;
}

export default function LyricsPanel({ dark, lines, currentTimeMs, sizeScale = 1, "data-testid": testId = "lyrics-panel" }: LyricsPanelProps) {
  const activeIndex = findActiveLine(lines, currentTimeMs);
  const activeRef = useRef<HTMLLIElement | null>(null);

  useEffect(() => {
    if (activeIndex < 0) return;
    const el = activeRef.current;
    if (el && typeof el.scrollIntoView === "function") {
      // 平滑滚到居中（jsdom 测试环境无 scrollIntoView；try/catch 容错）
      try {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
      } catch {
        /* 静默忽略 */
      }
    }
  }, [activeIndex]);

  if (lines.length === 0) {
    return (
      <div
        data-testid={testId}
        data-state="empty"
        className={`flex h-full items-center justify-center p-8 text-center text-sm ${dark ? "text-zinc-500" : "text-muted-foreground"}`}
      >
        <div>
          <p className="text-base">还没有歌词</p>
          <p className="mt-1 text-xs opacity-75">在歌曲库双击歌曲后，可在编辑弹窗里粘贴 LRC / 纯文本歌词</p>
        </div>
      </div>
    );
  }

  return (
    <ul
      data-testid={testId}
      data-state="ready"
      data-active-index={activeIndex}
      className="h-full overflow-y-auto px-6 py-[40vh]"
    >
      {lines.map((line, idx) => {
        const isActive = idx === activeIndex;
        return (
          <li
            key={`${line.timeMs}-${idx}`}
            ref={isActive ? activeRef : null}
            data-testid={`${testId}-line`}
            data-active={isActive ? "true" : "false"}
            data-time-ms={line.timeMs}
            style={{ fontSize: isActive ? `${(1.5 * sizeScale).toFixed(3)}rem` : `${(1 * sizeScale).toFixed(3)}rem` }}
            className={`py-2 transition-all duration-300 ${
              isActive
                ? `font-semibold ${dark ? "text-zinc-50" : "text-foreground"} scale-100`
                : `${dark ? "text-zinc-500" : "text-muted-foreground"} scale-95 opacity-60`
            }`}
          >
            {line.text || <span className="opacity-30">（空白）</span>}
          </li>
        );
      })}
    </ul>
  );
}
