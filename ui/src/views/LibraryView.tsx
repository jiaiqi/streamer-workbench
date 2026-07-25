import { useState, useEffect, useMemo, useRef } from "react";
import type { Song, SongsData } from "../types";

/* ================= 歌曲编辑对话框（增删改全字段，弹唱信息独立分组） ================= */
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

/* ================= 符号化元数据 ================= */
// 难度 → 菱形阶（◆◆◇），一瞥可读
function DifficultyMark({ value, dark }: { value: string; dark: boolean }) {
  const level = value === "简单" ? 1 : value === "中等" ? 2 : value === "困难" ? 3 : 0;
  if (level === 0) return <span className="text-muted-foreground/60">—</span>;
  return (
    <span className={`tracking-[0.15em] text-[10px] ${dark ? "text-zinc-400" : "text-muted-foreground"}`}
      title={`难度：${value}`}>
      {"◆".repeat(level)}{"◇".repeat(3 - level)}
    </span>
  );
}

// 选调 + 变调夹（等宽排版，保证列对齐）
function KeyCapo({ song }: { song: Song }) {
  if (!song.key && song.capo === null) return <span className="text-muted-foreground/60">—</span>;
  return (
    <span className="tabular-nums">
      <span className={song.key ? "" : "text-muted-foreground/60"}>{song.key || "?"}</span>
      {song.capo !== null && <span className="text-muted-foreground text-[11px]"> +{song.capo}</span>}
    </span>
  );
}

