import { useState, useEffect } from "react";
import type { Dispatch, SetStateAction } from "react";
import type { Song, SongsData } from "../types";
import SongEditDialog from "../components/SongEditDialog";
import TabsPanel from "../components/TabsPanel";
import AsyncStateNotice from "../components/AsyncStateNotice";
import { apiRequest } from "../api/client";
import { toRequestFailure, useLatestRequest } from "../async/requestState";

/* ---- 学歌管理视图（按设计稿 learning.html 重写）----
   设计语言：晨光纸感 · 卡片网格 · 星光难度 · 衬线标题
   功能：
   - 只显示 draft 歌曲，卡片式网格布局（两列）
   - 难度星标（简单2星/中等3星/困难4星/未标灰）
   - 弹唱信息（Key / Capo）突出显示
   - 备注用 primary-softer 底色便签呈现
   - 一键「标记学会」（主按钮）+ 编辑（次按钮）
   - 批量导入对话框（一行一首，「歌手 歌名」或纯歌名）
   - 卡片入场 stagger 动画
*/

/* 难度 → 星数映射 */
function diffToStars(d: string): number {
  if (d === "困难") return 4;
  if (d === "中等") return 3;
  if (d === "简单") return 2;
  return 0;
}

function Stars({ n, dark }: { n: number; dark: boolean }) {
  return (
    <span className="inline-flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map(i => (
        <svg key={i} width="13" height="13" viewBox="0 0 24 24"
          fill={i <= n ? "currentColor" : "none"}
          stroke="currentColor" strokeWidth="2"
          style={{ color: i <= n ? "var(--color-warning)" : (dark ? "#3f3f46" : "var(--color-border)") }}>
          <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
        </svg>
      ))}
    </span>
  );
}

