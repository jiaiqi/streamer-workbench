/// R8.0 弹唱：ChordPro 曲谱格式解析（前端 mirror core/chordpro.py）。
///
/// 标签形态：
///   {title: 歌名}              元数据
///   {key: C} {capo: 2}          元数据
///   {comment: 前奏}             行级注释
///   {start_of_verse}            section 标签（自动应用 section=verse）
///   [C]歌词[Am]文字             行内 chord + 歌词
///   \\{ \\} \\\\                  转义还原
export interface ChordPosition {
  charIndex: number;  // 歌词字符串中的位置（0-based）
  name: string;       // chord 名
}

export interface ChordProLine {
  lineIndex: number;
  text: string;            // 歌词文本（去掉 [...]）
  chords: ChordPosition[];
  directive: string | null; // "comment" / null
  section: string | null;   // "verse" / "chorus" / "bridge" …
}

export interface ParsedChordPro {
  lines: ChordProLine[];
  meta: Record<string, string>;
}

const DIRECTIVE_RE = /\{([a-zA-Z_][a-zA-Z0-9_-]*)(?::\s*([^{}]*?)\s*)?\}/g;

export function parseChordpro(text: string | null | undefined): ParsedChordPro {
  if (!text || !text.trim()) {
    return { lines: [], meta: {} };
  }
  const rawLines: ChordProLine[] = [];
  const meta: Record<string, string> = {};
  let currentSection: string | null = null;

  const META_EXCLUDE = new Set([
    "start_of_verse", "end_of_verse",
    "start_of_chorus", "end_of_chorus",
    "start_of_bridge", "end_of_bridge",
    "comment",
    "start_of_tab", "end_of_tab",
  ]);

  text.split(/\r?\n/).forEach((rawLine, lineIndex) => {
    // reset regex state（避免 lastIndex 残留）
    DIRECTIVE_RE.lastIndex = 0;
    const directives: Array<[string, string | null]> = [];
    let m: RegExpExecArray | null;
    while ((m = DIRECTIVE_RE.exec(rawLine)) !== null) {
      directives.push([m[1], m[2] ?? null]);
    }
    const stripped = rawLine.replace(DIRECTIVE_RE, "").trim();

    let isMetaOnly = false;
    for (const [name, value] of directives) {
      const lname = name.toLowerCase();
      if (value !== null && !META_EXCLUDE.has(lname)) {
        if (!(lname in meta)) meta[lname] = value.trim();
        isMetaOnly = true;
      } else if (lname === "comment" && value !== null) {
        rawLines.push({
          lineIndex,
          text: value.trim(),
          chords: [],
          directive: "comment",
          section: currentSection,
        });
        isMetaOnly = true;
      } else if (lname in {
        "start_of_verse": 1, "end_of_verse": 1,
        "start_of_chorus": 1, "end_of_chorus": 1,
        "start_of_bridge": 1, "end_of_bridge": 1,
      }) {
        const sectionName = lname.replace(/^start_of_/, "").replace(/^end_of_/, "");
        if (lname.startsWith("start_of_")) {
          currentSection = sectionName;
        }
        isMetaOnly = !stripped;
      }
    }

    if (isMetaOnly && !stripped) return;

    // 行内 chord 字符级解析
    const chords: ChordPosition[] = [];
    const lyricsChars: string[] = [];
    let i = 0;
    while (i < stripped.length) {
      if (stripped[i] === "[") {
        const end = stripped.indexOf("]", i + 1);
        if (end < 0) {
          lyricsChars.push(stripped[i]);
          i += 1;
          continue;
        }
        const chordName = stripped.slice(i + 1, end).trim();
        if (chordName) {
          chords.push({ charIndex: lyricsChars.length, name: chordName });
        }
        i = end + 1;
      } else {
        lyricsChars.push(stripped[i]);
        i += 1;
      }
    }
    const lyricsText = lyricsChars.join("")
      .replace(/\\\{/g, "{").replace(/\\\}/g, "}").replace(/\\\\/g, "\\");

    rawLines.push({
      lineIndex,
      text: lyricsText,
      chords,
      directive: null,
      section: currentSection,
    });
  });

  return { lines: rawLines, meta };
}

/// 提取整首曲谱里所有出现过的 chord 名（去重保序）。
export function collectChordNames(parsed: ParsedChordPro): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const line of parsed.lines) {
    for (const chord of line.chords) {
      if (!seen.has(chord.name)) {
        seen.add(chord.name);
        result.push(chord.name);
      }
    }
  }
  return result;
}
