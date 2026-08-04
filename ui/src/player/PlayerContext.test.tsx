/// M1.3 PlayerContext 测试
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, renderHook, act } from "@testing-library/react";
import { PlayerProvider, usePlayer } from "./PlayerContext";

afterEach(() => cleanup());

describe("PlayerContext", () => {
  it("初始状态：currentSongId=null / mode=browse / isPlaying=false / currentTimeMs=0", () => {
    const { result } = renderHook(() => usePlayer(), { wrapper: PlayerProvider });
    expect(result.current.currentSongId).toBeNull();
    expect(result.current.mode).toBe("browse");
    expect(result.current.isPlaying).toBe(false);
    expect(result.current.currentTimeMs).toBe(0);
  });

  it("setCurrent(songId) 更新 currentSongId + 重置 isPlaying / currentTimeMs", () => {
    const { result } = renderHook(() => usePlayer(), { wrapper: PlayerProvider });
    act(() => { result.current.setPlaying(true); result.current.setCurrentTime(30000); });
    act(() => { result.current.setCurrent("song_1"); });
    expect(result.current.currentSongId).toBe("song_1");
    expect(result.current.isPlaying).toBe(false);
    expect(result.current.currentTimeMs).toBe(0);
  });

  it("setCurrent(songId, mode) 同时切歌 + 切模式", () => {
    const { result } = renderHook(() => usePlayer(), { wrapper: PlayerProvider });
    act(() => { result.current.setCurrent("song_1", "live"); });
    expect(result.current.currentSongId).toBe("song_1");
    expect(result.current.mode).toBe("live");
  });

  it("setMode 切换场景（live ↔ practice ↔ browse）", () => {
    const { result } = renderHook(() => usePlayer(), { wrapper: PlayerProvider });
    act(() => { result.current.setMode("live"); });
    expect(result.current.mode).toBe("live");
    act(() => { result.current.setMode("practice"); });
    expect(result.current.mode).toBe("practice");
    act(() => { result.current.setMode("browse"); });
    expect(result.current.mode).toBe("browse");
  });

  it("setPlaying(true) 标记播放中", () => {
    const { result } = renderHook(() => usePlayer(), { wrapper: PlayerProvider });
    act(() => { result.current.setPlaying(true); });
    expect(result.current.isPlaying).toBe(true);
  });

  it("setCurrentTime(ms) 更新进度", () => {
    const { result } = renderHook(() => usePlayer(), { wrapper: PlayerProvider });
    act(() => { result.current.setCurrentTime(12345); });
    expect(result.current.currentTimeMs).toBe(12345);
  });

  it("Provider 包裹外的 usePlayer 降级为 no-op（不抛）", () => {
    // P0 桌面集成后变更：usePlayer 在无 Provider 时返回 NOOP_PLAYER，
    // 让 PlayView 等单测不必强制包 Provider。生产环境 App 顶层包了 Provider。
    const { result } = renderHook(() => usePlayer());
    expect(result.current.currentSongId).toBeNull();
    expect(result.current.isPlaying).toBe(false);
    // setCurrent 等是 no-op，不抛
    expect(() => result.current.setCurrent("s1")).not.toThrow();
  });

  it("Provider 包裹下：多个组件共享同一 state", () => {
    function Reader({ id }: { id: string }) {
      const p = usePlayer();
      return <div data-testid={`reader-${id}`}>{p.currentSongId ?? "none"}</div>;
    }
    function Controller() {
      const p = usePlayer();
      return <button data-testid="controller" onClick={() => p.setCurrent("song_X")}>set</button>;
    }
    const { getByTestId } = render(
      <PlayerProvider>
        <Reader id="a" />
        <Reader id="b" />
        <Controller />
      </PlayerProvider>,
    );
    expect(getByTestId("reader-a").textContent).toBe("none");
    expect(getByTestId("reader-b").textContent).toBe("none");
    act(() => { getByTestId("controller").click(); });
    expect(getByTestId("reader-a").textContent).toBe("song_X");
    expect(getByTestId("reader-b").textContent).toBe("song_X");
  });
});
