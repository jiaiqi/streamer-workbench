import type { Song } from "../types";

export const STORAGE_KEY = "quick-view-storage-v2";
export const LEGACY_QUEUE_KEY = "tonight-queue-v1";
export const LEGACY_PENDING_KEY = "quick-events-pending-v1";

export interface QueueItem {
  song_id: string;
  title_snapshot: string;
  sung: boolean;
  added_at: number;
}

export type QuickEventType = "queue_added" | "song_sung";

export interface PendingEvent {
  event_id: string;
  type: QuickEventType;
  song_id: string;
  title_snapshot: string;
  occurred_at: string;
  source: "quick-view";
}

export interface UnresolvedQueueItem {
  title: string;
  sung: boolean;
  added_at: number;
  reason: "missing_song" | "ambiguous_title" | "invalid_item";
}

export interface UnresolvedPendingEvent {
  type: string;
  title: string;
  occurred_at: string;
  reason: "missing_song" | "ambiguous_title" | "invalid_item";
}

export interface QuickViewStorageV2 {
  version: 2;
  queue: QueueItem[];
  pending_events: PendingEvent[];
  unresolved_queue: UnresolvedQueueItem[];
  unresolved_pending_events: UnresolvedPendingEvent[];
}

export interface MigrationResult {
  storage: QuickViewStorageV2 | null;
  migrated: boolean;
  error: string | null;
}

export const emptyStorage = (): QuickViewStorageV2 => ({
  version: 2,
  queue: [],
  pending_events: [],
  unresolved_queue: [],
  unresolved_pending_events: [],
});

