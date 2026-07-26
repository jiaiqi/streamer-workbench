import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import QuickView from "./QuickView";
import "./index.css";

// /quick = 速查小窗（直播中置顶速查选调）；其余路径 = 主应用
const isQuick = window.location.pathname.startsWith("/quick");

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {isQuick ? <QuickView /> : <App />}
  </StrictMode>
);
