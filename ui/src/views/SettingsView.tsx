import { useEffect, useState } from "react";
import { ACCENT_OPTIONS, APPEARANCE_OPTIONS, normalizeAppearance } from "../appearance";
import { apiRequest } from "../api/client";
import type { SettingsUpdateResponse } from "../api/generated";
import DataDirPanel from "../components/DataDirPanel";
import WebDavPanel from "../components/WebDavPanel";
import ExportHistoryView from "../posters/ExportHistoryView";
import Spinner from "../components/Spinner";
import EmptyState from "../components/EmptyState";
import type { AppearanceSettings, Settings, Theme } from "../types";
import { CANVAS_OPTIONS } from "../types";
import { useApiError } from "../async/useApiError";
import { type RequestFailure } from "../async/requestState";

interface SettingsViewProps {
  dark: boolean;
  themes: Theme[];
  appearance: AppearanceSettings;
  onAppearancePreview: (appearance: AppearanceSettings) => void;
  onAppearanceSaved: (appearance: AppearanceSettings) => void;
  onSavingChange: (saving: boolean) => void;
}

export default function SettingsView({
  dark,
  themes,
  appearance,
  onAppearancePreview,
  onAppearanceSaved,
  onSavingChange,
}: SettingsViewProps) {
  // M2.6 错误全局 toast 化
  const { runWithToast } = useApiError();
  const [form, setForm] = useState<Settings | null>(null);
  const [baseline, setBaseline] = useState<AppearanceSettings>(appearance);
  const [status, setStatus] = useState<"loading" | "ready" | "saving" | "saved" | "error">("loading");
  const [error, setError] = useState("");

  const loadSettings = () => {
    setStatus("loading");
    setError("");
    runWithToast(() => apiRequest<Settings>("/api/settings"), "设置加载失败")
      .then(settings => {
        if (!settings) return;
        const nextAppearance = normalizeAppearance(settings);
        setForm({ ...settings, ...nextAppearance });
        setBaseline(nextAppearance);
        onAppearancePreview(nextAppearance);
        setStatus("ready");
      })
      .catch(failure => {
        setError((failure as RequestFailure).message);
        setStatus("error");
      });
  };

  useEffect(() => {
    loadSettings();
    // 仅首次挂载触发；loadSettings 变化由用户主动 retry
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const updateAppearance = (next: AppearanceSettings) => {
    setForm(current => current ? { ...current, ...next } : current);
    onAppearancePreview(next);
    setStatus("ready");
    setError("");
  };

  const save = async () => {
    if (!form) return;
    setStatus("saving");
    onSavingChange(true);
    setError("");
    try {
      const response = await runWithToast(
        () => apiRequest<SettingsUpdateResponse>("/api/settings", { method: "POST", body: form }),
        "设置保存失败",
      );
      const nextAppearance = normalizeAppearance(response.settings);
      setForm({ ...response.settings, ...nextAppearance });
      setBaseline(nextAppearance);
      onAppearanceSaved(nextAppearance);
      setStatus("saved");
      window.setTimeout(() => setStatus(current => current === "saved" ? "ready" : current), 2500);
    } catch (failure) {
      setForm(current => current ? { ...current, ...baseline } : current);
      onAppearancePreview(baseline);
      setError(`${(failure as RequestFailure).message}，外观已恢复为上次保存状态。`);
      setStatus("error");
    } finally {
      onSavingChange(false);
    }
  };

  if (status === "loading") {
    return (
      <main className="settings-view" aria-busy="true">
        {/* M4 polish 3.4: 改用 Spinner 组件（统一），配 EmptyState 风格包装 */}
        <EmptyState
          icon={<Spinner size="md" tone="primary" decorative label="正在加载设置" />}
          title="正在加载设置…"
          dark={dark}
        />
      </main>
    );
  }
  if (!form) {
    return (
      <main className="settings-view">
        {/* M4 polish 3.4: 加载失败用 EmptyState（全屏式而非 ErrorBanner） */}
        <EmptyState
          icon={<span aria-hidden="true">⚠️</span>}
          title="无法读取设置"
          description={error || "请检查后端服务是否启动，或稍后重试。"}
          actionLabel="重试"
          onAction={loadSettings}
          dark={dark}
        />
      </main>
    );
  }

  const currentAppearance = normalizeAppearance(form);
  const fieldClass = "field-control";

  return (
    <main className="settings-view">
      <header className="view-heading">
        <div><span className="eyebrow">偏好与安全</span><h1>设置</h1><p>工作台外观与海报主题彼此独立，修改应用主色不会改变导出的海报。</p></div>
      </header>

      <div className="settings-grid">
        <section className="settings-card settings-card-wide">
          <div className="section-heading"><span>外观</span><small>即时预览 · 保存失败自动恢复</small></div>
          <fieldset className="appearance-options">
            <legend>显示模式</legend>
            {APPEARANCE_OPTIONS.map(option => (
              <button key={option.id} type="button" aria-pressed={currentAppearance.appearanceMode === option.id}
                className="appearance-choice" onClick={() => updateAppearance({ ...currentAppearance, appearanceMode: option.id })}>
                <strong>{option.label}</strong><span>{option.description}</span>
              </button>
            ))}
          </fieldset>
          <fieldset className="accent-options">
            <legend>应用主色</legend>
            {ACCENT_OPTIONS.map(option => (
              <button key={option.id} type="button" aria-pressed={currentAppearance.applicationAccentId === option.id}
                className="accent-choice" onClick={() => updateAppearance({ ...currentAppearance, applicationAccentId: option.id })}>
                <span className="accent-swatch" style={{ background: dark ? option.dark : option.light }} aria-hidden="true" />
                <span>{option.label}</span>
              </button>
            ))}
          </fieldset>
          <p className="field-note">传统色只用于导航、按钮、焦点与选中态；海报继续使用各主题自己的五角色 Palette。</p>
        </section>

        <section className="settings-card">
          <div className="section-heading"><span>输出</span></div>
          <label className="field-label">输出目录<input className={fieldClass} type="text" value={form.output_dir} onChange={event => setForm({ ...form, output_dir: event.target.value })} /></label>
          <div className="field-pair">
            <label className="field-label">默认画布<select className={fieldClass} value={form.default_canvas} onChange={event => setForm({ ...form, default_canvas: event.target.value })}>{CANVAS_OPTIONS.map(item => <option key={item}>{item}</option>)}</select></label>
            <label className="field-label">默认主题<select className={fieldClass} value={form.default_theme} onChange={event => setForm({ ...form, default_theme: event.target.value })}>{themes.map(theme => <option key={theme.name}>{theme.name}</option>)}</select></label>
          </div>
          <p className="field-note">默认值仅在没有上次工作区记录时生效。</p>
        </section>

        <DataDirPanel />

        <WebDavPanel />

        <section className="settings-card">
          <div className="section-heading"><span>数据与安全</span></div>          <label className="field-label">自动备份保留份数<input className={`${fieldClass} short-field`} type="number" min={0} max={100} value={form.backup_count} onChange={event => setForm({ ...form, backup_count: Math.max(0, Math.min(100, Number(event.target.value) || 0)) })} /></label>
          <p className="field-note">每次变更歌曲数据前自动备份，超出数量后滚动清理；设为 0 可停用新备份。</p>
        </section>

        {/* 1.2 导出历史完整列表（专家评审 P1 #1 收口） */}
        <section className="settings-card settings-card-wide">
          <ExportHistoryView dark={dark} />
        </section>

        <section className="settings-card settings-card-wide">
          <div className="section-heading"><span>高级</span></div>
          <label className="field-label">字体文件路径<input className={fieldClass} type="text" value={form.font_path} onChange={event => setForm({ ...form, font_path: event.target.value })} /></label>
          <p className="field-note warning-note">更换字体会改变海报像素输出，且需重启后端生效；当前仍使用内置猫啃糖圆体。</p>
          <label className="field-label">渲染线程数（规划中）<input className={`${fieldClass} short-field`} type="number" value={form.render_threads} disabled /></label>
        </section>
      </div>

      <footer className="settings-actions">
        <button type="button" className="primary-action" disabled={status === "saving"} onClick={save}>{status === "saving" ? "保存中…" : "保存设置"}</button>
        <span className="save-status" aria-live="polite">{status === "saved" ? "设置已保存" : status === "error" ? error : "更改会先预览，保存后永久生效"}</span>
      </footer>
    </main>
  );
}
