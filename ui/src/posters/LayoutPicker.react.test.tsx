/// LayoutPicker 测试：两种布局切换 + magazine-flow 自动切 page_policy。
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LayoutPicker from "./LayoutPicker";
import type { PosterStore } from "./usePosterStore";

function makeStore(layout: "grid-wrap" | "magazine-flow" = "grid-wrap"): PosterStore {
  return {
    current: {
      name: "doc",
      song_source: { type: "all_active", artists: [] },
      selected_song_ids: [],
      grouping: "none",
      sorting: "manual",
      layout_id: layout,
      theme_id: "海洋柔光",
      canvas_id: "9:20",
      page_policy: layout === "grid-wrap"
        ? { mode: "legacy-fixed-2" }
        : { mode: "auto", min_pages: 1, max_pages: 8 },
      parameters: {},
      export_settings: { format: "png", jpeg_quality: 92, single_page: false, dpi: 144 },
    },
    revision: "",
    status: "idle",
    lastSavedAt: null,
    error: null,
    posters: [],
    refreshList: vi.fn(async () => undefined),
    select: vi.fn(async () => undefined),
    newDraft: vi.fn(),
    update: vi.fn(),
    saveNow: vi.fn(async () => null),
    flush: vi.fn(async () => undefined),
    deleteCurrent: vi.fn(async () => undefined),
    cancel: vi.fn(),
    resetError: vi.fn(),
    isDirty: false,
  } as unknown as PosterStore;
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("LayoutPicker", () => {
  it("渲染两个布局按钮", () => {
    render(<LayoutPicker store={makeStore()} />);
    expect(screen.getAllByRole("radio")).toHaveLength(2);
    expect(screen.getByText("网格")).toBeTruthy();
    expect(screen.getByText("刊头")).toBeTruthy();
  });

  it("grid-wrap 当前为 active", () => {
    render(<LayoutPicker store={makeStore("grid-wrap")} />);
    const buttons = screen.getAllByRole("radio");
    expect(buttons[0].getAttribute("aria-checked")).toBe("true");
    expect(buttons[1].getAttribute("aria-checked")).toBe("false");
  });

  it("点击 magazine-flow 触发 update 并自动切 page_policy=auto", async () => {
    const store = makeStore("grid-wrap");
    const user = userEvent.setup();
    render(<LayoutPicker store={store} />);
    await user.click(screen.getByText("刊头"));
    expect(store.update).toHaveBeenCalledWith({
      layout_id: "magazine-flow",
      page_policy: { mode: "auto", min_pages: 1, max_pages: 8 },
    });
  });

  it("点击 grid-wrap 触发 update 并恢复 page_policy=legacy-fixed-2", async () => {
    const store = makeStore("magazine-flow");
    const user = userEvent.setup();
    render(<LayoutPicker store={store} />);
    await user.click(screen.getByText("网格"));
    expect(store.update).toHaveBeenCalledWith({
      layout_id: "grid-wrap",
      page_policy: { mode: "legacy-fixed-2" },
    });
  });

  it("点击当前已选 layout 不触发 update", async () => {
    const store = makeStore("grid-wrap");
    const user = userEvent.setup();
    render(<LayoutPicker store={store} />);
    await user.click(screen.getByText("网格"));
    expect(store.update).not.toHaveBeenCalled();
  });

  it("saving 态时禁用按钮", () => {
    const store = { ...makeStore(), status: "saving" } as PosterStore;
    render(<LayoutPicker store={store} />);
    const buttons = screen.getAllByRole("radio");
    expect((buttons[0] as HTMLButtonElement).disabled).toBe(true);
  });
});