function parseJson(raw: string | null, fallback: unknown, label: string): unknown {
  if (raw === null) return fallback;
  try {
    return JSON.parse(raw);
  } catch {
    throw new Error(`${label} JSON 已损坏；原值已保留，请备份后修复或清除`);
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isQueueItem(value: unknown): value is QueueItem {
  return isRecord(value)
    && isNonEmptyString(value.song_id)
    && isNonEmptyString(value.title_snapshot)
    && typeof value.sung === "boolean"
    && typeof value.added_at === "number"
    && Number.isFinite(value.added_at);
}

function isPendingEvent(value: unknown): value is PendingEvent {
  return isRecord(value)
    && isNonEmptyString(value.event_id)
    && (value.type === "queue_added" || value.type === "song_sung")
    && isNonEmptyString(value.song_id)
    && isNonEmptyString(value.title_snapshot)
    && isNonEmptyString(value.occurred_at)
    && value.source === "quick-view";
}

function isUnresolvedQueueItem(value: unknown): value is UnresolvedQueueItem {
  return isRecord(value)
    && isNonEmptyString(value.title)
    && typeof value.sung === "boolean"
    && typeof value.added_at === "number"
    && Number.isFinite(value.added_at)
    && (value.reason === "missing_song"
      || value.reason === "ambiguous_title"
      || value.reason === "invalid_item");
}

function isUnresolvedPendingEvent(value: unknown): value is UnresolvedPendingEvent {
  return isRecord(value)
    && isNonEmptyString(value.type)
    && isNonEmptyString(value.title)
    && typeof value.occurred_at === "string"
    && (value.reason === "missing_song"
      || value.reason === "ambiguous_title"
      || value.reason === "invalid_item");
}

function validateV2(value: unknown): QuickViewStorageV2 {
  if (!isRecord(value) || value.version !== 2
      || !Array.isArray(value.queue) || !value.queue.every(isQueueItem)
      || !Array.isArray(value.pending_events) || !value.pending_events.every(isPendingEvent)
      || !Array.isArray(value.unresolved_queue)
      || !value.unresolved_queue.every(isUnresolvedQueueItem)
      || !Array.isArray(value.unresolved_pending_events)
      || !value.unresolved_pending_events.every(isUnresolvedPendingEvent)) {
    throw new Error("QuickView v2 存储结构无效；原值已保留，请备份后修复或清除");
  }
  return {
    version: 2,
    queue: value.queue,
    pending_events: value.pending_events,
    unresolved_queue: value.unresolved_queue,
    unresolved_pending_events: value.unresolved_pending_events,
  };
}

export function loadStorageV2(rawV2: string | null): MigrationResult {
  if (rawV2 === null) return { storage: null, migrated: false, error: null };
  try {
    return { storage: validateV2(parseJson(rawV2, null, "QuickView v2")), migrated: false, error: null };
  } catch (error) {
    return {
      storage: null,
      migrated: false,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

function titleIndex(songs: Song[]): Map<string, Song[]> {
  const result = new Map<string, Song[]>();
  for (const song of songs) {
    const matches = result.get(song.title) ?? [];
    matches.push(song);
    result.set(song.title, matches);
  }
  return result;
}

function resolutionReason(matches: Song[] | undefined): "missing_song" | "ambiguous_title" {
  return matches?.length ? "ambiguous_title" : "missing_song";
}

export function migrateStorage(
  rawV2: string | null,
  rawLegacyQueue: string | null,
  rawLegacyPending: string | null,
  songs: Song[],
  createEvent: (type: QuickEventType, song: Song, occurredAt?: string) => PendingEvent,
): MigrationResult {
  try {
    if (rawV2 !== null) {
      return loadStorageV2(rawV2);
    }

    const legacyQueue = parseJson(rawLegacyQueue, [], "旧队列");
    const legacyPending = parseJson(rawLegacyPending, [], "旧事件队列");
    if (!Array.isArray(legacyQueue) || !Array.isArray(legacyPending)) {
      throw new Error("旧 QuickView 存储结构无效；原值已保留，请备份后修复或清除");
    }

    const byTitle = titleIndex(songs);
    const storage = emptyStorage();
    const queueById = new Map<string, QueueItem>();

    for (const value of legacyQueue) {
      if (!isRecord(value) || typeof value.title !== "string") {
        storage.unresolved_queue.push({
          title: "（无法读取）", sung: false, added_at: 0, reason: "invalid_item",
        });
        continue;
      }
      const title = value.title;
      const sung = value.sung === true;
      const addedAt = typeof value.addedAt === "number" ? value.addedAt : 0;
      const matches = byTitle.get(title);
      if (matches?.length !== 1) {
        storage.unresolved_queue.push({ title, sung, added_at: addedAt, reason: resolutionReason(matches) });
        continue;
      }
      const song = matches[0];
      const previous = queueById.get(song.id);
      queueById.set(song.id, previous ? {
        ...previous,
        sung: previous.sung || sung,
        added_at: Math.min(previous.added_at, addedAt),
      } : { song_id: song.id, title_snapshot: title, sung, added_at: addedAt });
    }
    storage.queue = [...queueById.values()].sort((a, b) => a.added_at - b.added_at);

    for (const value of legacyPending) {
      if (!isRecord(value) || typeof value.type !== "string" || typeof value.title !== "string") {
        storage.unresolved_pending_events.push({
          type: "unknown", title: "（无法读取）", occurred_at: "", reason: "invalid_item",
        });
        continue;
      }
      const occurredAt = typeof value.ts === "string" ? value.ts : "";
      const matches = byTitle.get(value.title);
      const eventType: QuickEventType | null = value.type === "queue_added" || value.type === "song_sung"
        ? value.type : null;
      if (matches?.length !== 1 || eventType === null) {
        storage.unresolved_pending_events.push({
          type: value.type,
          title: value.title,
          occurred_at: occurredAt,
          reason: eventType ? resolutionReason(matches) : "invalid_item",
        });
        continue;
      }
      storage.pending_events.push(createEvent(eventType, matches[0], occurredAt || undefined));
    }
    return { storage, migrated: true, error: null };
  } catch (error) {
    return { storage: null, migrated: false, error: error instanceof Error ? error.message : String(error) };
  }
}

export function enqueue(queue: QueueItem[], song: Song, addedAt: number): QueueItem[] {
  if (queue.some(item => item.song_id === song.id)) return queue;
  return [...queue, { song_id: song.id, title_snapshot: song.title, sung: false, added_at: addedAt }];
}

export function toggleSung(queue: QueueItem[], songId: string): QueueItem[] {
  return queue.map(item => item.song_id === songId ? { ...item, sung: !item.sung } : item);
}

export function moveQueueItem(queue: QueueItem[], songId: string, direction: -1 | 1): QueueItem[] {
  const index = queue.findIndex(item => item.song_id === songId && !item.sung);
  const target = index + direction;
  if (index < 0 || target < 0 || target >= queue.length || queue[target].sung) return queue;
  const next = [...queue];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

export function resolveQueueItem(item: QueueItem, songsById: Map<string, Song>) {
  const song = songsById.get(item.song_id);
  return { song, title: song?.title ?? item.title_snapshot, missing: !song };
}

export function createPendingEvent(
  type: QuickEventType,
  song: Song,
  now: () => Date = () => new Date(),
  uuid: () => string = createUuid,
  occurredAt?: string,
): PendingEvent {
  return {
    event_id: `evt_${uuid().replaceAll("-", "")}`,
    type,
    song_id: song.id,
    title_snapshot: song.title,
    occurred_at: occurredAt ?? now().toISOString(),
    source: "quick-view",
  };
}

function createUuid(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  return [...bytes].map(byte => byte.toString(16).padStart(2, "0")).join("");
}

export interface ReportResult { ok: boolean; diagnostic?: string }

export async function flushPending(
  events: PendingEvent[],
  reporter: (event: PendingEvent) => Promise<ReportResult>,
): Promise<{ completedIds: string[]; remaining: PendingEvent[]; diagnostic: string | null }> {
  const completedIds: string[] = [];
  for (let index = 0; index < events.length; index += 1) {
    const result = await reporter(events[index]);
    if (!result.ok) {
      return {
        completedIds,
        remaining: events.slice(index),
        diagnostic: result.diagnostic ?? "事件补报失败，将在后续重试",
      };
    }
    completedIds.push(events[index].event_id);
  }
  return { completedIds, remaining: [], diagnostic: null };
}
