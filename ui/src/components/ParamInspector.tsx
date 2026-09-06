/// P2 R4: 通用参数 Inspector。
///
/// 读 ParamSpec 列表自动渲染控件，按 spec.group 折叠分组。
/// 控件：
///   - int / float   滑块 + 数字输入（双向联动）
///   - bool          开关
///   - select        下拉
///   - section_map   分组→数值二维表（"每字数分组的栏数"专用）
///   - group_order   上下拖拽排序列表（占位：v1 仅作列表展示）
///
/// 状态：
///   - onChange(value) 每次值变化时调用，父组件做防抖
///   - 每个 spec 行带「重置默认」按钮，恢复到 spec.default
import { useEffect, useMemo, useState, useCallback, useRef } from "react";
import type { ParamSpec, ParamSpecKind } from "../types";

interface ParamInspectorProps {
  specs: ParamSpec[];
  values: Record<string, unknown>;
  onChange: (key: string, value: unknown) => void;
  onReset?: (key: string) => void;
  dark?: boolean;
}

export default function ParamInspector({ specs, values, onChange, onReset, dark }: ParamInspectorProps) {
  // 按 spec.group 分组
  const groups = useMemo(() => {
    const map = new Map<string, ParamSpec[]>();
    for (const sp of specs) {
      const g = sp.group ?? "布局";
      if (!map.has(g)) map.set(g, []);
      map.get(g)!.push(sp);
    }
    return Array.from(map.entries());
  }, [specs]);

  if (specs.length === 0) {
    return <p className="text-xs text-muted-foreground">参数加载中…</p>;
  }

  return (
    <div className="space-y-3">
      {groups.map(([groupName, groupSpecs]) => (
        <details key={groupName} open className="group">
          <summary className="flex items-center justify-between cursor-pointer py-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground select-none">
            {groupName}
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="transition-transform group-open:rotate-180">
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </summary>
          <div className="mt-2.5 space-y-2.5">
            {groupSpecs.map(sp => (
              <ParamRow
                key={sp.key}
                spec={sp}
                value={values[sp.key]}
                onChange={v => onChange(sp.key, v)}
                onReset={onReset ? () => onReset(sp.key) : undefined}
                dark={dark}
              />
            ))}
          </div>
        </details>
      ))}
    </div>
  );
}

interface ParamRowProps {
  spec: ParamSpec;
  value: unknown;
  onChange: (v: unknown) => void;
  onReset?: () => void;
  dark?: boolean;
}

function ParamRow({ spec, value, onChange, onReset, dark }: ParamRowProps) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          {spec.label}
          {spec.unit && <span className="text-[10px] opacity-70">({spec.unit})</span>}
          {spec.help && <HelpTip text={spec.help} />}
        </span>
        {onReset && !isDefaultValue(spec, value) && (
          <button
            type="button"
            onClick={onReset}
            className="text-[10px] text-muted-foreground hover:text-primary transition-colors"
            title="恢复默认值"
            data-testid={`param-reset-${spec.key}`}
          >
            重置
          </button>
        )}
      </div>
      <ParamControl spec={spec} value={value} onChange={onChange} dark={dark} />
    </div>
  );
}

function isDefaultValue(spec: ParamSpec, value: unknown): boolean {
  return JSON.stringify(spec.default) === JSON.stringify(value);
}

function ParamControl({ spec, value, onChange, dark }: {
  spec: ParamSpec; value: unknown; onChange: (v: unknown) => void; dark?: boolean;
}) {
  switch (spec.kind) {
    case "int":
    case "float":
      return <NumericControl spec={spec} value={value} onChange={onChange} dark={dark} />;
    case "bool":
      return <BoolControl value={Boolean(value)} onChange={onChange} dark={dark} />;
    case "select":
      return <SelectControl spec={spec} value={value} onChange={onChange} dark={dark} />;
    case "section_map":
      return <SectionMapControl spec={spec} value={value} onChange={onChange} dark={dark} />;
    case "group_order":
      return <GroupOrderControl spec={spec} value={value} onChange={onChange} dark={dark} />;
    default: {
      // 兜底：把未知 kind 显式抛错（防止 silent fail）
      const _exhaustive: never = spec.kind;
      return <span className={`text-[10px] ${dark ? "text-red-400" : "text-red-600"}`}>未知 kind: {spec.kind}</span>;
    }
  }
}

/* ============= 数值控件（int / float）：滑块 + 数字 ============= */

function NumericControl({ spec, value, onChange, dark }: {
  spec: ParamSpec; value: unknown; onChange: (v: number) => void; dark?: boolean;
}) {
  const isFloat = spec.kind === "float";
  const numValue = typeof value === "number" ? value : Number(spec.default);
  const min = spec.min ?? 0;
  const max = spec.max ?? 100;
  const step = spec.step ?? (isFloat ? 0.1 : 1);
  const [textDraft, setTextDraft] = useState(String(numValue));
  // value 变化时同步 textDraft
  useEffect(() => { setTextDraft(String(numValue)); }, [numValue]);

  const base = dark
    ? "bg-zinc-800 border-zinc-700 text-zinc-300"
    : "bg-muted border-border text-foreground border";
  const inputCls = `w-16 rounded-lg px-2 py-1 text-xs outline-none text-right ${base}`;

  return (
    <div className="flex items-center gap-2">
      <input
        type="range"
        min={min} max={max} step={step}
        value={numValue}
        onChange={e => onChange(isFloat ? parseFloat(e.target.value) : parseInt(e.target.value, 10))}
        className="flex-1 accent-primary"
        data-testid={`param-slider-${spec.key}`}
      />
      <input
        type="number"
        value={textDraft}
        min={min} max={max} step={step}
        onChange={e => {
          setTextDraft(e.target.value);
          const n = isFloat ? parseFloat(e.target.value) : parseInt(e.target.value, 10);
          if (!isNaN(n) && n >= min && n <= max) onChange(n);
        }}
        onBlur={() => {
          // 失焦时如果文本无效 → 还原到当前 value
          const n = isFloat ? parseFloat(textDraft) : parseInt(textDraft, 10);
          if (isNaN(n)) setTextDraft(String(numValue));
          else onChange(Math.max(min, Math.min(max, n)));
        }}
        className={inputCls}
        data-testid={`param-number-${spec.key}`}
      />
    </div>
  );
}

