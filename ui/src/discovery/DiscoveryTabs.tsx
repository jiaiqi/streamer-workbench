/// R3 学歌发现 — 3 套机制 tab 切换器
///
/// Tab 1: 今天该练什么 (recommend, 综合学习间隔 + 点歌热度 + 难度)
/// Tab 2: 最近学会 (recent-learned, 按 song_learned 倒序)
/// Tab 3: 点歌热度 (request-hot, queue_added + performance_sung 加权)
///
/// 冷启动: 接口返回 note 时, 顶部显示提示文案 + 引导用户去打卡 / 直播。
import { useEffect, useState } from "react";
import { apiRequest } from "../api/client";
import type { DiscoveryResponse } from "../api/generated";
import { toRequestFailure, type RequestFailure, useLatestRequest } from "../async/requestState";
import { Icon } from "../icons";
import TheoryHelper from "./TheoryHelper";

type Tab = "recommend" | "recent-learned" | "request-hot";

const TAB_LABELS: Record<Tab, { title: string; hint: string }> = {
  "recommend":     { title: "今天该练什么", hint: "综合学习间隔 + 点歌热度 + 难度" },
  "recent-learned": { title: "最近学会",     hint: "按 song_learned 事件倒序" },
  "request-hot":   { title: "点歌热度",     hint: "近 90 天点歌 / 演唱加权" },
};

interface DiscoveryTabsProps {
  dark: boolean;
}

export default function DiscoveryTabs({ dark }: DiscoveryTabsProps) {
  const [tab, setTab] = useState<Tab>("recommend");
  const [items, setItems] = useState<DiscoveryResponse | null>(null);
  const [error, setError] = useState<RequestFailure | null>(null);
  const fetchRequest = useLatestRequest<DiscoveryResponse>({
    isEmpty: r => (r.items?.length ?? 0) === 0 && !r.note,
  });

  const load = (which: Tab) => {
    setError(null);
    void fetchRequest.run(signal =>
      apiRequest<DiscoveryResponse>(`/api/discovery/${which}?limit=20`, { signal })
    ).then(result => {
      if (result) setItems(result);
    }).catch(reason => {
      setError(toRequestFailure(reason));
    });
  };

  useEffect(() => { load(tab); /* eslint-disable-next-line */ }, [tab]);

  return (
    <div className={`rounded-2xl border ${dark ? "border-zinc-700/50 bg-zinc-800/30" : "border-border bg-card"} overflow-hidden`}>
      {/* tab bar */}
      <div className={`flex items-center gap-1 border-b px-3 pt-2 ${dark ? "border-zinc-700/50" : "border-border"}`}>
        {(Object.keys(TAB_LABELS) as Tab[]).map(k => {
          const active = k === tab;
          const { title } = TAB_LABELS[k];
          return (
            <button
              key={k}
              type="button"
              onClick={() => setTab(k)}
              data-testid={`discovery-tab-${k}`}
              className={`relative px-3 py-2 text-sm font-medium transition-colors ${
                active
                  ? (dark ? "text-zinc-100" : "text-foreground")
                  : (dark ? "text-zinc-500 hover:text-zinc-300" : "text-muted-foreground hover:text-foreground")
              }`}
            >
              {title}
              {active && (
                <span
                  className="absolute bottom-0 left-0 right-0 h-0.5 rounded-t"
                  style={{ background: "var(--color-primary)" }}
                />
              )}
            </button>
          );
        })}
      </div>

      {/* content */}
      <div className="p-4">
        <p className={`text-[11px] mb-3 ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
          {TAB_LABELS[tab].hint}
        </p>
        {error && (
          <div className={`text-xs px-3 py-2 rounded-lg ${
            dark ? "bg-rose-500/10 text-rose-400" : "bg-rose-50 text-rose-700"
          }`}>
            {error.message}
          </div>
        )}
        {!error && items?.note && (
          <div className={`text-sm px-4 py-6 text-center rounded-xl ${
            dark ? "bg-zinc-800/40 text-zinc-400" : "bg-muted text-muted-foreground"
          }`}>
            <div className="mb-1 opacity-70">{Icon.lightbulb}</div>
            {items.note}
          </div>
        )}
        {!error && items && (items.items?.length ?? 0) > 0 && (
          <ul className="space-y-2">
            {(items.items ?? []).map((it, idx) => (
              <DiscoveryRow key={it.song_id} index={idx + 1} item={it} dark={dark} showTab={tab} />
            ))}
          </ul>
        )}
        {!error && items && (items.items?.length ?? 0) === 0 && !items.note && (
          <div className={`text-xs py-4 text-center ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
            暂无数据
          </div>
        )}
      </div>
    </div>
  );
}

function DiscoveryRow({ index, item, dark, showTab }: {
  index: number;
  item: import("../api/generated").DiscoveryItem;
  dark: boolean;
  showTab: Tab;
}) {
  return (
    <li className={`flex items-start gap-3 px-3 py-2.5 rounded-xl border transition-colors ${
      dark ? "border-zinc-700/40 hover:border-zinc-600" : "border-border hover:border-primary/40"
    }`} data-testid="discovery-row">
      <span className={`shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold ${
        index === 1
          ? (dark ? "bg-amber-500/20 text-amber-300" : "bg-amber-100 text-amber-700")
          : (dark ? "bg-zinc-700/60 text-zinc-400" : "bg-muted text-muted-foreground")
      }`}>
        {index}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2">
          <span className={`font-medium truncate ${dark ? "text-zinc-100" : "text-foreground"}`}>
            {item.title}
          </span>
          {item.artist && (
            <span className={`text-xs truncate ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
              {item.artist}
            </span>
          )}
        </div>
        <div className={`flex items-center gap-2 mt-0.5 text-[11px] ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
          {item.difficulty && <span>{item.difficulty}</span>}
          {item.key && <span>· Key {item.key}</span>}
          {item.capo != null && item.capo > 0 && <span>· Capo {item.capo}</span>}
          {showTab === "recent-learned" && item.last_learned_at && (
            <span>· {formatDate(item.last_learned_at)} 学会</span>
          )}
          {showTab === "request-hot" && (
            <>
              {(item.request_count ?? 0) > 0 && <span>· 点 {item.request_count}</span>}
              {(item.perform_count ?? 0) > 0 && <span>· 演 {item.perform_count}</span>}
            </>
          )}
          {showTab === "recommend" && (item.request_count ?? 0) > 0 && (
            <span>· 被点 {item.request_count} 次</span>
          )}
        </div>
        {item.reason && (
          <p className={`mt-1 text-[11px] ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
            {item.reason}
          </p>
        )}
      </div>
    </li>
  );
}

function formatDate(iso: string): string {
  return iso.slice(0, 10);
}
