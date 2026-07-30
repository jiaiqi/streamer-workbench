import { useState } from "react";
import type { Song } from "../types";
import { apiRequest } from "../api/client";
import { toRequestFailure } from "../async/requestState";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

/* ---- 歌曲编辑对话框（增删改全字段，弹唱信息独立分组）----
   基于 shadcn/ui Dialog：自带焦点锁定、Escape、遮罩关闭与 aria 属性。
   保存中禁止关闭；语义令牌驱动亮暗，不再接收 dark prop。 */
export default function SongEditDialog({ target, onClose, onSaved }: {
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

  const field = (id: string, label: React.ReactNode, node: React.ReactNode) => (
    <div className="grid gap-1.5">
      <Label htmlFor={id} className="text-muted-foreground text-xs font-normal">{label}</Label>
      {node}
    </div>
  );

  return (
    <Dialog open onOpenChange={open => { if (!open && !saving) onClose(); }}>
      <DialogContent className="sm:max-w-[460px] max-h-[85vh] overflow-y-auto"
        onInteractOutside={e => { if (saving) e.preventDefault(); }}
        onEscapeKeyDown={e => { if (saving) e.preventDefault(); }}>
        <DialogHeader>
          <DialogTitle>{target === "new" ? "新增歌曲" : `编辑「${target.title}」`}</DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          {field("song-title", <>歌名 <span className="text-destructive">*</span></>,
            <Input id="song-title" value={form.title ?? ""}
              onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />)}

          <div className="grid grid-cols-2 gap-3">
            {field("song-artists", "歌手（逗号分隔）",
              <Input id="song-artists" value={form.artists ?? ""}
                onChange={e => setForm(f => ({ ...f, artists: e.target.value }))} />)}
            <div className="grid gap-1.5">
              <Label className="text-muted-foreground text-xs font-normal">分类</Label>
              <Select value={form.section || "auto"}
                onValueChange={value => setForm(f => ({ ...f, section: value === "auto" ? "" : value }))}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="auto">自动（按字数）</SelectItem>
                  {[1, 2, 3, 4, 5, 6, 7].map(n => (
                    <SelectItem key={n} value={String(n)}>
                      {n === 7 ? "7+（长歌名/英文）" : `${n} 字`}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="rounded-xl bg-muted/60 p-3 space-y-3">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">弹唱信息</p>
            <div className="grid grid-cols-3 gap-3">
              {field("song-key", "选调",
                <Input id="song-key" placeholder="如 G" value={form.key ?? ""}
                  onChange={e => setForm(f => ({ ...f, key: e.target.value }))} />)}
              {field("song-capo", "变调夹（品）",
                <Input id="song-capo" type="number" min={0} max={12} placeholder="空=未填"
                  value={form.capo ?? ""}
                  onChange={e => setForm(f => ({ ...f, capo: e.target.value }))} />)}
              <div className="grid gap-1.5">
                <Label className="text-muted-foreground text-xs font-normal">难度</Label>
                <Select value={form.difficulty || "unset"}
                  onValueChange={value => setForm(f => ({ ...f, difficulty: value === "unset" ? "" : value }))}>
                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="unset">未标</SelectItem>
                    <SelectItem value="简单">简单</SelectItem>
                    <SelectItem value="中等">中等</SelectItem>
                    <SelectItem value="困难">困难</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            {field("song-tabs", "谱子（链接或来源）",
              <Input id="song-tabs" value={form.tabs ?? ""}
                onChange={e => setForm(f => ({ ...f, tabs: e.target.value }))} />)}
          </div>

          <div className="grid grid-cols-2 gap-3">
            {field("song-lyricist", "作词",
              <Input id="song-lyricist" value={form.lyricist ?? ""}
                onChange={e => setForm(f => ({ ...f, lyricist: e.target.value }))} />)}
            {field("song-composer", "作曲",
              <Input id="song-composer" value={form.composer ?? ""}
                onChange={e => setForm(f => ({ ...f, composer: e.target.value }))} />)}
          </div>

          <div className="grid grid-cols-2 gap-3">
            {field("song-tags", "标签（逗号分隔）",
              <Input id="song-tags" placeholder="如：小甜歌，苦情" value={form.tags ?? ""}
                onChange={e => setForm(f => ({ ...f, tags: e.target.value }))} />)}
            {field("song-pinyin", "拼音首字母",
              <Input id="song-pinyin" placeholder="空=自动生成" value={form.pinyin ?? ""}
                onChange={e => setForm(f => ({ ...f, pinyin: e.target.value }))} />)}
          </div>

          {field("song-notes", "备注",
            <Textarea id="song-notes" rows={2} placeholder="如：副歌高音要降 key"
              value={form.notes ?? ""} className="resize-none"
              onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} />)}
        </div>

        {error && <p className="mt-3 text-sm text-destructive" role="alert" aria-live="polite">{error}</p>}

        <DialogFooter>
          <Button type="button" variant="ghost" onClick={() => !saving && onClose()} disabled={saving}>
            取消
          </Button>
          <Button type="button" onClick={save} disabled={saving}>
            {saving ? "保存中…" : "保存"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
