/// R1b: 海报文档区「布局」迷你标签页（grid-wrap / magazine-flow）。
///
/// 切换写入 store.current.layout_id 并触发自动保存；
/// magazine-flow 自动把 page_policy 切到 auto（grid-wrap 强制 legacy-fixed-2）。
/// 不重写 App.tsx 主预览：当前 desk 端 /api/render 只走 grid-wrap；
/// magazine-flow 的预览由后续渲染管线接入（render_pages + poster_id 驱动的单独路径）。
///
/// R4 Runtime v2 v2.5: Theme × Layout 能力矩阵 — 不兼容时显示警告 banner。
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import type { PosterStore } from "./usePosterStore";
import { getCompatibilityMatrix, type CompatibilityMatrix } from "@/api/posters";

interface LayoutPickerProps {
  store: PosterStore;
  /** 可选：传入当前主题 id 触发实时校验（默认空 = 只读 layout 切换） */
  currentThemeId?: string;
}

const LAYOUTS: Array<{ id: "grid-wrap" | "magazine-flow"; label: string; sub: string }> = [
  { id: "grid-wrap",    label: "网格",
    sub: "兼容 2 页" },
  { id: "magazine-flow", label: "刊头",
    sub: "自动分页" },
];

export default function LayoutPicker({ store, currentThemeId }: LayoutPickerProps) {
  const current = store.current.layout_id;
  // R4 Runtime v2 v2.5: 启动时拉一次兼容矩阵缓存（仅在有 currentThemeId 时）
  const [matrix, setMatrix] = useState<CompatibilityMatrix | null>(null);
  useEffect(() => {
    if (!currentThemeId) {
      setMatrix(null);
      return;
    }
    let cancelled = false;
    getCompatibilityMatrix()
      .then(m => { if (!cancelled) setMatrix(m); })
      .catch(() => { /* 静默 — 失败不阻挡 layout 切换 */ });
    return () => { cancelled = true; };
  }, [currentThemeId]);

  // R4 Runtime v2 v2.5: 实时校验 (current layout, current theme) 兼容性
  const incompatReason = (() => {
    if (!matrix || !currentThemeId) return null;
    const cell = matrix.matrix[current]?.[currentThemeId];
    if (cell && !cell.compatible) return cell.reason;
    return null;
  })();

  return (
    <div className="mt-2.5" data-testid="layout-picker">
      <div className="flex items-center gap-1" role="radiogroup" aria-label="布局选择">
        {LAYOUTS.map(opt => {
          const active = current === opt.id;
          return (
            <Button
              key={opt.id}
              type="button"
              size="sm"
              role="radio"
              aria-checked={active}
              variant={active ? "default" : "outline"}
              className="flex-1 h-7 px-2 text-[11px]"
              disabled={store.status === "saving"}
              onClick={() => {
                if (active) return;
                if (opt.id === "grid-wrap") {
                  store.update({
                    layout_id: "grid-wrap",
                    page_policy: { mode: "legacy-fixed-2" },
                  });
                } else {
                  // magazine-flow：page_policy 必须非 legacy-fixed-2
                  store.update({
                    layout_id: "magazine-flow",
                    page_policy: { mode: "auto", min_pages: 1, max_pages: 8 },
                  });
                }
              }}
              title={opt.sub}
              data-testid={`layout-opt-${opt.id}`}
            >
              {opt.label}
            </Button>
          );
        })}
      </div>
      {incompatReason && (
        <div
          className="mt-1 text-[10px] text-amber-600 dark:text-amber-400 leading-tight"
          role="status"
          aria-live="polite"
          data-testid="layout-compat-warning"
        >
          ⚠ 不兼容：{incompatReason}
        </div>
      )}
    </div>
  );
}
