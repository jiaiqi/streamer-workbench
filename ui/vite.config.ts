import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => {
  const proxyTarget = loadEnv(mode, ".", "").VITE_API_PROXY_TARGET || "http://127.0.0.1:8000";
  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      proxy: {
        "/api": { target: proxyTarget, changeOrigin: true },
        "/bg": { target: proxyTarget, changeOrigin: true },
        "/tabs": { target: proxyTarget, changeOrigin: true },
      },
    },
  };
});
