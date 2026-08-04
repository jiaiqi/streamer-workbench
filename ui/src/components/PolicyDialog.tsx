/// M2.4 点歌条件配置弹窗。
///
/// 4 字段（cooldown / max_queue / per_song / per_user），每条都有：
/// - 数字 input
/// - 「不限」toggle（值为 0）
/// - 说明 tooltip
///
/// 设计要点：
/// - 不在"不限"时显示数字 input（占位 "0" 即可，避免误以为"必填"）
/// - 0 = 不限（RequestPolicy 内部约定）
/// - 提交后调 POST /api/live-sessions/{id}/policy，server 自动 bump rule_version
/// - 失败透传 toast（M2.6 useApiError 双通道）
import { useEffect, useState } from "react";
import { apiRequest } from "../api/client";
import { useApiError } from "../async/useApiError";
import { useToast, type ToastApi } from "./Toast";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/** useToast 在 ToastProvider 外时返回 no-op（M2.4 让 PolicyDialog 在裸环境渲染不崩）。 */
function useSafeToast(): ToastApi {
  let toast: ToastApi;
  try {
    toast = useToast();
  } catch {
    toast = {
      success: () => undefined,
      error: () => undefined,
      warn: () => undefined,
      info: () => undefined,
    };
  }
  return toast;
}

export interface PolicyDialogProps {
  open: boolean;
  onClose: () => void;
  sessionId: string | null;
  onUpdated: () => void | Promise<void>;
}

interface Policy {
  cooldown_seconds_per_user: number;
  max_queue_length: number;
  per_song_max_per_session: number;
  per_user_max_in_queue: number;
  rule_version?: string;
}

interface FieldProps {
  name: keyof Policy;
  label: string;
  tooltip: string;
  unit: string;
  value: number;
  onChange: (v: number) => void;
}

/** 一个数字字段，0 = 不限（占位 "0"）。 */
function NumberField({ name, label, tooltip, unit, value, onChange }: FieldProps) {
  return (
    <div className="grid gap-1.5" data-testid={`policy-field-${name}`}>
      <div className="flex items-baseline justify-between">
        <Label htmlFor={`policy-${name}`} className="text-sm font-medium">
          {label}
        </Label>
        <span className="text-[11px] text-muted-foreground" title={tooltip}>
          {value === 0 ? "不限" : `${value} ${unit}`}
        </span>
      </div>
      <Input
        id={`policy-${name}`}
        type="number"
        min={0}
        step={name === "cooldown_seconds_per_user" ? 1 : 1}
        value={value === 0 ? "" : value}
        placeholder="0 = 不限"
        onChange={e => {
          const raw = e.target.value.trim();
          if (raw === "") return onChange(0);
          const n = Number(raw);
          if (!Number.isFinite(n) || n < 0) return;
          onChange(Math.floor(n));
        }}
        className="tabular-nums"
        data-testid={`policy-input-${name}`}
      />
    </div>
  );
}

