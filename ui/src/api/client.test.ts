import assert from "node:assert/strict";
import test from "node:test";

import { ApiClientError, createApiClient } from "./client.ts";

function jsonResponse(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "content-type": "application/json" },
  });
}

test("serializes JSON body and returns typed JSON", async () => {
  let received: { url: string; init?: RequestInit } | undefined;
  const request = createApiClient({
    baseUrl: "http://127.0.0.1:8000/",
    fetch: async (url, init) => {
      received = { url: String(url), init };
      return jsonResponse({ ok: true });
    },
  });
  const result = await request<{ ok: boolean }>("/api/example", {
    method: "POST",
    body: { title: "知足" },
  });
  assert.deepEqual(result, { ok: true });
  assert.equal(received?.url, "http://127.0.0.1:8000/api/example");
  assert.equal(received?.init?.body, JSON.stringify({ title: "知足" }));
  assert.equal(new Headers(received?.init?.headers).get("content-type"), "application/json");
});

test("passes FormData through without forcing a JSON content type", async () => {
  let received: RequestInit | undefined;
  const request = createApiClient({ fetch: async (_url, init) => {
    received = init;
    return jsonResponse({ tab_files: [] });
  } });
  const form = new FormData();
  form.append("file", new Blob(["tab"]), "tab.txt");
  await request("/api/tabs", { method: "POST", body: form });
  assert.equal(received?.body, form);
  assert.equal(new Headers(received?.headers).has("content-type"), false);
});

test("parses structured API error envelope", async () => {
  const request = createApiClient({
    fetch: async () => jsonResponse({
      error: {
        code: "repository_conflict",
        message: "数据已被其他操作修改",
        details: { revision: "old" },
        recovery: "重新加载后再提交",
        request_id: "req_1",
      },
    }, 409),
  });
  await assert.rejects(
    request("/api/events/report"),
    (error: unknown) => {
      assert.ok(error instanceof ApiClientError);
      assert.equal(error.status, 409);
      assert.equal(error.code, "repository_conflict");
      assert.deepEqual(error.details, { revision: "old" });
      assert.equal(error.recovery, "重新加载后再提交");
      assert.equal(error.requestId, "req_1");
      return true;
    },
  );
});

test("normalizes legacy text errors", async () => {
  const request = createApiClient({
    fetch: async () => new Response("旧接口错误", { status: 400 }),
  });
  await assert.rejects(
    request("/api/legacy"),
    (error: unknown) => error instanceof ApiClientError
      && error.code === "http_error"
      && error.details.response === "旧接口错误",
  );
});

test("normalizes network failures", async () => {
  const request = createApiClient({
    fetch: async () => { throw new TypeError("connection refused"); },
  });
  await assert.rejects(
    request("/api/health"),
    (error: unknown) => error instanceof ApiClientError
      && error.status === 0
      && error.code === "network_error",
  );
});

test("normalizes timeout but preserves caller cancellation", async () => {
  const waitForAbort: typeof fetch = async (_url, init) => new Promise((_resolve, reject) => {
    // AbortSignal.timeout() 的内部计时器不会保持 Node 事件循环存活；测试需显式
    // 保持事件循环，避免 CI 在 timeout signal 触发前把 pending Promise 取消。
    const keepAlive = setTimeout(() => reject(new Error("abort signal was not received")), 1_000);
    init?.signal?.addEventListener("abort", () => {
      clearTimeout(keepAlive);
      reject(init.signal?.reason);
    }, { once: true });
  });
  const timeoutRequest = createApiClient({ fetch: waitForAbort, timeoutMs: 1 });
  await assert.rejects(
    timeoutRequest("/api/slow"),
    (error: unknown) => error instanceof ApiClientError && error.code === "request_timeout",
  );

  const controller = new AbortController();
  const cancelled = createApiClient({ fetch: waitForAbort })("/api/cancelled", {
    signal: controller.signal,
  });
  controller.abort(new DOMException("caller cancelled", "AbortError"));
  await assert.rejects(
    cancelled,
    (error: unknown) => error instanceof DOMException && error.name === "AbortError",
  );
});

test("returns undefined for 204 response", async () => {
  const request = createApiClient({
    fetch: async () => new Response(null, { status: 204 }),
  });
  assert.equal(await request("/api/empty"), undefined);
});

// ===== P0-2: session token 自动注入 =====

test("P0-2: mutate 请求自动注入 X-Streamer-Session", async () => {
  let received: RequestInit | undefined;
  const request = createApiClient({
    getSessionToken: () => "tok-abc-123",
    fetch: async (_url, init) => {
      received = init;
      return jsonResponse({ ok: true });
    },
  });
  await request("/api/songs/import", { method: "POST", body: { title: "x" } });
  assert.equal(new Headers(received?.headers).get("x-streamer-session"), "tok-abc-123");
});

test("P0-2: GET 请求不注入 X-Streamer-Session（避免噪音）", async () => {
  let received: RequestInit | undefined;
  const request = createApiClient({
    getSessionToken: () => "tok-abc-123",
    fetch: async (_url, init) => {
      received = init;
      return jsonResponse([]);
    },
  });
  await request("/api/songs/list");
  assert.equal(new Headers(received?.headers).get("x-streamer-session"), null);
});

test("P0-2: 未提供 getSessionToken 时 mutate 不注入（dev mode 行为）", async () => {
  let received: RequestInit | undefined;
  const request = createApiClient({
    fetch: async (_url, init) => {
      received = init;
      return jsonResponse({ ok: true });
    },
  });
  await request("/api/songs/import", { method: "POST", body: { title: "x" } });
  assert.equal(new Headers(received?.headers).get("x-streamer-session"), null);
});

test("P0-2: FormData mutate 仍注入 X-Streamer-Session（被 csp 误伤）", async () => {
  let received: RequestInit | undefined;
  const request = createApiClient({
    getSessionToken: () => "tok-abc-123",
    fetch: async (_url, init) => {
      received = init;
      return jsonResponse({ tab_files: [] });
    },
  });
  const form = new FormData();
  form.append("file", new Blob(["x"]), "x.txt");
  await request("/api/tabs", { method: "POST", body: form });
  // FormData 走 multipart，不应强加 content-type，但 session 头必须注入
  assert.equal(new Headers(received?.headers).get("x-streamer-session"), "tok-abc-123");
});
