// 主播工作台 — Electron 桌面壳（dev 模式）
//
// 设计（ADR-005 / spike 后正式落地）：
// 1) Electron 主进程同时管理 Vite dev server + Python uvicorn
//    - 若 5174/8765 端口已被外部占用，假设用户已手起 → 复用不重启
//    - 若空闲，spawn 启动子进程，quit 时 kill（无孤儿）
// 2) 主窗口：常规可被 OBS 覆盖的窗口，加载 http://127.0.0.1:5174
// 3) 置顶速查子窗口：alwaysOnTop + screen-saver 层级（可压全屏直播软件）
//    加载 /quick?session=xxx，session 由主窗口通过 IPC 推送
// 4) 仅 dev 模式；不打包（PyInstaller/electron-builder 留 R7）
//
// 跨平台：
// - venv python: macOS/Linux → .venv/bin/python; Windows → .venv/Scripts/python.exe
// - vite bin:    node_modules/.bin/vite (用绝对路径 + shell: false)
//
// 环境变量（可选，用于自定义）：
// - STREAMER_REPO_ROOT     默认 ../  (electron 所在目录的父目录)
// - STREAMER_VENV_PYTHON   默认 <repo>/.venv/bin/python（或 Scripts\python.exe）
// - STREAMER_VITE_BIN      默认 <repo>/ui/node_modules/.bin/vite
// - STREAMER_VITE_PORT     默认 5174
// - STREAMER_PY_PORT       默认 8765
// - STREAMER_PY_HOST       默认 127.0.0.1
// - STREAMER_NO_SPAWN=1    强制不 spawn（用户自己起）
const { app, BrowserWindow, Menu, dialog, shell, ipcMain } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const http = require("http");
const net = require("net");

// ----- 路径解析 -----
const REPO_ROOT = process.env.STREAMER_REPO_ROOT
  ? path.resolve(process.env.STREAMER_REPO_ROOT)
  : path.resolve(__dirname, "..");

const UI_DIR = path.join(REPO_ROOT, "ui");

const isWin = process.platform === "win32";
const VENV_PY_DEFAULT = path.join(
  REPO_ROOT, ".venv",
  isWin ? "Scripts" : "bin",
  isWin ? "python.exe" : "python",
);
const VITE_BIN_DEFAULT = path.join(UI_DIR, "node_modules", ".bin", isWin ? "vite.cmd" : "vite");

const VENV_PY = process.env.STREAMER_VENV_PYTHON || VENV_PY_DEFAULT;
const VITE_BIN = process.env.STREAMER_VITE_BIN || VITE_BIN_DEFAULT;
const VITE_PORT = Number(process.env.STREAMER_VITE_PORT) || 5174;
const PY_PORT = Number(process.env.STREAMER_PY_PORT) || 8765;
const PY_HOST = process.env.STREAMER_PY_HOST || "127.0.0.1";
const NO_SPAWN = process.env.STREAMER_NO_SPAWN === "1";

const VITE_URL = `http://${PY_HOST}:${VITE_PORT}`;
const PY_URL = `http://${PY_HOST}:${PY_PORT}`;

// ----- 子进程管理 -----
let pyProc = null;
let viteProc = null;
let mainWin = null;
let quickWin = null;
let ready = false;
let shuttingDown = false;

function log(...args) {
  // 全部 [electron] 开头，方便 dev 终端定位
  console.log("[electron]", ...args);
}

function logErr(...args) {
  console.error("[electron]", ...args);
}

// 探测端口是否被占用（TCP 连接尝试）
function probe(port, host = "127.0.0.1", timeoutMs = 500) {
  return new Promise((resolve) => {
    const sock = new net.Socket();
    let done = false;
    const finish = (ok) => {
      if (done) return;
      done = true;
      sock.destroy();
      resolve(ok);
    };
    sock.setTimeout(timeoutMs);
    sock.once("connect", () => finish(true));
    sock.once("timeout", () => finish(false));
    sock.once("error", () => finish(false));
    sock.connect(port, host);
  });
}

// 等待 HTTP 200（GET /api/settings 即可）
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
      // 启动后挂掉：弹错对话框并退出
      dialog.showErrorBox(
        `${name} 异常退出`,
        `${name} 在启动后异常退出（code=${code}）。\n` +
        `Electron 将一起退出，请检查日志后重试。`,
      );
      app.quit();
    } else {
      // 启动期间挂掉：拒绝 ready 事件
      ready = false;
    }
  });
}

