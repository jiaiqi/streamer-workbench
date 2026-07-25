import { useState, useEffect } from "react";
import type { Settings, Theme } from "../types";
import { CANVAS_OPTIONS } from "../types";

/* ---- 设置视图：输出 / 数据与安全 / 高级 三组，对接 /api/settings ---- */
export default function SettingsView({ dark, themes }: {
  dark: boolean;
  themes: Theme[];
}) {
  const [form, setForm] = useState<Settings | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setSaved(false);
    fetch("/api/settings").then(r => r.json()).then(setForm);
  }, []);

  const save = async () => {
    if (!form) return;
    setSaving(true);
    try {
      const res = await fetch("/api/settings", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (res.ok) {
        setSaved(true);
        setTimeout(() => setSaved(false), 2500);
      }
    } catch (e) {
      console.error("设置保存失败", e);
    }
    setSaving(false);
  };

  return (
    <main className="flex-1 overflow-y-auto p-6">
      <h2 className={`text-lg font-semibold mb-4 ${dark ? "text-zinc-200" : "text-foreground"}`}>设置</h2>
      {form ? (
        <div className="max-w-xl space-y-5">
          <section className={`rounded-xl p-4 space-y-3 ${dark ? "bg-zinc-800/80 border border-zinc-700/50" : "bg-card border border-border"}`}>
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">输出</h3>
            <label className="block text-xs text-muted-foreground">
              输出目录
              <input type="text" value={form.output_dir}
                onChange={e => setForm(f => f && { ...f, output_dir: e.target.value })}
                className={`mt-1 w-full rounded-lg px-3 py-2 text-sm outline-none font-mono ${dark ? "bg-zinc-700 text-zinc-200" : "bg-muted border border-border text-foreground"}`} />
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="block text-xs text-muted-foreground">
                默认画布
                <select value={form.default_canvas}
                  onChange={e => setForm(f => f && { ...f, default_canvas: e.target.value })}
                  className={`mt-1 w-full rounded-lg px-3 py-2 text-sm outline-none ${dark ? "bg-zinc-700 text-zinc-200" : "bg-muted border border-border text-foreground"}`}>
                  {CANVAS_OPTIONS.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </label>
              <label className="block text-xs text-muted-foreground">
                默认主题
                <select value={form.default_theme}
                  onChange={e => setForm(f => f && { ...f, default_theme: e.target.value })}
                  className={`mt-1 w-full rounded-lg px-3 py-2 text-sm outline-none ${dark ? "bg-zinc-700 text-zinc-200" : "bg-muted border border-border text-foreground"}`}>
                  {themes.map(t => <option key={t.name} value={t.name}>{t.name}</option>)}
                </select>
              </label>
            </div>
            <p className="text-[11px] text-muted-foreground">默认画布/主题在无历史使用记录（首次启动）时生效；日常使用以「启动恢复」的上次状态为准。</p>
          </section>

          <section className={`rounded-xl p-4 space-y-3 ${dark ? "bg-zinc-800/80 border border-zinc-700/50" : "bg-card border border-border"}`}>
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">数据与安全</h3>
            <label className="block text-xs text-muted-foreground">
              自动备份保留份数（1-100）
              <input type="number" min={1} max={100} value={form.backup_count}
                onChange={e => setForm(f => f && { ...f, backup_count: Math.max(1, Math.min(100, parseInt(e.target.value, 10) || 20)) })}
                className={`mt-1 w-24 rounded-lg px-3 py-2 text-sm outline-none text-right ${dark ? "bg-zinc-700 text-zinc-200" : "bg-muted border border-border text-foreground"}`} />
            </label>
            <p className="text-[11px] text-muted-foreground">歌曲数据每次变更前自动备份到 data/backups/，超出份数滚动清理。</p>
          </section>

          <section className={`rounded-xl p-4 space-y-3 ${dark ? "bg-zinc-800/80 border border-zinc-700/50" : "bg-card border border-border"}`}>
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">高级</h3>
            <label className="block text-xs text-muted-foreground">
              字体文件路径
              <input type="text" value={form.font_path}
                onChange={e => setForm(f => f && { ...f, font_path: e.target.value })}
                className={`mt-1 w-full rounded-lg px-3 py-2 text-sm outline-none font-mono ${dark ? "bg-zinc-700 text-zinc-200" : "bg-muted border border-border text-foreground"}`} />
            </label>
            <p className="text-[11px] text-muted-foreground">⚠️ 更换字体会使金标准测试失效（渲染像素必变），且需重启后端生效；当前渲染仍使用内置猫啃糖圆体。</p>
            <label className="block text-xs text-muted-foreground">
              渲染线程数（预留，暂未生效）
              <input type="number" min={1} max={8} value={form.render_threads} disabled
                className={`mt-1 w-24 rounded-lg px-3 py-2 text-sm outline-none text-right opacity-50 ${dark ? "bg-zinc-700 text-zinc-200" : "bg-muted border border-border text-foreground"}`} />
            </label>
          </section>

          <div className="flex items-center gap-3">
            <button onClick={save} disabled={saving}
              className="rounded-xl px-5 py-2 text-sm transition-colors cursor-pointer bg-emerald-600 hover:bg-emerald-700 text-white font-medium disabled:opacity-50">
              {saving ? "保存中…" : "保存设置"}
            </button>
            {saved && <span className="text-sm text-emerald-600">✅ 已保存</span>}
          </div>
        </div>
      ) : (
        <div className="text-muted-foreground">加载中…</div>
      )}
    </main>
  );
}
