/// R4 退出条件 #2: 草稿/手动分页 UI V3 测试。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import PagesPanel from "./PagesPanel";

const PANEL = "pages-panel";
const ADD = "pages-add";
const MODE = "pages-mode";
const ERROR = "pages-error";
const HINT = "pages-disabled-hint";
const EMPTY = "pages-empty-hint";
const THUMB = (i: number) => `pages-thumb-${i}`;
const UP = (i: number) => `pages-up-${i}`;
const DOWN = (i: number) => `pages-down-${i}`;
const DELETE = (i: number) => `pages-delete-${i}`;

const POSTER_ID = "poster_xyz";

function makeFetchSpy(extra: {
  items?: Array<Record<string, unknown>>;
  mode?: "manual" | "auto" | "legacy-fixed-2";
} = {}) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : (input as URL).toString();
    const method = init?.method ?? "GET";
    if (url.endsWith(`/api/posters/${POSTER_ID}/pages`)) {
      if (method === "GET") {
        return new Response(JSON.stringify({
          items: extra.items ?? [],
          mode: extra.mode ?? "auto",
        }), { status: 200, headers: { "content-type": "application/json" } });
      }
      if (method === "POST") {
        // 追加空页
        const newItems = [...(extra.items ?? []), {}];
        return new Response(JSON.stringify({ items: newItems, mode: "manual" }),
          { status: 200, headers: { "content-type": "application/json" } });
      }
      if (method === "PATCH") {
        const body = JSON.parse((init?.body as string) || "{}");
        const order: number[] = body.new_order;
        const newItems = order.map((i: number) => (extra.items ?? [])[i] ?? {});
        return new Response(JSON.stringify({ items: newItems, mode: "manual" }),
          { status: 200, headers: { "content-type": "application/json" } });
      }
    }
    const m = url.match(new RegExp(`/api/posters/${POSTER_ID}/pages/(\\d+)`));
    if (m && method === "DELETE") {
      const idx = parseInt(m[1], 10);
      const newItems = (extra.items ?? []).filter((_, i) => i !== idx);
      const newMode = newItems.length === 0 ? "auto" : "manual";
      return new Response(JSON.stringify({ items: newItems, mode: newMode }),
        { status: 200, headers: { "content-type": "application/json" } });
    }
    return new Response("{}", { status: 200 });
  });
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("PagesPanel 不支持手动分页的 layout", () => {
  it("grid-wrap 显示灰显提示", () => {
    globalThis.fetch = makeFetchSpy() as unknown as typeof fetch;
    render(
      <PagesPanel
        posterId={POSTER_ID}
        layoutId="grid-wrap"
        supportsManualPages={false}
        dark={false}
      />,
    );
    expect(screen.getByTestId(PANEL)).toBeTruthy();
    expect(screen.getByTestId(HINT).textContent).toContain("grid-wrap");
    expect(screen.queryByTestId(ADD)).toBeNull();  // 无添加按钮
  });
});

describe("PagesPanel 支持手动分页的 layout（magazine-flow）", () => {
  it("空列表显示「暂无手动页」+ 添加按钮", async () => {
    globalThis.fetch = makeFetchSpy() as unknown as typeof fetch;
    render(
      <PagesPanel
        posterId={POSTER_ID}
        layoutId="magazine-flow"
        supportsManualPages={true}
        dark={false}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId(EMPTY)).toBeTruthy();
    });
    expect(screen.getByTestId(ADD)).toBeTruthy();
    expect(screen.getByTestId(MODE).textContent).toBe("自动");
  });

  it("点击添加按钮追加一页 + mode 切到 manual", async () => {
    globalThis.fetch = makeFetchSpy() as unknown as typeof fetch;
    render(
      <PagesPanel
        posterId={POSTER_ID}
        layoutId="magazine-flow"
        supportsManualPages={true}
        dark={false}
      />,
    );
    await waitFor(() => expect(screen.getByTestId(EMPTY)).toBeTruthy());
    fireEvent.click(screen.getByTestId(ADD));
    await waitFor(() => {
      expect(screen.getByTestId(THUMB(0))).toBeTruthy();
    });
    expect(screen.getByTestId(MODE).textContent).toBe("手动");
  });

  it("有 3 页时，删除 index=1 后剩 2 页", async () => {
    globalThis.fetch = makeFetchSpy({ items: [{}, {}, {}] }) as unknown as typeof fetch;
    render(
      <PagesPanel
        posterId={POSTER_ID}
        layoutId="magazine-flow"
        supportsManualPages={true}
        dark={false}
      />,
    );
    await waitFor(() => expect(screen.getByTestId(THUMB(2))).toBeTruthy());
    fireEvent.click(screen.getByTestId(DELETE(1)));
    await waitFor(() => {
      expect(screen.queryByTestId(THUMB(2))).toBeNull();  // 索引重排
    });
    // 此时剩 2 页：index 0, 1
    expect(screen.getByTestId(THUMB(0))).toBeTruthy();
    expect(screen.getByTestId(THUMB(1))).toBeTruthy();
  });

  it("up 按钮在最首页禁用，down 按钮在最后页禁用", async () => {
    globalThis.fetch = makeFetchSpy({ items: [{}, {}, {}] }) as unknown as typeof fetch;
    render(
      <PagesPanel
        posterId={POSTER_ID}
        layoutId="magazine-flow"
        supportsManualPages={true}
        dark={false}
      />,
    );
    await waitFor(() => expect(screen.getByTestId(THUMB(2))).toBeTruthy());
    // index 0 的 up 禁用
    expect((screen.getByTestId(UP(0)) as HTMLButtonElement).disabled).toBe(true);
    // index 0 的 down 启用
    expect((screen.getByTestId(DOWN(0)) as HTMLButtonElement).disabled).toBe(false);
    // index 2 的 down 禁用
    expect((screen.getByTestId(DOWN(2)) as HTMLButtonElement).disabled).toBe(true);
  });

  it("down 按钮触发 reorder API", async () => {
    globalThis.fetch = makeFetchSpy({ items: [{}, {}, {}] }) as unknown as typeof fetch;
    render(
      <PagesPanel
        posterId={POSTER_ID}
        layoutId="magazine-flow"
        supportsManualPages={true}
        dark={false}
      />,
    );
    await waitFor(() => expect(screen.getByTestId(THUMB(2))).toBeTruthy());
    fireEvent.click(screen.getByTestId(DOWN(0)));  // 把第 0 页下移
    // fetchSpy 收到 PATCH /api/posters/{id}/pages with new_order=[1,0,2]
    await waitFor(() => {
      const calls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls;
      const patchCall = calls.find((call: unknown[]) => {
        const [url, init] = call as [string, RequestInit];
        return url.endsWith("/pages") && init?.method === "PATCH";
      });
      expect(patchCall).toBeTruthy();
      const [, patchInit] = patchCall as unknown[];
      const body = JSON.parse((patchInit as RequestInit).body as string);
      expect(body.new_order).toEqual([1, 0, 2]);
    });
  });

  it("API 错误显示错误条", async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response("err", { status: 500 }),
    ) as unknown as typeof fetch;
    render(
      <PagesPanel
        posterId={POSTER_ID}
        layoutId="magazine-flow"
        supportsManualPages={true}
        dark={false}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId(ERROR).textContent).toContain("失败");
    });
  });
});
