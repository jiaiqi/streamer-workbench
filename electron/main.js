// 主播工作台 — Electron 桌面壳（dev 模式 + packaged 模式）
//
// 模式检测：
//   dev     (npm start  /  npm run dev): app.isPackaged === false
//   packaged (electron-builder 出包):   app.isPackaged === true
//
// dev 模式行为：
//   - spawn venv python:  <repo>/../.venv/bin/python -m server --port X
//   - spawn vite dev:     <ui>/node_modules/.bin/vite --port X --strictPort
//   - main window:        loadURL http://localhost:5174
//   - quick window:       loadURL http://localhost:5174/quick?session=...
//
// packaged 模式行为：
//   - spawn PyInstaller binary:  <resources>/backend/streamer-workbench-backend --port X
//       (PyInstaller binary 内含 themes/fonts/server/core, 启动 ~25s)
//   - main window:               loadFile <dist>/index.html  (vite build 产物)
//   - quick window:              loadFile <dist>/index.html#quick?session=...
//   - 每次启动随机生成 STREAMER_WORKBENCH_SESSION_TOKEN (32+ 字符)
//
// 跨平台：
//   - PyInstaller binary: streamer-workbench-backend (.app 内 / .exe 同名 / 可执行)
//   - venv python:        macOS/Linux → .venv/bin/python; Windows → .venv/Scripts/python.exe
//   - vite bin:           node_modules/.bin/vite (用绝对路径 + shell: false)
//
// 环境变量（可选，用于自定义）：
//   dev:
//     STREAMER_REPO_ROOT     默认 ../  (electron 所在目录的父目录)
//     STREAMER_VENV_PYTHON   默认 <repo>/.venv/bin/python (worktree 嵌套时 ../../.venv)
//     STREAMER_VITE_BIN      默认 <repo>/ui/node_modules/.bin/vite
//     STREAMER_VITE_PORT     默认 5174
//     STREAMER_PY_PORT       默认 8765
//     STREAMER_NO_SPAWN=1    强制不 spawn（用户自己起）
//   packaged:
//     STREAMER_DATA_DIR      用户数据目录（默认 platform_data_root）
//     STREAMER_BACKEND_BIN   自定义 PyInstaller binary 路径
//     STREAMER_PY_PORT       默认 8765
//     STREAMER_NO_SPAWN=1    强制不 spawn
//
// 子进程管理：
//   - 端口被外部占用 → 复用
//   - 端口空闲 + spawn 成功 → 启动后 quit 时双保险 kill
//   - 启动后子进程异常退出 → 弹错并退出 Electron
//
// 系统集成（P0 桌面平台特性首批 — MediaSession 替身 / 系统通知 / Dock Badge）：
//   - 渲染层订阅 PlayerContext（isPlaying / currentSongId / currentTimeMs / duration），
//     通过 IPC `player:state` 推给主进程
//   - 主进程 macOS 平台：
//       · `dock.setBadge(queueCount)`     - Dock 图标显示待唱数
//       · `new Notification(...)`         - 切歌 / 直播开始时弹系统通知
//       · 菜单栏「播控」菜单（上一首/暂停-继续/下一首） - 不开窗口也能控
//
// 海报分享（M2.16）：
//   - 跨平台：clipboard:writeImage / shell:showItemInFolder
//   - macOS 原生：share:macosSheet 调 `osascript` 桥接 `NSSharingServicePicker`，
//     弹系统级分享面板（AirDrop / 微信 / 邮件 / 备忘录 / Pages / Finder 全支持）
//   - 菜单点击 / 系统通知回调通过 `mainWin.webContents.send("player:control", cmd)` 派回渲染层
//   - 其他平台 (win/linux) 仅保留菜单 + IPC，dock / notification no-op，不崩
const { app, BrowserWindow, Menu, dialog, shell, ipcMain, protocol, Notification } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const crypto = require("crypto");
const http = require("http");
const net = require("net");

const isPackaged = app.isPackaged;
const isWin = process.platform === "win32";

// ----- 路径解析 -----
const REPO_ROOT = process.env.STREAMER_REPO_ROOT
  ? path.resolve(process.env.STREAMER_REPO_ROOT)
  : path.resolve(__dirname, "..");

const UI_DIR = path.join(REPO_ROOT, "ui");

// packaged 模式下资源路径:  macOS StreamerWorkbench.app/Contents/Resources/
//                            Windows StreamerWorkbench/resources/
//                            Linux streamer-workbench/resources/
const BACKEND_RESOURCES_DIR = isPackaged
  ? path.join(process.resourcesPath, "backend")
  : null;
const UI_DIST_DIR = isPackaged
  ? path.join(process.resourcesPath, "ui-dist")
  : null;
const PRELOAD_PATH = path.join(__dirname, "preload.js");

