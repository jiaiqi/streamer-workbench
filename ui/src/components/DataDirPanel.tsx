import { useEffect, useState } from "react";
import { ApiClientError, apiRequest } from "../api/client";
import type {
  DataDirInspectResponse,
  DataDirStatusResponse,
  DataDirSwitchResponse,
} from "../api/generated";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import Spinner from "./Spinner";

/* ---- 数据目录面板（R0.9 / 主规格 §11.5.3）----
   契约：验证失败不切换、不丢数据；切换只写启动配置，重启后端后生效。
   Web 开发模式手动输入绝对路径；Electron 原生目录选择器随 R2.6 接入。
   UI 组件优先使用 shadcn/ui（见 AGENTS.md 技术栈）。 */

type Phase =
  | { kind: "loading" }
  | { kind: "ready" }
  | { kind: "inspecting" }
  | { kind: "switching" }
  | { kind: "error"; message: string };

export default function DataDirPanel() {
  const [status, setStatus] = useState<DataDirStatusResponse | null>(null);
  const [phase, setPhase] = useState<Phase>({ kind: "loading" });
  const [path, setPath] = useState("");
  const [inspection, setInspection] = useState<DataDirInspectResponse | null>(null);
  const [migrate, setMigrate] = useState(false);
  const [conflictItems, setConflictItems] = useState<string[]>([]);
  const [done, setDone] = useState<DataDirSwitchResponse | null>(null);

  useEffect(() => {
    let active = true;
    apiRequest<DataDirStatusResponse>("/api/settings/data-dir")
      .then(result => {
        if (!active) return;
        setStatus(result);
        setPhase({ kind: "ready" });
      })
      .catch(reason => {
        if (!active) return;
        setPhase({
          kind: "error",
          message: reason instanceof Error ? reason.message : "数据目录状态加载失败",
        });
      });
    return () => { active = false; };
  }, []);

  const busy = phase.kind === "inspecting" || phase.kind === "switching";

  const inspect = async () => {
    setPhase({ kind: "inspecting" });
    setInspection(null);
    setConflictItems([]);
    setDone(null);
    try {
      const result = await apiRequest<DataDirInspectResponse>(
        "/api/settings/data-dir/inspect", { method: "POST", body: { path } });
      setInspection(result);
      setPhase({ kind: "ready" });
    } catch (reason) {
      setPhase({
        kind: "error",
        message: reason instanceof Error ? reason.message : "目录验证失败",
      });
    }
  };

  const switchDir = async (useExisting: boolean) => {
    setPhase({ kind: "switching" });
    setConflictItems([]);
    try {
      const result = await apiRequest<DataDirSwitchResponse>(
        "/api/settings/data-dir",
        { method: "POST", body: { path, migrate, use_existing: useExisting } });
      setDone(result);
      setInspection(null);
      setPhase({ kind: "ready" });
    } catch (reason) {
      if (reason instanceof ApiClientError && reason.code === "data_dir_conflict") {
        const items = reason.details.existing_items;
        setConflictItems(Array.isArray(items) ? items.map(String) : []);
        setPhase({ kind: "ready" });
        return;
      }
      setPhase({
        kind: "error",
        message: reason instanceof Error ? reason.message : "切换数据目录失败",
      });
    }
  };

  if (phase.kind === "loading") {
    return (
      <section className="settings-card settings-card-wide" aria-busy="true">
        <div className="section-heading"><span>数据目录</span></div>
        <p className="field-note">
          {/* 3.1 收口：原 <span className="spinner" /> 改用 Spinner 组件 */}
          <Spinner size="sm" tone="current" decorative label="正在读取数据目录" /> 正在读取数据目录…
        </p>
      </section>
    );
  }

  return (
    <section className="settings-card settings-card-wide">
      <div className="section-heading">
        <span>数据目录</span>
        <small>验证失败不切换 · 迁移只复制不删除 · 重启后生效</small>
      </div>

      {status && (
        <div className="field-pair">
          <div className="mt-3 grid gap-1.5">
            <Label htmlFor="data-dir-current">当前目录</Label>
            <Input id="data-dir-current" className="min-h-11" value={status.current} readOnly />
          </div>
          <div className="mt-3 grid gap-1.5">
            <Label htmlFor="data-dir-source">来源</Label>
            <Input id="data-dir-source" className="min-h-11" value={status.source_label} readOnly />
          </div>
        </div>
      )}
      {status?.pinned && (
        <p className="field-note warning-note">
          当前目录由{status.source_label}指定，优先级高于启动配置；在此处切换不会生效，需调整启动方式。
        </p>
      )}

      <div className="mt-3 grid gap-1.5">
        <Label htmlFor="data-dir-target">新目录（绝对路径）</Label>
        <Input id="data-dir-target" className="min-h-11" value={path}
          placeholder={status?.platform_default ?? "/绝对/路径/streamer-workbench"}
          onChange={event => {
            setPath(event.target.value);
            setInspection(null);
            setConflictItems([]);
            setDone(null);
          }} />
      </div>

      <div className="settings-inline-actions">
        <Button type="button" variant="outline" className="min-h-11"
          disabled={busy || !path.trim()} onClick={inspect}>
          {phase.kind === "inspecting" ? "验证中…" : "验证目录"}
        </Button>
        {inspection?.valid && inspection.will_initialize && (
          <Button type="button" className="min-h-11" disabled={busy}
            onClick={() => switchDir(false)}>
            {phase.kind === "switching" ? "切换中…" : "切换到该目录"}
          </Button>
        )}
      </div>

      {inspection && !inspection.valid && (
        <p className="field-note warning-note" role="alert">{inspection.message}</p>
      )}
      {inspection?.valid && inspection.will_initialize && (
        <>
          <p className="field-note">
            空目录：切换时自动创建 songs/events/tabs/presets/backups/output 标准结构。
          </p>
          <div className="mt-3 flex items-center gap-2">
            <Checkbox id="data-dir-migrate" checked={migrate}
              onCheckedChange={checked => setMigrate(checked === true)} />
            <Label htmlFor="data-dir-migrate" className="text-muted-foreground font-normal">
              把当前数据复制到新目录（原目录保留不动）
            </Label>
          </div>
        </>
      )}
      {(inspection?.valid && inspection.has_existing_data) || conflictItems.length > 0 ? (
        <div className="state-panel state-error" role="alert">
          <strong>目标目录已有数据</strong>
          <span>
            发现：{(conflictItems.length > 0 ? conflictItems : inspection?.existing_items ?? []).join("、")}
          </span>
          <span>直接使用该目录的数据，或换一个空目录迁移当前数据。</span>
          <Button type="button" variant="outline" className="min-h-11" disabled={busy}
            onClick={() => { setMigrate(false); void switchDir(true); }}>
            我已确认，使用已有数据切换
          </Button>
        </div>
      ) : null}

      {done && (
        <p className="field-note" role="status">
          已写入启动配置（{done.startup_config}），重启后端后使用新目录：{done.data_root}
          {(done.migrated ?? []).length > 0 && `；已复制：${(done.migrated ?? []).join("、")}`}
          {done.used_existing && "；将使用该目录已有数据"}。
        </p>
      )}
      {phase.kind === "error" && (
        <p className="field-note warning-note" role="alert">{phase.message}</p>
      )}
      <p className="field-note">
        Electron 桌面版将提供原生目录选择器；当前请手动输入绝对路径。
      </p>
    </section>
  );
}
