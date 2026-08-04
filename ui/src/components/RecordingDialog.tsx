/// R8.2.x 弹唱录屏 Dialog。
///
/// 4 个状态：
/// - idle：源选择 + 含音频 + 开始
/// - recording / paused：当前计时 + 文件数 + 暂停/停止
/// - stopping：loading
/// - stopped：完成态 — 列文件 + 「在 Finder 中显示」按钮
///
/// 不在 Electron 模式：显示说明 + 指引「请用 desktop shell 启动」。
import { useEffect } from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
  formatElapsed, formatBytes,
  useRecording, type UseRecordingOptions,
} from "../hooks/useRecording";

interface RecordingDialogProps {
  open: boolean;
  onClose: () => void;
  options?: UseRecordingOptions;
}

export default function RecordingDialog({ open, onClose, options }: RecordingDialogProps) {
  const r = useRecording(options);

  useEffect(() => {
    if (open) {
      void r.refreshSources();
      void r.refreshHistory();
    }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleStart = async (sourceId: string, sourceName: string,
                            includeAudio: boolean) => {
    await r.start({ sourceId, sourceName, includeAudio });
  };

  const handleStop = async () => {
    await r.stop();
  };

  // ── 渲染 ──

  const renderUnsupported = () => (
    <div className="grid gap-2 text-sm" data-testid="recording-unsupported">
      <p>当前不在 Electron 桌面模式，录屏功能不可用。</p>
      <p className="text-muted-foreground">
        请用 <code>npm start</code> 启动 desktop shell 后再打开本弹窗。
      </p>
    </div>
  );

  const renderIdle = () => {
    return (
      <div className="grid gap-3" data-testid="recording-idle">
        <div className="grid gap-1.5">
          <Label htmlFor="recording-source">录制源</Label>
          <select
            id="recording-source"
            className="border rounded px-2 py-1 text-sm"
            value={r.sources[0]?.id ?? ""}
            data-testid="recording-source-select"
            disabled={r.sourcesLoading || r.sources.length === 0}
          >
            {r.sources.length === 0 && (
              <option value="">{r.sourcesLoading ? "加载中…" : "暂无可用源"}</option>
            )}
            {r.sources.map(s => (
              <option key={s.id} value={s.id}>
                {s.isScreen ? "🖥 " : "🪟 "}{s.name}
              </option>
            ))}
          </select>
          {r.sourcesError && (
            <p className="text-xs text-destructive" role="alert">
              {r.sourcesError}（首次录屏需在 macOS「系统设置 → 隐私与安全性 → 屏幕录制」允许）
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Checkbox
            id="recording-include-audio"
            defaultChecked
            data-testid="recording-include-audio"
          />
          <Label htmlFor="recording-include-audio" className="font-normal text-sm">
            包含系统音频（推荐；录到观众号那侧的直播声音）
          </Label>
        </div>
        <p className="text-xs text-muted-foreground">
          视频编码 VP9 / 音频 Opus；容器 webm；4Mbps 视频码率；
          每 1GB 自动分文件（SRT 字幕按 LRC 时间戳生成）
        </p>
      </div>
    );
  };

  const renderActive = () => (
    <div className="grid gap-3" data-testid="recording-active">
      <div className="flex items-center gap-3 text-sm">
        <span
          className="inline-block w-2.5 h-2.5 rounded-full bg-red-500 animate-pulse"
          aria-label="录制中"
        />
        <span className="font-mono text-lg tabular-nums" data-testid="recording-elapsed">
          {formatElapsed(r.elapsedMs)}
        </span>
        <span className="text-muted-foreground text-xs">
          {r.status === "paused" ? "已暂停" : "录制中"} · 段 #{r.segmentIndex}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div>
          <div className="text-muted-foreground">本段</div>
          <div className="font-mono tabular-nums">
            {formatBytes(r.currentBytes)}
          </div>
        </div>
        <div>
          <div className="text-muted-foreground">累计</div>
          <div className="font-mono tabular-nums">
            {formatBytes(r.totalBytes)}
          </div>
        </div>
      </div>
      <p className="text-xs text-muted-foreground truncate" title={r.outputDir}>
        目录：{r.outputDir}
      </p>
    </div>
  );

  const renderStopped = () => (
    <div className="grid gap-3" data-testid="recording-stopped">
      <p className="text-sm">
        ✓ 录制完成，{r.files.length} 个文件已写入：
      </p>
      <ul className="grid gap-1.5 max-h-60 overflow-y-auto">
        {r.files.map(f => (
          <li
            key={f.path}
            className="flex items-center justify-between gap-2 text-xs bg-muted/50 rounded px-2 py-1.5"
            data-testid={`recording-file-${f.name}`}
          >
            <div className="grid gap-0.5 min-w-0 flex-1">
              <span className="font-mono truncate">{f.name}</span>
              <span className="text-muted-foreground text-[10px]">
                {formatBytes(f.bytes)}{f.isSrt ? " · 字幕" : " · 视频"}
              </span>
            </div>
            <Button
              type="button" variant="outline" size="sm"
              onClick={() => revealInFinder(f.path)}
              data-testid={`recording-reveal-${f.name}`}
            >
              在 Finder 中显示
            </Button>
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted-foreground">
        SRT 字幕基于 LRC 时间戳生成；可导入剪辑软件（Final Cut / 剪映 / Premiere 全部支持）
      </p>
    </div>
  );

  const renderError = () => (
    <div className="grid gap-2 text-sm" data-testid="recording-error">
      <p className="text-destructive">录制出错：{r.errorMessage}</p>
      <p className="text-muted-foreground text-xs">
        常见原因：macOS 未授权屏幕录制；源被关闭；磁盘空间不足
      </p>
    </div>
  );

  // 弹窗打开时若状态是 stopped 允许点"关闭"清空回 idle
  const handleClose = () => {
    if (r.status === "stopped" || r.status === "error") {
      r.reset();
    }
    onClose();
  };

  return (
    <Dialog open={open} onOpenChange={o => { if (!o) handleClose(); }}>
      <DialogContent className="sm:max-w-[520px] max-h-[85vh] overflow-hidden flex flex-col"
        data-testid="recording-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span
              className={`inline-block w-2.5 h-2.5 rounded-full ${
                r.status === "recording"
                  ? "bg-red-500 animate-pulse"
                  : r.status === "paused"
                    ? "bg-amber-500"
                    : "bg-muted-foreground/40"
              }`}
              aria-hidden="true"
            />
            录制
            {r.status === "recording" && (
              <span className="text-xs font-normal text-muted-foreground font-mono">
                {formatElapsed(r.elapsedMs)}
              </span>
            )}
            {r.status === "paused" && (
              <span className="text-xs font-normal text-amber-500">已暂停</span>
            )}
          </DialogTitle>
        </DialogHeader>

        <div className="overflow-y-auto px-1">
          {(r.status === "idle" || r.status === "starting") && renderIdle()}
          {(r.status === "recording" || r.status === "paused") && renderActive()}
          {r.status === "stopping" && (
            <p className="text-sm text-muted-foreground py-4 text-center" data-testid="recording-stopping">
              正在停止…
            </p>
          )}
          {r.status === "stopped" && renderStopped()}
          {r.status === "error" && renderError()}
          {r.status === "unsupported" && renderUnsupported()}
        </div>

        <DialogFooter className="flex-shrink-0">
          {r.status === "idle" && (
            <>
              <Button type="button" variant="ghost" onClick={handleClose}
                data-testid="recording-cancel-button">
                取消
              </Button>
              <Button type="button" onClick={() => {
                const sel = document.getElementById("recording-source") as HTMLSelectElement | null;
                const sourceId = sel?.value || r.sources[0]?.id;
                const sourceName = sel?.selectedOptions[0]?.text || r.sources[0]?.name;
                const audioCheckbox = document.getElementById("recording-include-audio") as HTMLInputElement | null;
                const includeAudio = audioCheckbox?.checked ?? true;
                if (sourceId) void handleStart(sourceId, sourceName || "(unknown)", includeAudio);
              }} disabled={r.sources.length === 0 || r.status === "starting"}
                data-testid="recording-start-button">
                {r.status === "starting" ? "启动中…" : "开始录制"}
              </Button>
            </>
          )}
          {r.status === "recording" && (
            <>
              <Button type="button" variant="ghost" onClick={() => void r.pause()}
                data-testid="recording-pause-button">暂停</Button>
              <Button type="button" variant="destructive" onClick={() => void handleStop()}
                data-testid="recording-stop-button">停止</Button>
            </>
          )}
          {r.status === "paused" && (
            <>
              <Button type="button" variant="ghost" onClick={() => void r.resume()}
                data-testid="recording-resume-button">继续</Button>
              <Button type="button" variant="destructive" onClick={() => void handleStop()}
                data-testid="recording-stop-button">停止</Button>
            </>
          )}
          {r.status === "stopped" && (
            <Button type="button" onClick={handleClose}
              data-testid="recording-close-button">完成</Button>
          )}
          {r.status === "error" && (
            <>
              <Button type="button" variant="ghost" onClick={handleClose}
                data-testid="recording-cancel-button">关闭</Button>
              <Button type="button" onClick={() => r.reset()}
                data-testid="recording-retry-button">重试</Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// 工具：从 streamer IPC 调 revealInFinder
function revealInFinder(filePath: string) {
  const w = window as { streamer?: {
    revealInFinder: (params: { filePath: string }) => Promise<unknown>;
  } };
  void w.streamer?.revealInFinder({ filePath })?.catch(() => { /* noop */ });
}
