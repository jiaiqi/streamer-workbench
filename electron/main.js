// Electron 壳 spike：验证三件事
// 1) child_process spawn PyInstaller 单文件后端（8001 端口）
// 2) 后端就绪后 BrowserWindow 加载其页面/接口
// 3) alwaysOnTop（速查小窗的技术前提，screen-saver 层级 = 可压全屏直播软件）
const { app, BrowserWindow } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const http = require("http");

const BACKEND = path.join(__dirname, "..", "packaging", "dist", "poster-backend");
const PORT = 8001;

let backend = null;
let mainWin = null;

function waitForBackend(retries = 60) {
  return new Promise((resolve, reject) => {
    const tryOnce = (left) => {
      const req = http.get(`http://127.0.0.1:${PORT}/api/settings`, (res) => {
        res.resume();
        resolve();
      });
      req.on("error", () => {
        if (left <= 0) return reject(new Error("backend not ready"));
        setTimeout(() => tryOnce(left - 1), 500);
      });
    };
    tryOnce(retries);
  });
}

app.whenReady().then(async () => {
  backend = spawn(BACKEND, [], { env: { ...process.env, GP_PORT: String(PORT) } });
  backend.stderr.on("data", d => console.error("[backend]", d.toString().trim()));

  await waitForBackend();
  console.log("[spike] backend ready");

  mainWin = new BrowserWindow({
    width: 420, height: 680,
    alwaysOnTop: true,          // ← 速查小窗关键 API
    title: "spike · alwaysOnTop",
  });
  mainWin.setAlwaysOnTop(true, "screen-saver"); // 最高层级，可压 OBS 全屏投影
  // 直接加载打包后端渲染出的 PNG，证明「Electron → 本地后端」链路
  mainWin.loadURL(`http://127.0.0.1:${PORT}/api/render?theme=%E6%B5%B7%E6%B4%8B%E6%9F%94%E5%85%89&page=1&canvas=%E6%8A%96%E9%9F%B3%E5%85%A8%E5%B1%8F%209%3A20&avoid=true`);
  console.log("[spike] window shown with alwaysOnTop =", mainWin.isAlwaysOnTop());

  // spike 只验证可行性：20 秒后自动退出，不留窗口
  setTimeout(() => app.quit(), 20000);
});

app.on("will-quit", () => {
  if (backend) backend.kill();
});
