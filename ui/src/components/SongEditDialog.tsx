import { useState, useEffect } from "react";
import type { Song } from "../types";
import { apiRequest } from "../api/client";
import { toRequestFailure } from "../async/requestState";

/* ---- 歌曲编辑对话框（增删改全字段，弹唱信息独立分组） ---- */
export default function SongEditDialog({ dark, target, onClose, onSaved }: {
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
    if (saving) return;
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
      await (target === "new"
        ? apiRequest("/api/songs/add", { method: "POST", body: fields })
        : apiRequest("/api/songs/update", { method: "POST", body: { title: target.title, fields } }));
      await onSaved();
      onClose();
    } catch (reason) {
      const failure = toRequestFailure(reason, "保存失败");
      setError([failure.message, failure.recovery, failure.requestId && `请求编号：${failure.requestId}`].filter(Boolean).join(" · "));
    } finally { setSaving(false); }
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

        {error && <p className="mt-3 text-sm text-red-500" role="alert" aria-live="polite">{error}</p>}

        <div className="flex justify-end gap-2 mt-5">
          <button onClick={() => !saving && onClose()} disabled={saving}
            className={`rounded-xl px-4 py-2 text-sm transition-colors cursor-pointer disabled:opacity-50 ${dark ? "text-zinc-400 hover:text-zinc-200" : "text-muted-foreground hover:text-foreground"}`}>
            取消
          </button>
          <button onClick={save} disabled={saving}
            className="primary-action rounded-xl px-5 py-2 text-sm cursor-pointer disabled:opacity-50">
            {saving ? "保存中…" : "保存"}
          </button>
        </div>
      </div>
    </div>
  );
}
