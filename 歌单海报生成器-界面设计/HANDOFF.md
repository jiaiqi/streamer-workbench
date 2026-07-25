# 歌单海报生成器 · Agent 交接上下文

> 写给下一位接手协作的 Agent。本文汇总项目现状、已完成工作、关键决策与坑位，读完后可直接继续开发，无需重新探索。
> 最近更新：2026-07-25 · 代码重构 + 文档同步

---

## 1. 项目全景

工作目录 `F:\Desktop\李梓涵\` 下有 **两个相互独立的 git 仓库**（刻意不嵌套，各自提交）：

| 路径 | 仓库 | GitHub 远程（私有） | 内容 |
|---|---|---|---|
| `李梓涵\`（外层） | git 仓库 A（分支 `master`） | `jiaiqi/playlist-poster-design` | 设计文档、界面设计稿（`歌单海报生成器-界面设计\`） |
| `李梓涵\歌单海报生成器\`（内层） | git 仓库 B（主分支 `master`，另有 `feature/golden-align`） | `jiaiqi/playlist-poster-generator` | 产品本体：Python 渲染引擎 + FastAPI 后端 + 前端 |

> GitHub 账号 `jiaiqi`，凭据已存于 Windows 凭据管理器，`git push` 直接可用。

**协作约定（仓库历史中有明确记录）：每次改动都要 git 提交，原子提交、中文提交信息。**

### 产品是什么
把旧脚本 `歌单-排版一\build_playlist.py` 的 PIL 海报能力升级为桌面 App。**铁律：`core/` 禁止 import 任何 UI 框架，UI 只通过 `engine.render_page()` 拿 PIL.Image。** 先可用、后惊艳。

### 内层仓库结构（`歌单海报生成器\`）
```
core/       纯函数引擎（spec/style/engine/watermark/mist/context + themes/ + layouts/ + data/）
server/     FastAPI 渲染后端（main.py，端口 8000）
web/        原生验证页（开发期用）
ui/         React 19 + Vite 6 + Tailwind 4 前端（初版，暗色，未按新设计稿改造）
prototype/  高保真 UI 原型（暖暗 studio 风静态页 + 7 主题背景 + 14 张成品海报）
themes/     7 套主题包（theme.json + 背景图 + 设计理念.md）
fonts/      MaokenAssortedSans.ttf（糖圆体）
tests/      test_golden.py 金标准逐像素对比
```

### 外层仓库结构（`李梓涵\歌单海报生成器-界面设计\`）
```
shared.css / shared.js   ★ 共享设计系统（本次新建，见 §3）
pages/
  workspace.html   海报工作台（精修）
  library.html     歌曲库（重做）
  learning.html    学歌管理（新增）
  themes.html      主题管理（新增）
  presets.html     场景预设（新增）
  history.html     导出历史（新增）
  settings.html    设置（重做）
  songs-data.js    177 首真实歌名数据（从 core/data/songs.py 提取生成）