/* ================= 主视图 ================= */
export default function LibraryView({ dark, onStatsChange, onEditTargetChange }: {
  dark: boolean;
  onStatsChange: (s: { active: number; draft: number }) => void;
  onEditTargetChange?: (open: boolean) => void;
}) {
  const [songsData, setSongsData] = useState<SongsData | null>(null);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "draft">("all");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [editTarget, setEditTarget] = useState<Song | "new" | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const rowRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const listRef = useRef<HTMLDivElement>(null);

  const refresh = async () => {
    const d: SongsData = await (await fetch("/api/songs/list")).json();
    setSongsData(d);
    onStatsChange({ active: d.active, draft: d.draft });
  };

  useEffect(() => { refresh(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);
  useEffect(() => { onEditTargetChange?.(editTarget !== null); }, [editTarget, onEditTargetChange]);

  /* ---- 筛选：歌名 / 歌手 / 拼音首字母 ---- */
  const filtered = useMemo(() => {
    if (!songsData) return [];
    const q = query.trim().toLowerCase();
    return songsData.songs
      .filter(s => statusFilter === "all" || s.status === statusFilter)
      .filter(s => !q
        || s.title.toLowerCase().includes(q)
        || s.artists.join(" ").toLowerCase().includes(q)
        || (s.pinyin ?? "").toLowerCase().includes(q));
  }, [songsData, query, statusFilter]);

  /* ---- 按字数分类分组（1..7 + 未分类），组内保持后端序 ---- */
  const groups = useMemo(() => {
    const map = new Map<number, Song[]>();
    for (const s of filtered) {
      const sec = s.section ?? 0;
      if (!map.has(sec)) map.set(sec, []);
      map.get(sec)!.push(s);
    }
    return [...map.entries()].sort((a, b) => (a[0] === 0 ? 99 : a[0]) - (b[0] === 0 ? 99 : b[0]));
  }, [filtered]);

  const groupLabel = (sec: number) => sec === 0 ? "未分类" : sec >= 7 ? "7+ 字" : `${sec} 字`;

  /* ---- 键盘导航：↑↓ 光标 · Enter 展开 · X 学会了 · / 搜索 ---- */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (editTarget !== null) return;
      const tag = (e.target as HTMLElement)?.tagName;
      const typing = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";

      if (e.key === "/" && !typing) {
        e.preventDefault();
        searchRef.current?.focus();
        return;
      }
      if (typing || filtered.length === 0) return;

      const idx = cursor === null ? -1 : filtered.findIndex(s => s.title === cursor);
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        const next = e.key === "ArrowDown"
          ? Math.min(filtered.length - 1, idx + 1)
          : Math.max(0, idx === -1 ? 0 : idx - 1);
        const title = filtered[next].title;
        setCursor(title);
        rowRefs.current.get(title)?.scrollIntoView({ block: "nearest" });
      } else if (e.key === "Enter" && cursor) {
        e.preventDefault();
        setExpanded(prev => prev === cursor ? null : cursor);
      } else if ((e.key === "x" || e.key === "X") && cursor) {
        e.preventDefault();
        const song = filtered.find(s => s.title === cursor);
        if (song) toggleStatus(song);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtered, cursor, editTarget]);

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
      if (expanded === song.title) setExpanded(null);
      await refresh();
    } catch (e) {
      console.error("删除失败", e);
    }
  };

  /* ---- 设计令牌速记 ---- */
  const hairline = dark ? "border-zinc-700/60" : "border-border";
  const label = "text-[10px] font-semibold uppercase tracking-widest text-muted-foreground";

  return (
    <main className="flex-1 flex flex-col overflow-hidden">
      {/* ===== 第一层：主工具栏 ===== */}
      <div className={`shrink-0 flex items-center gap-4 px-6 h-14 border-b ${hairline}`}>
        <h2 className={`font-serif text-[17px] font-semibold tracking-wide ${dark ? "text-zinc-100" : "text-foreground"}`}>
          歌曲库
        </h2>
        <span className={`text-xs tabular-nums ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
          {songsData ? `${songsData.total} 首 · 已会 ${songsData.active} · 未会 ${songsData.draft}` : "…"}
        </span>

        {/* 搜索：歌名 / 歌手 / 拼音首字母；按 / 聚焦 */}
        <div className={`ml-auto flex items-center gap-2 rounded-lg px-3 h-8 w-64 transition-colors ${
          dark ? "bg-zinc-800 border border-zinc-700/60 focus-within:border-emerald-500/60"
               : "bg-muted border border-border focus-within:border-primary/60"}`}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-muted-foreground shrink-0">
            <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
          </svg>
          <input ref={searchRef} type="text" placeholder="歌名 / 歌手 / 拼音首字母…" value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => { if (e.key === "Escape") { setQuery(""); searchRef.current?.blur(); } }}
            className="flex-1 bg-transparent text-[13px] outline-none placeholder:text-muted-foreground/70" />
          <kbd className={`text-[10px] px-1 rounded ${dark ? "bg-zinc-700 text-zinc-500" : "bg-background text-muted-foreground/70 border border-border"}`}>/</kbd>
        </div>

        <button onClick={() => setEditTarget("new")}
          className="flex items-center gap-1.5 rounded-lg px-3.5 h-8 text-[13px] font-medium transition-colors cursor-pointer bg-emerald-600 hover:bg-emerald-700 text-white">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M12 5v14M5 12h14"/></svg>
          新增歌曲
        </button>
      </div>

      {/* ===== 第二层：状态筛选条 ===== */}
      <div className={`shrink-0 flex items-center gap-1 px-6 h-10 border-b ${hairline} ${dark ? "bg-zinc-800/40" : "bg-muted/40"}`}>
        {([["all", "全部"], ["active", "已会"], ["draft", "未会"]] as const).map(([id, text]) => (
          <button key={id} onClick={() => setStatusFilter(id)}
            className={`rounded-md px-3 h-6.5 py-1 text-xs font-medium transition-all duration-300 ease-out cursor-pointer ${statusFilter === id
              ? (dark ? "bg-emerald-500/20 text-emerald-300" : "bg-primary-soft text-primary")
              : (dark ? "text-zinc-500 hover:text-zinc-300" : "text-muted-foreground hover:text-foreground")}`}>
            {text}
            <span className="ml-1 tabular-nums opacity-60">
              {id === "all" ? songsData?.total ?? "" : id === "active" ? songsData?.active ?? "" : songsData?.draft ?? ""}
            </span>
          </button>
        ))}
        <span className={`ml-auto text-[11px] ${dark ? "text-zinc-600" : "text-muted-foreground/70"}`}>
          ↑↓ 移动 · Enter 展开 · X 学会了 · / 搜索
        </span>
      </div>

      {/* ===== 分组列表 ===== */}
      {songsData ? (
        <div ref={listRef} className="flex-1 overflow-y-auto">
          {groups.length === 0 && (
            <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
              没有匹配「{query}」的歌曲
            </div>
          )}
          {groups.map(([sec, songs]) => (
            <div key={sec}>
              {/* 吸顶组头：大号分类字 + 数量 + 发线 */}
              <div className={`sticky top-0 z-10 flex items-baseline gap-3 px-6 py-2 border-b ${hairline} ${
                dark ? "bg-zinc-900/95 backdrop-blur-sm" : "bg-background/95 backdrop-blur-sm"}`}>
                <span className={`font-serif text-[15px] font-semibold ${dark ? "text-zinc-300" : "text-foreground"}`}>
                  {groupLabel(sec)}
                </span>
                <span className={`text-[11px] tabular-nums ${dark ? "text-zinc-600" : "text-muted-foreground"}`}>
                  {songs.length} 首
                </span>
              </div>

              {songs.map((s, i) => {
                const isOpen = expanded === s.title;
                const isCursor = cursor === s.title;
                return (
                  <div key={s.title} ref={el => { if (el) rowRefs.current.set(s.title, el); else rowRefs.current.delete(s.title); }}>
                    {/* ---- 行：点击就地展开 ---- */}
                    <div
                      onClick={() => setExpanded(isOpen ? null : s.title)}
                      className={`group flex items-center gap-3 px-6 py-2 cursor-pointer border-b transition-colors duration-300 ease-out ${hairline} ${
                        isOpen
                          ? (dark ? "bg-zinc-800/70" : "bg-muted/70")
                          : isCursor
                            ? (dark ? "bg-zinc-800/50" : "bg-muted/50")
                            : (dark ? "hover:bg-zinc-800/40" : "hover:bg-muted/40")}`}
                    >
                      {/* 序号 */}
                      <span className={`w-7 text-right text-[11px] tabular-nums shrink-0 ${dark ? "text-zinc-600" : "text-muted-foreground/60"}`}>
                        {String(i + 1).padStart(2, "0")}
                      </span>

                      {/* 状态点：单击直接切换 学会了⇄未会 */}
                      <button
                        onClick={e => { e.stopPropagation(); toggleStatus(s); }}
                        title={s.status === "active" ? "已会 · 点击标回未会" : "未会 · 点击标记学会了"}
                        className="shrink-0 w-5 h-5 flex items-center justify-center cursor-pointer">
                        <span className={`w-2 h-2 rounded-full transition-all duration-300 ${
                          s.status === "active"
                            ? (dark ? "bg-emerald-400" : "bg-emerald-600")
                            : `bg-transparent border ${dark ? "border-amber-400/70" : "border-amber-500/80"}`}`} />
                      </button>

                      {/* 歌名 + 歌手 */}
                      <div className="flex-1 min-w-0 flex items-baseline gap-2.5">
                        <span className={`font-serif text-[14px] truncate ${
                          s.status === "draft"
                            ? (dark ? "text-zinc-400" : "text-muted-foreground")
                            : (dark ? "text-zinc-100" : "text-foreground")}`}>
                          {s.title}
                        </span>
                        <span className={`text-[12px] truncate ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
                          {s.artists.join("、") || "—"}
                        </span>
                      </div>

                      {/* 右侧元数据：符号化 + 等宽对齐 */}
                      <div className="shrink-0 flex items-center gap-5 text-[12px]">
                        <span className="w-14 text-right"><DifficultyMark value={s.difficulty} dark={dark} /></span>
                        <span className={`w-16 text-right font-mono ${dark ? "text-zinc-300" : "text-foreground"}`}><KeyCapo song={s} /></span>
                        {(s.tags ?? []).length > 0 && (
                          <span className={`hidden xl:block w-24 truncate text-right text-[11px] ${dark ? "text-zinc-500" : "text-muted-foreground"}`}>
                            {s.tags.join(" · ")}
                          </span>
                        )}
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                          className={`transition-transform duration-300 ${isOpen ? "rotate-180" : ""} ${dark ? "text-zinc-600" : "text-muted-foreground/60"}`}>
                          <path d="m6 9 6 6 6-6"/>
                        </svg>
                      </div>
                    </div>

                    {/* ---- 展开面板：大字选调 + 详情网格 + 操作 ---- */}
                    {isOpen && (
                      <div className={`border-b ${hairline} ${dark ? "bg-zinc-800/40" : "bg-muted/30"}`}>
                        <div className="flex gap-8 px-6 py-5 pl-[4.5rem]">
                          {/* 大字选调：主播一瞥可读 */}
                          <div className="shrink-0 w-36">
                            <p className={label}>选调</p>
                            <p className={`font-mono text-4xl font-semibold mt-1 leading-none ${dark ? "text-zinc-100" : "text-foreground"}`}>
                              {s.key || "—"}
                            </p>
                            <p className={`mt-2 text-[12px] tabular-nums ${dark ? "text-zinc-400" : "text-muted-foreground"}`}>
                              {s.capo !== null ? `变调夹 ${s.capo} 品` : "变调夹未填"}
                            </p>
                            <p className="mt-1"><DifficultyMark value={s.difficulty} dark={dark} /></p>
                          </div>

                          {/* 详情网格 */}
                          <div className="flex-1 grid grid-cols-2 gap-x-8 gap-y-3 content-start text-[13px]">
                            <div><p className={label}>作词</p><p className={`mt-0.5 ${dark ? "text-zinc-300" : ""}`}>{s.lyricist || "—"}</p></div>
                            <div><p className={label}>作曲</p><p className={`mt-0.5 ${dark ? "text-zinc-300" : ""}`}>{s.composer || "—"}</p></div>
                            <div>
                              <p className={label}>谱子</p>
                              <p className={`mt-0.5 break-all ${dark ? "text-zinc-300" : ""}`}>
                                {s.tabs
                                  ? /^https?:\/\//.test(s.tabs)
                                    ? <a href={s.tabs} target="_blank" rel="noreferrer" className="underline underline-offset-2 hover:text-emerald-500">{s.tabs}</a>
                                    : s.tabs
                                  : "—"}
                              </p>
                            </div>
                            <div><p className={label}>拼音</p><p className={`mt-0.5 font-mono ${dark ? "text-zinc-300" : ""}`}>{s.pinyin || "—"}</p></div>
                            {(s.tags ?? []).length > 0 && (
                              <div className="col-span-2">
                                <p className={label}>标签</p>
                                <div className="mt-1 flex flex-wrap gap-1.5">
                                  {s.tags.map(t => (
                                    <span key={t} className={`rounded-md px-2 py-0.5 text-[11px] ${
                                      dark ? "bg-zinc-700/70 text-zinc-300" : "bg-background border border-border text-muted-foreground"}`}>{t}</span>
                                  ))}
                                </div>
                              </div>
                            )}
                            {s.notes && (
                              <div className="col-span-2">
                                <p className={label}>备注</p>
                                <p className={`mt-0.5 leading-relaxed ${dark ? "text-zinc-300" : ""}`}>{s.notes}</p>
                              </div>
                            )}
                          </div>

                          {/* 操作列 */}
                          <div className="shrink-0 flex flex-col gap-1.5 w-24">
                            <button onClick={() => toggleStatus(s)}
                              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors cursor-pointer ${s.status === "draft"
                                ? "bg-emerald-600 hover:bg-emerald-700 text-white"
                                : dark ? "bg-zinc-700 text-zinc-300 hover:bg-zinc-600" : "bg-background border border-border text-muted-foreground hover:text-foreground"}`}>
                              {s.status === "draft" ? "学会了 ✓" : "标回未会"}
                            </button>
                            <button onClick={() => setEditTarget(s)}
                              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors cursor-pointer ${dark ? "bg-zinc-700 text-zinc-300 hover:bg-zinc-600" : "bg-background border border-border text-foreground hover:bg-muted"}`}>
                              编辑
                            </button>
                            <button onClick={() => deleteSong(s)}
                              className={`rounded-lg px-3 py-1.5 text-xs transition-colors cursor-pointer ${dark ? "text-red-400/80 hover:bg-zinc-700 hover:text-red-400" : "text-red-500/80 hover:bg-red-50 hover:text-red-500"}`}>
                              删除
                            </button>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center text-muted-foreground">加载中…</div>
      )}

      {/* ===== 底栏：键盘提示（右侧筛选条已有，此处仅计数收尾） ===== */}
      <div className={`shrink-0 flex items-center px-6 h-8 border-t text-[11px] ${hairline} ${dark ? "text-zinc-600" : "text-muted-foreground"}`}>
        <span className="tabular-nums">显示 {filtered.length} / {songsData?.total ?? 0} 首</span>
        {query && <span className="ml-3">匹配：「{query}」（歌名 / 歌手 / 拼音）</span>}
      </div>

      {editTarget !== null && (
        <SongEditDialog dark={dark} target={editTarget}
          onClose={() => setEditTarget(null)} onSaved={refresh} />
      )}
    </main>
  );
}