// dev 模式工具路径
const VENV_PY_DEV = isPackaged ? null : (process.env.STREAMER_VENV_PYTHON || path.join(REPO_ROOT, "..", ".venv", "bin", isWin ? "python.exe" : "python"));
const VITE_BIN_DEV = isPackaged ? null : (process.env.STREAMER_VITE_BIN || path.join(UI_DIR, "node_modules", ".bin", isWin ? "vite.cmd" : "vite"));

// packaged 模式 PyInstaller binary
const BACKEND_BIN_DEV_NAME = isWin ? "streamer-workbench-backend.exe" : "streamer-workbench-backend";
const BACKEND_BIN = isPackaged
  ? (process.env.STREAMER_BACKEND_BIN || path.join(BACKEND_RESOURCES_DIR, BACKEND_BIN_DEV_NAME))
  : null;

const VITE_PORT = Number(process.env.STREAMER_VITE_PORT) || 5174;
const PY_PORT = Number(process.env.STREAMER_PY_PORT) || 8765;
const PY_HOST = process.env.STREAMER_PY_HOST || "127.0.0.1";
const NO_SPAWN = process.env.STREAMER_NO_SPAWN === "1";

// R8.2.x 录屏：解析 data_root 路径（与 Python 端 build_app_paths 一致）
// - dev 模式：<REPO_ROOT>/data
// - packaged：STREAMER_DATA_DIR env → 否则 platform_data_root
function resolveDataRoot() {
  if (process.env.STREAMER_DATA_DIR && process.env.STREAMER_DATA_DIR.trim()) {
    return path.resolve(process.env.STREAMER_DATA_DIR);
  }
  if (isPackaged) {
    // 平台默认
    const home = require("os").homedir();
    if (isWin) {
      const appdata = process.env.APPDATA || path.join(home, "AppData", "Roaming");
      return path.join(appdata, "streamer-workbench");
    }
    if (process.platform === "darwin") {
      return path.join(home, "Library", "Application Support", "streamer-workbench");
    }
    const xdg = process.env.XDG_DATA_HOME || path.join(home, ".local", "share");
    return path.join(xdg, "streamer-workbench");
  }
  return path.join(REPO_ROOT, "data");
}

const VITE_URL = `http://localhost:${VITE_PORT}`;
const PY_URL = `http://localhost:${PY_PORT}`;

// ----- 子进程管理 -----
let pyProc = null;
let viteProc = null;
let mainWin = null;
let quickWin = null;
let ready = false;
let shuttingDown = false;
let sessionToken = null;  // packaged mode 每次启动随机生成

function log(...args) {
  console.log("[electron]", `[${isPackaged ? "packaged" : "dev"}]`, ...args);
}

function logErr(...args) {
  console.error("[electron]", `[${isPackaged ? "packaged" : "dev"}]`, ...args);
}

// 探测端口（IPv4 + IPv6 双探, 修 macOS vite::1 only listen）
function probe(port, host = "localhost", timeoutMs = 800) {
  return new Promise((resolve) => {
    const tryConnect = (target) => new Promise((r) => {
      const sock = new net.Socket();
      let done = false;
      const finish = (ok) => {
        if (done) return;
        done = true;
        sock.destroy();
        r(ok);
      };
      sock.setTimeout(timeoutMs);
      sock.once("connect", () => finish(true));
      sock.once("timeout", () => finish(false));
      sock.once("error", () => finish(false));
      sock.connect(port, target);
    });
    (async () => {
      const v4 = await tryConnect("127.0.0.1");
      if (v4) return resolve(true);
      const v6 = await tryConnect("::1");
      resolve(v6);
    })();
  });
}

function waitHttp(url, retries = 60, intervalMs = 500) {
  return new Promise((resolve, reject) => {
    const tryOnce = (left) => {
      const req = http.get(url, (res) => {
        res.resume();
        if (res.statusCode && res.statusCode < 500) return resolve();
        if (left <= 0) return reject(new Error(`status ${res.statusCode}`));
        setTimeout(() => tryOnce(left - 1), intervalMs);
      });
      req.on("error", () => {
        if (left <= 0) return reject(new Error("backend not ready"));
        setTimeout(() => tryOnce(left - 1), intervalMs);
      });
    };
    tryOnce(retries);
  });
}

function pipeProcess(name, proc) {
  proc.stdout?.on("data", (d) => log(name, d.toString().trimEnd()));
  proc.stderr?.on("data", (d) => logErr(name, d.toString().trimEnd()));
  proc.on("exit", (code, signal) => {
    if (shuttingDown) return;
    logErr(`${name} exited unexpectedly code=${code} signal=${signal}`);
    if (ready) {
      dialog.showErrorBox(
        `${name} 异常退出`,
        `${name} 在启动后异常退出（code=${code}）。\n` +
        `Electron 将一起退出，请检查日志后重试。`,
      );
      app.quit();
    } else {
      ready = false;
    }
  });
}

