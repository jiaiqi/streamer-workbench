// 主播工作台 — Electron preload
//
// contextIsolation: true, sandbox: true
// 渲染层只能通过 window.streamer.* 调受控 API
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("streamer", {
  /**
   * 打开置顶速查子窗口。
   * @param {string} [sessionId] LiveSession id（可选；不传则使用 localStorage 中记住的）
   */
  openQuickView(sessionId) {
    return ipcRenderer.invoke("quickview:open", sessionId);
  },
  closeQuickView() {
    return ipcRenderer.invoke("quickview:close");
  },
  /**
   * 子窗口订阅主窗口推送的 session id。
   * @param {(sessionId: string) => void} listener
   */
  onQuickViewSession(listener) {
    const wrapped = (_evt, sessionId) => listener(sessionId);
    ipcRenderer.on("quickview:session", wrapped);
    return () => ipcRenderer.removeListener("quickview:session", wrapped);
  },
  /**
   * R4.0.12 海报真保存路径：弹原生保存对话框写盘。
   * @param {{ data: ArrayBuffer, defaultName: string, mimeType?: string }} params
   * @returns {Promise<{ok: boolean, path?: string, cancelled?: boolean, error?: string}>}
   */
  saveFile(params) {
    return ipcRenderer.invoke("dialog:saveFile", params);
  },
  // ===== 海报分享（M2.16） =====
  /**
   * 把 PNG 字节写入系统剪贴板（用户 Cmd+V 即可贴到任何 App：微信、邮件、Pages 等）。
   * @param {{ data: ArrayBuffer }} params
   * @returns {Promise<{ ok: boolean, error?: string }>}
   */
  copyImageToClipboard(params) {
    return ipcRenderer.invoke("clipboard:writeImage", params || {});
  },
  /**
   * 在文件管理器中定位文件（macOS 高亮 / Windows 打开 Explorer / Linux 打开文件管理器）。
   * @param {{ filePath: string }} params
   * @returns {Promise<{ ok: boolean, error?: string }>}
   */
  revealInFinder(params) {
    return ipcRenderer.invoke("shell:showItemInFolder", params || {});
  },
  /**
   * macOS 原生分享面板：调系统级 NSSharingServicePicker（AirDrop / 微信 / 邮件 / 备忘录）。
   * 非 darwin 平台返回 `{ ok: false, code: "unsupported" }`，UI 端应 disabled 按钮。
   * @param {{ data: ArrayBuffer, defaultName?: string }} params
   * @returns {Promise<{ ok: boolean, code?: string, error?: string }>}
   */
  shareToMacOS(params) {
    return ipcRenderer.invoke("share:macosSheet", params || {});
  },
  /**
   * 当前主进程是否支持 macOS Share Sheet（仅 darwin）。
   * 渲染层用此 disable 按钮。
   * @returns {boolean}
   */
  isMacOSShareSupported() {
    return navigator.platform.toLowerCase().includes("mac") ||
      // navigator.userAgent 在 Electron renderer 里有 "Mac OS X"
      /mac/i.test(navigator.userAgent);
  },
  /**
   * M3 海报 UI/UX：macOS Quick Look 预览。
   * 主进程把 PNG bytes 写 tmp + spawn qlmanage -p 弹原生 Quick Look 面板。
   * 非 darwin 返回 `{ ok: false, code: "unsupported" }`。
   * @param {{ data: ArrayBuffer, posterId?: string }} params
   * @returns {Promise<{ ok: boolean, code?: string, error?: string, path?: string }>}
   */
  quickLookPoster(params) {
    return ipcRenderer.invoke("quicklook:open-poster", params || {});
  },
  /**
   * 当前主进程是否支持 Quick Look（仅 darwin）。
   * @returns {boolean}
   */
  isQuickLookSupported() {
    return navigator.platform.toLowerCase().includes("mac") ||
      /mac/i.test(navigator.userAgent);
  },

  // ===== 系统集成首批（桌面平台特性 P0） =====
  /**
   * 渲染层 → 主进程：推当前播放器状态（PlayerContext 同步 + LiveSession 队列数）。
   * 频率 1Hz 即可；主进程会用 diff 决定是否发通知 / 改 dock badge / 刷新菜单。
   * @param {{
   *   isPlaying: boolean,
   *   currentSongId: string | null,
   *   currentTitle: string | null,
   *   currentArtist: string | null,
   *   currentTimeMs: number,
   *   durationMs: number,
   *   queueCount: number,
   *   notifySongChanged?: boolean,  // true 时若 song id 变化则弹系统通知
   *   notifyQueueStarted?: boolean, // true 时若队列 0→>0 则弹直播开始通知
   * }} state
   */
  sendPlayerState(state) {
    ipcRenderer.send("player:state", state);
  },
  /**
   * 渲染层 → 主进程：手动弹一条系统通知（UI 上「提醒」按钮用）。
   * @param {{ title?: string, body?: string, tag?: string }} opts
   */
  notify(opts) {
    return ipcRenderer.invoke("player:notify", opts || {});
  },
  /**
   * 主进程 → 渲染层：菜单 / 通知 / 后续可能的全局快捷键点击 → 播控指令。
   * @param {(cmd: "play"|"pause"|"next"|"prev") => void} listener
   * @returns {() => void} unsubscribe
   */
  onPlayerControl(listener) {
    const wrapped = (_evt, cmd) => listener(cmd);
    ipcRenderer.on("player:control", wrapped);
    return () => ipcRenderer.removeListener("player:control", wrapped);
  },
  /**
   * 测试用：拉主进程当前 player 状态快照。
   * @returns {Promise<{ isPlaying: boolean, currentSongId: string|null, queueCount: number, ... }>}
   */
  getPlayerState() {
    return ipcRenderer.invoke("player:getState");
  },

  // ===== P0-2: API 配置（baseUrl + sessionToken 单一来源） =====
  /**
   * 拉取 Python 后端的 baseUrl + session token。
   * 渲染层所有 mutate 请求必须经统一 client 注入 X-Streamer-Session；
   * 不应各组件自行 fetch + 自行塞 token。
   * dev mode sessionToken 为空；packaged mode 是主进程启动时生成的随机串。
   * @returns {Promise<{ baseUrl: string, sessionToken: string }>}
   */
  getApiConfig() {
    return ipcRenderer.invoke("app:get-api-config");
  },

  // ===== R8.2.x 弹唱录屏（Electron desktopCapturer + MediaRecorder） =====
  /**
   * 列出可录制的源（屏幕 / 窗口）。
   * @returns {Promise<{ok: boolean, platform?: string, sources?: Array<{id: string, name: string, isScreen: boolean, thumbnailDataUrl: string|null}>, code?: string, error?: string}>}
   */
  listRecordingSources() {
    return ipcRenderer.invoke("recording:list-sources");
  },
  /**
   * 开始录制。
   * @param {{
   *   sourceId: string,           // 来自 listRecordingSources
   *   sourceName?: string,         // 显示用
   *   includeAudio?: boolean,      // 是否含系统音频（默认 false）
   *   sessionId?: string,          // 关联到直播 session（可选；非法值会被拒绝）
   *   segmentBytes?: number,       // 默认 1GB
   *   videoBitsPerSecond?: number, // 默认 4Mbps
   *   audioBitsPerSecond?: number, // 默认 128kbps
   * }} opts
   * @returns {Promise<{ok: boolean, id?: string, startedAt?: number, outputDir?: string, mimeType?: string, code?: string, error?: string}>}
   */
  startRecording(opts) {
    return ipcRenderer.invoke("recording:start", opts || {});
  },
  pauseRecording(id) {
    return ipcRenderer.invoke("recording:pause", id);
  },
  resumeRecording(id) {
    return ipcRenderer.invoke("recording:resume", id);
  },
  /**
   * 推 LRC 字幕事件到主进程；停止时会合并生成 SRT。
   * @param {string} id
   * @param {Array<{offset_ms: number, text: string}>} events
   */
  appendRecordingLrc(id, events) {
    return ipcRenderer.invoke("recording:append-lrc", { id, events });
  },
  /**
   * 停止录制，返回产物文件列表（含 SRT）。
   * @returns {Promise<{ok: boolean, id?: string, durationMs?: number, outputDir?: string, files?: Array<{name: string, path: string, bytes: number, index: number, isSrt: boolean}>, code?: string, error?: string}>}
   */
  stopRecording(id) {
    return ipcRenderer.invoke("recording:stop", id);
  },
  /**
   * 拿当前录制状态（id 不传时拿活跃录制）。
   * @returns {Promise<{ok: boolean, active?: null, id?: string, status?: string, elapsedMs?: number, currentBytes?: number, totalBytes?: number, segmentIndex?: number, files?: string[], sourceName?: string, outputDir?: string, code?: string}>}
   */
  getRecordingState(id) {
    return ipcRenderer.invoke("recording:get-state", id);
  },
  /**
   * 列某 session 的录制产物（webm + srt）。
   * @param {string} [sessionId] - 不传列所有
   */
  listRecordingFiles(sessionId) {
    return ipcRenderer.invoke("recording:list-files", sessionId);
  },
  /** 列所有有录制的 session。 */
  listRecordingSessions() {
    return ipcRenderer.invoke("recording:list-sessions");
  },
  /** 删除某 session 录制目录（含 webm + srt）。 */
  deleteRecording(sessionId) {
    return ipcRenderer.invoke("recording:delete", sessionId);
  },
});
