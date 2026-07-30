/// SongSourcePicker 测试：三种 source 切换 + artist 输入触发 update。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SongSourcePicker from "./SongSourcePicker";
import type { PosterStore } from "./usePosterStore";

const noop = () => undefined;

function makeFakeStore(initialType: "all_active" | "manual" | "artist" = "all_active"): PosterStore {
  return {
    current: {
      name: "海报",
      song_source: { type: initialType, artists: ["周杰伦", "林俊杰"] },
      selected_song_ids: [],
      grouping: "none",
      sorting: "manual",
      layout_id: "grid-wrap",
      theme_id: "海洋柔光",
      canvas_id: "9:20",
      page_policy: { mode: "legacy-fixed-2" },
      parameters: {},
      export_settings: { format: "png", jpeg_quality: 92, single_page: false, dpi: 144 },
    },
    revision: "",
    status: "idle",
    lastSavedAt: null,
    error: null,
    posters: [],
    refreshList: async () => undefined,
    select: async () => undefined,
    newDraft: noop,
    update: vi.fn(),
    saveNow: async () => null,
    flush: async () => undefined,
    deleteCurrent: async () => undefined,
    cancel: noop,
    resetError: noop,
    isDirty: false,
  } as unknown as PosterStore;
}

let confirmSpy: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
});
afterEach(() => {
  confirmSpy.mockRestore();
  vi.restoreAllMocks();
});

describe("SongSourcePicker", () => {
  it("渲染三个 radio 选项", () => {
    render(<SongSourcePicker store={makeFakeStore()} dark={false} />);
    expect(screen.getAllByRole("radio")).toHaveLength(3);
    expect(screen.getByText("全部已会")).toBeTruthy();
    expect(screen.getByText("手动集合")).toBeTruthy();
    expect(screen.getByText("指定歌手")).toBeTruthy();
  });

  it("点击歌手 radio 触发 update", async () => {
    const store = makeFakeStore();
    const user = userEvent.setup();
    render(<SongSourcePicker store={store} dark={false} />);
    await user.click(screen.getByText("指定歌手"));
    expect(store.update).toHaveBeenCalledWith({
      song_source: expect.objectContaining({ type: "artist" }),
    });
  });

  it("artist 模式下可见歌手输入框", () => {
    render(<SongSourcePicker store={makeFakeStore("artist")} dark={false} />);
    const input = screen.getByPlaceholderText(/周杰伦 \/ 林俊杰/) as HTMLInputElement;
    expect(input).toBeTruthy();
    expect(input.value).toBe("周杰伦 / 林俊杰");
  });

  it("输入框失焦触发 update 并切分歌手", async () => {
    const store = makeFakeStore("artist");
    const user = userEvent.setup();
    render(<SongSourcePicker store={store} dark={false} />);
    const input = screen.getByPlaceholderText(/周杰伦 \/ 林俊杰/);
    await user.clear(input);
    await user.type(input, "陈奕迅/王菲");
    input.blur();
    expect(store.update).toHaveBeenCalledWith({
      song_source: expect.objectContaining({
        type: "artist",
        artists: ["陈奕迅", "王菲"],
      }),
    });
  });

  it("manual 模式下显示说明文字", () => {
    render(<SongSourcePicker store={makeFakeStore("manual")} dark={false} />);
    expect(screen.getByText(/进入歌曲库多选已会歌曲/)).toBeTruthy();
  });
});
