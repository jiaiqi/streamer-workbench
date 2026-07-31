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
const { app, BrowserWindow, Menu, dialog, shell, ipcMain, protocol } = require("electron");
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

ipcMain.handle("desktop:info", () => ({
  isPackaged,
  dataDir: process.env.STREAMER_DATA_DIR || null,
  pyUrl: PY_URL,
}));

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
});

app.on("will-quit", () => {
  if (viteProc && !viteProc.killed) {
    try { viteProc.kill("SIGKILL"); } catch { /* noop */ }
  }
  if (pyProc && !pyProc.killed) {
    try { pyProc.kill("SIGKILL"); } catch { /* noop */ }
  }
});