export default function PolicyDialog({
  open, onClose, sessionId, onUpdated,
}: PolicyDialogProps) {
  const { runWithToast } = useApiError();
  const toast = useSafeToast();
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [draft, setDraft] = useState<Policy | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [inlineError, setInlineError] = useState("");

  // 打开时拉一次
  useEffect(() => {
    if (!open || !sessionId) {
      setPolicy(null);
      setDraft(null);
      setInlineError("");
      return;
    }
    setLoading(true);
    setInlineError("");
    apiRequest<Policy>(`/api/live-sessions/${sessionId}/policy`, { method: "GET" })
      .then(p => {
        setPolicy(p);
        setDraft(p);
      })
      .catch(reason => {
        setInlineError("加载规则失败");
        // 透传给 toast 通道，但不 rethrow（避免 unhandled rejection）
        void runWithToast(() => Promise.reject(reason), "加载规则失败")
          .catch(() => undefined);
      })
      .finally(() => setLoading(false));
  }, [open, sessionId, runWithToast]);

  const setField = (name: keyof Policy, v: number) => {
    setDraft(prev => (prev ? { ...prev, [name]: v } : prev));
  };

  const handleSave = async () => {
    if (!sessionId || !draft) return;
    setSaving(true);
    setInlineError("");
    try {
      const updated = await runWithToast(
        () => apiRequest<Policy>(`/api/live-sessions/${sessionId}/policy`, {
          method: "POST",
          body: {
            cooldown_seconds_per_user: draft.cooldown_seconds_per_user,
            max_queue_length: draft.max_queue_length,
            per_song_max_per_session: draft.per_song_max_per_session,
            per_user_max_in_queue: draft.per_user_max_in_queue,
          },
        }),
        "保存规则失败",
      );
      setPolicy(updated);
      setDraft(updated);
      const changed = policy && (
        policy.cooldown_seconds_per_user !== updated.cooldown_seconds_per_user
        || policy.max_queue_length !== updated.max_queue_length
        || policy.per_song_max_per_session !== updated.per_song_max_per_session
        || policy.per_user_max_in_queue !== updated.per_user_max_in_queue
      );
      toast.success(
        changed ? "规则已更新" : "规则未变化（无新版本）",
        `version ${updated.rule_version?.slice(0, 16) ?? ""}…`,
      );
      await onUpdated();
    } catch {
      setInlineError("保存失败，请重试");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    setDraft(policy);
    setInlineError("");
  };

  const dirty = policy && draft && (
    policy.cooldown_seconds_per_user !== draft.cooldown_seconds_per_user
    || policy.max_queue_length !== draft.max_queue_length
    || policy.per_song_max_per_session !== draft.per_song_max_per_session
    || policy.per_user_max_in_queue !== draft.per_user_max_in_queue
  );

  return (
    <Dialog open={open} onOpenChange={o => { if (!o) onClose(); }}>
      <DialogContent
        className="sm:max-w-[480px] max-h-[85vh] overflow-hidden flex flex-col"
        data-testid="policy-dialog"
      >
        <DialogHeader>
          <DialogTitle>点歌规则</DialogTitle>
        </DialogHeader>

        <p className="text-xs text-muted-foreground -mt-2 mb-3">
          0 = 不限。仅影响观众点歌；主播手动加歌始终允许。
        </p>

        {loading && (
          <p className="text-sm text-muted-foreground py-6 text-center" data-testid="policy-loading">
            加载中…
          </p>
        )}

        {!loading && draft && (
          <div className="grid grid-cols-2 gap-3">
            <NumberField
              name="cooldown_seconds_per_user"
              label="同用户冷却"
              tooltip="同一用户两次入队的最小间隔（秒）"
              unit="秒"
              value={draft.cooldown_seconds_per_user}
              onChange={v => setField("cooldown_seconds_per_user", v)}
            />
            <NumberField
              name="max_queue_length"
              label="队列上限"
              tooltip="队列总长上限（不含正在演唱）"
              unit="首"
              value={draft.max_queue_length}
              onChange={v => setField("max_queue_length", v)}
            />
            <NumberField
              name="per_song_max_per_session"
              label="单歌单场被点"
              tooltip="同一首歌在一场直播中累计被点上限"
              unit="次"
              value={draft.per_song_max_per_session}
              onChange={v => setField("per_song_max_per_session", v)}
            />
            <NumberField
              name="per_user_max_in_queue"
              label="同用户在场已点"
              tooltip="同一用户在同一场直播中已点（未唱）上限"
              unit="首"
              value={draft.per_user_max_in_queue}
              onChange={v => setField("per_user_max_in_queue", v)}
            />
          </div>
        )}

        {inlineError && (
          <p className="text-sm text-destructive mt-2" role="alert" data-testid="policy-error">
            {inlineError}
          </p>
        )}

        <DialogFooter className="flex-shrink-0">
          <Button type="button" variant="ghost" onClick={onClose} disabled={saving}>
            关闭
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={handleReset}
            disabled={!dirty || saving}
            data-testid="policy-reset-button"
          >
            重置
          </Button>
          <Button
            type="button"
            onClick={handleSave}
            disabled={!draft || !dirty || saving || loading}
            data-testid="policy-save-button"
          >
            {saving ? "保存中…" : "保存"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
