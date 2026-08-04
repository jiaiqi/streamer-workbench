// R8.2.x 弹唱录屏主进程模块。
//
// 设计目标：
// - 观众视角录屏：desktopCapturer 抓主屏 + 系统音频，1GB 自动切片
// - MediaRecorder 浏览器原生 webm (VP9/Opus)，零新依赖
// - 支持暂停/恢复；LRC 字幕由渲染层收集，主进程停止时统一生成 SRT
// - 产物路径：<data_root>/recordings/<session_or_orphan>/<prefix>-seg<NNN>.webm
//            <data_root>/recordings/<session_or_orphan>/<prefix>.srt
// - 写盘用 fs.WriteStream 流式 append，避免内存里堆 1GB
//
// 状态机：idle → recording ⇄ paused → stopped
//
// macOS 屏幕录制权限：
//   - 首次启动会弹系统级授权（"主播工作台 想录制您的屏幕"）
//   - 用户在「系统设置 → 隐私与安全性 → 屏幕录制」允许后即可
//   - 没权限时 getUserMedia 直接 throw，我们捕获后返回 ok:false
//
// 错误约定（IPC 返回）：
//   { ok: false, code: "permission_denied" | "no_source" | "not_supported" | "internal", error }

const { desktopCapturer } = require("electron");
const { existsSync, mkdirSync, createWriteStream, statSync, unlinkSync, renameSync } = require("fs");
const path = require("path");
const crypto = require("crypto");

// ── 常量 ──────────────────────────────────────────────────────────

const DEFAULT_SEGMENT_BYTES = 1_000_000_000; // 1 GB
const DEFAULT_MIMETYPE = "video/webm;codecs=vp9,opus";
const DEFAULT_VIDEO_BITRATE = 4_000_000;      // 4 Mbps
const DEFAULT_AUDIO_BITRATE = 128_000;        // 128 kbps
const TIMESLICE_MS = 1_000;                   // MediaRecorder timeslice

// ── 工具 ──────────────────────────────────────────────────────────

function _nowPrefix() {
  const d = new Date();
  const pad = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
}

function _newRecordingId() {
  return crypto.randomBytes(8).toString("hex");
}

function _isSafeBackupName(name) {
  if (!name || typeof name !== "string" || name.length > 200) return false;
  if (name.includes("/") || name.includes("\\") || name.includes("..")) return false;
  // null byte
  for (let i = 0; i < name.length; i++) {
    if (name.charCodeAt(i) === 0) return false;
  }
  // 允许字母数字 + . + _ + -
  return /^[A-Za-z0-9._-]+$/.test(name);
}

function _safeSessionId(sid) {
  if (!sid || typeof sid !== "string") return null;
  // 只允许字母数字 + _ + - + .（防 path traversal）
  if (!/^[A-Za-z0-9_.-]{1,64}$/.test(sid)) return null;
  return sid;
}

function _resolveOutputDir(dataRoot, sessionId) {
  const safe = _safeSessionId(sessionId);
  const folder = safe ? `s-${safe}` : "orphan";
  return path.join(dataRoot, "recordings", folder);
}

// ── Manager ───────────────────────────────────────────────────────

class RecordingManager {
  constructor({ dataRoot, log = () => {}, logErr = () => {} } = {}) {
    if (!dataRoot) throw new Error("RecordingManager 需要 dataRoot");
    this._dataRoot = dataRoot;
    this._log = log;
    this._logErr = logErr;
    /** @type {Map<string, ActiveRecording>} */
    this._active = new Map();
  }

  // ── 公共 API ──

  async listSources() {
    if (process.platform === "linux") {
      // Linux 多数 desktop env 不支持 desktopCapturer；返回空数组
      return { ok: true, sources: [], platform: "linux" };
    }
    try {
      const sources = await desktopCapturer.getSources({
        types: ["screen", "window"],
        thumbnailSize: { width: 320, height: 180 },
      });
      return {
        ok: true,
        platform: process.platform,
        sources: sources.map(s => ({
          id: s.id,
          name: s.name,
          isScreen: s.id.startsWith("screen:"),
          thumbnailDataUrl: s.thumbnail && !s.thumbnail.isEmpty()
            ? s.thumbnail.toDataURL()
            : null,
        })),
      };
    } catch (err) {
      this._logErr("desktopCapturer:", err.message);
      return { ok: false, code: "no_source", error: err.message };
    }
  }

