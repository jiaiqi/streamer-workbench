/// M2.2 WebDAV 云端同步面板（设置 → 数据与安全 段）。
///
/// 3 个状态机：
/// 1. unconfigured  → 显示「配置」表单（URL / 账号 / 密码 / 远端目录 + 主密码）
/// 2. configured+locked → 显示「解锁」表单（主密码）+ 清除按钮
/// 3. unlocked → 显示已配置概览 + 远端文件列表 + 推送 / 拉取 / 测试 / 清除
///
/// 设计原则：
/// - 在线功能（M2.15 铁律）：检测到 navigator.onLine=false 时禁用所有动作 + toast 提示
/// - 错误透传 toast（M2.6 useApiError 双通道）
/// - 凭证永不入 React state（密码字段保持 local state 不上报；提交后清空）
/// - 主密码用于解锁 + 加密 settings 字段

import { useCallback, useEffect, useState } from "react";
import { ApiClientError, apiRequest } from "../api/client";
import { useApiError } from "../async/useApiError";
import { useToast, type ToastApi } from "./Toast";
import type {
  WebDavConfigResponse,
  WebDavConfigSaveResponse,
  WebDavRemoteListResponse,
  WebDavPushResponse,
  WebDavPullResponse,
  WebDavTestResponse,
} from "../api/generated";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import Spinner from "./Spinner";

function useSafeToast(): ToastApi {
  // useToast() 内部已经做了"未包 Provider 时返回 no-op"的兜底（Toast.tsx:155），
  // 这里直接调用即可，不再 try-catch（早期 try-catch 是 useContext 抛错的临时方案）。
  return useToast();
}

type Phase =
  | { kind: "loading" }
  | { kind: "unconfigured" }
  | { kind: "locked"; updatedAt: string }
  | { kind: "unlocked"; url: string; username: string; remoteDir: string; updatedAt: string }
  | { kind: "error"; message: string };

interface RemoteFile {
  name: string;
  size: number;
  last_modified: string;
  href: string;
}

