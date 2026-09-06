/// R5c WCAG AA 对比度契约测试（纯数学，无 DOM）。
///
/// 解析 src/index.css 的令牌块（:root → .app-shell → data-mode 覆盖），
/// 按 WCAG 2.x 相对亮度公式计算关键「文字/背景」对的对比度，
/// 断言全部 ≥ 4.5:1（AA normal text）——防止未来改令牌时无警回归。
/// 修改任何 --color-* 令牌前先跑本测试；新令牌进入文字用途后必须在此登记。
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const CSS = readFileSync(join(__dirname, "index.css"), "utf-8");

function luminance(hex: string): number {
  const c = hex.replace("#", "");
  const full = c.length === 3
    ? c.split("").map(ch => ch + ch).join("")
    : c;
  const f = (v: number) =>
    v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  const [r, g, b] = [0, 2, 4].map(i =>
    f(parseInt(full.slice(i, i + 2), 16) / 255));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(fg: string, bg: string): number {
  const [hi, lo] = [luminance(fg), luminance(bg)].sort((a, b) => b - a);
  return (hi + 0.05) / (lo + 0.05);
}

function parseBlock(selectorPattern: string): Record<string, string> {
  const re = new RegExp(`${selectorPattern}\\s*\\{([^}]*)\\}`, "m");
  const m = CSS.match(re);
  expect(m, `CSS 块 ${selectorPattern} 应存在`).toBeTruthy();
  const tokens: Record<string, string> = {};
  for (const line of m![1].split(";")) {
    const t = line.match(/(--[\w-]+)\s*:\s*([^;]+)/);
    if (t) tokens[t[1]] = t[2].trim();
  }
  return tokens;
}

/** 令牌合并顺序：@theme（Tailwind 4 生成 :root 变量）→ .app-shell → data-mode 覆盖 */
function tokensFor(mode: "light" | "dark"): Record<string, string> {
  return {
    ...parseBlock("@theme"),
    ...parseBlock("\\.app-shell"),
    ...parseBlock(`\\.app-shell\\[data-mode="${mode}"\\]`),
  };
}

const AA = 4.5;

describe("WCAG AA 对比度契约（R5c）", () => {
  it.each([
    ["light", tokensFor("light")],
    ["dark", tokensFor("dark")],
  ])("%s 模式：正文/次要文字/强调小字 全部 ≥ 4.5", (_mode, t) => {
    const bg = t["--color-background"];
    const card = t["--color-card"];
    const muted = t["--color-muted"];
    const fg = t["--color-foreground"];
    const mutedFg = t["--color-muted-foreground"];
    const accentText = t["--color-accent-text"];
    const dangerText = t["--color-danger-text"];
    const warning = t["--color-warning"];

    expect(contrast(fg, bg)).toBeGreaterThanOrEqual(AA);
    // 次要文字出现在背景/卡片/muted 三种底上（11-13px 正文）
    expect(contrast(mutedFg, bg)).toBeGreaterThanOrEqual(AA);
    expect(contrast(mutedFg, card)).toBeGreaterThanOrEqual(AA);
    expect(contrast(mutedFg, muted)).toBeGreaterThanOrEqual(AA);
    // eyebrow / inspector-label（10px 小字，位于背景与灰卡）
    expect(contrast(accentText, bg)).toBeGreaterThanOrEqual(AA);
    expect(contrast(accentText, muted)).toBeGreaterThanOrEqual(AA);
    // 危险文字（.state-error / .resource-alert / .mobile-preview-error，11-12px）
    expect(contrast(dangerText, bg)).toBeGreaterThanOrEqual(AA);
    expect(contrast(dangerText, card)).toBeGreaterThanOrEqual(AA);
    // warning 文字（.warning-note 提示，11px）
    expect(contrast(warning, bg)).toBeGreaterThanOrEqual(AA);
    expect(contrast(warning, card)).toBeGreaterThanOrEqual(AA);
  });

  it.each([
    ["light", tokensFor("light")],
    ["dark", tokensFor("dark")],
  ])("%s 模式：按钮白字 on primary/strong/destructive ≥ 4.5", (_mode, t) => {
    const primary = t["--color-primary"];
    const strong = t["--color-primary-strong"];
    const danger = t["--color-danger"];
    const fg = t["--color-primary-foreground"];
    expect(contrast(fg, primary)).toBeGreaterThanOrEqual(AA);
    expect(contrast(fg, strong)).toBeGreaterThanOrEqual(AA);
    expect(contrast("#ffffff", danger)).toBeGreaterThanOrEqual(AA);
  });

  it("reduced-motion 下 stagger 列表直接可见（不延迟、不依赖动画基态）", () => {
    const block = CSS.match(
      /@media \(prefers-reduced-motion: reduce\) \{[\s\S]*?\n\}/,
    );
    expect(block).toBeTruthy();
    expect(block![0]).toContain(".stagger-list");
    expect(block![0]).toMatch(/opacity:\s*1\s*!important/);
    expect(block![0]).toMatch(/animation:\s*none\s*!important/);
  });
});
