/// P4 R4: 快速打卡对话框 (记录一次练习)。
///
/// 填入: 练习时长 (分钟) / 自评 (1-5) / 备注。
/// 可选关联歌曲 (从歌曲库选一首).
/// 提交 → POST /api/practice/log.
import { useState } from "react";
import { apiRequest } from "../api/client";
import { type RequestFailure } from "../async/requestState";
import { useApiError } from "../async/useApiError";
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
import { Textarea } from "@/components/ui/textarea";

interface PracticeLogDialogProps {
  open: boolean;
  onClose: () => void;
  onSaved: () => Promise<void>;
  songTitle?: string;
}

export default function PracticeLogDialog({ open, onClose, onSaved, songTitle }: PracticeLogDialogProps) {
  // M2.6 错误全局 toast 化
  const { runWithToast } = useApiError();
  const [minutes, setMinutes] = useState("30");
  const [rating, setRating] = useState("0");
  const [note, setNote] = useState(songTitle ? `练习了《${songTitle}》` : "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const save = async () => {
    if (saving) return;
    const m = parseInt(minutes, 10);
    if (!m || m < 1) {
      setError("练习时长至少 1 分钟");
      return;
    }
    const r = parseInt(rating, 10) || 0;
    if (r < 0 || r > 5) {
      setError("自评必须在 0-5 之间");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await runWithToast(
        () => apiRequest("/api/practice/log", {
          method: "POST",
          body: {
            song_id: "",
            title_snapshot: songTitle ?? "",
            minutes: m,
            self_rating: r,
            note: note.trim(),
            occurred_at: "",
          },
        }),
        "打卡失败",
      );
      await onSaved();
      onClose();
    } catch (failure) {
      setError((failure as RequestFailure).message);
    } finally {
      setSaving(false);
    }
  };

  const stars = [1, 2, 3, 4, 5].map(n => (
    <button key={n} type="button"
      className={`text-xl transition-colors cursor-pointer ${n <= parseInt(rating, 10) ? "text-amber-500" : "text-zinc-300"}`}
      onClick={() => setRating(n === parseInt(rating, 10) ? "0" : String(n))}
      aria-label={`${n} 星`}>
      ★
    </button>
  ));

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o && !saving) onClose(); }}>
      <DialogContent className="sm:max-w-[420px]"
        onInteractOutside={e => { if (saving) e.preventDefault(); }}
        onEscapeKeyDown={e => { if (saving) e.preventDefault(); }}>
        <DialogHeader>
          <DialogTitle>{songTitle ? `练习《${songTitle}》` : "记录一次练习"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid gap-1.5">
            <Label className="text-muted-foreground text-xs font-normal">练习时长（分钟）</Label>
            <div className="flex gap-2">
              {[15, 30, 45, 60, 90].map(n => (
                <button key={n} type="button"
                  className={`flex-1 rounded-lg py-2 text-sm font-medium transition-all active:scale-95 ${
                    parseInt(minutes, 10) === n
                      ? "bg-primary text-white"
                      : "bg-muted text-muted-foreground hover:bg-border"
                  }`}
                  onClick={() => setMinutes(String(n))}>
                  {n}
                </button>
              ))}
            </div>
            <Input type="number" min={1} max={999} value={minutes}
              onChange={e => setMinutes(e.target.value)}
              className="mt-1" placeholder="自定义分钟数" />
          </div>

          <div className="grid gap-1.5">
            <Label className="text-muted-foreground text-xs font-normal">自评（点星）</Label>
            <div className="flex gap-1">{stars}</div>
          </div>

          <div className="grid gap-1.5">
            <Label className="text-muted-foreground text-xs font-normal">备注 / 卡点</Label>
            <Textarea rows={3} value={note}
              placeholder="如：副歌和弦转换不顺畅"
              onChange={e => setNote(e.target.value)} className="resize-none" />
          </div>
        </div>

        {error && <p className="text-sm text-destructive" role="alert">{error}</p>}

        <DialogFooter>
          <Button variant="ghost" onClick={() => !saving && onClose()} disabled={saving}>
            取消
          </Button>
          <Button onClick={save} disabled={saving}>
            {saving ? "打卡中…" : "打卡"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
