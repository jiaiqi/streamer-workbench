import assert from "node:assert/strict";
import test from "node:test";

import type { Song } from "../types.ts";
import {
  createPendingEvent, enqueue, flushPending, loadStorageV2, migrateStorage, moveQueueItem,
  resolveQueueItem, toggleSung,
} from "./model.ts";

const song = (id: string, title: string): Song => ({
  id, title, status: "active", section: null, artists: [], lyricist: "", composer: "",
  key: "", capo: null, difficulty: "", tabs: "", tags: [], pinyin: "", added_at: "",
  notes: "", learned_at: "", tab_files: [],
});

const eventFactory = (type: "queue_added" | "song_sung", value: Song, occurredAt?: string) =>
  createPendingEvent(type, value, () => new Date("2026-01-01T00:00:00.000Z"), () => "fixed-uuid", occurredAt);

test("旧队列按 song_id 迁移、稳定去重并保留未解析项", () => {
  const songs = [song("song_a", "后来"), song("song_b", "知足")];
  const result = migrateStorage(null, JSON.stringify([
    { title: "后来", sung: false, addedAt: 20 },
    { title: "后来", sung: true, addedAt: 10 },
    { title: "不存在", sung: false, addedAt: 30 },
  ]), "[]", songs, eventFactory);
  assert.equal(result.error, null);
  assert.deepEqual(result.storage?.queue, [{
    song_id: "song_a", title_snapshot: "后来", sung: true, added_at: 10,
  }]);
  assert.equal(result.storage?.unresolved_queue[0].title, "不存在");
});

test("旧事件获得稳定 Event v2 信封，未解析事件不自动上报", () => {
  const result = migrateStorage(null, "[]", JSON.stringify([
    { type: "song_sung", title: "后来", ts: "2026-01-02T03:04:05" },
    { type: "queue_added", title: "未知", ts: "2026-01-02T03:05:00" },
  ]), [song("song_a", "后来")], eventFactory);
  assert.deepEqual(result.storage?.pending_events[0], {
    event_id: "evt_fixeduuid", type: "song_sung", song_id: "song_a",
    title_snapshot: "后来", occurred_at: "2026-01-02T03:04:05", source: "quick-view",
  });
  assert.equal(result.storage?.unresolved_pending_events.length, 1);
});

test("v2 重复读取幂等，损坏 JSON 不产生覆盖值", () => {
  const original = {
    version: 2 as const, queue: [], pending_events: [], unresolved_queue: [], unresolved_pending_events: [],
  };
  const loaded = migrateStorage(JSON.stringify(original), null, null, [], eventFactory);
  assert.deepEqual(loaded.storage, original);
  assert.equal(loaded.migrated, false);
  const broken = migrateStorage("{", null, null, [], eventFactory);
  assert.equal(broken.storage, null);
  assert.match(broken.error ?? "", /已损坏/);
  assert.deepEqual(loadStorageV2(JSON.stringify(original)).storage, original);
});

test("队列操作只使用 ID，改名显示最新标题，删除后显示快照", () => {
  const oldSong = song("song_a", "旧名");
  const newSong = song("song_a", "新名");
  let queue = enqueue([], oldSong, 10);
  assert.strictEqual(enqueue(queue, newSong, 20), queue);
  queue = toggleSung(queue, "song_a");
  assert.equal(queue[0].sung, true);
  assert.strictEqual(enqueue(queue, newSong, 20), queue);
  assert.equal(resolveQueueItem(queue[0], new Map([[newSong.id, newSong]])).title, "新名");
  assert.deepEqual(resolveQueueItem(queue[0], new Map()), { song: undefined, title: "旧名", missing: true });
  const second = { ...queue[0], song_id: "song_b", sung: false };
  assert.deepEqual(moveQueueItem([{ ...queue[0], sung: false }, second], "song_b", -1).map(i => i.song_id), ["song_b", "song_a"]);
});

test("补报保序、失败保留且重试复用原 event_id", async () => {
  const first = eventFactory("queue_added", song("song_a", "后来"));
  const second = { ...eventFactory("song_sung", song("song_a", "后来")), event_id: "evt_second" };
  const called: string[] = [];
  const failed = await flushPending([first, second], async event => {
    called.push(event.event_id);
    return { ok: false, diagnostic: "409: event_id 冲突" };
  });
  assert.deepEqual(called, [first.event_id]);
  assert.deepEqual(failed.remaining.map(e => e.event_id), [first.event_id, second.event_id]);
  assert.match(failed.diagnostic ?? "", /冲突/);

  const retried = await flushPending(failed.remaining, async event => {
    called.push(event.event_id);
    return { ok: true };
  });
  assert.deepEqual(retried.completedIds, [first.event_id, second.event_id]);
  assert.deepEqual(retried.remaining, []);
});