// 生成 32+ 字符随机 session token（packaged mode 必填）
function makeSessionToken() {
  return crypto.randomBytes(32).toString("hex");
}

async function ensurePython() {
  if (await probe(PY_PORT, PY_HOST)) {
    log(`python: ${PY_URL} 已被外部占用，复用`);
    return;
  }
  if (NO_SPAWN) {
    throw new Error(`Python 后端未在 ${PY_URL} 运行，且 STREAMER_NO_SPAWN=1 不允许自动启动`);
  }

  if (isPackaged) {
    // packaged: spawn PyInstaller binary
    if (!fs.existsSync(BACKEND_BIN)) {
      throw new Error(`packaged mode 需要 ${BACKEND_BIN}，但文件不存在`);
    }
    const env = { ...process.env, STREAMER_DESKTOP: "1" };
    if (sessionToken) env.STREAMER_WORKBENCH_SESSION_TOKEN = sessionToken;
    if (process.env.STREAMER_DATA_DIR) env.STREAMER_WORKBENCH_DATA_DIR = process.env.STREAMER_DATA_DIR;
    log(`python: spawn binary ${BACKEND_BIN} --port ${PY_PORT}`);
    pyProc = spawn(BACKEND_BIN, ["--port", String(PY_PORT)], {
      env,
      // macOS 上 binary 解压到 sys._MEIPASS, 启动 ~25s, 给 waitHttp 60 次重试 (30s)
    });
  } else {
    // dev: spawn venv python
    log(`python: spawn ${VENV_PY_DEV} -m server --port ${PY_PORT}`);
    pyProc = spawn(VENV_PY_DEV, ["-m", "server", "--port", String(PY_PORT)], {
      cwd: REPO_ROOT,
      env: {
        ...process.env,
        PYTHONPATH: REPO_ROOT,
        PYTHONUTF8: "1",
        STREAMER_DESKTOP: "1",
      },
    });
  }
  pipeProcess("python", pyProc);
  await waitHttp(`${PY_URL}/api/settings`);
  log("python: ready");
}

async function ensureViteOrUI() {
  if (isPackaged) {
    // packaged: 用 vite build 产物, 不需要 dev server
    if (!fs.existsSync(path.join(UI_DIST_DIR, "index.html"))) {
      throw new Error(`packaged mode 需要 ${UI_DIST_DIR}/index.html`);
    }
    log(`vite: packaged dist at ${UI_DIST_DIR}`);
    return;
  }
  // dev: spawn vite
  if (await probe(VITE_PORT, PY_HOST)) {
    log(`vite: ${VITE_URL} 已被外部占用，复用`);
    return;
  }
  if (NO_SPAWN) {
    throw new Error(`Vite dev server 未在 ${VITE_URL} 运行，且 STREAMER_NO_SPAWN=1 不允许自动启动`);
  }
  log(`vite: spawn ${VITE_BIN_DEV} --port ${VITE_PORT} --strictPort`);
  viteProc = spawn(VITE_BIN_DEV, ["--port", String(VITE_PORT), "--strictPort"], {
    cwd: UI_DIR,
    env: { ...process.env, VITE_API_PROXY_TARGET: `http://127.0.0.1:${PY_PORT}` },
  });
  pipeProcess("vite", viteProc);
  await waitHttp(VITE_URL);
  log("vite: ready");
}

