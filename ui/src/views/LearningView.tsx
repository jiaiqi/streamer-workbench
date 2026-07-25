import { useState, useEffect } from "react";
import type { Song, SongsData } from "../types";

/* ---- 学歌管理视图：在学列表 + 难度排序 + 备注 + 一键学会了 ----
   与 LibraryView 的区别：
   - 只显示 draft 歌曲（未会）
   - 按难度排序（困难→中等→简单→未标）
   - 突出备注和弹唱信息
   - 一键「学会了」是主要操作
   - 支持从文本批量导入（一行一首，"歌手 歌名" 或纯歌名）
*/
export default function LearningView({ dark, onStatsChange, onEditTargetChange }: {
  dark: boolean;
  onStatsChange: (s: { active: number; draft: number }) => void;
  onEditTargetChange?: (open: boolean) => void;
}) {
  const [songs, setSongs] = useState<Song[]>([]);
  const [loading, setLoading] = useState(true);
  const [importOpen, setImportOpen] = useState(false);
  const [importText, setImportText] = useState("");
  const [importResult, setImportResult] = useState<string[]>([]);

  const refresh = async () => {
    const d: SongsData = await (await fetch("/api/songs/list?status=draft")).json();
    setSongs(d.songs);
    // 同步顶部统计
    const all: SongsData = await (await fetch("/api/songs/list")).json();
    onStatsChange({ active: all.active, draft: all.draft });
    setLoading(false);
  };

  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, []);
  useEffect(() => { onEditTargetChange?.(importOpen); }, [importOpen, onEditTargetChange]);

  const difficultyOrder: Record<string, number> = { "困难": 0, "中等": 1, "简单": 2, "": 3 };
  const sorted = [...songs].sort((a, b) =>
    (difficultyOrder[a.difficulty] ?? 3) - (difficultyOrder[b.difficulty] ?? 3));

  const learn = async (song: Song) => {
    try {
      const res = await fetch("/api/songs/status", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: song.title, status: "active" }),
      });
      if (!res.ok) { console.error("标记失败", await res.text()); return; }
      setSongs(prev => prev.filter(s => s.title !== song.title));
      onStatsChange(prev => prev && ({ active: prev.active + 1, draft: prev.draft - 1 }));
    } catch (e) {
      console.error("标记失败", e);
    }
  };

  const doImport = async () => {
    const lines = importText.split("\n").map(l => l.trim()).filter(Boolean);
    if (!lines.length) return;
    setImportResult([]);
    const results: string[] = [];
    for (const line of lines) {
      // 解析「歌手 歌名」或纯歌名
      const parts = line.split(/\s+/);
      let title: string, artists: string[];
      if (parts.length >= 2 && /[\u4e00-\u9fa5a-zA-Z]/.test(parts[0])) {
        artists = [parts[0]];
        title = parts.slice(1).join(" ");
      } else {
        artists = [];
        title = line;
      }
      try {
        const res = await fetch("/api/songs/add", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title, artists, status: "draft" }),
        });
        if (res.ok) {
          results.push(`✅ ${title}`);
        } else {
          const err = await res.text();
          results.push(`❌ ${title} — ${err}`);
        }
      } catch {
        results.push(`❌ ${title} — 网络错误`);
      }
    }
    setImportResult(results);
    await refresh();
    setImportText("");
  };

  const inputCls = `mt-1 w-full rounded-lg px-3 py-2 text-sm outline-none ${dark ? "bg-zinc-700 text-zinc-200" : "bg-muted border border-border text-foreground"}`;

  return (
    <main className="flex-1 flex flex-col overflow-hidden p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className={`text-lg font-semibold ${dark ? "text-zinc-200" : "text-foreground"}`}>学歌管理</h2>
          <p className="text-xs text-muted-foreground mt-0.5">{sorted.length} 首在学 · 按难度排序</p>
        </div>
        <button onClick={() => { setImportOpen(true); setImportResult([]); }}
          className="rounded-lg px-3 py-1.5 text-sm font-medium transition-colors cursor-pointer bg-emerald-600 hover:bg-emerald-700 text-white">
          + 批量导入
        </button>
      </div>

      {loading ? (
        <div className="flex-1 flex items-center justify-center text-muted-foreground">加载中…</div>
      ) : sorted.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center space-y-3">
            <div className={`w-16 h-16 mx-auto rounded-2xl flex items-center justify-center text-2xl shadow-sm ${dark ? "bg-zinc-800" : "bg-muted"}`}>🎉</div>
            <p className="text-sm text-muted-foreground">没有在学的歌了！</p>
            <p className="text-xs text-muted-foreground">点击右上角「批量导入」添加新歌</p>
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-auto space-y-2">
          {sorted.map(s => (
            <div key={s.title}
              className={`flex items-center gap-3 rounded-xl px-4 py-3 transition-colors ${dark ? "bg-zinc-800/50 border border-zinc-700/50 hover:bg-zinc-800/80" : "bg-card border border-border hover:shadow-sm"}`}>
              {/* 难度标签 */}
              <span className={`shrink-0 inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                s.difficulty === "困难" ? "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300"
                : s.difficulty === "中等" ? "bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300"
                : s.difficulty === "简单" ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300"
                : "bg-gray-100 text-gray-500 dark:bg-zinc-700 dark:text-zinc-400"
              }`}>
                {s.difficulty || "未标"}
              </span>

              {/* 歌名 + 歌手 */}
              <div className="flex-1 min-w-0">
                <p className={`text-sm font-medium truncate ${dark ? "text-zinc-200" : "text-foreground"}`}>{s.title}</p>
                <p className="text-xs text-muted-foreground truncate">
                  {s.artists.join("、") || "未知歌手"}
                  {s.key && ` · ${s.key}${s.capo != null ? ` capo${s.capo}` : ""}`}
                </p>
              </div>

              {/* 备注 */}
              {s.notes && (
                <p className={`hidden sm:block text-xs truncate max-w-[200px] ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
                  📝 {s.notes}
                </p>
              )}

              {/* 学会了 */}
              <button onClick={() => learn(s)}
                className="shrink-0 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors cursor-pointer bg-emerald-600 hover:bg-emerald-700 text-white">
                学会了 ✓
              </button>
            </div>
          ))}
        </div>
      )}

      {/* 批量导入对话框 */}
      {importOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-[2px]"
          onClick={() => setImportOpen(false)}>
          <div className={`w-[480px] rounded-2xl p-6 shadow-2xl ${dark ? "bg-zinc-800 border border-zinc-700 text-zinc-200" : "bg-card border border-border text-card-foreground"}`}
            onClick={e => e.stopPropagation()}>
            <h3 className="text-base font-semibold mb-1">批量导入学歌</h3>
            <p className="text-xs text-muted-foreground mb-3">每行一首，支持「歌手 歌名」或纯歌名格式</p>
            <textarea rows={8} placeholder={"周杰伦 晴天\n五月天 倔强\n红豆"}
              value={importText}
              onChange={e => setImportText(e.target.value)}
              className={`${inputCls} resize-none font-mono text-sm`} />
            {importResult.length > 0 && (
              <div className={`mt-3 max-h-32 overflow-auto rounded-lg p-3 text-xs space-y-0.5 ${dark ? "bg-zinc-700/50" : "bg-muted"}`}>
                {importResult.map((r, i) => <p key={i}>{r}</p>)}
              </div>
            )}
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => setImportOpen(false)}
                className={`rounded-xl px-4 py-2 text-sm transition-colors cursor-pointer ${dark ? "text-zinc-400 hover:text-zinc-200" : "text-muted-foreground hover:text-foreground"}`}>
                关闭
              </button>
              <button onClick={doImport} disabled={!importText.trim()}
                className="rounded-xl px-5 py-2 text-sm transition-colors cursor-pointer bg-emerald-600 hover:bg-emerald-700 text-white font-medium disabled:opacity-50">
                导入
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