async function ensurePython() {
  if (await probe(PY_PORT, PY_HOST)) {
    log(`python: ${PY_URL} 已被外部占用，复用`);
    return;
  }
  if (NO_SPAWN) {
    throw new Error(`Python 后端未在 ${PY_URL} 运行，且 STREAMER_NO_SPAWN=1 不允许自动启动`);
  }
  log(`python: spawn ${VENV_PY} -m server --port ${PY_PORT}`);
  pyProc = spawn(VENV_PY, ["-m", "server", "--port", String(PY_PORT)], {
    cwd: REPO_ROOT,
    env: { ...process.env, PYTHONPATH: REPO_ROOT, PYTHONUTF8: "1", STREAMER_DESKTOP: "1" },
  });
  pipeProcess("python", pyProc);
  await waitHttp(`${PY_URL}/api/settings`);
  log("python: ready");
}

async function ensureVite() {
  if (await probe(VITE_PORT, PY_HOST)) {
    log(`vite: ${VITE_URL} 已被外部占用，复用`);
    return;
  }
  if (NO_SPAWN) {
    throw new Error(`Vite dev server 未在 ${VITE_URL} 运行，且 STREAMER_NO_SPAWN=1 不允许自动启动`);
  }
  log(`vite: spawn ${VITE_BIN} --port ${VITE_PORT} --strictPort --host ${PY_HOST}`);
  viteProc = spawn(VITE_BIN, ["--port", String(VITE_PORT), "--strictPort", "--host", PY_HOST], {
    cwd: UI_DIR,
    env: { ...process.env, VITE_API_PROXY_TARGET: PY_URL },
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
        {
          label: "在浏览器打开主窗口",
          click: () => shell.openExternal(VITE_URL),
        },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

function createMainWindow() {
  mainWin = new BrowserWindow({
    width: 1280,
    height: 820,
    title: "主播工作台",
    backgroundColor: "#0b0b0f",
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  mainWin.once("ready-to-show", () => mainWin.show());
  mainWin.on("closed", () => { mainWin = null; });
  mainWin.loadURL(VITE_URL);
  log(`main: loadURL ${VITE_URL}`);
}

function openQuickView(sessionId) {
  if (quickWin && !quickWin.isDestroyed()) {
    quickWin.focus();
    if (sessionId) {
      quickWin.webContents.send("quickview:session", sessionId);
    }
    return;
  }
  const query = sessionId ? `?session=${encodeURIComponent(sessionId)}` : "";
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
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  // 最高层级（screen-saver 之上）— 可压 OBS 全屏投影
  quickWin.setAlwaysOnTop(true, "screen-saver");
  quickWin.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  quickWin.once("ready-to-show", () => quickWin.show());
  quickWin.on("closed", () => { quickWin = null; });
  quickWin.loadURL(`${VITE_URL}/quick${query}`);
  log(`quick: loadURL ${VITE_URL}/quick${query ? " (session=" + sessionId + ")" : ""}`);
}

// IPC：主窗口通知 Electron 打开速查子窗口
ipcMain.handle("quickview:open", (_evt, sessionId) => {
  openQuickView(sessionId);
  return { ok: true };
});

ipcMain.handle("quickview:close", () => {
  if (quickWin && !quickWin.isDestroyed()) quickWin.close();
  return { ok: true };
});

app.whenReady().then(async () => {
  buildMenu();
  try {
    await ensurePython();
    await ensureVite();
    ready = true;
    createMainWindow();
  } catch (err) {
    logErr("启动失败:", err.message);
    dialog.showErrorBox(
      "主播工作台启动失败",
      `${err.message}\n\n请确认：\n` +
      `1. ${VITE_URL} 端口空闲（可手动跑 \`cd ui && npm run dev\`）\n` +
      `2. ${PY_URL} 端口空闲（可手动跑 \`python -m server --port ${PY_PORT}\`）\n` +
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
});

app.on("will-quit", () => {
  // 双保险：before-quit 已杀，这里再补一次
  if (viteProc && !viteProc.killed) {
    try { viteProc.kill("SIGKILL"); } catch { /* noop */ }
  }
  if (pyProc && !pyProc.killed) {
    try { pyProc.kill("SIGKILL"); } catch { /* noop */ }
  }
});
