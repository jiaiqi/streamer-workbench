/// TheoryHelper 测试 — 回归 R3 时代埋的 isHover 块作用域 bug
///
/// 背景（M2.13 验收时复现）：
/// R3 提交 TheoryHelper 时，`{isHover && ...}` 里的 isHover 是在 KEYS.map(k => {...})
/// 块作用域内定义的 const，但引用点 94 行在 map 外面，导致组件 mount 时直接 ReferenceError，
/// 整个学歌视图白屏。该 bug 一直没被测出来是因为：所有测试都没触发 mouseEnter，
/// 渲染早期阶段 setState hoverKey=null，所以引用点之前 map 内没实例化分支。
///
/// 本测试覆盖：
/// 1. mount 不抛错（直接 fix 后通过；旧代码会 ReferenceError）
/// 2. 12 个调性按钮全部渲染
/// 3. 选中态高亮：通过 selectedKey 触发 activeKey
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import TheoryHelper from "./TheoryHelper";

afterEach(() => cleanup());

describe("TheoryHelper", () => {
  it("mount 不抛错（防 isHover 块作用域 bug 回归）", () => {
    // 旧代码会在这一行 ReferenceError: isHover is not defined
    expect(() => {
      render(<TheoryHelper dark={false} />);
    }).not.toThrow();
  });

  it("12 个调性按钮全部渲染（data-testid=theory-key-XXX）", () => {
    render(<TheoryHelper dark={false} />);
    const buttons = screen.getAllByTestId(/^theory-key-/);
    expect(buttons).toHaveLength(12);
  });

  it("12 个调名（C / C# / D / Eb / E / F / F# / G / Ab / A / Bb / B）", () => {
    render(<TheoryHelper dark={false} />);
    for (const k of ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]) {
      expect(screen.getByTestId(`theory-key-${k}`)).toBeTruthy();
    }
  });

  it("selectedKey=C → C 按钮应用激活样式（暗色 primary bg）", () => {
    const { container } = render(<TheoryHelper dark={true} selectedKey="C" />);
    const cBtn = screen.getByTestId("theory-key-C");
    // active 样式是 bg-primary text-primary-foreground
    expect(cBtn.className).toMatch(/bg-primary/);
  });

  it("selectedKey=无效值（如 #FFFFFF）→ 无按钮高亮", () => {
    render(<TheoryHelper dark={true} selectedKey="#FFFFFF" />);
    const buttons = screen.getAllByTestId(/^theory-key-/);
    expect(buttons.every((b) => !b.className.match(/bg-primary/))).toBe(true);
  });
});
