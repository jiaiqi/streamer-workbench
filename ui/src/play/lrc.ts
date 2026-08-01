/// R8.0 弹唱：LRC 歌词格式解析（前端 mirror core/lrc.py）。
///
/// 与后端解析逻辑保持一致——两边用同一套测试样例验证。
/// 解析规则参考：https://en.wikipedia.org/wiki/LRC_(file_format)
///
/// 标签形态：
///   [mm:ss.xx]歌词        标准时间戳
///   [mm:ss.xx][mm:ss.xx] 增强 LRC：同行多时间戳
///   [ti:标题][ar:歌手]   元数据
///   [offset:+0]          全局时间偏移（毫秒）
export interface LrcLine {
  timeMs: number;   // 触发时间（毫秒，含 offset）
  text: string;     // 歌词文本（去掉前后空白）
}

export interface ParsedLRC {
  lines: LrcLine[];     // 按 timeMs 升序
  meta: Record<string, string>;
}

const TIMESTAMP_RE = /\[(\d{1,2}):(\d{1,2})(?:[.:](\d{1,3}))?\]/;
const META_RE = /^\[([a-zA-Z][a-zA-Z0-9_-]*):([^\]]*)\]$/;
const TAG_RE = /\[[^\]]+\]/g;

function parseTimestampToMs(minute: string, second: string, fraction: string | undefined): number {
  const m = parseInt(minute, 10);
  const s = parseInt(second, 10);
  let fracMs = 0;
  if (fraction) {
    const scale = 3 - fraction.length;
    const base = scale >= 0 ? parseInt(fraction, 10) : parseInt(fraction.slice(0, 3), 10);
    fracMs = base * Math.pow(10, scale);
  }
  return (m * 60 + s) * 1000 + fracMs;
}

export function parseLrc(text: string | null | undefined): ParsedLRC {
  if (!text || !text.trim()) {
    return { lines: [], meta: {} };
  }
  const rawLines: LrcLine[] = [];
  const meta: Record<string, string> = {};
  let offsetMs = 0;

  for (const line of text.split(/\r?\n/)) {
    const stripped = line.trim();
    if (!stripped) continue;

    const tags = stripped.match(TAG_RE);
    if (!tags) continue;

    const textPart = stripped.replace(TAG_RE, "").trim();

    const timestamps: number[] = [];
    let isMetaLine = false;
    for (const tag of tags) {
      const tsMatch = TIMESTAMP_RE.exec(tag);
      if (tsMatch) {
        timestamps.push(parseTimestampToMs(tsMatch[1], tsMatch[2], tsMatch[3]));
        continue;
      }
      const inner = tag.slice(1, -1);
      const metaMatch = META_RE.exec(tag);
      if (metaMatch) {
        const key = metaMatch[1];
        const value = metaMatch[2].trim();
        if (!(key in meta)) meta[key] = value;
        isMetaLine = true;
        if (key === "offset") {
          const off = parseInt(value, 10);
          if (!Number.isNaN(off)) offsetMs += off;
        }
        continue;
      }
    }

    if (timestamps.length === 0) continue;
    if (isMetaLine && !textPart) continue;

    for (const ts of timestamps) {
      rawLines.push({ timeMs: ts + offsetMs, text: textPart });
    }
  }

  rawLines.sort((a, b) => a.timeMs - b.timeMs);
  return { lines: rawLines, meta };
}

/// 二分查找：position_ms 时刻正在唱的歌词行索引。
/// - 空 lines → -1
/// - position < lines[0].timeMs → -1
/// - position > lines[last].timeMs → 末行索引
export function findActiveLine(lines: LrcLine[], positionMs: number): number {
  if (lines.length === 0) return -1;
  if (positionMs < lines[0].timeMs) return -1;
  let lo = 0;
  let hi = lines.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (lines[mid].timeMs <= positionMs) {
      lo = mid + 1;
    } else {
      hi = mid;
    }
  }
  return lo - 1;
}

/// 把纯文本歌词按行均分到时间轴（无 LRC 时 fallback 用）。
/// 给定总时长（毫秒），每行均分；最后一行追加到末尾。
export function distributePlainLyrics(plainText: string, totalMs: number): LrcLine[] {
  const texts = plainText.split(/\r?\n/).map(t => t.trim()).filter(Boolean);
  if (texts.length === 0) return [];
  const perLine = totalMs / texts.length;
  return texts.map((text, idx) => ({
    timeMs: Math.floor(idx * perLine),
    text,
  }));
}
