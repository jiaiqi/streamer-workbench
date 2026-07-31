/// R3 乐理辅助占位 UI
///
/// 当前显示:
/// - 12 平均律基础调表 (C / C# / D / Eb / E / F / F# / G / Ab / A / Bb / B)
/// - 关系小调 (如 C 的关系小调是 Am)
/// - 简易和弦提示 (大三和弦: I IV V)
///
/// 占位说明: 完整乐理辅助 (按调显示常用和弦进行 / 简谱对照 / 转调建议) 待 R4 接入。
import { useState } from "react";

const KEYS = [
  { major: "C",  minor: "Am" },
  { major: "C#", minor: "A#m" },
  { major: "D",  minor: "Bm" },
  { major: "Eb", minor: "Cm" },
  { major: "E",  minor: "C#m" },
  { major: "F",  minor: "Dm" },
  { major: "F#", minor: "D#m" },
  { major: "G",  minor: "Em" },
  { major: "Ab", minor: "Fm" },
  { major: "A",  minor: "F#m" },
  { major: "Bb", minor: "Gm" },
  { major: "B",  minor: "G#m" },
];

const COMMON_CHORDS_BY_KEY: Record<string, string[]> = {
  "C":  ["C",  "F",  "G",  "Am",  "Dm",  "Em",  "G7"],
  "D":  ["D",  "G",  "A",  "Bm",  "Em",  "F#m", "A7"],
  "E":  ["E",  "A",  "B",  "C#m", "F#m", "G#m", "B7"],
  "F":  ["F",  "Bb", "C",  "Dm",  "Gm",  "Am",  "C7"],
  "G":  ["G",  "C",  "D",  "Em",  "Am",  "Bm",  "D7"],
  "A":  ["A",  "D",  "E",  "F#m", "Bm",  "C#m", "E7"],
  "B":  ["B",  "E",  "F#", "G#m", "C#m", "D#m", "F#7"],
};

interface TheoryHelperProps {
  dark: boolean;
  /** 当前选中歌曲的 Key (如有), 选中后高亮该调。 */
  selectedKey?: string;
  /** Capo 夹几品 (如有), 影响实际演奏调。 */
  capo?: number;
}

export default function TheoryHelper({ dark, selectedKey, capo }: TheoryHelperProps) {
  const [hoverKey, setHoverKey] = useState<string | null>(null);

  const activeKey = selectedKey?.trim();
  const displayKey = activeKey && KEYS.some(k => k.major === activeKey)
    ? activeKey
    : null;

  return (
    <div className={`rounded-2xl border ${dark ? "border-zinc-700/50 bg-zinc-800/30" : "border-border bg-card"} p-4`}>
      <div className="flex items-center justify-between mb-3">
        <h3 className={`text-sm font-semibold ${dark ? "text-zinc-100" : "text-foreground"}`}>
          乐理辅助
        </h3>
        {(displayKey || capo != null) && (
          <span className={`text-[11px] px-2 py-0.5 rounded-full ${
            dark ? "bg-primary/20 text-primary" : "bg-primary-soft text-primary"
          }`}>
            {displayKey ?? "—"} {capo != null && capo > 0 && `· Capo ${capo}`}
          </span>
        )}
      </div>

      <div className="grid grid-cols-4 gap-1.5">
        {KEYS.map(k => {
          const isActive = displayKey === k.major;
          const isHover = hoverKey === k.major;
          return (
            <button
              key={k.major}
              type="button"
              data-testid={`theory-key-${k.major}`}
              onMouseEnter={() => setHoverKey(k.major)}
              onMouseLeave={() => setHoverKey(null)}
              className={`flex flex-col items-center gap-0.5 py-2 rounded-lg text-xs font-medium transition-colors ${
                isActive
                  ? (dark ? "bg-primary text-primary-foreground" : "bg-primary text-primary-foreground")
                  : (dark ? "bg-zinc-800/60 text-zinc-300 hover:bg-zinc-700/60" : "bg-muted text-foreground hover:bg-primary-soft")
              }`}
            >
              <span className="text-sm">{k.major}</span>
              <span className={`text-[10px] ${isActive ? "opacity-80" : "opacity-60"}`}>
                {k.minor}
              </span>
            </button>
          );
        })}
      </div>

      {/* 选中调的和弦提示 */}
      {isHover && COMMON_CHORDS_BY_KEY[hoverKey ?? ""] && (
        <div className={`mt-3 p-2.5 rounded-lg text-xs ${dark ? "bg-zinc-800/60" : "bg-muted"}`}>
          <p className={`mb-1 ${dark ? "text-zinc-400" : "text-muted-foreground"}`}>
            <span className="font-semibold">{hoverKey}</span> 大调常用和弦
          </p>
          <div className="flex flex-wrap gap-1">
            {COMMON_CHORDS_BY_KEY[hoverKey ?? ""].map(c => (
              <span
                key={c}
                className={`px-1.5 py-0.5 rounded text-[11px] ${
                  dark ? "bg-zinc-700/60 text-zinc-200" : "bg-card text-card-foreground border border-border"
                }`}
              >
                {c}
              </span>
            ))}
          </div>
        </div>
      )}

      <p className={`mt-3 text-[10px] ${dark ? "text-zinc-600" : "text-muted-foreground/70"}`}>
        完整乐理辅助（和弦进行 / 简谱对照 / 转调建议）待 R4 接入
      </p>
    </div>
  );
}
