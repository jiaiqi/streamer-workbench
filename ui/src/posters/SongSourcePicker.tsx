/// R1a.5 歌曲来源切换：三选一卡片（全部已会 / 手动选歌 / 指定歌手）。
///
/// 切换会调用 store.update() 触发自动保存；不立即重新计算 selected_song_ids
/// （manual 模式待用户从歌曲库选歌；artist 模式 UI 上同时显示多行输入）。
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { PosterStore } from "./usePosterStore";

interface SongSourcePickerProps {
  store: PosterStore;
  dark: boolean;
}

const OPTIONS = [
  { id: "all_active" as const, label: "全部已会", sub: "当前库中所有已会歌曲" },
  { id: "manual" as const, label: "手动集合", sub: "从歌曲库多选（song_id）" },
  { id: "artist" as const, label: "指定歌手", sub: "按歌手名筛选" },
];

export default function SongSourcePicker({ store, dark }: SongSourcePickerProps) {
  const src = store.current.song_source;
  const artists = src.artists ?? [];
  const [artistDraft, setArtistDraft] = useState(artists.join(" / "));

  return (
    <section
      aria-label="歌曲来源"
      className={`px-4 pt-4 pb-3 border-b transition-colors duration-500 ${dark ? "border-zinc-700/50" : "border-border"}`}
    >
      <p className="eyebrow mb-2">歌曲来源</p>

      <div className="space-y-1.5" role="radiogroup">
        {OPTIONS.map(opt => {
          const active = src.type === opt.id;
          return (
            <Button
              key={opt.id}
              type="button"
              variant={active ? "default" : "outline"}
              size="sm"
              onClick={() => store.update({ song_source: { ...src, type: opt.id } })}
              className="w-full justify-start h-auto py-2 px-2.5"
              role="radio"
              aria-checked={active}
            >
              <div className="flex flex-col items-start">
                <span className="text-xs font-semibold">{opt.label}</span>
                <span className="text-[10px] opacity-70 font-normal">{opt.sub}</span>
              </div>
            </Button>
          );
        })}
      </div>

      {src.type === "artist" && (
        <div className="mt-3 space-y-2">
          <label className="block text-[11px] text-muted-foreground">
            歌手（多个用 <span className="font-mono">/</span> 分隔）
          </label>
          <Input
            type="text"
            value={artistDraft}
            placeholder="如：周杰伦 / 林俊杰"
            onChange={(e) => setArtistDraft(e.target.value)}
            onBlur={() => {
              const artists = artistDraft
                .split(/[／/]/)
                .map(s => s.trim())
                .filter(Boolean);
              store.update({ song_source: { ...src, artists } });
            }}
            className="h-8 text-xs"
          />
          {artists.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {artists.map((a, i) => (
                <span
                  key={`${a}-${i}`}
                  className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] bg-primary-soft text-primary"
                >
                  {a}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {src.type === "manual" && (
        <p className={`mt-3 text-[11px] leading-relaxed ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
          进入歌曲库多选已会歌曲；选择完成后点击下方「保存当前」会自动写入 selected_song_ids。
        </p>
      )}
    </section>
  );
}
