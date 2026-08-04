/// P0 桌面平台特性首批：useSystemIntegration hook 单元测试。
///
/// 覆盖：
/// - 浏览器模式（无 window.streamer）静默 no-op
/// - subscribe 后 sendPlayerState 被调
/// - queueCount 变化触发重新推
/// - 主进程播控指令：play/pause 改 player.setPlaying；next/prev 弹通知
/// - 卸载时 flush 一次（state 清零）
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render } from "@testing-library/react";
import { useSystemIntegration } from "./useSystemIntegration";
import { PlayerProvider, usePlayer } from "../player/PlayerContext";

function HookConsumer({ opts }: { opts: Parameters<typeof useSystemIntegration>[0] }) {
  useSystemIntegration(opts);
  return null;
}

function PlayerProbe({ onPlayer }: { onPlayer: (p: ReturnType<typeof usePlayer>) => void }) {
  const p = usePlayer();
  onPlayer(p);
  return null;
}

function setupHarness() {
  const sendPlayerState = vi.fn();
  const listeners: Array<(cmd: string) => void> = [];
  const onPlayerControl = vi.fn((cb: (cmd: string) => void) => {
    listeners.push(cb);
    return () => {
      const i = listeners.indexOf(cb);
      if (i >= 0) listeners.splice(i, 1);
    };
  });
  const notify = vi.fn().mockResolvedValue({ ok: true });
  (window as unknown as { streamer: unknown }).streamer = {
    sendPlayerState, onPlayerControl, notify,
  };
  return { sendPlayerState, listeners, notify };
}

beforeEach(() => {
  vi.useFakeTimers();
  (window as unknown as { __liveQueueCount: number }).__liveQueueCount = 0;
  (window as unknown as { streamer: unknown }).streamer = undefined;
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  (window as unknown as { __liveQueueCount: number }).__liveQueueCount = 0;
  (window as unknown as { streamer: unknown }).streamer = undefined;
});

describe("useSystemIntegration", () => {
  it("无 window.streamer（浏览器模式）静默 no-op，不抛错", () => {
    const { unmount } = render(
      <PlayerProvider>
        <HookConsumer opts={{ currentTitle: "x" }} />
      </PlayerProvider>,
    );
    expect(() => unmount()).not.toThrow();
  });

  it("mount 后推一次 state（含 title/artist）", () => {
    const { sendPlayerState } = setupHarness();
    render(
      <PlayerProvider>
        <HookConsumer opts={{ currentTitle: "七里香", currentArtist: "周杰伦" }} />
      </PlayerProvider>,
    );
    expect(sendPlayerState).toHaveBeenCalledTimes(1);
    expect(sendPlayerState.mock.calls[0][0]).toMatchObject({
      isPlaying: false,
      currentTitle: "七里香",
      currentArtist: "周杰伦",
      currentTimeMs: 0,
      durationMs: 0,
      queueCount: 0,
    });
  });

  it("LiveView 推 queueCount → 重新推 state", () => {
    const { sendPlayerState } = setupHarness();
    render(
      <PlayerProvider>
        <HookConsumer opts={{}} />
      </PlayerProvider>,
    );
    expect(sendPlayerState).toHaveBeenCalledTimes(1);
    act(() => {
      (window as unknown as { __liveQueueCount: number }).__liveQueueCount = 3;
      window.dispatchEvent(new Event("live:queueCount"));
    });
    expect(sendPlayerState).toHaveBeenCalledTimes(2);
    expect(sendPlayerState.mock.calls[1][0].queueCount).toBe(3);
  });

  it("主进程播控 play → setPlaying(true)；pause → setPlaying(false)", () => {
    const { listeners } = setupHarness();
    let captured: ReturnType<typeof usePlayer> | null = null;
    render(
      <PlayerProvider>
        <PlayerProbe onPlayer={(p) => { captured = p; }} />
        <HookConsumer opts={{}} />
      </PlayerProvider>,
    );
    expect(listeners).toHaveLength(1);
    act(() => { listeners[0]("play"); });
    expect(captured!.isPlaying).toBe(true);
    act(() => { listeners[0]("pause"); });
    expect(captured!.isPlaying).toBe(false);
  });

  it("主进程播控 next/prev → 弹通知", () => {
    const { listeners, notify } = setupHarness();
    render(
      <PlayerProvider>
        <HookConsumer opts={{}} />
      </PlayerProvider>,
    );
    act(() => { listeners[0]("next"); });
    expect(notify).toHaveBeenCalledWith(expect.objectContaining({ tag: "queue-tip" }));
    act(() => { listeners[0]("prev"); });
    expect(notify).toHaveBeenCalledTimes(2);
  });

  it("卸载时 flush 一次清零 state", () => {
    const { sendPlayerState } = setupHarness();
    const { unmount } = render(
      <PlayerProvider>
        <HookConsumer opts={{ currentTitle: "七里香" }} />
      </PlayerProvider>,
    );
    expect(sendPlayerState).toHaveBeenCalledTimes(1);
    act(() => { unmount(); });
    expect(sendPlayerState).toHaveBeenCalledTimes(2);
    expect(sendPlayerState.mock.calls[1][0]).toMatchObject({
      isPlaying: false,
      currentSongId: null,
      currentTimeMs: 0,
      durationMs: 0,
      queueCount: 0,
    });
  });

  it("相同 state 不重复推（去重）", () => {
    const { sendPlayerState } = setupHarness();
    const { rerender } = render(
      <PlayerProvider>
        <HookConsumer opts={{ currentTitle: "七里香" }} />
      </PlayerProvider>,
    );
    expect(sendPlayerState).toHaveBeenCalledTimes(1);
    // rerender 但依赖没变 → effect 不重跑；保持 1 次
    rerender(
      <PlayerProvider>
        <HookConsumer opts={{ currentTitle: "七里香" }} />
      </PlayerProvider>,
    );
    expect(sendPlayerState).toHaveBeenCalledTimes(1);
  });
});
