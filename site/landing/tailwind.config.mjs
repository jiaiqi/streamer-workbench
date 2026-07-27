/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{astro,html,ts,tsx,md,mdx}'],
  theme: {
    extend: {
      fontFamily: {
        serif: ['Noto Serif SC', 'Source Han Serif SC', 'Songti SC', 'STSong', 'SimSun', 'serif'],
        sans: ['PingFang SC', 'Microsoft YaHei', 'Noto Sans SC', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'SF Mono', 'Cascadia Code', 'ui-monospace', 'monospace'],
      },
      maxWidth: { 'container': '1280px' },
    },
  },
  plugins: [],
};