import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import QuickView from "./QuickView";
import "./index.css";

// /quick = 速查小窗（直播中置顶速查选调）；其余路径 = 主应用
// 兼容 hash 路由：file:// 模式下 pathname 永远是 dist 目录, 用 hash #/quick
const isQuick = window.location.pathname.startsWith("/quick")
  || window.location.hash.startsWith("#/quick");

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {isQuick ? <QuickView /> : <App />}
  </StrictMode>
);