  async start({ sourceId, sourceName, includeAudio, sessionId,
                segmentBytes, videoBitsPerSecond, audioBitsPerSecond } = {}) {
    if (this._active.size > 0) {
      return { ok: false, code: "already_recording", error: "已有录制进行中" };
    }
    if (process.platform === "linux") {
      return { ok: false, code: "not_supported", error: "Linux 暂不支持屏幕录制" };
    }

    let stream;
    try {
      stream = await this._buildMediaStream({
        sourceId, includeAudio, videoBitsPerSecond,
      });
    } catch (err) {
      this._logErr("buildMediaStream:", err.message);
      const code = /Permission|NotAllowed/i.test(err.message)
        ? "permission_denied"
        : "internal";
      return { ok: false, code, error: err.message };
    }

    const id = _newRecordingId();
    const outputDir = _resolveOutputDir(this._dataRoot, sessionId);
    try {
      mkdirSync(outputDir, { recursive: true });
    } catch (err) {
      this._cleanupStream(stream);
      return { ok: false, code: "internal", error: `无法创建输出目录: ${err.message}` };
    }

    const startedAt = Date.now();
    const prefix = _nowPrefix();
    const active = {
      id, sourceId, sourceName: sourceName || "(unknown)",
      sessionId: sessionId || null,
      includeAudio: !!includeAudio,
      outputDir, prefix,
      startedAt, segmentIndex: 0,
      stream, currentFile: null, currentWriter: null,
      currentBytes: 0, totalBytes: 0,
      segmentBytes: segmentBytes || DEFAULT_SEGMENT_BYTES,
      status: "recording",
      mimeType: DEFAULT_MIMETYPE,
      videoBitsPerSecond: videoBitsPerSecond || DEFAULT_VIDEO_BITRATE,
      audioBitsPerSecond: audioBitsPerSecond || DEFAULT_AUDIO_BITRATE,
      files: [],
      lrcEvents: [],  // [{ offset_ms, text }] 由渲染层推过来
      pausedAccumMs: 0,
      pausedAt: null,
    };
    this._active.set(id, active);

    this._startSegment(active);
    this._log(`recording ${id} started: source=${active.sourceName} audio=${active.includeAudio} dir=${outputDir}`);
    return {
      ok: true,
      id,
      startedAt,
      outputDir,
      prefix,
      mimeType: active.mimeType,
    };
  }

  pause(id) {
    const a = this._active.get(id);
    if (!a) return { ok: false, code: "not_found", error: "录制不存在" };
    if (a.status !== "recording") {
      return { ok: false, code: "invalid_state", error: `当前状态: ${a.status}` };
    }
    if (a.recorder && a.recorder.state === "recording") {
      try { a.recorder.pause(); } catch (err) {
        return { ok: false, code: "internal", error: err.message };
      }
    }
    a.pausedAt = Date.now();
    a.status = "paused";
    return { ok: true, status: "paused" };
  }

  resume(id) {
    const a = this._active.get(id);
    if (!a) return { ok: false, code: "not_found", error: "录制不存在" };
    if (a.status !== "paused") {
      return { ok: false, code: "invalid_state", error: `当前状态: ${a.status}` };
    }
    if (a.recorder && a.recorder.state === "paused") {
      try { a.recorder.resume(); } catch (err) {
        return { ok: false, code: "internal", error: err.message };
      }
    }
    if (a.pausedAt) {
      a.pausedAccumMs = (a.pausedAccumMs || 0) + (Date.now() - a.pausedAt);
      a.pausedAt = null;
    }
    a.status = "recording";
    return { ok: true, status: "recording" };
  }