/* ============= 布尔控件 ============= */

function BoolControl({ value, onChange, dark }: {
  value: boolean; onChange: (v: boolean) => void; dark?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={value}
      onClick={() => onChange(!value)}
      data-testid="param-bool"
      className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
        value ? "bg-primary" : (dark ? "bg-zinc-700" : "bg-muted-foreground/30")
      }`}
    >
      <span
        className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
          value ? "translate-x-5" : "translate-x-1"
        }`}
      />
    </button>
  );
}

/* ============= 下拉控件 ============= */

function SelectControl({ spec, value, onChange, dark }: {
  spec: ParamSpec; value: unknown; onChange: (v: unknown) => void; dark?: boolean;
}) {
  const base = dark
    ? "bg-zinc-800 border-zinc-700 text-zinc-300"
    : "bg-muted border-border text-foreground border";
  return (
    <select
      value={String(value ?? spec.default)}
      onChange={e => {
        const v = e.target.value;
        // 数字反序列化：保留原始类型
        const matched = (spec.choices ?? []).find(c => String(c) === v);
        onChange(matched !== undefined ? matched : v);
      }}
      className={`w-full rounded-lg px-2 py-1 text-xs outline-none cursor-pointer ${base}`}
      data-testid={`param-select-${spec.key}`}
    >
      {(spec.choices ?? []).map(c => (
        <option key={String(c)} value={String(c)}>{String(c)}</option>
      ))}
    </select>
  );
}

/* ============= section_map：分组→数值二维表 ============= */

function SectionMapControl({ spec, value, onChange, dark }: {
  spec: ParamSpec; value: unknown; onChange: (v: Record<string, number>) => void; dark?: boolean;
}) {
  const dict = useMemo<Record<string, number>>(() => {
    if (value && typeof value === "object") return value as Record<string, number>;
    if (spec.default && typeof spec.default === "object") return { ...(spec.default as Record<string, number>) };
    return {};
  }, [value, spec.default]);
  const ref = useRef(dict);
  ref.current = dict;
  const labels = Object.keys(dict);

  const inputCls = dark
    ? "bg-zinc-800 border-zinc-700 text-zinc-300"
    : "bg-muted border-border text-foreground border";

  return (
    <div className="rounded-lg border border-border/50 divide-y divide-border/30" data-testid="param-section-map">
      {labels.map(label => {
        const v = dict[label];
        return (
          <div key={label} className="flex items-center gap-2 px-2 py-1.5">
            <span className="text-xs text-muted-foreground flex-1">{label}</span>
            <input
              type="number"
              min={spec.min ?? 0} max={spec.max ?? 99}
              value={v}
              onChange={e => {
                const n = parseInt(e.target.value, 10);
                if (isNaN(n)) return;
                const next = { ...ref.current, [label]: Math.max(0, n) };
                onChange(next);
              }}
              className={`w-12 rounded px-2 py-0.5 text-xs text-right outline-none ${inputCls}`}
              data-testid={`param-section-map-${label}`}
            />
          </div>
        );
      })}
    </div>
  );
}

/* ============= group_order：列表顺序（v1 只展示） ============= */

function GroupOrderControl({ spec, value, onChange, dark }: {
  spec: ParamSpec; value: unknown; onChange: (v: string[]) => void; dark?: boolean;
}) {
  const list = useMemo<string[]>(() => {
    if (Array.isArray(value)) return value as string[];
    if (Array.isArray(spec.default)) return spec.default as string[];
    return [];
  }, [value, spec.default]);
  return (
    <ol className="rounded-lg border border-border/50 px-3 py-2 text-xs text-muted-foreground space-y-1">
      {list.map((it, idx) => (
        <li key={it} className="flex items-center gap-2">
          <span className="text-[10px] opacity-60">{idx + 1}.</span>
          <span>{it}</span>
        </li>
      ))}
    </ol>
  );
}

/* ============= 帮助 tooltip ============= */

function HelpTip({ text }: { text: string }) {
  return (
    <span className="relative inline-flex items-center group/tip">
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="opacity-60 hover:opacity-100 cursor-help">
        <circle cx="12" cy="12" r="10" />
        <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
        <line x1="12" y1="17" x2="12.01" y2="17" />
      </svg>
      <span className="absolute left-full ml-1.5 px-2 py-1 rounded-md text-[11px] bg-zinc-900 text-zinc-100 whitespace-nowrap opacity-0 group-hover/tip:opacity-100 pointer-events-none z-50 transition-opacity shadow-lg">
        {text}
      </span>
    </span>
  );
}
