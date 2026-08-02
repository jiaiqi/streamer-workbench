/// R9.3 Capo 工具函数
///
/// Capo 变调夹的物理含义：
///   - 吉他谱上的和弦按法是"弹 C 和弦"
///   - Capo 夹在 N 品 + 弹 C 和弦 = 实际音高是 (C + N 个半音)
///   - 例：原 Key C + Capo 2 = 实际 D 调
///
/// 因此 Capo 改了，"实际 Key" 也跟着变。
///
/// 简化：本工具只处理大调（key 为 C / D / E / F / G / A / B + 可选 #）；
/// 小调（Am / Em 等）按同名大调处理（Am → A）。
/// 完整乐理（考虑 #/b 等价、五度循环）不在 R9.3 范围。

const SHARP_KEYS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];

/** 把任意 key 字符串归一为 SHARP_KEYS 之一（不识别返回 null）。 */
function normalizeKeyIndex(key: string): { index: number; isMinor: boolean } | null {
  if (!key) return null;
  const trimmed = key.trim();
  // 识别小调（"Am" / "Em" 等，大小写均可）
  const isMinor = /m$/i.test(trimmed);
  const withoutMinor = trimmed.replace(/m$/i, "");
  // 处理 b（降号）：Db = C#, Eb = D#, Gb = F#, Ab = G#, Bb = A#
  const upper = withoutMinor.toUpperCase();
  const flatMap: Record<string, number> = {
    "DB": 1, "EB": 3, "GB": 6, "AB": 8, "BB": 10,
  };
  let index: number;
  if (flatMap[upper] !== undefined) {
    index = flatMap[upper];
  } else {
    const idx = SHARP_KEYS.indexOf(upper);
    if (idx < 0) return null;
    index = idx;
  }
  return { index, isMinor };
}

/**
 * 把原 Key 升 N 个半音。
 *
 * - capo 半音差 = capo 品数
 * - 实际 Key = transpose(originalKey, capo)
 * - capo=0 时返回原 Key
 * - 小调（Am/Em）保留 m 后缀
 */
export function transposeKey(originalKey: string, capo: number): string {
  if (!originalKey || capo === 0) return originalKey;
  const norm = normalizeKeyIndex(originalKey);
  if (norm === null) return originalKey;
  const next = (norm.index + capo + 120) % 12;
  return SHARP_KEYS[next] + (norm.isMinor ? "m" : "");
}

/** Capo 的合理范围（0-12）。大于 12 视为不夹。 */
export const CAPO_MIN = 0;
export const CAPO_MAX = 12;
export function clampCapo(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(CAPO_MIN, Math.min(CAPO_MAX, Math.round(value)));
}