  appendLrc(id, events) {
    const a = this._active.get(id);
    if (!a) return { ok: false, code: "not_found" };
    if (!Array.isArray(events)) return { ok: false, code: "invalid_state" };
    for (const e of events) {
      if (typeof e?.offset_ms === "number" && typeof e?.text === "string") {
        a.lrcEvents.push({
          offset_ms: Math.max(0, Math.floor(e.offset_ms)),
          text: e.text.slice(0, 500),  // 防御
        });
      }
    }
    return { ok: true, count: events.length };
  }

  async stop(id) {
    const a = this._active.get(id);
    if (!a) return { ok: false, code: "not_found" };
    if (a.status === "stopped" || a.status === "stopping") {
      return { ok: false, code: "invalid_state", error: `已停止` };
    }
    a.status = "stopping";
    await this._stopCurrentSegment(a);
    this._cleanupStream(a);
    a.status = "stopped";
    a.endedAt = Date.now();

    // 生成 SRT（如果有任何 lrcEvents）
    let srtFile = null;
    if (a.lrcEvents.length > 0) {
      try {
        srtFile = await this._writeSrt(a);
      } catch (err) {
        this._logErr("writeSrt:", err.message);
      }
    }

    this._log(`recording ${id} stopped: ${a.files.length} files, ${a.totalBytes} bytes`);
    const result = {
      ok: true,
      id,
      durationMs: a.endedAt - a.startedAt - (a.pausedAccumMs || 0),
      outputDir: a.outputDir,
      files: a.files.map(f => ({
        name: path.basename(f.path),
        path: f.path,
        bytes: f.bytes,
        index: f.index,
        isSrt: false,
      })),
    };
    if (srtFile) {
      result.files.push({
        name: path.basename(srtFile),
        path: srtFile,
        bytes: statSync(srtFile).size,
        index: -1,
        isSrt: true,
      });
    }
    // 保持 active 状态一段时间（5s）让渲染层可以收尾
    setTimeout(() => this._active.delete(id), 5_000);
    return result;
  }

  getState(id) {
    const a = this._active.get(id);
    if (!a) return { ok: false, code: "not_found" };
    return {
      ok: true,
      id,
      status: a.status,
      startedAt: a.startedAt,
      elapsedMs: _elapsedMs(a),
      currentBytes: a.currentBytes,
      totalBytes: a.totalBytes,
      segmentIndex: a.segmentIndex,
      files: a.files.map(f => path.basename(f.path)),
      sourceName: a.sourceName,
      outputDir: a.outputDir,
    };
  }

  /** 渲染层挂载时调：拿当前活跃录制（如果存在）。 */
  getActive() {
    for (const [id, a] of this._active) {
      if (a.status === "recording" || a.status === "paused") {
        return this.getState(id);
      }
    }
    return { ok: true, active: null };
  }

  _elapsedMs(active) {
    return _elapsedMs(active);
  }

  listFiles(sessionId) {
    const dir = _resolveOutputDir(this._dataRoot, sessionId);
    if (!existsSync(dir)) return { ok: true, files: [] };
    try {
      const { readdirSync } = require("fs");
      const entries = readdirSync(dir)
        .filter(n => /\.(webm|srt)$/i.test(n))
        .map(n => {
          const full = path.join(dir, n);
          const st = statSync(full);
          return {
            name: n,
            path: full,
            bytes: st.size,
            mtime: st.mtimeMs,
            isSrt: /\.srt$/i.test(n),
          };
        })
        .sort((a, b) => a.mtime - b.mtime);
      return { ok: true, dir, files: entries };
    } catch (err) {
      return { ok: false, code: "internal", error: err.message };
    }
  }

