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
});
