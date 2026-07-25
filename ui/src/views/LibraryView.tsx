import { useState, useEffect } from "react";
import type { Song, SongsData } from "../types";

/* ---- 歌曲编辑对话框（增删改全字段，弹唱信息独立分组） ---- */
function SongEditDialog({ dark, target, onClose, onSaved }: {
  dark: boolean;
  target: Song | "new";
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const [form, setForm] = useState<Record<string, string>>(() => {
    if (target === "new") {
      return { title: "", artists: "", key: "", capo: "", difficulty: "", section: "", lyricist: "", composer: "", tabs: "", tags: "", pinyin: "", notes: "" };
    }
    // 防御性回显：字段缺失（如旧后端/旧数据）时降级为空串而不是 undefined
    return {
      title: target.title ?? "", artists: (target.artists ?? []).join("，"),
      key: target.key ?? "", capo: target.capo == null ? "" : String(target.capo),
      difficulty: target.difficulty ?? "", section: target.section == null ? "" : String(target.section),
      lyricist: target.lyricist ?? "", composer: target.composer ?? "", tabs: target.tabs ?? "",
      tags: (target.tags ?? []).join("，"), pinyin: target.pinyin ?? "", notes: target.notes ?? "",
    };
  });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  // Esc 关闭（保存中不响应）——输入框聚焦时也要生效
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !saving) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [saving, onClose]);

  const save = async () => {
    if (!form.title?.trim()) { setError("歌名不能为空"); return; }
    setSaving(true);
    setError("");
    const fields: Record<string, unknown> = {
      title: form.title.trim(),
      artists: form.artists.split(/[，,]/).map(s => s.trim()).filter(Boolean),
      key: form.key, difficulty: form.difficulty,
      lyricist: form.lyricist, composer: form.composer,
      tabs: form.tabs, notes: form.notes, pinyin: form.pinyin,
      tags: form.tags.split(/[，,]/).map(s => s.trim()).filter(Boolean),
      capo: form.capo === "" ? null : parseInt(form.capo, 10),
      section: form.section === "" ? null : parseInt(form.section, 10),
    };
    try {
      const res = target === "new"
        ? await fetch("/api/songs/add", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(fields) })
        : await fetch("/api/songs/update", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title: target.title, fields }) });
      if (!res.ok) { setError(await res.text()); setSaving(false); return; }
      await onSaved();
      onClose();
    } catch (e) {
      setError("保存失败：" + e);
    }
    setSaving(false);
  };

  const inputCls = `mt-1 w-full rounded-lg px-3 py-2 text-sm outline-none ${dark ? "bg-zinc-700 text-zinc-200" : "bg-muted border border-border text-foreground"}`;
  const innerCls = `mt-1 w-full rounded-lg px-3 py-2 text-sm outline-none ${dark ? "bg-zinc-700 text-zinc-200" : "bg-card border border-border text-foreground"}`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-[2px]"
      onClick={() => !saving && onClose()}>
      <div className={`w-[460px] max-h-[85vh] overflow-y-auto rounded-2xl p-6 shadow-2xl transition-colors ${dark ? "bg-zinc-800 border border-zinc-700 text-zinc-200" : "bg-card border border-border text-card-foreground"}`}
        onClick={e => e.stopPropagation()}>
        <h3 className="text-base font-semibold mb-4">
          {target === "new" ? "新增歌曲" : `编辑「${target.title}」`}
        </h3>

        <div className="space-y-3">
          <label className="block text-xs text-muted-foreground">
            歌名 <span className="text-red-400">*</span>
            <input type="text" value={form.title ?? ""} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} className={inputCls} />
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="block text-xs text-muted-foreground">
              歌手（逗号分隔）
              <input type="text" value={form.artists ?? ""} onChange={e => setForm(f => ({ ...f, artists: e.target.value }))} className={inputCls} />
            </label>
            <label className="block text-xs text-muted-foreground">
              分类
              <select value={form.section ?? ""} onChange={e => setForm(f => ({ ...f, section: e.target.value }))} className={inputCls}>
                <option value="">自动（按字数）</option>
                {[1, 2, 3, 4, 5, 6, 7].map(n => <option key={n} value={n}>{n === 7 ? "7+（长歌名/英文）" : `${n} 字`}</option>)}
              </select>
            </label>
          </div>

          <div className={`rounded-xl p-3 space-y-3 ${dark ? "bg-zinc-700/40" : "bg-muted/60"}`}>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">弹唱信息</p>
            <div className="grid grid-cols-3 gap-3">
              <label className="block text-xs text-muted-foreground">
                选调
                <input type="text" placeholder="如 G" value={form.key ?? ""} onChange={e => setForm(f => ({ ...f, key: e.target.value }))} className={innerCls} />
              </label>
              <label className="block text-xs text-muted-foreground">
                变调夹（品）
                <input type="number" min={0} max={12} placeholder="空=未填" value={form.capo ?? ""} onChange={e => setForm(f => ({ ...f, capo: e.target.value }))} className={innerCls} />
              </label>
              <label className="block text-xs text-muted-foreground">
                难度
                <select value={form.difficulty ?? ""} onChange={e => setForm(f => ({ ...f, difficulty: e.target.value }))} className={innerCls}>
                  <option value="">未标</option>
                  <option value="简单">简单</option>
                  <option value="中等">中等</option>
                  <option value="困难">困难</option>
                </select>
              </label>
            </div>
            <label className="block text-xs text-muted-foreground">
              谱子（链接或来源）
              <input type="text" value={form.tabs ?? ""} onChange={e => setForm(f => ({ ...f, tabs: e.target.value }))} className={innerCls} />
            </label>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="block text-xs text-muted-foreground">
              作词
              <input type="text" value={form.lyricist ?? ""} onChange={e => setForm(f => ({ ...f, lyricist: e.target.value }))} className={inputCls} />
            </label>
            <label className="block text-xs text-muted-foreground">
              作曲
              <input type="text" value={form.composer ?? ""} onChange={e => setForm(f => ({ ...f, composer: e.target.value }))} className={inputCls} />
            </label>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="block text-xs text-muted-foreground">
              标签（逗号分隔）
              <input type="text" placeholder="如：小甜歌，苦情" value={form.tags ?? ""} onChange={e => setForm(f => ({ ...f, tags: e.target.value }))} className={inputCls} />
            </label>
            <label className="block text-xs text-muted-foreground">
              拼音首字母
              <input type="text" placeholder="空=自动生成" value={form.pinyin ?? ""} onChange={e => setForm(f => ({ ...f, pinyin: e.target.value }))} className={inputCls} />
            </label>
          </div>

          <label className="block text-xs text-muted-foreground">
            备注
            <textarea rows={2} placeholder="如：副歌高音要降 key" value={form.notes ?? ""} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
              className={`${inputCls} resize-none`} />
          </label>
        </div>

        {error && <p className="mt-3 text-sm text-red-500">{error}</p>}

        <div className="flex justify-end gap-2 mt-5">
          <button onClick={() => !saving && onClose()} disabled={saving}
            className={`rounded-xl px-4 py-2 text-sm transition-colors cursor-pointer disabled:opacity-50 ${dark ? "text-zinc-400 hover:text-zinc-200" : "text-muted-foreground hover:text-foreground"}`}>
            取消
          </button>
          <button onClick={save} disabled={saving}
            className="rounded-xl px-5 py-2 text-sm transition-colors cursor-pointer bg-emerald-600 hover:bg-emerald-700 text-white font-medium disabled:opacity-50">
            {saving ? "保存中…" : "保存"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ---- 歌曲库视图：表格 + 搜索筛选 + 增删改 + 学会了 ---- */
export default function LibraryView({ dark, onStatsChange, onEditTargetChange }: {
  dark: boolean;
  onStatsChange: (s: { active: number; draft: number }) => void;
  onEditTargetChange?: (open: boolean) => void;
}) {
  const [songsData, setSongsData] = useState<SongsData | null>(null);
  const [songFilter, setSongFilter] = useState("");
  const [songStatusFilter, setSongStatusFilter] = useState("all");
  const [editTarget, setEditTarget] = useState<Song | "new" | null>(null);

  const refresh = async () => {
    const d: SongsData = await (await fetch("/api/songs/list")).json();
    setSongsData(d);
    onStatsChange({ active: d.active, draft: d.draft });
  };

  useEffect(() => { refresh(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);
  useEffect(() => { onEditTargetChange?.(editTarget !== null); }, [editTarget, onEditTargetChange]);

  const toggleStatus = async (song: Song) => {
    const next = song.status === "active" ? "draft" : "active";
    try {
      const res = await fetch("/api/songs/status", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: song.title, status: next }),
      });
      if (!res.ok) { console.error("状态切换失败", await res.text()); return; }
      // 本地更新该行 + 统计，避免整表重拉
      setSongsData(prev => {
        if (!prev) return prev;
        const songs = prev.songs.map(s => s.title === song.title ? { ...s, status: next } : s);
        const stats = {
          active: songs.reduce((n, s) => n + (s.status === "active" ? 1 : 0), 0),
          draft: songs.reduce((n, s) => n + (s.status === "draft" ? 1 : 0), 0),
        };
        onStatsChange(stats);
        return { ...prev, ...stats, songs };
      });
    } catch (e) {
      console.error("状态切换失败", e);
    }
  };

  const deleteSong = async (song: Song) => {
    if (!window.confirm(`确定删除「${song.title}」？此操作会立即写入 songs.json（有自动备份）。`)) return;
    try {
      const res = await fetch("/api/songs/delete", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: song.title }),
      });
      if (!res.ok) { console.error("删除失败", await res.text()); return; }
      await refresh();
    } catch (e) {
      console.error("删除失败", e);
    }
  };

  return (
    <main className="flex-1 flex flex-col overflow-hidden p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className={`text-lg font-semibold ${dark ? "text-zinc-200" : "text-foreground"}`}>歌曲库</h2>
        <div className="flex items-center gap-2">
          <input type="text" placeholder="搜索歌名…" value={songFilter}
            onChange={e => setSongFilter(e.target.value)}
            className={`rounded-lg px-3 py-1.5 text-sm outline-none ${dark ? "bg-zinc-800 border-zinc-700 text-zinc-300" : "bg-muted border-border text-foreground border"}`} />
          <select value={songStatusFilter} onChange={e => setSongStatusFilter(e.target.value)}
            className={`rounded-lg px-3 py-1.5 text-sm outline-none ${dark ? "bg-zinc-800 border-zinc-700 text-zinc-300" : "bg-muted border-border text-foreground border"}`}>
            <option value="all">全部</option>
            <option value="active">已会</option>
            <option value="draft">未会</option>
          </select>
          <button onClick={() => setEditTarget("new")}
            className="rounded-lg px-3 py-1.5 text-sm font-medium transition-colors cursor-pointer bg-emerald-600 hover:bg-emerald-700 text-white">
            + 新增歌曲
          </button>
        </div>
      </div>
      {songsData ? (
        <div className={`flex-1 overflow-auto rounded-xl border ${dark ? "border-zinc-700/50" : "border-border"}`}>
          <table className="w-full text-sm">
            <thead className={`sticky top-0 ${dark ? "bg-zinc-800" : "bg-muted"}`}>
              <tr>
                <th className="text-left px-4 py-2 font-medium">歌名</th>
                <th className="text-left px-4 py-2 font-medium">歌手</th>
                <th className="text-left px-4 py-2 font-medium">弹唱</th>
                <th className="text-left px-4 py-2 font-medium">状态</th>
                <th className="text-left px-4 py-2 font-medium">分类</th>
                <th className="text-left px-4 py-2 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {songsData.songs
                .filter(s => songStatusFilter === "all" || s.status === songStatusFilter)
                .filter(s => !songFilter || s.title.includes(songFilter))
                .map(s => (
                  <tr key={s.title} className={`border-t ${dark ? "border-zinc-700/50 hover:bg-zinc-800/50" : "border-border hover:bg-muted/50"}`}>
                    <td className="px-4 py-2">{s.title}</td>
                    <td className="px-4 py-2 text-muted-foreground">{s.artists.join("、") || "—"}</td>
                    <td className="px-4 py-2 text-muted-foreground tabular-nums">
                      {s.key || s.capo !== null
                        ? `${s.key || "?"}${s.capo !== null ? ` · capo${s.capo}` : ""}`
                        : "—"}
                    </td>
                    <td className="px-4 py-2">
                      <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${s.status === "active" ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300" : "bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300"}`}>
                        {s.status === "active" ? "已会" : "未会"}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-muted-foreground">{s.section ? `${s.section}字` : "—"}</td>
                    <td className="px-4 py-2">
                      <div className="flex items-center gap-1.5">
                        <button onClick={() => toggleStatus(s)}
                          className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-colors cursor-pointer ${s.status === "draft"
                            ? "bg-emerald-100 text-emerald-700 hover:bg-emerald-200 dark:bg-emerald-900 dark:text-emerald-300"
                            : "bg-amber-100 text-amber-700 hover:bg-amber-200 dark:bg-amber-900 dark:text-amber-300"}`}>
                          {s.status === "draft" ? "学会了 ✓" : "标回未会"}
                        </button>
                        <button onClick={() => setEditTarget(s)}
                          className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-colors cursor-pointer ${dark ? "bg-zinc-700 text-zinc-300 hover:bg-zinc-600" : "bg-muted text-foreground hover:bg-border"}`}>
                          编辑
                        </button>
                        <button onClick={() => deleteSong(s)}
                          className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-colors cursor-pointer ${dark ? "text-red-400 hover:bg-zinc-700" : "text-red-500 hover:bg-red-50"}`}>
                          删除
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center text-muted-foreground">加载中…</div>
      )}
      <div className={`mt-3 text-xs ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
        共 {songsData?.total ?? 0} 首 · 已会 {songsData?.active ?? 0} · 未会 {songsData?.draft ?? 0}
      </div>

      {editTarget !== null && (
        <SongEditDialog dark={dark} target={editTarget}
          onClose={() => setEditTarget(null)} onSaved={refresh} />
      )}
    </main>
  );
}
