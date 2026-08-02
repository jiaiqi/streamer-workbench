/// L1.4 通用确认对话框
///
/// 用于「放弃未保存改动 / 删除 / 关闭会话」等破坏性操作的二次确认。
/// 基于 shadcn/ui Dialog + Button（自带焦点锁定 + Escape + a11y）。
///
/// 用法：
///   <ConfirmDialog
///     open={confirmOpen}
///     onClose={() => setConfirmOpen(false)}
///     onConfirm={handleDiscard}
///     title="放弃未保存的改动？"
///     description="关闭后已修改的内容将丢失。"
///     confirmLabel="放弃改动"
///     confirmVariant="destructive"
///   />
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Button } from "./ui/button";

export interface ConfirmDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  description?: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  /** 确认按钮变体：destructive（红）= 危险操作；default（emerald）= 普通确认 */
  confirmVariant?: "default" | "destructive";
}

export default function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmLabel = "确认",
  cancelLabel = "取消",
  confirmVariant = "default",
}: ConfirmDialogProps) {
  const handleConfirm = () => {
    onConfirm();
    onClose();
  };

  return (
    <Dialog open={open} onOpenChange={o => { if (!o) onClose(); }}>
      <DialogContent className="sm:max-w-[420px]"
        data-testid="confirm-dialog">
        <DialogHeader>
          <DialogTitle data-testid="confirm-dialog-title">{title}</DialogTitle>
          {description && (
            <DialogDescription data-testid="confirm-dialog-description">
              {description}
            </DialogDescription>
          )}
        </DialogHeader>
        <DialogFooter className="gap-2">
          <Button type="button" variant="ghost" onClick={onClose}
            data-testid="confirm-dialog-cancel">
            {cancelLabel}
          </Button>
          <Button type="button"
            variant={confirmVariant === "destructive" ? "destructive" : "default"}
            onClick={handleConfirm}
            data-testid="confirm-dialog-confirm">
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