export default function LearningView({ dark, onStatsChange, onEditTargetChange }: {
  dark: boolean;
  onStatsChange: Dispatch<SetStateAction<{ active: number; draft: number } | null>>;
  onEditTargetChange?: (open: boolean) => void;
}) {
  const [songs, setSongs] = useState<Song[]>([]);
  const [importOpen, setImportOpen] = useState(false);
  const [importText, setImportText] = useState("");
  const [importResult, setImportResult] = useState<string[]>([]);
  const [importing, setImporting] = useState(false);
  const [justLearned, setJustLearned] = useState<string | null>(null);
  const [editTarget, setEditTarget] = useState<Song | null>(null);
  const [tabsOpen, setTabsOpen] = useState<string | null>(null);
  const [learningSong, setLearningSong] = useState<string | null>(null);
  const [actionError, setActionError] = useState("");
  const listRequest = useLatestRequest<{ draft: SongsData; all: SongsData }>({ isEmpty: result => result.draft.total === 0 });

  const refresh = async () => {
    const result = await listRequest.run(signal => Promise.all([
      apiRequest<SongsData>("/api/songs/list?status=draft", { signal }),
      apiRequest<SongsData>("/api/songs/list", { signal }),
    ]).then(([draft, all]) => ({ draft, all })));
    if (!result) return;
    setSongs(result.draft.songs);
    onStatsChange({ active: result.all.active, draft: result.all.draft });
  };

  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, []);
  useEffect(() => { onEditTargetChange?.(importOpen || editTarget !== null); }, [importOpen, editTarget, onEditTargetChange]);

  /* 按难度排序：困难 → 中等 → 简单 → 未标 */
  const difficultyOrder: Record<string, number> = { "困难": 0, "中等": 1, "简单": 2, "": 3 };
  const sorted = [...songs].sort((a, b) =>
    (difficultyOrder[a.difficulty] ?? 3) - (difficultyOrder[b.difficulty] ?? 3));

  const learn = async (song: Song) => {
    if (learningSong) return;
    setLearningSong(song.id); setActionError("");
    try {
      await apiRequest("/api/songs/status", { method: "POST", body: { title: song.title, status: "active" } });
      setJustLearned(song.title);
      setTimeout(() => {
        setSongs(prev => prev.filter(s => s.title !== song.title));
        setJustLearned(null);
      }, 450);
      onStatsChange(prev => prev && ({ active: prev.active + 1, draft: prev.draft - 1 }));
    } catch (reason) { setActionError(toRequestFailure(reason, "标记失败").message); }
    finally { setLearningSong(null); }
  };

  const doImport = async () => {
    const lines = importText.split("\n").map(l => l.trim()).filter(Boolean);
    if (!lines.length) return;
    setImporting(true);
    setImportResult([]);
    const results: string[] = [];
    for (const line of lines) {
      const parts = line.split(/\s+/);
      let title: string, artists: string[];
      if (parts.length >= 2) {
        artists = [parts[0]];
        title = parts.slice(1).join(" ");
      } else {
        artists = [];
        title = line;
      }
      try {
        await apiRequest("/api/songs/add", { method: "POST", body: { title, artists, status: "draft" } });
        results.push(`✅ ${title}`);
      } catch (reason) {
        results.push(`❌ ${title} — ${toRequestFailure(reason).message}`);
      }
    }
    setImportResult(results);
    setImporting(false);
    await refresh();
    setImportText("");
  };

  const inputCls = `mt-1 w-full rounded-lg px-3 py-2 text-sm outline-none transition-shadow focus:ring-2 ${
    dark ? "bg-zinc-700 text-zinc-200 focus:ring-emerald-500/30" : "bg-muted border border-border text-foreground focus:ring-primary/20"}`;

  return (
    <main className="flex-1 flex flex-col overflow-hidden">
      {/* ===== 页头（衬线大标题 + 副标题 + 操作）===== */}
      <header className="flex shrink-0 items-end justify-between px-8 pt-7 pb-5">
        <div>
          <h1 className={`font-serif text-[26px] font-bold tracking-wide ${dark ? "text-zinc-100" : "text-foreground"}`}>
            学歌管理
          </h1>
          <p className="mt-1 text-[13px] text-muted-foreground">
            学会后自动进入歌曲库 · 同步更新海报排版
          </p>
        </div>
        <button onClick={() => { setImportOpen(true); setImportResult([]); }}
          className="flex items-center gap-1.5 rounded-xl px-4 py-2 text-sm font-medium text-white transition-all active:scale-95 cursor-pointer"
          style={{ background: "linear-gradient(150deg, var(--color-primary), var(--color-primary-strong))", boxShadow: "var(--shadow-primary)" }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          添加在学
        </button>
      </header>

      {/* ===== 内容区 ===== */}
      <div className="flex-1 overflow-y-auto px-8 pb-10">
        {actionError && <div className="mb-4 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-500" role="alert">{actionError}</div>}
        {listRequest.status === "loading" && songs.length === 0 ? (
          <div className="grid grid-cols-2 gap-4">
            {[1, 2, 3, 4].map(i => (
              <div key={i} className={`h-44 rounded-2xl animate-pulse ${dark ? "bg-zinc-800/60" : "bg-muted/70"}`} />
            ))}
          </div>
        ) : listRequest.status === "error" && songs.length === 0 ? (
          <AsyncStateNotice kind="error" label="在学歌曲" error={listRequest.error} onRetry={refresh} />
        ) : sorted.length === 0 ? (
          <div className="flex h-full items-center justify-center">
            <div className="text-center space-y-4">
              <div className={`w-20 h-20 mx-auto rounded-3xl flex items-center justify-center text-3xl ${dark ? "bg-zinc-800" : "bg-muted"}`}
                style={{ boxShadow: "var(--shadow-md)" }}>🎉</div>
              <div>
                <p className={`font-serif text-lg font-semibold ${dark ? "text-zinc-200" : "text-foreground"}`}>全部拿下！</p>
                <p className="mt-1 text-sm text-muted-foreground">没有在学的歌了，去挑下一首吧</p>
              </div>
              <button onClick={() => { setImportOpen(true); setImportResult([]); }}
                className="rounded-xl px-5 py-2 text-sm font-medium text-white transition-all active:scale-95 cursor-pointer"
                style={{ background: "linear-gradient(150deg, var(--color-primary), var(--color-primary-strong))" }}>
                添加在学
              </button>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4">
            {sorted.map((s, idx) => (
              <article key={s.title}
                className={`flex flex-col rounded-2xl p-5 transition-all duration-300 ${
                  dark ? "bg-zinc-800/70 border border-zinc-700/60 hover:bg-zinc-800 hover:border-zinc-600"
                       : "bg-card border border-border hover:-translate-y-0.5"
                } ${justLearned === s.title ? "opacity-0 scale-95" : "opacity-100"}`}
                style={{
                  boxShadow: "var(--shadow-sm)",
                  animation: `learningCardIn .5s cubic-bezier(.22,1,.36,1) ${idx * 70}ms both`,
                }}>
                {/* 头部：歌名 + 歌手 */}
                <div className="mb-3 flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h3 className={`truncate font-serif text-[16px] font-semibold ${dark ? "text-zinc-100" : "text-foreground"}`}>
                      {s.title}
                    </h3>
                    <p className="mt-0.5 text-xs text-muted-foreground truncate">
                      {s.artists.join("、") || "未知歌手"}
                    </p>
                  </div>
                  <Stars n={diffToStars(s.difficulty)} dark={dark} />
                </div>

                {/* 弹唱信息行 */}
                <div className="mb-3 flex items-center gap-4 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1.5">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>
                    Key
                    <b className={`font-semibold ${dark ? "text-zinc-200" : "text-foreground"}`}>{s.key || "—"}</b>
                  </span>
                  <span className="flex items-center gap-1.5">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
                    Capo
                    <b className={`font-semibold tabular-nums ${dark ? "text-zinc-200" : "text-foreground"}`}>
                      {s.capo != null ? s.capo : "—"}
                    </b>
                  </span>
                  {s.difficulty && (
                    <span className={`ml-auto rounded-full px-2 py-0.5 text-[11px] font-medium ${
                      s.difficulty === "困难" ? "bg-red-100 text-red-700 dark:bg-red-900/60 dark:text-red-300"
                      : s.difficulty === "中等" ? "bg-amber-100 text-amber-700 dark:bg-amber-900/60 dark:text-amber-300"
                      : "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/60 dark:text-emerald-300"
                    }`}>{s.difficulty}</span>
                  )}
                </div>

                {/* 备注便签 */}
                <div className="mb-4 flex-1 rounded-xl p-3 text-xs leading-relaxed"
                  style={{
                    background: dark ? "rgba(47,143,122,0.08)" : "var(--color-primary-softer)",
                    color: dark ? "#a1a1aa" : "var(--color-muted-foreground)",
                  }}>
                  {s.notes || <span className="opacity-50">还没有练习备注，点「编辑」记一笔…</span>}
                </div>

                {/* 曲谱面板（可展开，S3） */}
                {tabsOpen === s.title && (
                  <div className={`mb-4 rounded-xl p-3 ${dark ? "bg-zinc-900/50" : "bg-muted/50"}`}>
                    <TabsPanel title={s.title} tabFiles={s.tab_files ?? []} dark={dark}
                      onChanged={files => setSongs(prev => prev.map(x =>
                        x.title === s.title ? { ...x, tab_files: files } : x))} />
                  </div>
                )}

                {/* 操作行 */}
                <div className="flex items-center gap-2">
                  <button onClick={() => setTabsOpen(tabsOpen === s.title ? null : s.title)}
                    title="曲谱附件（图片/PDF）"
                    className={`rounded-xl px-3 py-2 text-xs font-medium transition-all active:scale-95 cursor-pointer ${
                      tabsOpen === s.title
                        ? (dark ? "bg-emerald-900/50 text-emerald-300" : "bg-primary/15 text-primary")
                        : (dark ? "bg-zinc-700/70 text-zinc-300 hover:bg-zinc-700" : "bg-muted text-muted-foreground hover:text-foreground")
                    }`}>
                    谱 {(s.tab_files ?? []).length}
                  </button>
                  <button onClick={() => setEditTarget(s)}
                    className={`flex-1 rounded-xl py-2 text-xs font-medium transition-all active:scale-95 cursor-pointer ${
                      dark ? "bg-zinc-700/70 text-zinc-300 hover:bg-zinc-700" : "bg-muted text-foreground hover:bg-border"
                    }`}>
                    编辑
                  </button>
                  <button onClick={() => learn(s)}
                    disabled={learningSong === s.id}
                    className="flex-1 flex items-center justify-center gap-1 rounded-xl py-2 text-xs font-medium text-white transition-all active:scale-95 cursor-pointer"
                    style={{ background: "linear-gradient(150deg, var(--color-primary), var(--color-primary-strong))" }}>
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                    {learningSong === s.id ? "标记中…" : "标记学会"}
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </div>

      {/* ===== 批量导入对话框 ===== */}
      {importOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-[2px]"
          onClick={() => !importing && setImportOpen(false)}>
          <div className={`w-[480px] rounded-2xl p-6 ${dark ? "bg-zinc-800 border border-zinc-700 text-zinc-200" : "bg-card border border-border text-card-foreground"}`}
            style={{ boxShadow: "var(--shadow-lg)" }}
            onClick={e => e.stopPropagation()}>
            <h3 className={`font-serif text-lg font-semibold ${dark ? "text-zinc-100" : "text-foreground"}`}>批量导入学歌</h3>
            <p className="mt-1 text-xs text-muted-foreground">每行一首，支持「歌手 歌名」或纯歌名格式</p>
            <textarea rows={8} placeholder={"周杰伦 晴天\n五月天 倔强\n红豆"}
              value={importText}
              onChange={e => setImportText(e.target.value)}
              className={`${inputCls} mt-3 resize-none font-mono text-[13px] leading-relaxed`} />
            {importResult.length > 0 && (
              <div className={`mt-3 max-h-32 overflow-auto rounded-xl p-3 text-xs space-y-1 ${dark ? "bg-zinc-700/50" : "bg-muted"}`}>
                {importResult.map((r, i) => <p key={i}>{r}</p>)}
              </div>
            )}
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => !importing && setImportOpen(false)} disabled={importing}
                className={`rounded-xl px-4 py-2 text-sm transition-colors cursor-pointer disabled:opacity-50 ${dark ? "text-zinc-400 hover:text-zinc-200" : "text-muted-foreground hover:text-foreground"}`}>
                关闭
              </button>
              <button onClick={doImport} disabled={!importText.trim() || importing}
                className="rounded-xl px-5 py-2 text-sm font-medium text-white transition-all active:scale-95 cursor-pointer disabled:opacity-50"
                style={{ background: "linear-gradient(150deg, var(--color-primary), var(--color-primary-strong))" }}>
                {importing ? "导入中…" : "导入"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ===== 编辑对话框（共享组件） ===== */}
      {editTarget !== null && (
        <SongEditDialog dark={dark} target={editTarget}
          onClose={() => setEditTarget(null)} onSaved={refresh} />
      )}

      {/* 卡片入场动画 keyframes */}
      <style>{`
        @keyframes learningCardIn {
          from { opacity: 0; transform: translateY(14px) scale(.97); }
          to { opacity: 1; transform: translateY(0) scale(1); }
        }
      `}</style>
    </main>
  );
}
