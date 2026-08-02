/// M1.2 CommandPalette 全局找歌集成测试
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import CommandPalette from "./CommandPalette";
import type { Command } from "./CommandPalette";

const SAMPLE_SONGS = [
  { id: "song_1", title: "江南", artists: ["林俊杰"], key: "C", status: "active" },
  { id: "song_2", title: "十年", artists: ["陈奕迅"], key: "G", status: "active" },
];

const SAMPLE_COMMANDS: Command[] = [
  { id: "view-library", title: "切换到歌曲库", group: "视图", action: vi.fn() },
];

beforeEach(() => {
  SAMPLE_COMMANDS.forEach(c => { if (vi.isMockFunction(c.action)) c.action.mockReset(); });
});
afterEach(() => cleanup());

describe("CommandPalette - M1.2 全局找歌", () => {
  it("无 songResults 时只显示命令", () => {
    const { queryByText } = render(
      <CommandPalette open={true} onClose={() => {}} commands={SAMPLE_COMMANDS} />
    );
    expect(queryByText("切换到歌曲库")).toBeTruthy();
    expect(queryByText("歌曲")).toBeNull();
  });

  it("有 songResults 时显示「歌曲」分组（与命令并列）", () => {
    const { getByText, queryByText } = render(
      <CommandPalette
        open={true}
        onClose={() => {}}
        commands={SAMPLE_COMMANDS}
        songResults={SAMPLE_SONGS}
        onPickSong={() => {}}
      />
    );
    // 歌曲分组标签
    expect(getByText("歌曲")).toBeTruthy();
    // 歌曲条目（不管 query 都显示 songResults）
    expect(getByText("江南")).toBeTruthy();
    expect(getByText("十年")).toBeTruthy();
    // 命令也在
    expect(queryByText("切换到歌曲库")).toBeTruthy();
  });

  it("点击歌曲条目 → 调 onPickSong(songId) + 关闭 palette", () => {
    const onPickSong = vi.fn();
    const onClose = vi.fn();
    const { getByTestId } = render(
      <CommandPalette
        open={true}
        onClose={onClose}
        commands={SAMPLE_COMMANDS}
        songResults={SAMPLE_SONGS}
        onPickSong={onPickSong}
      />
    );
    fireEvent.click(getByTestId("command-song-song_1"));
    expect(onPickSong).toHaveBeenCalledWith("song_1");
    expect(onClose).toHaveBeenCalled();
  });

  it("空 songResults 时不显示「歌曲」分组", () => {
    const { queryByText } = render(
      <CommandPalette
        open={true}
        onClose={() => {}}
        commands={SAMPLE_COMMANDS}
        songResults={[]}
        onPickSong={() => {}}
      />
    );
    expect(queryByText("歌曲")).toBeNull();
  });

  it("受控 query 模式：onQueryChange 回调触发", () => {
    const onQueryChange = vi.fn();
    const { getByTestId } = render(
      <CommandPalette
        open={true}
        onClose={() => {}}
        commands={SAMPLE_COMMANDS}
        songResults={[]}
        onPickSong={() => {}}
        query=""
        onQueryChange={onQueryChange}
      />
    );
    fireEvent.change(getByTestId("command-palette-input"), { target: { value: "江南" } });
    expect(onQueryChange).toHaveBeenCalledWith("江南");
  });
});