  listAllSessions() {
    const root = path.join(this._dataRoot, "recordings");
    if (!existsSync(root)) return { ok: true, sessions: [] };
    try {
      const { readdirSync, statSync: st } = require("fs");
      const entries = readdirSync(root)
        .filter(n => !n.startsWith("."))
        .map(n => {
          const full = path.join(root, n);
          if (!st(full).isDirectory()) return null;
          let sessionId = null;
          if (n.startsWith("s-")) sessionId = n.slice(2);
          // 算总大小
          const files = readdirSync(full).filter(f => /\.(webm|srt)$/i.test(f));
          let totalBytes = 0;
          for (const f of files) {
            try { totalBytes += st(path.join(full, f)).size; } catch { /* skip */ }
          }
          return {
            folder: n,
            sessionId,
            fileCount: files.length,
            totalBytes,
          };
        })
        .filter(Boolean)
        .sort((a, b) => b.totalBytes - a.totalBytes);
      return { ok: true, sessions: entries };
    } catch (err) {
      return { ok: false, code: "internal", error: err.message };
    }
  }

  async deleteFolder(sessionId) {
    const dir = _resolveOutputDir(this._dataRoot, sessionId);
    if (!existsSync(dir)) return { ok: true, deleted: 0 };
    try {
      const { readdirSync, rmdirSync, unlinkSync } = require("fs");
      let deleted = 0;
      for (const f of readdirSync(dir)) {
        try { unlinkSync(path.join(dir, f)); deleted++; } catch { /* skip */ }
      }
      try { rmdirSync(dir); } catch { /* not empty / permission */ }
      return { ok: true, deleted };
    } catch (err) {
      return { ok: false, code: "internal", error: err.message };
    }
  }

  // ── 内部 ──

  async _buildMediaStream({ sourceId, includeAudio, videoBitsPerSecond }) {
    const videoConstraints = {
      audio: false,
      video: {
        mandatory: {
          chromeMediaSource: "desktop",
          chromeMediaSourceId: sourceId,
          maxWidth: 1920,
          maxHeight: 1080,
          maxFrameRate: 30,
        },
      },
    };
    const videoStream = await navigator.mediaDevices.getUserMedia(videoConstraints);
    const tracks = [...videoStream.getVideoTracks()];
    if (includeAudio) {
      try {
        const audioStream = await navigator.mediaDevices.getUserMedia({
          audio: {
            mandatory: {
              chromeMediaSource: "desktop",
            },
          },
          video: false,
        });
        tracks.push(...audioStream.getAudioTracks());
      } catch (err) {
        // 音频失败不阻塞视频
        this._logErr("audio capture failed (continue without audio):", err.message);
      }
    }
    if (tracks.length === 0) throw new Error("no media tracks");
    return new MediaStream(tracks);
  }

  _cleanupStream(active) {
    if (!active.stream) return;
    try {
      active.stream.getTracks().forEach(t => {
        try { t.stop(); } catch { /* noop */ }
      });
    } catch { /* noop */ }
  }

  _startSegment(active) {
    const filename = `${active.prefix}-seg${String(active.segmentIndex).padStart(3, "0")}.webm`;
    const filepath = path.join(active.outputDir, filename);
    const writer = createWriteStream(filepath, { flags: "a" });
    active.currentFile = filepath;
    active.currentWriter = writer;
    active.currentBytes = 0;
    let firstError = null;
    writer.on("error", err => {
      firstError = err;
      this._logErr(`writeStream error: ${err.message}`);
    });

    const recorder = new MediaRecorder(active.stream, {
      mimeType: active.mimeType,
      videoBitsPerSecond: active.videoBitsPerSecond,
      audioBitsPerSecond: active.audioBitsPerSecond,
    });
    active.recorder = recorder;
    recorder.ondataavailable = (e) => {
      if (firstError) return;  // 已失败不再写
      if (!e.data || e.data.size === 0) return;
      e.data.arrayBuffer().then(buf => {
        if (firstError) return;
        const b = Buffer.from(buf);
        active.currentBytes += b.length;
        active.totalBytes += b.length;
        if (!writer.write(b)) {
          // backpressure 暂时忽略（Node stream 内部 buffer 4MB 够用）
        }
        if (active.currentBytes >= active.segmentBytes) {
          this._rotateSegment(active).catch(err => {
            this._logErr("rotate:", err.message);
          });
        }
      }).catch(err => this._logErr("arrayBuffer:", err.message));
    };
    recorder.onerror = (e) => this._logErr("MediaRecorder error:", e?.error?.message || String(e));
    try {
      recorder.start(TIMESLICE_MS);
    } catch (err) {
      this._logErr("recorder.start:", err.message);
      throw err;
    }
  }