export default function WebDavPanel({ dark = false }: { dark?: boolean } = {}) {
  const { runWithToast } = useApiError();
  const toast = useSafeToast();
  const [phase, setPhase] = useState<Phase>({ kind: "loading" });
  const [files, setFiles] = useState<RemoteFile[]>([]);
  const [busy, setBusy] = useState<null | "test" | "list" | "push" | "pull" | "save" | "unlock" | "clear" | "autosync">(null);
  const [inlineError, setInlineError] = useState("");
  const [online, setOnline] = useState(
    typeof navigator !== "undefined" ? navigator.onLine : true,
  );

  // 配置表单（unconfigured 状态）
  const [cfg, setCfg] = useState({
    url: "",
    username: "",
    password: "",
    remoteDir: "/backups",
  });
  // 主密码（save / unlock / clear / push / pull 都用）
  const [masterPwd, setMasterPwd] = useState("");
  // M2.4 自动同步状态
  const [autoSync, setAutoSync] = useState<{
    enabled: boolean; interval_minutes: number; direction: "push" | "pull" | "both";
    last_at: string | null; last_status: string | null; last_error: string | null;
    last_remote_name: string | null;
    // P0-1：主密码改存系统密钥环；后端多返两个字段供 UI 展示
    has_master_password?: boolean;
    secret_store_available?: boolean;
    secret_store_backend?: string;
  } | null>(null);

  // M2.15：监听离线
  useEffect(() => {
    if (typeof window === "undefined") return;
    const onOnline = () => setOnline(true);
    const onOffline = () => setOnline(false);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, []);

  // 启动时拉一次脱敏配置
  useEffect(() => {
    let active = true;
    setPhase({ kind: "loading" });
    apiRequest<WebDavConfigResponse>("/api/backup/webdav/config")
      .then(data => {
        if (!active) return;
        if (!data.configured) {
          setPhase({ kind: "unconfigured" });
          return;
        }
        if (data.needs_unlock) {
          setPhase({ kind: "locked", updatedAt: data.updated_at ?? "" });
          return;
        }
        setPhase({
          kind: "unlocked",
          url: data.url ?? "",
          username: data.username ?? "",
          remoteDir: data.remote_dir ?? "",
          updatedAt: data.updated_at ?? "",
        });
      })
      .catch(reason => {
        if (!active) return;
        setPhase({
          kind: "error",
          message: reason instanceof Error ? reason.message : "加载 WebDAV 配置失败",
        });
      });
    return () => { active = false; };
  }, []);

  // M2.4 拉自动同步状态（unlocked / locked 视图都用得到）
  const refreshAutoSync = useCallback(async () => {
    try {
      const data = await apiRequest<{
        enabled: boolean; interval_minutes: number;
        direction: "push" | "pull" | "both";
        last_at: string | null; last_status: string | null; last_error: string | null;
        last_remote_name: string | null;
        has_master_password?: boolean;
        secret_store_available?: boolean;
        secret_store_backend?: string;
      }>("/api/backup/webdav/auto-sync");
      setAutoSync({
        enabled: data.enabled,
        interval_minutes: data.interval_minutes,
        direction: data.direction,
        last_at: data.last_at,
        last_status: data.last_status,
        last_error: data.last_error,
        last_remote_name: data.last_remote_name,
        has_master_password: data.has_master_password,
        secret_store_available: data.secret_store_available,
        secret_store_backend: data.secret_store_backend,
      });
    } catch {
      // 静默 — 自动同步是可选的
    }
  }, []);
  useEffect(() => { void refreshAutoSync(); }, [refreshAutoSync]);

  // M2.4: 自动同步相关 handlers
  const handleAutoSyncChange = useCallback(async (patch: {
    interval_minutes?: number; direction?: "push" | "pull" | "both";
  }) => {
    if (!guardOnline("修改自动同步设置")) return;
    setBusy("autosync");
    setInlineError("");
    try {
      await apiRequest("/api/backup/webdav/auto-sync", {
        method: "POST", body: patch,
      });
      toast.success("自动同步设置已更新");
      await refreshAutoSync();
    } catch (reason) {
      const failure = reason instanceof ApiClientError ? reason : null;
      toast.error("更新失败", failure?.recovery ?? "请稍后重试");
    } finally {
      setBusy(null);
    }
  }, [refreshAutoSync, toast]);

  const handleAutoSyncToggle = useCallback(async (enable: boolean) => {
    if (!guardOnline(enable ? "启用自动同步" : "关闭自动同步")) return;
    if (enable) {
      if (!masterPwd) {
        setInlineError("启用自动同步必须先填写主密码");
        return;
      }
      // P0-1：检查系统密钥环是否可用
      if (autoSync && autoSync.secret_store_available === false) {
        setInlineError(
          `系统密钥环不可用（${autoSync.secret_store_backend ?? "未知"}）; 无法安全存储主密码，自动同步已拒绝`,
        );
        return;
      }
    }
    setBusy("autosync");
    setInlineError("");
    try {
      await apiRequest("/api/backup/webdav/auto-sync", {
        method: "POST",
        body: enable
          ? { enabled: true, master_password: masterPwd }
          : { enabled: false },
      });
      toast.success(enable ? "已启用自动同步" : "已关闭自动同步");
      await refreshAutoSync();
    } catch (reason) {
      const failure = reason instanceof ApiClientError ? reason : null;
      toast.error(enable ? "启用失败" : "关闭失败", failure?.recovery ?? "请稍后重试");
    } finally {
      setBusy(null);
    }
  }, [autoSync, masterPwd, refreshAutoSync, toast]);

  const handleAutoSyncRun = useCallback(async () => {
    if (!guardOnline("立即同步")) return;
    if (!masterPwd) {
      setInlineError("立即同步必须先填写主密码");
      return;
    }
    setBusy("autosync");
    setInlineError("");
    try {
      const r = await apiRequest<{ ok: boolean; result: { error?: string } }>(
        "/api/backup/webdav/auto-sync/run",
        { method: "POST", body: { master_password: masterPwd } },
      );
      if (r.ok) {
        toast.success("同步完成", "已写入远端 / 已从远端拉取");
      } else {
        toast.error("同步失败", r.result?.error ?? "未知错误");
      }
      await refreshAutoSync();
    } catch (reason) {
      const failure = reason instanceof ApiClientError ? reason : null;
      toast.error("同步失败", failure?.recovery ?? "请稍后重试");
    } finally {
      setBusy(null);
    }
  }, [masterPwd, refreshAutoSync, toast]);

  const guardOnline = (action: string): boolean => {
    if (online) return true;
    toast.warn(
      "当前离线",
      `${action} 需要联网，请检查网络后重试`,
    );
    return false;
  };

  // ── 表单提交：保存配置 ──

  const handleSave = async () => {
    if (!guardOnline("保存 WebDAV 配置")) return;
    if (!cfg.url.trim() || !cfg.remoteDir.trim() || !masterPwd) {
      setInlineError("URL / 远端目录 / 主密码必填");
      return;
    }
    setBusy("save");
    setInlineError("");
    try {
      const result = await runWithToast(
        () => apiRequest<WebDavConfigSaveResponse>("/api/backup/webdav/config", {
          method: "PUT",
          body: {
            url: cfg.url.trim(),
            username: cfg.username.trim(),
            password: cfg.password,
            remote_dir: cfg.remoteDir.trim(),
            master_password: masterPwd,
          },
        }),
        "保存 WebDAV 配置失败",
      );
      toast.success(
        "WebDAV 配置已保存",
        `更新于 ${result.updated_at ?? ""}`,
      );
      // 状态切到 unlocked（密码字段清空，保留主密码用于后续动作）
      setCfg(prev => ({ ...prev, password: "" }));
      setPhase({
        kind: "unlocked",
        url: cfg.url.trim(),
        username: cfg.username.trim(),
        remoteDir: cfg.remoteDir.trim(),
        updatedAt: result.updated_at ?? "",
      });
      // 自动拉一次列表
      void refreshList(masterPwd);
    } catch {
      setInlineError("保存失败，请检查字段或主密码");
    } finally {
      setBusy(null);
    }
  };

  // ── 解锁 ──

  const handleUnlock = async () => {
    if (!guardOnline("解锁 WebDAV 配置")) return;
    if (!masterPwd) {
      setInlineError("请输入主密码");
      return;
    }
    setBusy("unlock");
    setInlineError("");
    try {
      const data = await runWithToast(
        () => apiRequest<WebDavConfigResponse>(
          `/api/backup/webdav/config?${new URLSearchParams({ master_password: masterPwd }).toString()}`,
        ),
        "解锁失败",
      );
      if (data.needs_unlock) {
        setInlineError("主密码错误");
        return;
      }
      setPhase({
        kind: "unlocked",
        url: data.url ?? "",
        username: data.username ?? "",
        remoteDir: data.remote_dir ?? "",
        updatedAt: data.updated_at ?? "",
      });
      setMasterPwd("");
      void refreshList(data.url ? masterPwd : "");
    } catch {
      setInlineError("解锁失败");
    } finally {
      setBusy(null);
    }
  };

  // ── 列出远端文件 ──

  const refreshList = async (mp: string) => {
    if (!guardOnline("列出远端备份")) return;
    if (!mp) return;
    setBusy("list");
    try {
      const data = await runWithToast(
        () => apiRequest<WebDavRemoteListResponse>(
          `/api/backup/webdav/list?${new URLSearchParams({ master_password: mp }).toString()}`,
        ),
        "列出远端备份失败",
      );
      setFiles(Array.isArray(data.files) ? data.files : []);
    } catch {
      // 错误已由 toast 提示
    } finally {
      setBusy(null);
    }
  };

  // ── 测试已存连接 ──

  const handleTestSaved = async () => {
    if (!guardOnline("测试连接")) return;
    if (!masterPwd) {
      setInlineError("请先输入主密码");
      return;
    }
    setBusy("test");
    setInlineError("");
    try {
      const result = await runWithToast(
        () => apiRequest<WebDavTestResponse>("/api/backup/webdav/test-saved", {
          method: "POST",
          body: { master_password: masterPwd },
        }),
        "测试连接失败",
      );
      if (result.ok) {
        toast.success("连接成功", `HTTP ${result.status}`);
      } else {
        toast.error("连接失败", result.message);
      }
    } catch {
      // 已 toast
    } finally {
      setBusy(null);
    }
  };

  // ── 临时凭证测试 ──

  const handleTestTemp = async () => {
    if (!guardOnline("测试连接")) return;
    if (!cfg.url.trim()) {
      setInlineError("URL 不能为空");
      return;
    }
    setBusy("test");
    setInlineError("");
    try {
      const result = await runWithToast(
        () => apiRequest<WebDavTestResponse>("/api/backup/webdav/test", {
          method: "POST",
          body: {
            url: cfg.url.trim(),
            username: cfg.username.trim(),
            password: cfg.password,
          },
        }),
        "测试连接失败",
      );
      if (result.ok) {
        toast.success("连接成功", `HTTP ${result.status}`);
      } else {
        toast.error("连接失败", result.message);
      }
    } catch {
      // 已 toast
    } finally {
      setBusy(null);
    }
  };

  // ── 推送 ──

  const handlePush = async () => {
    if (!guardOnline("推送备份")) return;
    if (!masterPwd) {
      setInlineError("请先输入主密码");
      return;
    }
    setBusy("push");
    setInlineError("");
    try {
      const result = await runWithToast(
        () => apiRequest<WebDavPushResponse>("/api/backup/webdav/push", {
          method: "POST",
          body: { master_password: masterPwd },
        }),
        "推送失败",
      );
      toast.success(
        "已推送到云端",
        `${result.remote_name} · ${result.file_count} 个文件`,
      );
      void refreshList(masterPwd);
    } catch {
      // 已 toast
    } finally {
      setBusy(null);
    }
  };

  // ── 拉取 ──

  const handlePull = async (remoteName: string) => {
    if (!guardOnline("拉取备份")) return;
    if (!masterPwd) {
      setInlineError("请先输入主密码");
      return;
    }
    setBusy("pull");
    setInlineError("");
    try {
      const result = await runWithToast(
        () => apiRequest<WebDavPullResponse>("/api/backup/webdav/pull", {
          method: "POST",
          body: { master_password: masterPwd, remote_name: remoteName },
        }),
        "拉取失败",
      );
      toast.success(
        "已从云端拉回",
        `${result.remote_name} · 请重启后端使新数据生效`,
      );
    } catch (reason) {
      // 拉取失败尤其要给清晰提示
      if (reason instanceof ApiClientError && reason.code === "webdav_local_error") {
        toast.error("拉取失败：远端备份包不完整或已损坏", "请检查后再试");
      }
    } finally {
      setBusy(null);
    }
  };

  // ── 清除配置 ──

  const handleClear = async () => {
    if (!masterPwd) {
      setInlineError("请先输入主密码");
      return;
    }
    setBusy("clear");
    setInlineError("");
    try {
      await runWithToast(
        () => apiRequest<WebDavConfigSaveResponse>("/api/backup/webdav/config/clear", {
          method: "POST",
          body: { master_password: masterPwd },
        }),
        "清除配置失败",
      );
      setMasterPwd("");
      setFiles([]);
      setCfg({ url: "", username: "", password: "", remoteDir: "/backups" });
      setPhase({ kind: "unconfigured" });
      toast.success("配置已清除");
    } catch {
      setInlineError("清除失败");
    } finally {
      setBusy(null);
    }
  };

  // ── 渲染 ──

  if (phase.kind === "loading") {
    return (
      <section className="settings-card settings-card-wide" aria-busy="true"
        data-testid="webdav-panel">
        <div className="section-heading">
          <span>云端同步（WebDAV）</span>
          <small>把 .songworkbench 备份推到任意 WebDAV 服务器</small>
        </div>
        <p className="field-note">
          {/* 3.1 收口：原 <span className="spinner" /> 改用 Spinner 组件 */}
          <Spinner size="sm" tone="current" decorative label="正在读取" /> 正在读取…
        </p>
      </section>
    );
  }

  if (phase.kind === "error") {
    return (
      <section className="settings-card settings-card-wide" data-testid="webdav-panel">
        <div className="section-heading"><span>云端同步（WebDAV）</span></div>
        <p className="field-note warning-note" role="alert">{phase.message}</p>
      </section>
    );
  }

  return (
    <section className="settings-card settings-card-wide" data-testid="webdav-panel">
      <div className="section-heading">
        <span>云端同步（WebDAV）</span>
        <small>把 .songworkbench 备份推到任意 WebDAV 服务器 · 凭证用主密码加密存 settings</small>
      </div>

      {!online && (
        <p className="field-note warning-note" data-testid="webdav-offline-banner">
          当前离线，所有云端操作已禁用
        </p>
      )}

      {/* ── 未配置：显示完整配置表单 ── */}
      {phase.kind === "unconfigured" && (
        <div className="grid gap-3" data-testid="webdav-config-form">
          <div className="grid gap-1.5">
            <Label htmlFor="webdav-url">服务器 URL</Label>
            <Input id="webdav-url" placeholder="https://dav.example.com/dav"
              value={cfg.url}
              onChange={e => setCfg({ ...cfg, url: e.target.value })}
              data-testid="webdav-input-url" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="webdav-username">账号（可空）</Label>
              <Input id="webdav-username" placeholder="alice"
                value={cfg.username}
                onChange={e => setCfg({ ...cfg, username: e.target.value })}
                data-testid="webdav-input-username" />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="webdav-password">WebDAV 密码</Label>
              <Input id="webdav-password" type="password" placeholder="服务密码"
                value={cfg.password}
                onChange={e => setCfg({ ...cfg, password: e.target.value })}
                data-testid="webdav-input-password" />
            </div>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="webdav-remote-dir">远端目录（绝对路径）</Label>
            <Input id="webdav-remote-dir" placeholder="/backups"
              value={cfg.remoteDir}
              onChange={e => setCfg({ ...cfg, remoteDir: e.target.value })}
              data-testid="webdav-input-remote-dir" />
            <p className="text-[11px] text-muted-foreground">
              备份会存到此目录下的 <code>backups/</code> 子目录
            </p>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="webdav-master-pwd">主密码（加密本地凭证用）</Label>
            <Input id="webdav-master-pwd" type="password"
              value={masterPwd}
              onChange={e => setMasterPwd(e.target.value)}
              data-testid="webdav-input-master-password" />
            <p className="text-[11px] text-muted-foreground">
              留空则服务端拒绝保存；保存后请记住，后续解锁和同步都靠它
            </p>
          </div>
          <div className="settings-inline-actions">
            <Button type="button" variant="outline" disabled={busy === "test" || !online}
              onClick={handleTestTemp} data-testid="webdav-test-button">
              测试连接
            </Button>
            <Button type="button" disabled={busy === "save" || !online}
              onClick={handleSave} data-testid="webdav-save-button">
              {busy === "save" ? "保存中…" : "保存配置"}
            </Button>
          </div>
          {inlineError && (
            <p className="field-note warning-note" role="alert"
              data-testid="webdav-inline-error">{inlineError}</p>
          )}
        </div>
      )}

      {/* ── 已配置但锁定：只显示主密码 + 清除 ── */}
      {phase.kind === "locked" && (
        <div className="grid gap-3" data-testid="webdav-locked-form">
          <p className="field-note">
            已配置 WebDAV 同步（{phase.updatedAt && `更新于 ${phase.updatedAt.slice(0, 16)}…`}）
          </p>
          <div className="grid gap-1.5">
            <Label htmlFor="webdav-master-pwd-unlock">主密码</Label>
            <Input id="webdav-master-pwd-unlock" type="password"
              value={masterPwd}
              onChange={e => setMasterPwd(e.target.value)}
              data-testid="webdav-input-master-password" />
          </div>
          <div className="settings-inline-actions">
            <Button type="button" disabled={busy === "unlock" || !online}
              onClick={handleUnlock} data-testid="webdav-unlock-button">
              {busy === "unlock" ? "解锁中…" : "解锁"}
            </Button>
            <Button type="button" variant="outline" disabled={busy === "clear" || !online}
              onClick={handleClear} data-testid="webdav-clear-button">
              {busy === "clear" ? "清除中…" : "清除配置"}
            </Button>
          </div>
          {inlineError && (
            <p className="field-note warning-note" role="alert"
              data-testid="webdav-inline-error">{inlineError}</p>
          )}
        </div>
      )}

      {/* ── 已解锁：概览 + 列表 + 推送/拉取/测试/清除 ── */}
      {phase.kind === "unlocked" && (
        <div className="grid gap-3" data-testid="webdav-unlocked-section">
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label>URL</Label>
              <Input value={phase.url} readOnly className="min-h-11 font-mono text-xs" />
            </div>
            <div className="grid gap-1.5">
              <Label>账号</Label>
              <Input value={phase.username || "（匿名）"} readOnly className="min-h-11" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label>远端目录</Label>
              <Input value={phase.remoteDir} readOnly className="min-h-11 font-mono text-xs" />
            </div>
            <div className="grid gap-1.5">
              <Label>更新于</Label>
              <Input value={phase.updatedAt} readOnly className="min-h-11 font-mono text-xs" />
            </div>
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="webdav-master-pwd-keep">主密码（同步前必填）</Label>
            <Input id="webdav-master-pwd-keep" type="password"
              value={masterPwd}
              onChange={e => setMasterPwd(e.target.value)}
              data-testid="webdav-input-master-password"
              placeholder="保存后每次会话需重新输入" />
          </div>

          <div className="settings-inline-actions">
            <Button type="button" variant="outline"
              disabled={busy === "test" || !online || !masterPwd}
              onClick={handleTestSaved} data-testid="webdav-test-saved-button">
              {busy === "test" ? "测试中…" : "测试连接"}
            </Button>
            <Button type="button"
              disabled={busy === "list" || !online || !masterPwd}
              onClick={() => refreshList(masterPwd)} data-testid="webdav-list-button">
              {busy === "list" ? "列出中…" : "列出远端"}
            </Button>
            <Button type="button"
              disabled={busy === "push" || !online || !masterPwd}
              onClick={handlePush} data-testid="webdav-push-button">
              {busy === "push" ? "推送中…" : "推送新备份"}
            </Button>
            <Button type="button" variant="outline"
              disabled={busy === "clear" || !online}
              onClick={handleClear} data-testid="webdav-clear-button">
              {busy === "clear" ? "清除中…" : "清除配置"}
            </Button>
          </div>

          {inlineError && (
            <p className="field-note warning-note" role="alert"
              data-testid="webdav-inline-error">{inlineError}</p>
          )}

          {/* 远端文件列表 */}
          {files.length > 0 && (
            <div className="grid gap-2" data-testid="webdav-files">
              <Label>远端备份（{files.length}）</Label>
              <ul className="grid gap-1.5 max-h-60 overflow-y-auto">
                {files.map(f => (
                  <li key={f.href} className="flex items-center justify-between gap-2
                    text-xs bg-muted/50 rounded px-2 py-1.5"
                    data-testid={`webdav-file-${f.name}`}>
                    <div className="grid gap-0.5 min-w-0 flex-1">
                      <span className="font-mono truncate">{f.name}</span>
                      <span className="text-muted-foreground text-[10px]">
                        {(f.size / 1024).toFixed(1)} KB · {f.last_modified || "未知时间"}
                      </span>
                    </div>
                    <Button type="button" variant="outline" size="sm"
                      disabled={busy === "pull" || !online || !masterPwd}
                      onClick={() => handlePull(f.name)}
                      data-testid={`webdav-pull-${f.name}`}>
                      {busy === "pull" ? "拉取中…" : "拉取"}
                    </Button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {files.length === 0 && busy !== "list" && (
            <p className="field-note text-muted-foreground"
              data-testid="webdav-empty">
              暂无远端备份，点「列出远端」或「推送新备份」开始
            </p>
          )}

          {/* M2.4 自动同步 */}
          <div className="grid gap-2 border-t pt-3" data-testid="webdav-autosync-section">
            <div className="flex items-center justify-between">
              <Label className="font-semibold">自动同步（M2.4）</Label>
              <span className="text-[10px] text-muted-foreground" data-testid="webdav-autosync-status">
                {autoSync?.enabled
                  ? (autoSync.last_status === "success" ? `✅ 上次成功 ${autoSync.last_at ?? ""}`
                     : autoSync.last_status === "failed" ? `❌ 上次失败 ${autoSync.last_at ?? ""}`
                     : autoSync.last_status === "skipped" ? `⏸ 上次跳过 ${autoSync.last_at ?? ""}`
                     : `⏳ 已启用（每 ${autoSync.interval_minutes} 分钟）`)
                  : "未启用"}
              </span>
            </div>
            {autoSync && autoSync.last_error && autoSync.last_status === "failed" && (
              <p className="field-note warning-note text-[11px]"
                data-testid="webdav-autosync-error">
                错误：{autoSync.last_error}
              </p>
            )}
            <div className="grid grid-cols-2 gap-2">
              <div className="grid gap-1.5">
                <Label className="text-xs">间隔</Label>
                <select
                  className={`h-9 text-xs rounded-md border px-2 ${dark ? "bg-zinc-900 border-zinc-700" : "bg-background border-border"}`}
                  value={autoSync?.interval_minutes ?? 60}
                  disabled={busy === "autosync" || !online}
                  onChange={e => void handleAutoSyncChange({
                    interval_minutes: Number(e.target.value),
                  })}
                  data-testid="webdav-autosync-interval"
                >
                  <option value={15}>每 15 分钟</option>
                  <option value={30}>每 30 分钟</option>
                  <option value={60}>每 1 小时</option>
                  <option value={180}>每 3 小时</option>
                  <option value={360}>每 6 小时</option>
                  <option value={720}>每 12 小时</option>
                  <option value={1440}>每 24 小时</option>
                </select>
              </div>
              <div className="grid gap-1.5">
                <Label className="text-xs">方向</Label>
                <select
                  className={`h-9 text-xs rounded-md border px-2 ${dark ? "bg-zinc-900 border-zinc-700" : "bg-background border-border"}`}
                  value={autoSync?.direction ?? "push"}
                  disabled={busy === "autosync" || !online}
                  onChange={e => void handleAutoSyncChange({
                    direction: e.target.value as "push" | "pull" | "both",
                  })}
                  data-testid="webdav-autosync-direction"
                >
                  <option value="push">本地 → 远端（推荐）</option>
                  <option value="pull">远端 → 本地（恢复）</option>
                  <option value="both">双向</option>
                </select>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {autoSync?.enabled ? (
                <Button type="button" variant="outline"
                  disabled={busy === "autosync" || !online || !masterPwd}
                  onClick={() => void handleAutoSyncToggle(false)}
                  data-testid="webdav-autosync-disable">
                  关闭自动同步
                </Button>
              ) : (
                <Button type="button"
                  disabled={busy === "autosync" || !online || !masterPwd
                    || (autoSync?.secret_store_available === false)}
                  onClick={() => void handleAutoSyncToggle(true)}
                  data-testid="webdav-autosync-enable">
                  启用自动同步
                </Button>
              )}
              <Button type="button" variant="outline"
                disabled={busy === "autosync" || !online || !masterPwd}
                onClick={() => void handleAutoSyncRun()}
                data-testid="webdav-autosync-run">
                {busy === "autosync" ? "同步中…" : "立即同步一次"}
              </Button>
            </div>
            {/* P0-1：主密码现在存到系统密钥环；展示 backend 状态 + 不可用时警告 */}
            {autoSync && (
              <p
                className="field-note text-[10px] text-muted-foreground"
                data-testid="webdav-autosync-secret-store"
              >
                {autoSync.secret_store_available === false ? (
                  <span className="text-amber-600 dark:text-amber-400">
                    ⚠ 系统密钥环不可用（{autoSync.secret_store_backend ?? "未知"}）；
                    主密码无法安全存储，自动同步已拒绝启用。
                  </span>
                ) : (
                  <>
                    主密码存到系统密钥环（{autoSync.secret_store_backend ?? "未知"}）；
                    关闭自动同步时自动清除。
                    {autoSync.has_master_password ? "（已存）" : "（未存）"}
                  </>
                )}
              </p>
            )}
          </div>
        </div>
      )}

      <p className="field-note" data-testid="webdav-help">
        兼容 Apache mod_dav / nginx-dav / Nextcloud / ownCloud / 坚果云 等常见 WebDAV 服务。
        主密码丢失意味着已存的凭证无法解密，需要清除后重新配置。
      </p>
    </section>
  );
}
