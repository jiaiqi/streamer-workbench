/// P1-A1.2: ReadinessBadge 组件单测（5 个 spec）。
///
/// 覆盖：
/// 1. 4 枚徽章渲染（data-testid 各自命中）
/// 2. 全齐：data-ready-count=4 + 4 枚全部 data-ready=true
/// 3. 全空：data-ready-count=0 + 4 枚全部 data-ready=false
/// 4. 半空（缺 2 项）：data-ready-count=2 + 准确 2 枚 ready
/// 5. undefined 字段防御（与 evaluateReadiness 行为一致）
/// 6. size='sm' 不报错且渲染更大字号
/// 7. role + aria-label 正确（无障碍）
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import ReadinessBadge from "./ReadinessBadge";

afterEach(() => cleanup());

const fullSong = {
  tabs: "[Verse]\nC G",
  lyrics_plain: "副歌歌词",
  lyrics_lrc: "[00:01.00]副歌歌词",
  audio_vocal_path: "/data/audio/song_full/vocal.m4a",
  key: "C",
};

const emptySong = {
  tabs: "",
  lyrics_plain: "",
  lyrics_lrc: "",
  audio_vocal_path: null,
  key: "",
};

describe("ReadinessBadge", () => {
  it("渲染 4 枚徽章（data-testid 各自命中）", () => {
    render(<ReadinessBadge song={fullSong} dark={false} />);
    expect(screen.getByTestId("readiness-badge")).toBeTruthy();
    expect(screen.getByTestId("readiness-chip-tabs")).toBeTruthy();
    expect(screen.getByTestId("readiness-chip-lyrics")).toBeTruthy();
    expect(screen.getByTestId("readiness-chip-audio")).toBeTruthy();
    expect(screen.getByTestId("readiness-chip-key")).toBeTruthy();
  });

  it("全齐：data-ready-count=4 + 4 枚全部 data-ready=true", () => {
    render(<ReadinessBadge song={fullSong} dark={false} />);
    const badge = screen.getByTestId("readiness-badge");
    expect(badge.getAttribute("data-ready-count")).toBe("4");
    expect(badge.getAttribute("data-total-count")).toBe("4");
    for (const f of ["tabs", "lyrics", "audio", "key"]) {
      expect(screen.getByTestId(`readiness-chip-${f}`).getAttribute("data-ready")).toBe("true");
    }
  });

  it("全空：data-ready-count=0 + 4 枚全部 data-ready=false", () => {
    render(<ReadinessBadge song={emptySong} dark={false} />);
    const badge = screen.getByTestId("readiness-badge");
    expect(badge.getAttribute("data-ready-count")).toBe("0");
    for (const f of ["tabs", "lyrics", "audio", "key"]) {
      expect(screen.getByTestId(`readiness-chip-${f}`).getAttribute("data-ready")).toBe("false");
    }
  });

  it("半空（缺 tabs + audio）→ data-ready-count=2 + 准确 2 枚 ready", () => {
    render(
      <ReadinessBadge
        song={{ ...fullSong, tabs: "", audio_vocal_path: null }}
        dark={false}
      />,
    );
    const badge = screen.getByTestId("readiness-badge");
    expect(badge.getAttribute("data-ready-count")).toBe("2");
    expect(screen.getByTestId("readiness-chip-tabs").getAttribute("data-ready")).toBe("false");
    expect(screen.getByTestId("readiness-chip-lyrics").getAttribute("data-ready")).toBe("true");
    expect(screen.getByTestId("readiness-chip-audio").getAttribute("data-ready")).toBe("false");
    expect(screen.getByTestId("readiness-chip-key").getAttribute("data-ready")).toBe("true");
  });

  it("undefined 字段防御（与 evaluateReadiness 行为一致）", () => {
    // 故意不传任何字段 → 应等同于全空
    render(<ReadinessBadge song={{}} dark={false} />);
    const badge = screen.getByTestId("readiness-badge");
    expect(badge.getAttribute("data-ready-count")).toBe("0");
    for (const f of ["tabs", "lyrics", "audio", "key"]) {
      expect(screen.getByTestId(`readiness-chip-${f}`).getAttribute("data-ready")).toBe("false");
    }
  });

  it("size='sm' 也能渲染不报错", () => {
    render(<ReadinessBadge song={fullSong} size="sm" dark={true} />);
    expect(screen.getByTestId("readiness-badge")).toBeTruthy();
  });

  it("role + aria-label 正确（无障碍）", () => {
    render(<ReadinessBadge song={fullSong} dark={false} />);
    const badge = screen.getByTestId("readiness-badge");
    expect(badge.getAttribute("role")).toBe("group");
    expect(badge.getAttribute("aria-label")).toBe("就绪度 4 / 4");
  });

  it("暗色模式：缺失徽章不报错（line-through + 灰文字）", () => {
    render(<ReadinessBadge song={emptySong} dark={true} />);
    const chip = screen.getByTestId("readiness-chip-tabs");
    expect(chip.className).toContain("text-zinc-500");
    expect(chip.className).toContain("line-through");
  });
});
