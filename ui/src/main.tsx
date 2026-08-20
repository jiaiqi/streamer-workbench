import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import QuickView from "./QuickView";
import { initApiSession } from "./api/session";
import "./index.css";

// P0-2: 应用启动时拉主进程的 sessionToken，缓存到 module 状态。
// 浏览器 / dev mode 下 streamer.getApiConfig 不存在，initApiSession 静默 no-op。
void initApiSession();

// /quick = 速查小窗（直播中置顶速查选调）；其余路径 = 主应用
// 兼容 hash 路由：file:// 模式下 pathname 永远是 dist 目录, 用 hash #/quick
const isQuick = window.location.pathname.startsWith("/quick")
  || window.location.hash.startsWith("#/quick");

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {isQuick ? <QuickView /> : <App />}
  </StrictMode>
);