  async _rotateSegment(active) {
    if (active.rotating) return;
    active.rotating = true;
    try {
      await this._stopCurrentSegment(active, /*isRotate*/ true);
      active.segmentIndex++;
      if (active.status === "recording" || active.status === "paused") {
        this._startSegment(active);
      }
    } finally {
      active.rotating = false;
    }
  }

  _stopCurrentSegmentPromise(active) {
    return new Promise((resolve) => {
      if (!active.recorder) { resolve(); return; }
      const r = active.recorder;
      if (r.state === "inactive") { resolve(); return; }
      const handleStop = () => { try { r.removeEventListener("stop", handleStop); } catch {} resolve(); };
      r.addEventListener("stop", handleStop);
      try { r.stop(); } catch { resolve(); }
      // 兜底超时
      setTimeout(() => { try { r.removeEventListener("stop", handleStop); } catch {} resolve(); }, 2_000);
    });
  }

  async _stopCurrentSegment(active, isRotate = false) {
    if (!active.recorder) return;
    try {
      if (active.recorder.state !== "inactive") {
        await this._stopCurrentSegmentPromise(active);
      }
    } catch (err) {
      this._logErr("recorder.stop:", err.message);
    }
    if (active.currentWriter) {
      await new Promise((resolve) => {
        try { active.currentWriter.end(resolve); } catch { resolve(); }
      });
      active.currentWriter = null;
    }
    if (active.currentFile && existsSync(active.currentFile)) {
      let bytes = 0;
      try { bytes = statSync(active.currentFile).size; } catch { /* noop */ }
      active.files.push({
        path: active.currentFile,
        bytes,
        index: active.segmentIndex,
      });
    }
    if (!isRotate) {
      active.recorder = null;
    }
  }

  async _writeSrt(active) {
    const filepath = path.join(active.outputDir, `${active.prefix}.srt`);
    const events = active.lrcEvents.slice().sort((a, b) => a.offset_ms - b.offset_ms);
    const blocks = [];
    events.forEach((e, i) => {
      const start = e.offset_ms;
      const end = i + 1 < events.length ? events[i + 1].offset_ms : start + 5_000;
      blocks.push(
        `${i + 1}\n${_msToSrtTime(start)} --> ${_msToSrtTime(end)}\n${e.text}\n`,
      );
    });
    const { writeFile } = require("fs").promises;
    await writeFile(filepath, blocks.join("\n"), "utf-8");
    this._log(`srt written: ${filepath} (${events.length} lines)`);
    return filepath;
  }

  // 内部辅助（用 this._elapsedMs 形式）
}

function _elapsedMs(active) {
  let elapsed = Date.now() - active.startedAt - (active.pausedAccumMs || 0);
  if (active.status === "paused" && active.pausedAt) {
    elapsed -= (Date.now() - active.pausedAt);
  }
  return Math.max(0, elapsed);
}

function _msToSrtTime(ms) {
  const total = Math.max(0, Math.floor(ms));
  const h = Math.floor(total / 3_600_000);
  const m = Math.floor((total % 3_600_000) / 60_000);
  const s = Math.floor((total % 60_000) / 1_000);
  const milli = total % 1_000;
  const pad = n => String(n).padStart(2, "0");
  const pad3 = n => String(n).padStart(3, "0");
  return `${pad(h)}:${pad(m)}:${pad(s)},${pad3(milli)}`;
}

module.exports = { RecordingManager, _msToSrtTime, _elapsedMs,
  _resolveOutputDir, _isSafeBackupName, _safeSessionId };
