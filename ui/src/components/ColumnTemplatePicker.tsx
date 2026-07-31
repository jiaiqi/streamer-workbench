/// P2 R4: magazine-flow 栏数模板选择器。
///
/// 顶部下拉：均衡 / 密集 / 宽松 / 杂志 / 自定义
/// 选非自定义 → 直接把模板 values 写入 value
/// 选自定义 → value 保持不变，section_map 表露出供编辑
///
/// 关键设计：选非自定义的模板会**覆盖** value；选「自定义」是「不再用模板」，
/// UI 上不再有"当前选哪个模板"的状态——只关心"现在 section_map 是什么值"。
/// 切换 layout 之外（保留旧值）由父组件控制。
import { useEffect, useMemo, useState } from "react";
import type { ColumnTemplate } from "../types";

interface Props {
  templates: ColumnTemplate[];
  value: Record<string, number>;
  onChange: (next: Record<string, number>) => void;
  dark?: boolean;
}

export default function ColumnTemplatePicker({ templates, value, onChange, dark }: Props) {
  // 由 value 反推当前模板 key（若 value 匹配某模板.values → 该模板；
  // 否则 → "custom"）
  const matchedKey = useMemo(() => {
    for (const t of templates) {
      if (t.key === "custom") continue;
      if (sameMap(t.values, value)) return t.key;
    }
    return "custom";
  }, [templates, value]);

  // 本地选择 state：用户选了但还没合并到 value 时用
  const [pending, setPending] = useState<string | null>(null);
  // value 变化时清掉 pending
  useEffect(() => { setPending(null); }, [value]);

  const activeKey = pending ?? matchedKey;
  const active = templates.find(t => t.key === activeKey);

  const base = dark
    ? "bg-zinc-800 border-zinc-700 text-zinc-300"
    : "bg-muted border-border text-foreground border";

  return (
    <div className="space-y-1.5" data-testid="column-template-picker">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          栏数模板
          <span className="text-[10px] opacity-60">(每字数分组)</span>
        </span>
      </div>
      <select
        value={activeKey}
        onChange={e => {
          const k = e.target.value;
          setPending(k);
          const t = templates.find(x => x.key === k);
          if (t && t.key !== "custom") {
            onChange(t.values);
          }
        }}
        className={`w-full rounded-lg px-2 py-1 text-xs outline-none cursor-pointer ${base}`}
        data-testid="column-template-select"
      >
        {templates.map(t => (
          <option key={t.key} value={t.key}>
            {t.label} — {t.description}
          </option>
        ))}
      </select>
      {active && active.values && Object.keys(active.values).length > 0 && (
        <p className="text-[10px] text-muted-foreground/80 leading-relaxed">
          {Object.entries(active.values)
            .map(([k, v]) => `${k}=${v}`)
            .join(" · ")}
        </p>
      )}
    </div>
  );
}

function sameMap(a: Record<string, number>, b: Record<string, number>): boolean {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  for (const k of keys) {
    if ((a[k] ?? 0) !== (b[k] ?? 0)) return false;
  }
  return true;
}
