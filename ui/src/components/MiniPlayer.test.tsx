/// M1.4 MiniPlayer 测试
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render } from "@testing-library/react";
import MiniPlayer from "./MiniPlayer";
import { PlayerProvider, usePlayer, type PlayerMode } from "../player/PlayerContext";

afterEach(() => cleanup());

function renderWithProvider(ui: React.ReactNode) {
  return render(<PlayerProvider>{ui}</PlayerProvider>);
}

describe("MiniPlayer", () => {
  it("currentSongId=null 时不渲染", () => {
    const { queryByTestId } = renderWithProvider(
      <MiniPlayer currentTitle="江南" onOpen={() => {}} onClose={() => {}} dark={false} />,
    );
    expect(queryByTestId("mini-player")).toBeNull();
  });

  it("hidden=true 时强制不渲染（即使 currentSongId 已设）", () => {
    function Wrapper() {
      const player = usePlayer();
      player.setCurrent("song_1", "browse");
      return <MiniPlayer currentTitle="江南" onOpen={() => {}} onClose={() => {}} dark={false} hidden />;
    }
    const { queryByTestId } = renderWithProvider(<Wrapper />);
    expect(queryByTestId("mini-player")).toBeNull();
  });

  it("currentSongId 设置后渲染：模式徽章 + 歌名 + 时间 + 两个按钮", () => {
    function Wrapper() {
      const player = usePlayer();
      player.setCurrent("song_1", "browse");
      return <MiniPlayer currentTitle="江南" onOpen={() => {}} onClose={() => {}} dark={false} />;
    }
    const { getByTestId } = renderWithProvider(<Wrapper />);
    expect(getByTestId("mini-player")).toBeTruthy();
    expect(getByTestId("mini-player").getAttribute("data-mode")).toBe("browse");
    expect(getByTestId("mini-player-mode").textContent).toBe("试听");
    expect(getByTestId("mini-player-title").textContent).toBe("江南");
    expect(getByTestId("mini-player-time").textContent).toBe("00:00");
    expect(getByTestId("mini-player-open")).toBeTruthy();
    expect(getByTestId("mini-player-close")).toBeTruthy();
  });

  it("currentTitle 为 null 时显示「未命名歌曲」fallback", () => {
    function Wrapper() {
      const player = usePlayer();
      player.setCurrent("song_x", "live");
      return <MiniPlayer currentTitle={null} onOpen={() => {}} onClose={() => {}} dark={true} />;
    }
    const { getByTestId } = renderWithProvider(<Wrapper />);
    expect(getByTestId("mini-player-title").textContent).toBe("未命名歌曲");
    expect(getByTestId("mini-player-mode").textContent).toBe("联播");
  });

  it("3 种模式徽章文案正确（live/practice/browse）", () => {
    function WithMode({ m }: { m: PlayerMode }) {
      const player = usePlayer();
      player.setCurrent("song_1", m);
      return <MiniPlayer currentTitle="X" onOpen={() => {}} onClose={() => {}} dark={false} />;
    }
    const labels: [PlayerMode, string][] = [
      ["live", "联播"],
      ["practice", "练习"],
      ["browse", "试听"],
    ];
    for (const [mode, label] of labels) {
      const { getByTestId, unmount } = renderWithProvider(<WithMode m={mode} />);
      expect(getByTestId("mini-player-mode").textContent).toBe(label);
      unmount();
    }
  });

  it("currentTimeMs > 0 时显示 mm:ss", () => {
    function Wrapper() {
      const player = usePlayer();
      player.setCurrent("song_1", "browse");
      player.setCurrentTime(65 * 1000 + 500);  // 1:05
      return <MiniPlayer currentTitle="江南" onOpen={() => {}} onClose={() => {}} dark={false} />;
    }
    const { getByTestId } = renderWithProvider(<Wrapper />);
    expect(getByTestId("mini-player-time").textContent).toBe("01:05");
  });

  it("点「打开弹唱 →」调 onOpen", () => {
    const onOpen = vi.fn();
    function Wrapper() {
      const player = usePlayer();
      player.setCurrent("song_1", "browse");
      return <MiniPlayer currentTitle="江南" onOpen={onOpen} onClose={() => {}} dark={false} />;
    }
    const { getByTestId } = renderWithProvider(<Wrapper />);
    fireEvent.click(getByTestId("mini-player-open"));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it("点 ✕ 调 onClose（调用方负责清 PlayerContext + 切视图）", () => {
    const onClose = vi.fn();
    function Wrapper() {
      const player = usePlayer();
      player.setCurrent("song_1", "browse");
      return <MiniPlayer currentTitle="江南" onOpen={() => {}} onClose={onClose} dark={false} />;
    }
    const { getByTestId } = renderWithProvider(<Wrapper />);
    fireEvent.click(getByTestId("mini-player-close"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("dark 模式：背景色类含 bg-zinc-900/90", () => {
    function Wrapper() {
      const player = usePlayer();
      player.setCurrent("song_1", "browse");
      return <MiniPlayer currentTitle="江南" onOpen={() => {}} onClose={() => {}} dark={true} />;
    }
    const { getByTestId } = renderWithProvider(<Wrapper />);
    expect(getByTestId("mini-player").className).toContain("bg-zinc-900/90");
  });
});
