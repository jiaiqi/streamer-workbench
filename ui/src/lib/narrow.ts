/// R4.1.7 narrow helper 公共工具。
///
/// 取代散落在 LiveView / StatsView / 其他视图的 `asXxx` 函数：
///   - LiveView.tsx asQueueEntry / asPerformance
///   - 其他位置 `value as Type` 直接断言（不安全）
///
/// 风格：所有 narrow 函数返回 null 而不是 throw；调用方决定 null 怎么处理。
///
/// 命名：`as*` 表示"尝试 narrow 到 * 类型；失败返回 null"。

/** unknown → Record<string, unknown>（简化版；只校验是 plain object） */
export function asRecord(value: unknown): Record<string, unknown> | null {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

/** Record<string, unknown> → string（key 必须存在） */
export function asString(record: Record<string, unknown>, key: string): string | null {
  const v = record[key];
  return typeof v === "string" ? v : null;
}

/** Record<string, unknown> → number（key 必须存在） */
export function asNumber(record: Record<string, unknown>, key: string): number | null {
  const v = record[key];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** Record<string, unknown> → boolean */
export function asBoolean(record: Record<string, unknown>, key: string): boolean | null {
  const v = record[key];
  return typeof v === "boolean" ? v : null;
}

/** Record<string, unknown> → string[] */
export function asStringArray(record: Record<string, unknown>, key: string): string[] | null {
  const v = record[key];
  if (!Array.isArray(v)) return null;
  return v.every(item => typeof item === "string") ? v as string[] : null;
}

/** unknown → unknown[]（任一数组；调用方用 asStringArray / narrowWith 做元素 narrow） */
export function asArray(value: unknown): unknown[] | null {
  return Array.isArray(value) ? value : null;
}

/** Record<string, unknown> → T | null（带自定义 validator） */
export function narrowWith<T>(
  record: Record<string, unknown>,
  key: string,
  validator: (raw: unknown) => T | null,
): T | null {
  return validator(record[key]);
}

/** unknown 直接通过 validator 验证；典型用法 `narrowUnknown(value, asQueueEntry)` */
export function narrowUnknown<T>(
  value: unknown,
  validator: (raw: unknown) => T | null,
): T | null {
  return validator(value);
}

/** 必填 string（key 必须存在且是 string；否则返回 fallback） */
export function asStringOr(record: Record<string, unknown>, key: string, fallback: string): string {
  const v = record[key];
  return typeof v === "string" ? v : fallback;
}

/** 必填 number（key 缺失或非有限数 → fallback） */
export function asNumberOr(record: Record<string, unknown>, key: string, fallback: number): number {
  const v = record[key];
  return typeof v === "number" && Number.isFinite(v) ? v : fallback;
}
