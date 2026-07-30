/// 全局测试 setup（被 vitest 加载）。
///
/// jsdom 默认不实现：
/// - window.matchMedia（MediaQueryList）：App.tsx 监听 prefers-color-scheme
/// - IntersectionObserver：缩略图懒加载用
/// - ResizeObserver：react-md 检查
/// 在这里注入 naive 实现，避免每个测试单点 mock。
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

class MediaQueryListShim {
  readonly matches: boolean = false;
  media: string = "(prefers-color-scheme: dark)";
  onchange: ((this: MediaQueryList, ev: MediaQueryListEvent) => unknown) | null = null;
  addListener(): void { /* noop */ }
  removeListener(): void { /* noop */ }
  addEventListener(): void { /* noop */ }
  removeEventListener(): void { /* noop */ }
  dispatchEvent(): boolean { return true; }
}

if (typeof window !== "undefined" && !window.matchMedia) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => new MediaQueryListShim(),
  });
}

if (typeof window !== "undefined" && typeof window.IntersectionObserver === "undefined") {
  (window as any).IntersectionObserver = class { observe(){} unobserve(){} disconnect(){} };
}

if (typeof window !== "undefined" && typeof window.ResizeObserver === "undefined") {
  (window as any).ResizeObserver = class { observe(){} unobserve(){} disconnect(){} };
}

afterEach(() => cleanup());