function buildMenu() {
  const isMac = process.platform === "darwin";
  const template = [
    ...(isMac ? [{ role: "appMenu" }] : []),
    {
      label: "文件",
      submenu: [
        { label: "刷新", accelerator: "CmdOrCtrl+R", role: "reload" },
        { type: "separator" },
        isMac ? { role: "close" } : { role: "quit" },
      ],
    },
    {
      label: "窗口",
      submenu: [
        {
          label: "打开置顶速查",
          accelerator: "CmdOrCtrl+Shift+U",
          click: () => openQuickView(),
        },
        { type: "separator" },
        { role: "minimize" },
        { role: "togglefullscreen" },
      ],
    },
    {
      label: "开发",
      submenu: [
        { role: "toggleDevTools" },
        { type: "separator" },
        ...(isPackaged ? [] : [{
          label: "在浏览器打开主窗口",
          click: () => shell.openExternal(VITE_URL),
        }]),
      ],
    },
    {
      id: "player-controls",
      label: "播控",
      submenu: [
        { label: "⏸ 暂停", enabled: false, click: () => pushPlayerControl("pause") },
        { label: "▶ 继续", enabled: false, click: () => pushPlayerControl("play") },
        { label: "⏮ 上一首", enabled: false, click: () => pushPlayerControl("prev") },
        { label: "⏭ 下一首", enabled: false, click: () => pushPlayerControl("next") },
        { type: "separator" },
        { label: "📋 待唱队列（空）", enabled: false },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

function mainLoadConfig() {
  if (isPackaged) {
    return { file: path.join(UI_DIST_DIR, "index.html") };
  }
  return { url: VITE_URL };
}

function quickLoadConfig(sessionId) {
  if (isPackaged) {
    // SPA 路由用 hash 避免 file:// 下 path 解析问题
    const hash = sessionId ? `#/quick?session=${encodeURIComponent(sessionId)}` : "#/quick";
    return { file: path.join(UI_DIST_DIR, "index.html"), hash };
  }
  const query = sessionId ? `?session=${encodeURIComponent(sessionId)}` : "";
  return { url: `${VITE_URL}/quick${query}` };
}

function createMainWindow() {
  mainWin = new BrowserWindow({
    width: 1280,
    height: 820,
    title: "主播工作台",
    backgroundColor: "#0b0b0f",
    show: false,
    webPreferences: {
      preload: PRELOAD_PATH,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  mainWin.once("ready-to-show", () => mainWin.show());
  mainWin.on("closed", () => { mainWin = null; });
  const cfg = mainLoadConfig();
  if (cfg.file) {
    mainWin.loadFile(cfg.file);
    log(`main: loadFile ${cfg.file}`);
  } else {
    mainWin.loadURL(cfg.url);
    log(`main: loadURL ${cfg.url}`);
  }
}

function openQuickView(sessionId) {
  if (quickWin && !quickWin.isDestroyed()) {
    quickWin.focus();
    if (sessionId) {
      quickWin.webContents.send("quickview:session", sessionId);
    }
    return;
  }
  quickWin = new BrowserWindow({
    width: 420,
    height: 720,
    title: "直播速查",
    backgroundColor: "#0b0b0f",
    alwaysOnTop: true,
    skipTaskbar: false,
    resizable: true,
    minimizable: true,
    maximizable: false,
    show: false,
    parent: mainWin ?? undefined,
    webPreferences: {
      preload: PRELOAD_PATH,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  quickWin.setAlwaysOnTop(true, "screen-saver");
  quickWin.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  quickWin.once("ready-to-show", () => quickWin.show());
  quickWin.on("closed", () => { quickWin = null; });
  const cfg = quickLoadConfig(sessionId);
  if (cfg.file) {
    quickWin.loadFile(cfg.file, { hash: cfg.hash });
    log(`quick: loadFile ${cfg.file}${cfg.hash ?? ""}`);
  } else {
    quickWin.loadURL(cfg.url);
    log(`quick: loadURL ${cfg.url}`);
  }
}

ipcMain.handle("quickview:open", (_evt, sessionId) => {
  openQuickView(sessionId);
  return { ok: true };
});

ipcMain.handle("quickview:close", () => {
  if (quickWin && !quickWin.isDestroyed()) quickWin.close();
  return { ok: true };
});

/**
 * R4.0.12 海报真保存路径：渲染层把 ArrayBuffer 传过来，主进程弹原生保存对话框写盘。
 * @param {{ data: ArrayBuffer, defaultName: string, mimeType: string }} params
 * @returns { ok: boolean, path?: string, cancelled?: boolean, error?: string }
 */
ipcMain.handle("dialog:saveFile", async (_evt, params) => {
  const { data, defaultName, mimeType } = params || {};
  if (!data || !defaultName) {
    return { ok: false, error: "missing data or defaultName" };
  }
  try {
    const win = BrowserWindow.getFocusedWindow() || mainWin;
    const result = await dialog.showSaveDialog(win, {
      title: "保存海报",
      defaultPath: defaultName,
      filters: mimeType === "image/jpeg"
        ? [{ name: "JPEG", extensions: ["jpg", "jpeg"] }]
        : [{ name: "PNG", extensions: ["png"] }],
    });
    if (result.canceled || !result.filePath) {
      return { ok: false, cancelled: true };
    }
    fs.writeFileSync(result.filePath, Buffer.from(data));
    log(`saved: ${result.filePath} (${data.byteLength} bytes)`);
    return { ok: true, path: result.filePath };
  } catch (err) {
    logErr("saveFile:", err.message);
    return { ok: false, error: err.message };
  }
});

ipcMain.handle("desktop:info", () => ({
  isPackaged,
  dataDir: process.env.STREAMER_DATA_DIR || null,
  pyUrl: PY_URL,
}));

// =====================================================================
// R8.2.x 弹唱录屏（desktopCapturer + MediaRecorder + 1GB 自动切片 + SRT）
// =====================================================================
//
// 流程：
//   1. 渲染层 list-sources → 拿到 screen:xxx 选一个
//   2. start：主进程拿 source → getUserMedia → MediaRecorder → 写到 data/recordings/
//   3. 渲染层定时（每 5s）推 lrc 事件
//   4. stop：关 recorder + 写 SRT（如果有 lrc 事件） → 返回 files
//
// 注：desktopCapturer 在 macOS 首次调用会触发系统级屏幕录制授权弹窗。
// 拒绝后 getUserMedia 抛 NotAllowedError，我们捕获后返回 permission_denied。
const { RecordingManager } = require("./recording/recorder");
const recordingManager = new RecordingManager({
  dataRoot: resolveDataRoot(),
  log: (msg) => log(`recording: ${msg}`),
  logErr: (msg) => logErr(`recording: ${msg}`),
});
log(`recording dataRoot: ${resolveDataRoot()}`);

ipcMain.handle("recording:list-sources", async () => {
  return recordingManager.listSources();
});

ipcMain.handle("recording:start", async (_evt, opts) => {
  return recordingManager.start(opts || {});
});

ipcMain.handle("recording:pause", async (_evt, id) => {
  return recordingManager.pause(id);
});

ipcMain.handle("recording:resume", async (_evt, id) => {
  return recordingManager.resume(id);
});

ipcMain.handle("recording:append-lrc", async (_evt, params) => {
  return recordingManager.appendLrc(params?.id, params?.events || []);
});

ipcMain.handle("recording:stop", async (_evt, id) => {
  return recordingManager.stop(id);
});

ipcMain.handle("recording:get-state", async (_evt, id) => {
  if (!id) return recordingManager.getActive();
  return recordingManager.getState(id);
});

ipcMain.handle("recording:list-files", async (_evt, sessionId) => {
  return recordingManager.listFiles(sessionId);
});

ipcMain.handle("recording:list-sessions", async () => {
  return recordingManager.listAllSessions();
});

ipcMain.handle("recording:delete", async (_evt, sessionId) => {
  return recordingManager.deleteFolder(sessionId);
});

// =====================================================================
// 系统集成（P0 桌面平台特性首批：媒体播控 / 系统通知 / Dock Badge）
// =====================================================================
//
// 设计要点：
// 1. 渲染层是唯一真相源（PlayerContext + LiveView 队列），主进程只做"窗口外的投影"
// 2. 渲染层订阅 PlayerContext 后批量推 { isPlaying, currentSongId, currentTimeMs,
//    durationMs, queueCount } → 主进程；用 `send` 而不是 `invoke`，避免阻塞渲染
// 3. 主进程菜单/通知点击 → `mainWin.webContents.send("player:control", cmd)` 派回渲染
// 4. 菜单不依赖渲染层状态实时刷新（避免每帧 IPC），仅 enable/disable
// 5. 通知去重：同一首歌 / 同一队列变更 30s 内只发一次，避免刷屏
//
// 平台差异：
// - macOS：dock badge + Notification + 菜单
// - Windows / Linux：仅菜单 + Notification（无 dock badge，自动 no-op）
//
// 状态存储：
const playerState = {
  isPlaying: false,
  currentSongId: null,
  currentTitle: null,
  currentArtist: null,
  currentTimeMs: 0,
  durationMs: 0,
  queueCount: 0,         // 待唱 / 队列剩余
  hasSong: false,        // 是否有当前歌（用于菜单 enable）
};
let lastNotificationKey = null;
let lastNotificationAt = 0;

function pushPlayerControl(cmd) {
  // 菜单 / 通知 / 后续可能的全局快捷键都通过这条通道派回渲染层
  const target = mainWin && !mainWin.isDestroyed() ? mainWin : BrowserWindow.getAllWindows()[0];
  if (!target || target.isDestroyed()) return;
  target.webContents.send("player:control", cmd);
  log(`player:control → ${cmd}`);
}

function refreshPlayerMenu() {
  // 仅重建播控子菜单（不重建整个 app menu，避免覆盖用户正在交互的菜单项）
  const hasSong = !!playerState.hasSong;
  const isPlaying = !!playerState.isPlaying;
  const submenu = Menu.buildFromTemplate([
    {
      label: "⏮ 上一首",
      enabled: hasSong,
      click: () => pushPlayerControl("prev"),
    },
    {
      label: isPlaying ? "⏸ 暂停" : "▶ 继续",
      enabled: hasSong,
      click: () => pushPlayerControl(isPlaying ? "pause" : "play"),
    },
    {
      label: "⏭ 下一首",
      enabled: hasSong,
      click: () => pushPlayerControl("next"),
    },
    { type: "separator" },
    {
      label: playerState.queueCount > 0
        ? `📋 待唱 ${playerState.queueCount} 首`
        : "📋 待唱队列（空）",
      enabled: false,  // 信息性，不响应点击（点 dock badge 也只是切到主窗口）
    },
  ]);
  const menu = Menu.getApplicationMenu();
  if (menu) {
    const item = menu.getMenuItemById("player-controls");
    if (item) {
      item.submenu = submenu;
      // Electron 自动同步；无需显式重 build
    }
  }
}

function applyDockBadge() {
  if (process.platform !== "darwin" || !app.dock) return;
  const n = playerState.queueCount;
  try {
    app.dock.setBadge(n > 0 ? String(n) : "");
  } catch (err) {
    logErr("dock.setBadge:", err.message);
  }
}

function showSystemNotification(opts) {
  // { title, body, tag? }
  if (!Notification.isSupported || !Notification.isSupported()) {
    log(`notification skipped (unsupported): ${opts.title}`);
    return;
  }
  // 30s 内同 tag 去重
  const now = Date.now();
  const key = `${opts.tag || "default"}::${opts.title}::${opts.body}`;
  if (key === lastNotificationKey && now - lastNotificationAt < 30_000) {
    log(`notification dedup: ${opts.title}`);
    return;
  }
  lastNotificationKey = key;
  lastNotificationAt = now;
  try {
    const n = new Notification({
      title: opts.title,
      body: opts.body || "",
      silent: false,
    });
    n.on("click", () => {
      // 点击通知 → 切到主窗口
      const target = mainWin && !mainWin.isDestroyed() ? mainWin : BrowserWindow.getAllWindows()[0];
      if (target) {
        if (target.isMinimized()) target.restore();
        target.show();
        target.focus();
      }
    });
    if (opts.tag === "song_changed") {
      n.on("action", (_e, idx) => {
        if (idx === "0") pushPlayerControl("pause");
        else if (idx === "1") pushPlayerControl("next");
      });
    }
    n.show();
    log(`notification: ${opts.title}`);
  } catch (err) {
    logErr("notification.show:", err.message);
  }
}

// IPC：渲染层 → 主进程（推 state）
ipcMain.on("player:state", (_evt, state) => {
  if (!state || typeof state !== "object") return;
  const prev = { ...playerState };
  Object.assign(playerState, {
    isPlaying: !!state.isPlaying,
    currentSongId: state.currentSongId ?? null,
    currentTitle: state.currentTitle ?? null,
    currentArtist: state.currentArtist ?? null,
    currentTimeMs: Number(state.currentTimeMs) || 0,
    durationMs: Number(state.durationMs) || 0,
    queueCount: Number(state.queueCount) || 0,
    hasSong: !!state.currentSongId,
  });
  // 菜单状态变化时刷新
  if (prev.isPlaying !== playerState.isPlaying || prev.hasSong !== playerState.hasSong) {
    refreshPlayerMenu();
  }
  // Dock badge 变化
  if (prev.queueCount !== playerState.queueCount) {
    applyDockBadge();
  }
  // 切歌通知（song id 变化 + 之前有歌 → 切了）
  if (
    state.notifySongChanged === true &&
    prev.currentSongId &&
    playerState.currentSongId &&
    prev.currentSongId !== playerState.currentSongId
  ) {
    showSystemNotification({
      tag: "song_changed",
      title: `🎤 下一首：${playerState.currentTitle || "未知"}`,
      body: playerState.currentArtist ? `歌手：${playerState.currentArtist}` : "",
    });
  }
  // 直播开始通知（队列从 0 → >0 时，且首次）
  if (
    prev.queueCount === 0 && playerState.queueCount > 0 && state.notifyQueueStarted === true
  ) {
    showSystemNotification({
      tag: "queue_started",
      title: "📡 直播已开",
      body: `待唱 ${playerState.queueCount} 首`,
    });
  }
});

// IPC：渲染层 → 主进程（手动触发通知，供 UI 上"提醒"按钮使用）
ipcMain.handle("player:notify", async (_evt, opts) => {
  showSystemNotification({
    tag: opts?.tag || "manual",
    title: opts?.title || "主播工作台",
    body: opts?.body || "",
  });
  return { ok: true };
});

// IPC：测试用 — 当前 state 快照（vitest 集水）
ipcMain.handle("player:getState", () => ({ ...playerState }));

// =====================================================================
// 海报分享（M2.16 macOS Share Sheet + 跨平台剪贴板 / Finder 定位）
// =====================================================================
//
// 设计要点：
// 1. 渲染层持有 ArrayBuffer（来自 /api/render 字节流），通过 IPC 传给主进程
// 2. 主进程写临时文件 + 触发平台对应分享能力：
//    - clipboard:writeImage — 跨平台，把 PNG bytes 写进系统剪贴板（用户 Cmd+V 即可贴到任何 App）
//    - shell:showItemInFolder — 跨平台，macOS 高亮、Win 打开 Explorer、Linux 打开文件管理器
//    - share:macosSheet — 仅 darwin，通过 osascript 调 NSSharingServicePicker 弹系统分享面板
// 3. share:macosSheet 不可用时返回 { ok: false, code: "unsupported" }，UI 端按需 disabled
// 4. 临时文件统一在 OS temp 目录，文件名 `streamer-poster-{nanoid}.png`，由 OS 回收
//
// 平台差异：
// - macOS：全支持（剪贴板 / Finder 高亮 / Share Sheet）
// - Windows：剪贴板 / Explorer 打开（无原生 share sheet，UI 上 disabled）
// - Linux：剪贴板 / 文件管理器打开（无原生 share sheet，UI 上 disabled）
const os = require("os");
const { execFile, spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const crypto = require("crypto");
const { clipboard, nativeImage } = require("electron");

function tempPosterPath(defaultName) {
  const safe = (defaultName || "poster").replace(/[^a-zA-Z0-9._-]+/g, "_").slice(0, 60);
  const id = crypto.randomBytes(6).toString("hex");
  return path.join(os.tmpdir(), `streamer-poster-${id}-${safe}.png`);
}

// M3 海报 UI/UX：macOS Quick Look 预览 — 写临时 PNG + spawn qlmanage -p
const _quicklookTmp = new Set();

function tempQuickLookPath(posterId) {
  const safe = String(posterId || "poster").replace(/[^a-zA-Z0-9._-]+/g, "_").slice(0, 60);
  const id = crypto.randomBytes(6).toString("hex");
  return path.join(os.tmpdir(), `streamer-quicklook-${id}-${safe}.png`);
}

function cleanupQuickLookTmp() {
  for (const p of _quicklookTmp) {
    try { fs.unlinkSync(p); } catch { /* noop */ }
  }
  _quicklookTmp.clear();
}

/**
 * macOS 原生分享面板：写临时文件 + osascript 调 NSSharingServicePicker
 *
 * AppleScript 桥接说明：
 *   - use framework "Foundation" / "AppKit" 拿到 NSImage / NSSharingServicePicker
 *   - initWithContentsOfFile: 用 POSIX 路径读图
 *   - sharingServicePickerWithItems: 传 array of NSImage
 *   - showRelativeToRect:ofView:preferredEdge: 用零矩形 + 关键窗口定位弹板
 *
 * 为什么不用 Electron 的 webContents.share？
 *   - Electron 至今没有稳定暴露 Web Share API 给 BrowserWindow
 *   - osascript 桥接是 macOS 上最稳的方式，零新依赖
 */
function buildMacShareScript(filePath) {
  // 注意：osascript 的引号转义很脆弱，全部用单引号 + double-escape
  return `use framework "Foundation"
use framework "AppKit"
use scripting additions

set theFile to POSIX file "${filePath.replace(/"/g, '\\"')}"
set theImage to current application's NSImage's alloc()'s initWithContentsOfFile:theFile
if theImage is missing value then
  return "ERROR: failed to load image"
end if

set thePicker to current application's NSSharingServicePicker's sharingServicePickerWithItems:{theImage}
set theWindow to current application's NSApplication's sharedApplication()'s keyWindow()
if theWindow is missing value then
  return "ERROR: no key window"
end if
set theView to theWindow's contentView()
set zeroRect to current application's NSMakeRect(0, 0, 0, 0)
thePicker's showRelativeToRect:zeroRect ofView:theView preferredEdge:0
return "OK"
`;
}

ipcMain.handle("clipboard:writeImage", async (_evt, params) => {
  try {
    const data = params?.data;
    if (!data) return { ok: false, error: "missing data" };
    const buf = Buffer.from(data);
    const img = nativeImage.createFromBuffer(buf);
    if (img.isEmpty()) {
      return { ok: false, error: "invalid image buffer" };
    }
    clipboard.writeImage(img);
    return { ok: true };
  } catch (err) {
    logErr("clipboard:writeImage:", err.message);
    return { ok: false, error: err.message };
  }
});

ipcMain.handle("shell:showItemInFolder", async (_evt, params) => {
  const filePath = params?.filePath;
  if (!filePath || !fs.existsSync(filePath)) {
    return { ok: false, error: "file not found" };
  }
  try {
    shell.showItemInFolder(filePath);
    return { ok: true };
  } catch (err) {
    logErr("shell:showItemInFolder:", err.message);
    return { ok: false, error: err.message };
  }
});

ipcMain.handle("share:macosSheet", async (_evt, params) => {
  if (process.platform !== "darwin") {
    return { ok: false, code: "unsupported", error: "macOS only" };
  }
  try {
    const data = params?.data;
    const defaultName = params?.defaultName || "poster.png";
    if (!data) return { ok: false, error: "missing data" };
    const buf = Buffer.from(data);
    // 验证是有效图片
    const img = nativeImage.createFromBuffer(buf);
    if (img.isEmpty()) return { ok: false, error: "invalid image buffer" };
    const filePath = tempPosterPath(defaultName);
    fs.writeFileSync(filePath, buf);
    log(`share:macosSheet temp file ${filePath} (${buf.length} bytes)`);
    const script = buildMacShareScript(filePath);
    return await new Promise((resolve) => {
      execFile("osascript", ["-e", script], { timeout: 10_000 }, (err, stdout) => {
        const out = String(stdout || "").trim();
        if (err) {
          logErr("osascript:", err.message, out);
          resolve({ ok: false, error: err.message, osascript: out });
        } else if (out.startsWith("ERROR")) {
          resolve({ ok: false, error: out });
        } else {
          // 临时文件立刻删（用户拖到目标 App 时 Finder 已复制到目标）
          try { fs.unlinkSync(filePath); } catch { /* 留着让 OS 回收 */ }
          resolve({ ok: true });
        }
      });
    });
  } catch (err) {
    logErr("share:macosSheet:", err.message);
    return { ok: false, error: err.message };
  }
});

/**
 * M3 海报 UI/UX：macOS Quick Look 预览
 * - write 600x600 PNG 到 tmp
 * - spawn qlmanage -p <path> 弹原生 Quick Look 面板
 * - tmp 文件保留到 before-quit 时统一清理（qlmanage 子进程可能仍持有）
 */
ipcMain.handle("quicklook:open-poster", async (_evt, params) => {
  if (process.platform !== "darwin") {
    return { ok: false, code: "unsupported", error: "macOS only" };
  }
  try {
    const { data, posterId } = params || {};
    if (!data) return { ok: false, error: "missing data" };
    const buf = Buffer.from(data);
    const img = nativeImage.createFromBuffer(buf);
    if (img.isEmpty()) return { ok: false, error: "invalid image buffer" };
    const filePath = tempQuickLookPath(posterId);
    fs.writeFileSync(filePath, buf);
    _quicklookTmp.add(filePath);
    log(`quicklook:open-poster tmp file ${filePath} (${buf.length} bytes)`);
    return await new Promise((resolve) => {
      // qlmanage -p 弹 Quick Look 预览窗口（独立进程；detached 避免主进程阻塞）
      const child = spawn("qlmanage", ["-p", filePath], {
        detached: true,
        stdio: "ignore",
      });
      child.on("error", (err) => {
        logErr("qlmanage spawn:", err.message);
        resolve({ ok: false, error: err.message });
      });
      child.unref();
      // qlmanage -p 启动通常 < 500ms；给 2s 等待错误反馈
      setTimeout(() => resolve({ ok: true, path: filePath }), 2000);
    });
  } catch (err) {
    logErr("quicklook:open-poster:", err.message);
    return { ok: false, error: err.message };
  }
});

ipcMain.handle("quicklook:is-supported", () => {
  return { supported: process.platform === "darwin", platform: process.platform };
});

app.whenReady().then(async () => {
  // packaged mode 每次启动生成新 session token
  if (isPackaged) {
    sessionToken = makeSessionToken();
    log(`session_token: ${sessionToken.slice(0, 8)}... (${sessionToken.length} chars)`);
  }
  buildMenu();
  try {
    await ensurePython();
    await ensureViteOrUI();
    ready = true;
    createMainWindow();
    if (process.env.STREAMER_ELECTRON_SELFTEST) {
      const seconds = Number(process.env.STREAMER_ELECTRON_SELFTEST) || 5;
      log(`selftest: auto-quit in ${seconds}s`);
      if (process.env.STREAMER_ELECTRON_SELFTEST_QUICKVIEW === "1") {
        mainWin.once("ready-to-show", () => {
          log("selftest: openQuickView()");
          setTimeout(() => openQuickView("live_selftest"), 500);
        });
      }
      setTimeout(() => app.quit(), seconds * 1000);
    }
  } catch (err) {
    logErr("启动失败:", err.message);
    const uiHint = isPackaged
      ? `${UI_DIST_DIR}/index.html 存在`
      : `${VITE_URL} 端口空闲（可手动跑 cd ui && npm run dev）`;
    dialog.showErrorBox(
      "主播工作台启动失败",
      `${err.message}\n\n请确认：\n` +
      `1. ${PY_URL} 端口空闲（可手动跑 python -m server --port ${PY_PORT}）\n` +
      `2. ${uiHint}\n` +
      `3. 或设置 STREAMER_NO_SPAWN=1 自行管理进程`,
    );
    app.quit();
  }

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createMainWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  shuttingDown = true;
  if (viteProc && !viteProc.killed) {
    try { viteProc.kill(); } catch { /* noop */ }
  }
  if (pyProc && !pyProc.killed) {
    try { pyProc.kill(); } catch { /* noop */ }
  }
  // 清理 Quick Look 临时文件
  try { cleanupQuickLookTmp(); } catch { /* noop */ }
});

app.on("will-quit", () => {
  if (viteProc && !viteProc.killed) {
    try { viteProc.kill("SIGKILL"); } catch { /* noop */ }
  }
  if (pyProc && !pyProc.killed) {
    try { pyProc.kill("SIGKILL"); } catch { /* noop */ }
  }
});
