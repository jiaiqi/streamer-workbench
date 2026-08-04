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
});
