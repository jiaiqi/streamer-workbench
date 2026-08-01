/// R8.0 PlayerBar 单元测试
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render } from "@testing-library/react";
import PlayerBar from "./PlayerBar";

afterEach(() => cleanup());

describe("PlayerBar - 状态", () => {
  it("hasAudio=false 时按钮 disabled", () => {
    const { getByTestId } = render(
      <PlayerBar dark={false} isPlaying={false} currentTimeMs={0}
        totalMs={60000} hasAudio={false} onPlay={() => {}} onPause={() => {}} onSeek={() => {}} />
    );
    const btn = getByTestId("player-bar-play") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("hasAudio=true 时按钮可点", () => {
    const { getByTestId } = render(
      <PlayerBar dark={false} isPlaying={false} currentTimeMs={0}
        totalMs={60000} hasAudio={true} onPlay={() => {}} onPause={() => {}} onSeek={() => {}} />
    );
    const btn = getByTestId("player-bar-play") as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
  });

  it("data-state 反映 hasAudio", () => {
    const { getByTestId } = render(
      <PlayerBar dark={false} isPlaying={false} currentTimeMs={0}
        totalMs={60000} hasAudio={false} onPlay={() => {}} onPause={() => {}} onSeek={() => {}} />
    );
    expect(getByTestId("player-bar").getAttribute("data-state")).toBe("no-audio");
  });
});

describe("PlayerBar - 时间格式", () => {
  it("currentTimeMs=0 totalMs=60000 → 0:00 / 1:00", () => {
    const { getByTestId } = render(
      <PlayerBar dark={false} isPlaying={false} currentTimeMs={0}
        totalMs={60000} hasAudio={true} onPlay={() => {}} onPause={() => {}} onSeek={() => {}} />
    );
    expect(getByTestId("player-bar-time").textContent).toContain("0:00 / 1:00");
  });

  it("currentTimeMs=90000 → 1:30", () => {
    const { getByTestId } = render(
      <PlayerBar dark={false} isPlaying={false} currentTimeMs={90000}
        totalMs={180000} hasAudio={true} onPlay={() => {}} onPause={() => {}} onSeek={() => {}} />
    );
    expect(getByTestId("player-bar-time").textContent).toContain("1:30 / 3:00");
  });
});

describe("PlayerBar - 交互", () => {
  it("点击 play 按钮触发 onPlay（hasAudio=true 时）", () => {
    const onPlay = vi.fn();
    const onPause = vi.fn();
    const { getByTestId } = render(
      <PlayerBar dark={false} isPlaying={false} currentTimeMs={0}
        totalMs={60000} hasAudio={true} onPlay={onPlay} onPause={onPause} onSeek={() => {}} />
    );
    fireEvent.click(getByTestId("player-bar-play"));
    expect(onPlay).toHaveBeenCalledTimes(1);
    expect(onPause).not.toHaveBeenCalled();
  });

  it("isPlaying=true 时点击触发 onPause", () => {
    const onPlay = vi.fn();
    const onPause = vi.fn();
    const { getByTestId } = render(
      <PlayerBar dark={false} isPlaying={true} currentTimeMs={5000}
        totalMs={60000} hasAudio={true} onPlay={onPlay} onPause={onPause} onSeek={() => {}} />
    );
    fireEvent.click(getByTestId("player-bar-play"));
    expect(onPause).toHaveBeenCalledTimes(1);
    expect(onPlay).not.toHaveBeenCalled();
  });

  it("拖动进度条触发 onSeek", () => {
    const onSeek = vi.fn();
    const { getByTestId } = render(
      <PlayerBar dark={false} isPlaying={false} currentTimeMs={0}
        totalMs={60000} hasAudio={true} onPlay={() => {}} onPause={() => {}} onSeek={onSeek} />
    );
    const range = getByTestId("player-bar-progress") as HTMLInputElement;
    fireEvent.change(range, { target: { value: "50" } });
    expect(onSeek).toHaveBeenCalledWith(30000);
  });
});
