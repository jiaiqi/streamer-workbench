import { defineConfig } from 'astro/config';
import tailwind from '@astrojs/tailwind';
import sitemap from '@astrojs/sitemap';
import react from '@astrojs/react';

export default defineConfig({
  site: 'https://jiaiqi.github.io',
  base: '/playlist-poster-generator/',
  outDir: '../../docs',
  trailingSlash: 'never',
  build: { inlineStylesheets: 'auto' },
  integrations: [
    tailwind({ applyBaseStyles: true }),
    sitemap({ changefreq: 'monthly', priority: 0.8 }),
    react(),
  ],
  vite: {
    build: {
      assetsInlineLimit: 1024,
    },
  },
});