/// M3 P3 续: useIntersection hook — 严格控制元素进入视口才发请求。
///
/// 与 `loading="lazy"` 区别：
/// - `loading="lazy"`: 浏览器根据滚动位置 + layout 估算决定是否下载（启发式）
/// - IntersectionObserver: 真正进入视口才发请求（精确）
///
/// 适合 200+ 海报场景：用户滚动列表时，未进入视口的海报完全不发请求。
///
/// 零依赖 — 浏览器原生 IntersectionObserver。
import { useEffect, useRef, useState, type RefObject } from "react";

export interface UseIntersectionOptions {
  /** 视口外的提前量（px）— 提前 rootMargin px 触发进入。默认 0（精确） */
  rootMargin?: string;
  /** 触发阈值，0-1；默认 0（首次相交触发） */
  threshold?: number | number[];
  /** 是否只触发一次（true：进入一次后不再变化） */
  once?: boolean;
}

export function useIntersection<T extends Element = Element>(
  options: UseIntersectionOptions = {},
): [RefObject<T | null>, boolean] {
  const { rootMargin = "0px", threshold = 0, once = true } = options;
  const ref = useRef<T>(null);
  const [isIntersecting, setIsIntersecting] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    // SSR / 旧浏览器兜底：直接认为可见
    if (typeof IntersectionObserver === "undefined") {
      setIsIntersecting(true);
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        setIsIntersecting(entry.isIntersecting);
        if (entry.isIntersecting && once) {
          observer.disconnect();
        }
      },
      { rootMargin, threshold },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [rootMargin, JSON.stringify(threshold), once]);

  return [ref, isIntersecting];
}
