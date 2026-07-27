import { defineConfig } from 'astro/config';
import tailwind from '@astrojs/tailwind';
import react from '@astrojs/react';

export default defineConfig({
  site: 'https://jiaiqi.github.io',
  base: '/playlist-poster-generator/',
  outDir: '../../docs',
  trailingSlash: 'never',
  build: { inlineStylesheets: 'auto' },
  integrations: [
    tailwind({ applyBaseStyles: true }),
    react(),
  ],
  vite: {
    build: {
      assetsInlineLimit: 1024,
    },
  },
});

// 注：@astrojs/sitemap 在 base path + 单页面场景会触发 reduce 未定义 bug。
// 当前只有 index 页，sitemap 价值低；后续添加多页面后再启用。