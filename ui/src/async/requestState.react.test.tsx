import { useRef } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import SongEditDialog from "../components/SongEditDialog";
import { useLatestRequest } from "./requestState";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

function RequestProbe({ requests }: { requests: Array<(signal: AbortSignal) => Promise<string>> }) {
  const index = useRef(0);
  const request = useLatestRequest<string>({ isEmpty: value => value.length === 0 });
  return (
    <div>
      <output aria-label="status">{request.status}</output>
      <output aria-label="data">{request.data ?? "—"}</output>
      {request.error && <div role="alert">{request.error.message}</div>}
      <button onClick={() => request.run(signal => requests[index.current++](signal))}>加载</button>
      <button onClick={request.cancel}>取消</button>
    </div>
  );
}

describe("useLatestRequest interaction contract", () => {
  it("moves from loading to success", async () => {
    const pending = deferred<string>();
    render(<RequestProbe requests={[() => pending.promise]} />);
    fireEvent.click(screen.getByRole("button", { name: "加载" }));
    expect(screen.getByLabelText("status").textContent).toBe("loading");
    pending.resolve("新歌单");
    await waitFor(() => expect(screen.getByLabelText("status").textContent).toBe("success"));
    expect(screen.getByLabelText("data").textContent).toBe("新歌单");
  });

  it("shows an error and succeeds after retry", async () => {
    render(<RequestProbe requests={[() => Promise.reject(new Error("服务暂不可用")), () => Promise.resolve("已恢复")]} />);
    fireEvent.click(screen.getByRole("button", { name: "加载" }));
    expect((await screen.findByRole("alert")).textContent).toContain("服务暂不可用");
    fireEvent.click(screen.getByRole("button", { name: "加载" }));
    await waitFor(() => expect(screen.getByLabelText("data").textContent).toBe("已恢复"));
  });

  it("does not let an older request overwrite a newer result", async () => {
    const oldRequest = deferred<string>();
    const newRequest = deferred<string>();
    render(<RequestProbe requests={[() => oldRequest.promise, () => newRequest.promise]} />);
    const button = screen.getByRole("button", { name: "加载" });
    fireEvent.click(button);
    fireEvent.click(button);
    newRequest.resolve("新版");
    await waitFor(() => expect(screen.getByLabelText("data").textContent).toBe("新版"));
    oldRequest.resolve("旧版");
    await Promise.resolve();
    expect(screen.getByLabelText("data").textContent).toBe("新版");
  });

  it("treats cancellation as idle instead of an error", async () => {
    render(<RequestProbe requests={[signal => new Promise((_resolve, reject) => {
      signal.addEventListener("abort", () => reject(new DOMException("cancelled", "AbortError")), { once: true });
    })]} />);
    fireEvent.click(screen.getByRole("button", { name: "加载" }));
    expect(screen.getByLabelText("status").textContent).toBe("loading");
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    await waitFor(() => expect(screen.getByLabelText("status").textContent).toBe("idle"));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("restores empty when a refresh of existing empty data is cancelled", async () => {
    render(<RequestProbe requests={[
      () => Promise.resolve(""),
      signal => new Promise((_resolve, reject) => {
        signal.addEventListener("abort", () => reject(new DOMException("cancelled", "AbortError")), { once: true });
      }),
    ]} />);
    const load = screen.getByRole("button", { name: "加载" });
    fireEvent.click(load);
    await waitFor(() => expect(screen.getByLabelText("status").textContent).toBe("empty"));
    fireEvent.click(load);
    expect(screen.getByLabelText("status").textContent).toBe("loading");
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    await waitFor(() => expect(screen.getByLabelText("status").textContent).toBe("empty"));
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("SongEditDialog write feedback", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows a structured write error and restores the save button", async () => {
    const response = deferred<Response>();
    vi.stubGlobal("fetch", vi.fn(() => response.promise));
    const user = userEvent.setup();
    render(<SongEditDialog target="new" onClose={vi.fn()} onSaved={vi.fn(async () => {})} />);
    await user.type(screen.getByLabelText(/歌名/), "晴天");
    await user.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect((screen.getByRole("button", { name: "保存中…" }) as HTMLButtonElement).disabled).toBe(true));
    response.resolve(new Response(JSON.stringify({ error: { code: "write_failed", message: "保存被拒绝", recovery: "检查数据后重试", request_id: "req-test" } }), {
      status: 409,
      headers: { "content-type": "application/json" },
    }));
    expect((await screen.findByRole("alert")).textContent).toContain("保存被拒绝 · 检查数据后重试 · 请求编号：req-test");
    expect((screen.getByRole("button", { name: "保存" }) as HTMLButtonElement).disabled).toBe(false);
  });
});
