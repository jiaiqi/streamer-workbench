/// PostersSidebar 单元测试：覆盖「新建」/「选中」/「删除确认」。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PostersSidebar from "./PostersSidebar";
import type { PosterStore } from "./usePosterStore";

function makeFakeStore(overrides: Partial<PosterStore> = {}): PosterStore {
  const noop = () => undefined;
  return {
    current: {
      name: "我的第一张",
      song_source: { type: "all_active", artists: [] },
      selected_song_ids: [],
      grouping: "none",
      sorting: "manual",
      layout_id: "grid-wrap",
      theme_id: "海洋柔光",
      canvas_id: "9:20",
      page_policy: { mode: "legacy-fixed-2" },
      parameters: {},
      export_settings: {
        format: "png", jpeg_quality: 92, single_page: false, dpi: 144,
      },
    },
    revision: "",
    status: "idle",
    lastSavedAt: null,
    error: null,
    posters: [
      {
        id: "poster_1", name: "已保存1", layout_id: "grid-wrap",
        theme_id: "海洋柔光", canvas_id: "9:20",
        created_at: "2026-07-30T00:00:00", updated_at: "2026-07-30T00:00:00",
        song_count: 12,
      },
      {
        id: "poster_2", name: "已保存2", layout_id: "grid-wrap",
        theme_id: "海洋柔光", canvas_id: "9:20",
        created_at: "2026-07-30T00:00:00", updated_at: "2026-07-30T00:00:00",
        song_count: 7,
      },
    ],
    refreshList: vi.fn(async () => undefined),
    select: vi.fn(async () => undefined),
    newDraft: vi.fn(noop),
    update: vi.fn(noop),
    saveNow: vi.fn(async () => null),
    flush: vi.fn(async () => undefined),
    deleteCurrent: vi.fn(async () => undefined),
    cancel: vi.fn(noop),
    resetError: vi.fn(noop),
    isDirty: false,
    ...overrides,
  } as unknown as PosterStore;
}

let confirmSpy: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
});
afterEach(() => {
  confirmSpy.mockRestore();
});

describe("PostersSidebar", () => {
  it("显示当前海报名称", () => {
    render(<PostersSidebar store={makeFakeStore()} dark={false} />);
    expect(screen.getByText("我的第一张")).toBeTruthy();
  });

  it("显示已保存的海报列表（来自 store.posters）", () => {
    render(<PostersSidebar store={makeFakeStore()} dark={false} />);
    expect(screen.getByText("已保存1")).toBeTruthy();
    expect(screen.getByText("已保存2")).toBeTruthy();
  });

  it("新建按钮调用 newDraft", async () => {
    const store = makeFakeStore();
    const user = userEvent.setup();
    render(<PostersSidebar store={store} dark={false} />);
    await user.click(screen.getByRole("button", { name: /新建/ }));
    // 我们的 spy 应被调一次
    expect(store.newDraft).toHaveBeenCalledTimes(1);
  });

  it("点击列表项触发 select(id)", async () => {
    const store = makeFakeStore();
    const user = userEvent.setup();
    render(<PostersSidebar store={store} dark={false} />);
    await user.click(screen.getByText("已保存1"));
    expect(store.select).toHaveBeenCalledWith("poster_1");
  });

  it("current.id 为空时不显示删除按钮", () => {
    render(<PostersSidebar store={makeFakeStore({ revision: "" })} dark={false} />);
    expect(screen.queryByRole("button", { name: "删除当前" })).toBeNull();
  });

  it("current.id 存在时显示删除按钮 + 确认弹窗", async () => {
    const store = makeFakeStore({
      current: { ...makeFakeStore().current, id: "poster_cur" },
    });
    const user = userEvent.setup();
    render(<PostersSidebar store={store} dark={false} />);
    await user.click(screen.getByRole("button", { name: "删除当前" }));
    expect(window.confirm).toHaveBeenCalled();
    expect(store.deleteCurrent).toHaveBeenCalledTimes(1);
  });

  it("error 态显示重试按钮", async () => {
    const store = makeFakeStore({
      status: "error",
      error: { message: "网络中断", recovery: "重试" },
    });
    const user = userEvent.setup();
    render(<PostersSidebar store={store} dark={false} />);
    await user.click(screen.getByRole("button", { name: "重试" }));
    expect(store.saveNow).toHaveBeenCalledTimes(1);
  });
});
