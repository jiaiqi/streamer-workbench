/// R1b: 海报文档区「布局」迷你标签页（grid-wrap / magazine-flow）。
///
/// 切换写入 store.current.layout_id 并触发自动保存；
/// magazine-flow 自动把 page_policy 切到 auto（grid-wrap 强制 legacy-fixed-2）。
/// 不重写 App.tsx 主预览：当前 desk 端 /api/render 只走 grid-wrap；
/// magazine-flow 的预览由后续渲染管线接入（render_pages + poster_id 驱动的单独路径）。
import { Button } from "@/components/ui/button";
import type { PosterStore } from "./usePosterStore";

interface LayoutPickerProps {
  store: PosterStore;
}

const LAYOUTS: Array<{ id: "grid-wrap" | "magazine-flow"; label: string; sub: string }> = [
  { id: "grid-wrap",    label: "网格",
    sub: "兼容 2 页" },
  { id: "magazine-flow", label: "刊头",
    sub: "自动分页" },
];

export default function LayoutPicker({ store }: LayoutPickerProps) {
  const current = store.current.layout_id;
  return (
    <div className="mt-2.5 flex items-center gap-1" role="radiogroup" aria-label="布局选择">
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
          >
            {opt.label}
          </Button>
        );
      })}
    </div>
  );
}
