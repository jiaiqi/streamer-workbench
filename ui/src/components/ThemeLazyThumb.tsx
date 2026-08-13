/// M3 P3 续: ThemeLazyThumb — 主题缩略图 IntersectionObserver 懒加载。
///
/// 与 loading="lazy" 区别：
/// - loading="lazy": 浏览器根据滚动位置启发式决定（早期 Chrome ~3000px 视口外才不下载）
/// - IntersectionObserver: 严格 0 像素阈值，进入视口才发请求
///
/// 适合 8+ 主题列表：初次打开只下载 1-2 张可见缩略图。
///
/// 零依赖 — useIntersection hook 用浏览器原生 IntersectionObserver。
import { useIntersection } from "@/hooks/useIntersection";

export function ThemeLazyThumb({ name }: { name: string }) {
  const [ref, isVisible] = useIntersection<HTMLImageElement>({
    rootMargin: "100px",  // 提前 100px 触发（用户体验更顺）
    once: true,
  });
  return (
    <img
      ref={ref}
      src={isVisible ? `/api/thumb/${encodeURIComponent(name)}` : undefined}
      data-testid="theme-lazy-thumb"
      data-theme-name={name}
      alt={name}
      className="relative w-full h-full object-cover object-bottom opacity-90 group-hover:opacity-100 transition-opacity"
      onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }}
    />
  );
}