assets/            7 张主题缩略图 + 1 张海报成品图
colors_and_type.css 原始配色文档（保留作源头参考）
歌单海报生成器.design  设计工具页面注册文件（已注册全部 7 页）
.preflight/shots/  验证截图（7 页 × 亮/暗 + 交互，本地保留不入库）
```

---

## 2. 本次会话已完成

1. **全套 7 个界面静态设计稿**（见上），风格「晨光纸感 · 清新文艺」，亮色为主 + 暗色可选。
2. **共享设计系统** `shared.css` + `shared.js`（详见 §3）。
3. 提取真实数据：177 首歌名 → `pages/songs-data.js`；7 套主题配色已内嵌进 `themes.html`。
4. **浏览器全流程验证通过**：7 页 × 亮/暗两态截图、明暗切换闭环、搜索/筛选/折叠/开关/Toast/主题切换交互。
5. git 提交：
   - 外层：`38f857b 界面设计：全套 7 页晨光纸感设计稿 + 共享设计系统`、`30868ef chore: gitignore …`
   - 内层：`8ae6c37`（gitignore）→ `29b48d3`（server）→ `f95e546`（tools）→ `d1e1932`（prototype）→ `e7fdb16`（ui 初版）

### 用户明确的选择（不要推翻，除非有新理由）
- 界面实现位置：**静态设计页**（`歌单海报生成器-界面设计\`），不是 React。React `ui/` 是后续工程化载体。
- 视觉方向：**晨光纸感 · 清新文艺**（奶油纸底 #f7f6f2 + 海洋青 #2f8f7a + 暖珊瑚 #d9764f + 衬线标题），亮色为主、暗色可选。
- 要求：美观精致、方便操作、优雅、动画丝滑。

---

## 3. 设计系统使用方式（shared.css / shared.js）

每页 `<head>` 固定套路（防 FOUC 内联脚本 → Tailwind CDN → lucide CDN → shared.css）：
```html
<script>(function(){var t=localStorage.getItem("gp-theme");if(t==="dark"||(!t&&matchMedia("(prefers-color-scheme: dark)").matches))document.documentElement.classList.add("dark");})();</script>
<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4.3.1/dist/index.global.js"></script>
<script src="https://unpkg.com/lucide@1.8.0/dist/umd/lucide.min.js"></script>
<link rel="stylesheet" href="../shared.css?v=1">
```
页面底部：`<script src="../shared.js?v=1"></script>` + 页面自身脚本。

- **令牌**：`--gp-primary / --gp-background / --gp-card / --gp-muted / --gp-border / --gp-accent` 等，`.dark` 全套暗色覆盖；字体 `--gp-font-serif`（标题衬线）/ `--gp-font-sans`。
- **语义类**：`bg-card`、`text-muted-foreground`、`border-border`、`text-primary` 等（shared.css 内置，不依赖 Tailwind 生成）。
- **组件类**：`.gp-card(.gp-card-hover)`、`.gp-btn`（主按钮，光泽扫过+回弹）、`.gp-btn-ghost`、`.gp-chip(.active)`、`.gp-switch(.on)`、`.gp-input`、`.gp-badge(-accent/-muted)`、`.gp-collapse(+.open)`、`.gp-segment`、`.gp-nav-item(.active, data-label=悬浮标签)`、`.gp-progress`、`.gp-spinner`。
- **动效**：`.gp-stagger` / `.gp-stagger-scale`（JS 自动级联延迟，`data-stagger-step/base` 可调）、`.gp-rise/.gp-fade/.gp-scale-in/.gp-float`、曲线 `--gp-ease-spring: cubic-bezier(.34,1.56,.64,1)`、已内置 `prefers-reduced-motion` 降级。
- **JS 能力**（`window.gp`）：`gp.toast(msg, icon)`、`gp.applyTheme/toggleTheme`；自动初始化：折叠面板（`data-collapse-trigger="#id"`）、分段选择器滑块、开关、数字滚动（`data-count`）、亮暗切换按钮（`data-theme-toggle` + `data-theme-icon`）。
- **侧边导航**：7 页共用同一段 `<nav>` 结构（logo + 6 个页面链接 + 底部亮暗切换/设置），当前页 `.active`。新页面直接复制改 active。

---

## 4. 数据真相（以后端/引擎为准，设计稿已对齐）

- **歌曲**：内置 177 首（`core/data/songs.py`），**缺「奇妙能力歌」待补（目标 178）**。歌曲只有 title/status/section（1~6=字数, 7=长歌名/英文），artists/tags 等元数据为空。设计稿中「在学 5 首」是虚构演示数据。
- **主题**：7 套 = 卡通音符、奶油玻璃、奶油花园、梦幻海洋、海洋柔光、轻复古唱片、青提气泡。每套 theme.json 含双页背景 + 五角色配色（text/label/pill/line/mist）。背景图文件名不统一（bg1.png 或 background-1.png，以各自 theme.json 为准）。
- **排版**：仅 `grid-wrap`（全行网格绕排版），固定 2 页，支持避让。
- **画布预设**：`抖音全屏 9:20`（1080×2400，含禁文区 (940,1080,1080,2400)）、`标准 9:16`（1080×1920）。
- **排版参数**（ParamSpec）：margin 58 / font_song 36 / row_h 44 / sec_gap 26，另有 font_label 40 / label_h 74（CanvasSpec 字段）。

### 后端 API（server/main.py，uvicorn 8000 端口）
`GET /api/health`、`/api/themes`（含 backgrounds/notes）、`/api/layouts`（仅 id+name）、`/api/songs`（total + by_len）、`/api/render?theme=&page=&canvas=&avoid=` → PNG、`/bg/<主题>/<文件>` 静态背景。

### 已知 API 差距（前端工程化时需要补）
~~1. `/api/layouts` 不返回 `pages`/`supports_avoidance`（React ui/src/App.tsx 里已假设有）。~~
~~2. 排版参数 ParamSpec 无端点暴露（建议加 `/api/layouts/{id}/params`）。~~
~~3. `/api/render` 不接受参数覆盖（margin/font_song 等调了不生效）。~~
~~4. vite 代理只转 `/api`，`/bg` 需加代理或拼绝对地址。~~

> **2026-07-25 已全部补齐**（generator 仓库 `14f4ee2` + `9235246`）：`/api/layouts` 返回 pages/supports_avoidance；新增 `/api/layouts/{id}/params`；`/api/render` 支持 margin/font_song/row_h/sec_gap 覆盖及 layout 参数；vite 已代理 `/bg`。另：技术栈定稿「FastAPI + React 19/Vite 6/Tailwind 4 + Tauri sidecar」，PySide6 正式移除，《设计结论》《项目结构设计》两份文档已同步。macOS 环境已搭好，金标准 16/16 diff=0（需在仓库上级建 `歌单-排版一` 软链指向本设计仓库）。

---

## 5. 坑位与注意事项（踩过，别再踩）

1. **JS 注释里写路径通配符**：`/* themes/*/theme.json */` 中的 `*/` 会提前闭合块注释 → 整块脚本语法错误、页面白渲染。已修。
2. **主题持久化**：`shared.js` 初始化时**不得**把解析出的主题写回 localStorage（否则「跟随系统」永远失效）。只有用户主动切换才持久化（`applyTheme(theme, animate, persist)` 第三参）。
3. **python http.server 无 Cache-Control**，Chrome 启发式缓存会让旧 shared.js 阴魂不散 → 页面引用已加 `?v=1`，**改 shared.css/js 后记得 bump 版本号**。
4. **主题背景图是竖版且装饰集中在底部**，缩略图必须 `object-cover object-bottom`，否则只显示留白中段。
5. **git 双仓库**：不要把 `歌单海报生成器\` 提交进外层仓库（会形成 gitlink）。外层 .gitignore 已忽略它及 `.workbuddy/`、`.zcode/`、`.preflight/shots/`。内层已忽略 `node_modules/`、`.npm-cache/`。
6. Windows Git Bash 的 `find` 对中文路径 + `-path` 有 bug，用 `ls -R` 代替。

---

## 6. 验证工作流（可复用）

```bash
cd "F:\Desktop\李梓涵/歌单海报生成器-界面设计"
python -m http.server 8931 --bind 127.0.0.1          # 后台起静态服务
# agent-browser（npx 调用，本机无全局安装）
npx agent-browser set viewport 1600 900
npx agent-browser open "http://127.0.0.1:8931/pages/workspace.html"
npx agent-browser wait 2400 && npx agent-browser screenshot out.png
npx agent-browser set media dark                      # 模拟系统暗色（页面未存主题时跟随）
npx agent-browser snapshot -i                         # 拿交互元素 @eN ref 后 click/fill
npx agent-browser eval 'localStorage.clear()'         # 测暗色前先清 gp-theme
```
页面内联脚本语法检查：提取 `<script>` 内容后 `node --check`。

---

## 7. 建议的下一步（按优先级）

1. **React `ui/` 按新设计稿改造**：把 shared.css 的设计令牌/组件搬到 Tailwind 4 `@theme`，实现工作台（对接真实 /api/render），替换现有暗色初版。设计稿即视觉蓝本。
2. ~~**补后端端点**~~（2026-07-25 已完成，见 §4）。
3. ~~分组规则已定案（section 标记 + 字数回退）~~（2026-07-25 已完成）
4. **补数据**：加「奇妙能力歌」凑满 178 首，重跑金标准（`tests/test_golden.py`）。
5. `tools/migrate_data.py`：双源校验生成 songs.json 唯一数据源。
6. 歌曲库元数据（artists/key/capo）填充后，设计稿的学歌管理页可直接对接。
