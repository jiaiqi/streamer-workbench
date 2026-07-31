import { defineConfig, loadEnv } from "vite";
import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => {
  const proxyTarget = loadEnv(mode, ".", "").VITE_API_PROXY_TARGET || "http://127.0.0.1:8000";
  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
    },
    server: {
      // 固定 5174 + strictPort：与 Electron 壳 (electron/main.js) 探测端口一致；
      // strictPort=true 时端口被占直接失败，避免静默漂移。
      port: 5174,
      strictPort: true,
      hmr: {
        host: "localhost",
        port: 5174,
      },
      proxy: {
        "/api": { target: proxyTarget, changeOrigin: true },
        "/bg": { target: proxyTarget, changeOrigin: true },
        "/tabs": { target: proxyTarget, changeOrigin: true },
      },
    },
  };
});
