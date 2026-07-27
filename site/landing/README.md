# 落地页 · Astro 工程化

歌单海报生成器的产品门面落地页。基于「暗色舞台 Cinematic Stage × 画廊白 Art Gallery」双品牌设计令牌构建。

## 技术栈

- **Astro 4** 静态生成
- **React 18** Hero 区 client island（轮播/3D 堆叠/鼠标光晕）
- **Tailwind 3** 工具类 + tokens.css 双重驱动
- **sharp** 构建期图片优化（webp + OG image）

## 开发

```bash
cd site/landing
pnpm install
pnpm dev                # http://localhost:4321/playlist-poster-generator/
```

## 构建

```bash
pnpm build              # 输出到 ../../docs/（覆盖 GitHub Pages 部署）
```

构建流程会自动：
1. `prebuild` 钩子 → `scripts/gen-posters.mjs` 从 `tests/golden/` 生成 14 张 webp + OG image
2. Astro 编译 + 静态生成
3. 输出到仓库根 `docs/` 目录

## 部署

### GitHub Pages（默认，已生效）

构建后 `docs/` 即被 GitHub Pages 服务。仓库 Settings → Pages → Source: master → /docs。

URL: `https://jiaiqi.github.io/playlist-poster-generator/`

### Vercel（可选，主推）

仓库根 `vercel.json`（如启用）：

```json
{
  "buildCommand": "cd site/landing && pnpm install && pnpm build",
  "outputDirectory": "site/landing/dist",
  "framework": "astro"
}
```

## 目录结构

```
site/landing/
├── astro.config.mjs              base='/playlist-poster-generator/' + outDir='../../docs'
├── tailwind.config.mjs           content glob + 字体族
├── tsconfig.json
├── package.json
├── scripts/
│   └── gen-posters.mjs           webp + OG image 生成
├── public/
│   ├── favicon.svg
│   └── posters/                  ★ 忽略，gen:posters 自动生成
└── src/
    ├── layouts/Base.astro        <html> + 防 FOUC + window.gp.theme
    ├── components/
    │   ├── Nav.astro             静态 nav + 主题切换按钮
    │   ├── HeroStatic.astro      Hero 左半（标题+CTA）
    │   ├── HeroPosterDeck.tsx    ★ 唯一 island
    │   ├── Stats.astro           counting 数字
    │   ├── Features.astro        直播伴侣三件套
    │   ├── ThemeGallery.astro    7 主题卡片
    │   ├── LayoutGallery.astro   6 布局横向
    │   ├── Roadmap.astro         时间线三节点
    │   └── Footer.astro
    ├── styles/
    │   ├── tokens.css            4 状态令牌（从 design-tokens.json v2 派生）
    │   └── global.css            Tailwind base + 颗粒/光晕基础样式
    └── pages/index.astro         主入口
```

## 设计令牌

与仓库根 `design/design-tokens.json` v2 一致：
- `colors.stage.dark`（默认）
- `colors.stage.light`
- `colors.gallery.light`
- `colors.gallery.dark`

修改令牌：先改 `design-tokens.json`，再同步 `site/landing/src/styles/tokens.css`。

## 主题切换

`window.gp.theme` API（`Base.astro` 末尾注入）：

```js
window.gp.theme.apply('gallery', 'light');  // 切换品牌+明暗
window.gp.theme.cycleBrand();                // 循环品牌
window.gp.theme.toggleMode();                 // 切换明暗
window.gp.theme.label();                      // 当前状态标签
```

切换状态持久化到 `localStorage.gp-landing-theme`，下次进入恢复。