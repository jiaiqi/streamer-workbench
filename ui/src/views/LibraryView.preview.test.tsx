/// M1.5 试听入口测试
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import LibraryView from "./LibraryView";

const apiRequest = vi.fn();
vi.mock("../api/client", () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
}));

const SONGS_DATA = {
  total: 2, active: 1, draft: 1, trash: 0,
  songs: [
    { id: "song_1", title: "江南", artists: ["林俊杰"], status: "active",
      key: "C", capo: 0, difficulty: "中等", tags: ["流行"], pinyin: "jiang nan",
      tab_files: [], notes: "", lyrics_lrc: "", lyrics_plain: "",
      audio_vocal_path: null, audio_instrumental_path: null, audio_duration_ms: 0 },
    { id: "song_2", title: "十年", artists: ["陈奕迅"], status: "draft",
      key: "G", capo: 2, difficulty: "困难", tags: [], pinyin: "shi nian",
      tab_files: [], notes: "", lyrics_lrc: "", lyrics_plain: "",
      audio_vocal_path: null, audio_instrumental_path: null, audio_duration_ms: 0 },
  ],
};

beforeEach(() => {
  apiRequest.mockReset();
  // 默认返回 2 首歌
  apiRequest.mockImplementation((path: string) => {
    if (path === "/api/songs/list") return Promise.resolve(SONGS_DATA);
    return Promise.resolve({});
  });
});
afterEach(() => cleanup());

describe("LibraryView 试听入口（M1.5）", () => {
  it("网格卡片右上角 ▶ 图标渲染，aria-label 包含歌名", async () => {
    const onPlaySong = vi.fn();
    const { getByTestId } = render(
      <LibraryView dark={false} onStatsChange={() => {}} onPlaySong={onPlaySong} />,
    );
    await waitFor(() => expect(getByTestId("library-play-song_1")).toBeTruthy());
    const btn = getByTestId("library-play-song_1");
    expect(btn.getAttribute("aria-label")).toBe("弹唱 江南");
  });

  it("点 ▶ 图标调 onPlaySong(songId) — 不传 link（M1.5 browse 模式）", async () => {
    const onPlaySong = vi.fn();
    const { getByTestId } = render(
      <LibraryView dark={false} onStatsChange={() => {}} onPlaySong={onPlaySong} />,
    );
    await waitFor(() => expect(getByTestId("library-play-song_2")).toBeTruthy());
    fireEvent.click(getByTestId("library-play-song_2"));
    expect(onPlaySong).toHaveBeenCalledTimes(1);
    expect(onPlaySong).toHaveBeenCalledWith("song_2");
    // 关键：不传第二个 link 参数（M1.5 由 App.tsx 据此区分 browse vs live）
    expect(onPlaySong.mock.calls[0].length).toBe(1);
  });

  it("点 ▶ 不触发卡片展开（事件 stopPropagation）", async () => {
    const onPlaySong = vi.fn();
    const { getByTestId, queryByTestId } = render(
      <LibraryView dark={false} onStatsChange={() => {}} onPlaySong={onPlaySong} />,
    );
    await waitFor(() => expect(getByTestId("library-play-song_1")).toBeTruthy());
    fireEvent.click(getByTestId("library-play-song_1"));
    // 卡片展开后才有 library-preview-* 按钮；点击 ▶ 不应该展开
    expect(queryByTestId("library-preview-song_1")).toBeNull();
    expect(onPlaySong).toHaveBeenCalledTimes(1);
  });

  it("展开卡片后操作列出现「试听」按钮（library-preview-）", async () => {
    const onPlaySong = vi.fn();
    const { getByTestId } = render(
      <LibraryView dark={false} onStatsChange={() => {}} onPlaySong={onPlaySong} />,
    );
    await waitFor(() => expect(getByTestId("library-play-song_1")).toBeTruthy());
    // 展开卡片（点击歌名所在的卡片 body）
    const card = getByTestId("library-play-song_1").closest("div.h-full");
    fireEvent.click(card!);
    await waitFor(() => expect(getByTestId("library-preview-song_1")).toBeTruthy());
    const preview = getByTestId("library-preview-song_1");
    expect(preview.textContent).toContain("试听");
    expect(preview.getAttribute("aria-label")).toBe("试听 江南");
  });

  it("点「试听」按钮调 onPlaySong(songId)", async () => {
    const onPlaySong = vi.fn();
    const { getByTestId } = render(
      <LibraryView dark={false} onStatsChange={() => {}} onPlaySong={onPlaySong} />,
    );
    await waitFor(() => expect(getByTestId("library-play-song_1")).toBeTruthy());
    // 展开
    const card = getByTestId("library-play-song_1").closest("div.h-full");
    fireEvent.click(card!);
    await waitFor(() => expect(getByTestId("library-preview-song_1")).toBeTruthy());
    apiRequest.mockClear();
    onPlaySong.mockClear();
    fireEvent.click(getByTestId("library-preview-song_1"));
    expect(onPlaySong).toHaveBeenCalledTimes(1);
    expect(onPlaySong).toHaveBeenCalledWith("song_1");
    // 不触发任何后端请求
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it("onPlaySong 缺失时 ▶ 与「试听」按钮都不渲染（不影响原有库）", async () => {
    const { queryByTestId, getByTestId } = render(
      <LibraryView dark={false} onStatsChange={() => {}} />,
    );
    await waitFor(() => expect(getByTestId("library-tab-all")).toBeTruthy());
    expect(queryByTestId("library-play-song_1")).toBeNull();
    expect(queryByTestId("library-preview-song_1")).toBeNull();
  });
});
