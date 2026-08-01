/// R8.0 弹唱：TabsPanel — 曲谱面板（chordpro 渲染）
///
/// 显示已解析的 ChordProLine 列表：
///   - 行内 chord 用 <span data-active> 标记；高亮颜色由 CSS 控制
///   - 当前行高亮（粗体 + 浅背景）
///   - section 标签（verse/chorus）作为副标题
///   - 当前行高亮逻辑：当前时间落在 lyrics 非空行的"区间"内
///     （基于行号与音频时间戳的简化映射——v8.0 简化版；v8.x 可加 explicit 时间戳）
import { useMemo } from "react";
import type { ChordProLine, ParsedChordPro } from "./chordpro";

export interface TabsPanelProps {
  dark: boolean;
  parsed: ParsedChordPro;    // 已解析的 chordpro
  currentTimeMs: number;
  totalMs: number;           // 音频总时长（用于估算当前行号）
  "data-testid"?: string;
}

/** 简化版：根据 currentTimeMs / totalMs 估算当前行号（按行均分）。v8.1 接 audio 后可更准。 */
function estimateActiveLineIndex(lines: ChordProLine[], currentTimeMs: number, totalMs: number): number {
  const lyricLines = lines.filter(ln => ln.text && !ln.directive);
  if (lyricLines.length === 0 || totalMs <= 0) return -1;
  if (currentTimeMs < 0) return -1;
  if (currentTimeMs >= totalMs) return lyricLines.length - 1;
  // 行均分时间
  const perLine = totalMs / lyricLines.length;
  return Math.min(lyricLines.length - 1, Math.floor(currentTimeMs / perLine));
}

export default function TabsPanel({ dark, parsed, currentTimeMs, totalMs, "data-testid": testId = "tabs-panel" }: TabsPanelProps) {
  const activeLineIndex = useMemo(
    () => estimateActiveLineIndex(parsed.lines, currentTimeMs, totalMs),
    [parsed.lines, currentTimeMs, totalMs]
  );

  // 当前激活行的 chord 名集合（用于 chord 高亮）
  const activeChordNames = useMemo(() => {
    const lyricLines = parsed.lines.filter(ln => ln.text && !ln.directive);
    if (activeLineIndex < 0 || activeLineIndex >= lyricLines.length) return new Set<string>();
    return new Set(lyricLines[activeLineIndex].chords.map(c => c.name));
  }, [parsed.lines, activeLineIndex]);

  if (parsed.lines.length === 0) {
    return (
      <div
        data-testid={testId}
        data-state="empty"
        className={`flex h-full items-center justify-center p-8 text-center text-sm ${dark ? "text-zinc-500" : "text-muted-foreground"}`}
      >
        <div>
          <p className="text-base">还没有曲谱</p>
          <p className="mt-1 text-xs opacity-75">在歌曲库双击歌曲后，可在编辑弹窗里粘贴 chordpro 文本</p>
        </div>
      </div>
    );
  }

  // 计算"第几个 lyric 行"——给每行一个标记，便于比对 activeLineIndex
  let lyricIndex = -1;
  return (
    <div
      data-testid={testId}
      data-state="ready"
      data-active-line={activeLineIndex}
      className="h-full overflow-y-auto px-5 py-6"
    >
      <ol className="space-y-1 font-mono text-sm">
        {parsed.lines.map((line) => {
          // 注释行
          if (line.directive === "comment") {
            return (
              <li
                key={line.lineIndex}
                data-testid={`${testId}-comment`}
                className={`italic text-xs ${dark ? "text-zinc-600" : "text-muted-foreground/70"}`}
              >
                {/* {line.section && <span className="mr-2 opacity-60">[{line.section}]</span>} */}
                {line.text}
              </li>
            );
          }
          // 歌词行（含 chord / 空行）
          const isLyric = !!line.text;
          const thisLyricIndex = isLyric ? (lyricIndex += 1) : -1;
          const isActive = isLyric && thisLyricIndex === activeLineIndex;
          return (
            <li
              key={line.lineIndex}
              data-testid={`${testId}-line`}
              data-active={isActive ? "true" : "false"}
              data-line-index={line.lineIndex}
              data-section={line.section ?? ""}
              className={`rounded px-2 py-1.5 leading-relaxed transition-colors ${
                isActive
                  ? dark ? "bg-amber-500/15" : "bg-amber-100"
                  : ""
              }`}
            >
              {/* chord 行（chords 在 lyrics 上方） */}
              {line.chords.length > 0 && (
                <div className="flex h-5">
                  {line.chords.map((chord, ci) => (
                    <span
                      key={ci}
                      data-testid={`${testId}-chord`}
                      data-chord={chord.name}
                      data-active={activeChordNames.has(chord.name) ? "true" : "false"}
                      className={`absolute pointer-events-none`}
                      style={{ left: 0 }}
                    >
                      {/* chord 实际定位由下方歌词字符位置决定；这里仅展示名称 */}
                    </span>
                  ))}
                </div>
              )}
              {/* 歌词行：把 chord token 内联插到对应字符位置 */}
              <div className={isActive ? `font-semibold ${dark ? "text-zinc-50" : "text-foreground"}` : dark ? "text-zinc-300" : "text-foreground/80"}>
                {renderLineWithChords(line, activeChordNames, dark)}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function renderLineWithChords(
  line: ChordProLine,
  activeChordNames: Set<string>,
  dark: boolean
) {
  if (line.chords.length === 0) {
    return <span>{line.text || <span className="opacity-30">（空白）</span>}</span>;
  }
  // 按 charIndex 拆分：在位置 i 前插入 chord 节点
  const chars = line.text;
  const segments: Array<{ kind: "text" | "chord"; value: string; active?: boolean }> = [];
  let last = 0;
  for (const chord of line.chords) {
    if (chord.charIndex > last) {
      segments.push({ kind: "text", value: chars.slice(last, chord.charIndex) });
    }
    segments.push({ kind: "chord", value: chord.name, active: activeChordNames.has(chord.name) });
    last = chord.charIndex;
  }
  if (last < chars.length) {
    segments.push({ kind: "text", value: chars.slice(last) });
  }
  return (
    <>
      {segments.map((seg, si) => {
        if (seg.kind === "text") {
          return <span key={si}>{seg.value}</span>;
        }
        const activeClass = seg.active
          ? dark
            ? "text-amber-300 font-bold"
            : "text-amber-700 font-bold"
          : dark
            ? "text-blue-400"
            : "text-blue-600";
        return (
          <span key={si} className={`relative`}>
            {/* 用 zero-width space 占位：让 chord 上方有空间放标签 */}
            <span
              className={`absolute -top-4 left-0 text-[10px] font-semibold ${activeClass}`}
              data-testid="tabs-chord-token"
              data-active={seg.active ? "true" : "false"}
            >
              {seg.value}
            </span>
            <span className="invisible">·</span>
          </span>
        );
      })}
    </>
  );
}
