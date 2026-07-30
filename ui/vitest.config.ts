import { defineConfig } from "vitest/config";
import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    // vitest 只接管 .tsx（React 组件/hook）测试；.ts 单元测试走 node:test。
    // 这样两类测试互不干扰（顺序无关、独立 CI 阶段）。
    include: ["src/**/*.test.tsx"],
  },
});
