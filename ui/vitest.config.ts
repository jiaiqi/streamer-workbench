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
    // vitest 只接管 .tsx（React 组件/hook）测试 + play/ 模块的 .ts 解析器测试。
    // 其他 .ts 单元测试走 node:test（互不干扰、顺序无关、独立 CI 阶段）。
    // R8.0: play/ 下的 .ts 解析器（lrc/chordpro）也走 vitest，jsdom 环境足够
    // M1.1: search/ 下的 .ts 解析器（globalSongSearch）也走 vitest
    // M1.3: player/ 下的 .tsx（PlayerContext）也走 vitest
    // P0 桌面集成: hooks/ 下的 hook 测试也走 vitest（.test.tsx 走 esbuild React transform）
    include: ["src/**/*.test.tsx", "src/play/*.test.ts", "src/search/*.test.ts", "src/player/*.test.tsx", "src/hooks/*.test.tsx"],
    // 历史 node:test 文件（用 import test from "node:test"）— 让 vitest 跳过
    exclude: [
      "**/node_modules/**",
      "**/.git/**",
      "src/api/client.test.ts",
      "src/appearance/model.test.ts",
      "src/quick-view/model.test.ts",
    ],
  },
});
