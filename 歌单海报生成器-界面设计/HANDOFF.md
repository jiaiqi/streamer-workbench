# 歌单海报生成器 · Agent 交接上下文

> 写给下一位接手协作的 Agent。本文汇总项目现状、已完成工作、关键决策与坑位，读完后可直接继续开发，无需重新探索。
> 最近更新：2026-07-27 晚 · 数据时间维度 Phase 5 进行中（S1 事件日志 / S2 点歌双写 / S3 曲谱管理 已上线，S4 学歌打卡 / S5 统计视图 待开发），核实到最新提交 `42fc392`
> 项目整体完工度：引擎层 100%（金标准 16/16 diff=0，独立预言机基准），UI 层约 80%（工作台/歌曲库/学歌/设置/速查/曲谱可用），打包 spike 已过、正式壳 0%

---

## 0. 全局速览：两句话

这是一个「歌单海报生成器」——把 178 首中文歌曲以精美排版打印成竖版海报 PNG（抖音 9:20 全屏），7 套主题、2 页/主题、逐像素排版精度已用金标准锁死。架构是 **Python PIL 引擎 + FastAPI HTTP 后端 + React 前端 + Electron 壳（spike 已过，正式壳未做）**。

**当前状态**：引擎 100% 就绪；金标准为独立预言机基准（16/16 diff=0，随 git 版本化，禁止引擎自举）；CI 三件套在线；Phase 2 全部收官；Phase 3 打包 spike 完成；此后又落地：学歌管理视图、速查小窗 Web 版（/quick）、「今晚歌单」直播点歌队列、歌手/选调回填、UI/UX 快修包、歌曲库响应式卡片网格。**Phase 5（数据时间维度）进行中**：✅ S1 事件日志地基（events.jsonl + 迁移 v4 learned_at/tab_files + 五端点埋点 + /api/events feed）→ ✅ S2 点歌双写上报（/api/events/report + QuickView localStorage 双写保序补报）→ ✅ S3 曲谱管理（data/tabs/ 附件上传/删除/预览 + 曲库/学歌/直播 T 键三触点）→ ⬜ S4 学歌打卡 → ⬜ S5 统计视图。**下一步开发就按仓库 B 的 `design/roadmap-data-stats.md` 继续做 S4/S5**。其余缺口：3 个占位视图（主题/预设/历史）、正式 Electron 壳、引擎魔数清理。另有 UI/UX 重设计提案 v2 交互稿（仓库 B `design/redesign-v2.html`，暗色「演出后台」方向，未落地）。

---

## 1. 项目全景

### 产品定位

主播「梓涵吃不饱」的点歌歌单海报工具。每次直播用 PNG 海报展示已会歌单（按字数分类排版），支持 7 套不同视觉主题。使用场景已确认：**手机直播，电脑运行本软件**（速查走置顶小窗，不做手机查询页）。

### 技术栈（2026-07-25 定稿）

| 层 | 技术 | 说明 |
|---|---|---|
| 渲染引擎 | Python 3.13.14 + PIL/Pillow 12.2.0 | 纯函数库，金标准 16/16 逐像素 diff=0 |
| 后端 | FastAPI（uvicorn 8000 端口） | 23 个 API 端点 |
| 前端 | React 19 + Vite 6 + Tailwind 4 | 多文件结构（views/components），晨光纸感风格 |
| 桌面打包 | Electron（spike 已过） | Python 作 child_process；PyInstaller onefile 后端 |
| 测试 | 金标准逐像素对比 + 42 项单元测试 | make test-unit / make test-golden |

### 已废弃的路由

- PySide6 (Qt) → 改为 FastAPI + Web 前端（2026-07-23）
- Tauri 2.0 sidecar → 改为 Electron child_process（2026-07-25）

### 两个 Git 仓库（刻意不嵌套，各自提交）

| 仓库 | macOS 路径 | GitHub 远程（私有） | 内容 |
|---|---|---|---|
| A 设计 | `song-list/playlist-poster-design/` | `jiaiqi/playlist-poster-design` | 设计结论、项目结构设计、HANDOFF、7 页设计稿、旧脚本、歌单数据 |
| B 产品 | `song-list/playlist-poster-generator/` | `jiaiqi/playlist-poster-generator` | Python 引擎 + FastAPI + React + Electron spike + 主题包 + 测试 |

> 原 Windows 工作目录为 `F:\Desktop\李梓涵\`（外层=A、内层=B）；现主开发机为 macOS，两仓库并列放置。GitHub 账号 `jiaiqi`，macOS 上 SSH 凭据可用（HTTPS 443 不通，克隆/推送走 SSH）。

**协作约定：每次改动都要 git 提交，原子提交、中文提交信息。**

### 仓库 B git log（最新 12 条，截至 2026-07-27 晚）

```
42fc392 feat(tabs): 曲谱管理全链路——附件上传/预览/直播 T 键看谱（S3）
403165c feat(quick): 点歌双写上报——今晚歌单接入事件流（S2）
05ac6e7 feat(data): 事件日志地基 + songs.json 迁移 v4（S1）
cbbc5e1 docs(design): UI/UX 重设计提案 v1/v2 交互稿 + 数据时间维度路线图
52c538d feat(library): 歌曲库改响应式多列卡片网格
b980702 feat(quick): 今晚歌单——直播点歌队列
c942d20 feat(data): 批量回填弹唱选调/capo 27/178（主流弹唱谱版本）
519c919 feat(quick): 速查小窗 Web 版（/quick 路由）
2f803d1 feat(ux): UI/UX 快修包——P0 加载反馈 + P1 信息架构 + P2 引导
b52f198 feat(data): 批量回填歌手字段 141/178（高置信度条目）
f734fab fix(learning): 学歌卡片版收尾——接通编辑对话框 + 共享组件落地
8d8ce92 feat(library): 歌曲库视图重设计 + pinyin 搜索索引回填（迁移 v3）
```

### 仓库 B 结构速览

```
core/        纯函数引擎（spec/style/engine/watermark/mist/context + data/ + layouts/ + themes/）
             data/ 新增 events.py（事件日志）+ tabs.py（曲谱存储）
server/      FastAPI 后端（main.py 约 560 行，23 端点）
ui/src/      React 前端（App.tsx 壳层 + views/{Library,Learning,Settings}View + QuickView
             + components/{ExportDialog,SongEditDialog,TabsPanel} + types/icons）约 1900+ 行
design/      redesign-v1/v2.html（UI/UX 重设计交互稿）+ roadmap-data-stats.md（Phase 5 规格）
electron/    Electron 壳 spike（main.js：spawn 后端 + 就绪轮询 + alwaysOnTop）
packaging/   PyInstaller spike（backend_entry.py + poster-backend.spec）
web/         原生验证页（开发期）
prototype/   高保真原型 + 14 张成品海报 + 背景副本
themes/      7 套主题包（theme.json + 背景图 + 设计理念.md）
fonts/       MaokenAssortedSans.ttf（猫啃糖圆体，免费可商用）
data/        songs.json（v4，178 首，唯一数据源）+ backups/ + events.jsonl（gitignore）
             + tabs/（曲谱附件，gitignore）
output/      默认导出目录
tests/       test_golden.py（16 张，assert 拦截）+ test_unit.py（42 项）+ golden/（参照图入库）
tools/       migrate_data / migrate_themes / regenerate_golden / render_samples / fill_artists / fill_playing_fields
Makefile     test / test-unit / test-golden / run-backend / run-ui / export-sample / regenerate-golden
```

### 仓库 A 结构速览

```
歌单海报生成器-设计结论.md      最权威文档：13 节架构决策
歌单海报生成器-项目结构设计.md   工程蓝图：目录/模块边界/schema/插件接口/验收标准
歌单海报生成器-界面设计/
  HANDOFF.md                  本文档
  shared.css / shared.js      共享设计系统（见 §5）
  design-tokens.json          设计令牌单源真值（亮/暗色板+圆角+投影+字体+缓动）
  pages/                      7 页设计稿 + songs-data.js
  assets/                     主题缩略图 + 海报成品图
歌单-排版一/                   旧脚本 build_playlist.py（独立预言机）+ 歌单数据.md（178 首）
                             + 歌单更新提示词.md（像素级规格）+ 7 主题素材
```

---

## 2. 当前状态：已完成 vs 未完成

### ✅ 已完成

渲染引擎全部模块、7 套主题 JSON 驱动、Song 模型 17 字段（capo Optional[int]、learned_at、tab_files）、FastAPI 23 端点、React 工作台+歌曲库+学歌+设置四视图、速查小窗 Web 版（/quick）、「今晚歌单」点歌队列、视图路由、Ctrl+滚轮缩放、参数折叠面板、300ms 防抖、localStorage 启动恢复、设计令牌单源、42 项单元测试、178 首歌曲补齐、歌手回填 141/178、选调/capo 回填 27/178、pinyin 搜索索引全量回填（迁移 v3）、背景预处理缓存（热渲染 33.8ms）、自动备份（20 份滚动）、版本迁移框架（v1→v2→v3→v4 已实战）、CI 三件套、导出 API（单页+批量后台任务+进度+打开目录）、导出对话框、settings.json 持久化、一键「学会了⇄标回未会」、歌曲编辑全链路（增删改+弹唱字段+pinyin 自动）、参数面板 ParamSpec 动态渲染、状态栏、快捷键（⌘E/⌘R/←→/⌘1~7/⌘,/Esc）、App.tsx 组件拆分、PyInstaller+Electron 打包 spike、UI/UX 快修包（加载反馈/信息架构/引导）、歌曲库响应式卡片网格（auto-fill+四向键盘导航）、**事件日志地基**（events.jsonl 追加式事件流 + 五端点埋点 + /api/events feed + /api/events/report 客户端上报）、**点歌双写**（QuickView localStorage+后端双写、失败保序补报、撤销已唱不上报）、**曲谱管理**（data/tabs/ 附件存储、上传/列表/删除 API、TabsPanel 共享组件、曲库/学歌/直播 T 键三触点、白底卡片渲染兼容透明底谱图）

### ⚠️ 部分完成

| 项 | 缺口 |
|---|---|
| 视图 | 工作台/歌曲库/学歌/设置 ✅；主题/预设/历史 3 个仍占位 |
| 预览 | 切换主题重请求 ✅、Ctrl+滚轮 ✅；双击适应 ❌ |
| 暗色 | 设计令牌有暗色板，React index.css 仅亮态令牌 |

### ❌ 未开始

正式 Electron 壳（electron-builder 工程化：可写目录外置 + Vite 产物进壳 + 原生菜单快捷键）、性能基准脚本、引擎魔数清理

### P0 历史问题（全部已修复）

1. 参数面板装饰性 → 受控 state 拼入 render URL ✅
2. 刷新预览假按钮 → renderKey 强制重请求 ✅
3. 金标准无 assert → assert 拦截 + CI ✅
4. 数据双轨 → SongLibrary.load_from_json + save 原子写，songs.json 为唯一数据源 ✅

---

## 3. 核心引擎架构（必读）

### 四层解耦

```
渲染合成层  engine.py：背景→水印→延展→柔光→排版 → PNG
排版层(Layout 插件)  layouts/grid_wrap.py
主题层(Theme 资源包)  themes/loader.py → theme.json
数据层  data/songs.py：Song + SongLibrary + 分类规则
```

### 铁律

1. `core/` 禁止 import 任何 UI/服务器框架
2. 字体、主题、数据全来自资源文件，代码不得硬编码
3. 金标准逐像素 diff=0 是回归测试死线

### 颜色角色契约（5 角色，排版只认角色不认色值）

`text`（歌名）/ `label`（标签文字）/ `pill`（标签底色 RGBA）/ `line`（下划线）/ `mist`（柔光 RGBA）

### 分组规则（2026-07-25 定案）

1. 优先 `Song.section`（1-7，从旧脚本手工分组迁移；例「恋爱ing」5 字但 section=3）
2. fallback：中文按 len()（>6 归 7），含英文字母归 7

### Song 状态模型（两态简化版）

```
draft 未会 ── mark_active() ──→ active 已会（上海报）
```

### 用户明确的选择（不要推翻，除非有新理由）

- 界面实现位置：静态设计页是**视觉蓝本**，React `ui/` 是工程化载体
- 视觉方向：**晨光纸感 · 清新文艺**（奶油纸底 #f7f6f2 + 海洋青 #2f8f7a + 暖珊瑚 #d9764f + 衬线标题），亮色为主、暗色可选
- 要求：美观精致、方便操作、优雅、动画丝滑

---

## 4. 数据真相（以 data/songs.json 为准）

- **歌曲**：`data/songs.json` v4，178 首（175 active + 3 draft）；artists 回填 141/178，key/capo 回填 27/178，pinyin 全量；v4 新增 learned_at（标记学会时回填）与 tab_files（曲谱附件路径）。学歌 5 首身份已决策为 demo 数据保留现状（坑 17）
- **事件流**：`data/events.jsonl`（gitignore）——追加式 JSONL，9 类事件（song_added/deleted/edited/learned/unlearned、practice_logged、queue_added、song_sung、poster_exported）；songs.json 是当前状态唯一真相，事件流是历史；统计只算不存
- **曲谱附件**：`data/tabs/{歌名}/{文件}`（gitignore），tab_files 存相对 data/ 路径，/tabs 静态路由访问；示例：知足/下雨天 各挂 1 张 G 大调开放和弦图
- **主题**：7 套 = 卡通音符、奶油玻璃、奶油花园、梦幻海洋、海洋柔光、轻复古唱片、青提气泡。theme.json 含双页背景 + 五角色配色。背景图文件名不统一（bg1.png 或 background-1.png，以各自 theme.json 为准）
- **排版**：仅 `grid-wrap`，固定 2 页，支持避让
- **画布预设**：`抖音全屏 9:20`（1080×2400，禁文区 (940,1080,1080,2400)）、`标准 9:16`（1080×1920）
- **排版参数**（ParamSpec）：margin 58 / font_song 36 / row_h 44 / sec_gap 26，另有 font_label 40 / label_h 74

### 后端 API（server/main.py，23 端点）

`/api/health`、`/api/themes`、`/api/layouts`（含 pages/supports_avoidance）、`/api/layouts/{id}/params`、`/api/songs`、`/api/songs/list`、`/api/songs/status|add|update|delete`（POST）、`/api/songs/{title}/tabs`（POST 上传/GET 列表/DELETE 删除）、`/api/events`（feed）、`/api/events/report`（POST 客户端上报，仅 queue_added/song_sung/practice_logged）、`/api/render`（支持参数覆盖）、`/api/export`（POST）、`/api/export/batch`（POST 后台任务）、`/api/export/jobs/{id}`、`/api/export/open`（POST）、`/api/settings`（GET+POST）、`/bg/<主题>/<文件>`、`/tabs/<歌名>/<文件>`

---

## 5. 设计系统使用方式（shared.css / shared.js，设计稿专用）

每页 `<head>` 固定套路（防 FOUC 内联脚本 → Tailwind CDN → lucide CDN → shared.css）：
```html
<script>(function(){var t=localStorage.getItem("gp-theme");if(t==="dark"||(!t&&matchMedia("(prefers-color-scheme: dark)").matches))document.documentElement.classList.add("dark");})();</script>
<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4.3.1/dist/index.global.js"></script>
<script src="https://unpkg.com/lucide@1.8.0/dist/umd/lucide.min.js"></script>
<link rel="stylesheet" href="../shared.css?v=1">
```
页面底部：`<script src="../shared.js?v=1"></script>` + 页面自身脚本。

- **令牌**：`--gp-primary / --gp-background / --gp-card / --gp-muted / --gp-border / --gp-accent` 等，`.dark` 全套暗色覆盖；字体 `--gp-font-serif`（标题衬线）/ `--gp-font-sans`。单源为 `design-tokens.json`，React 端派生到 `ui/src/index.css` 的 Tailwind `@theme`（仅亮态）
- **语义类**：`bg-card`、`text-muted-foreground`、`border-border`、`text-primary` 等
- **组件类**（13 个）：`.gp-card(.gp-card-hover)`、`.gp-btn`、`.gp-btn-ghost`、`.gp-chip(.active)`、`.gp-switch(.on)`、`.gp-input`、`.gp-badge(-accent/-muted)`、`.gp-collapse(+.open)`、`.gp-segment`、`.gp-nav-item(.active)`、`.gp-progress`、`.gp-spinner`
- **动效**：`.gp-stagger(-scale)`、`.gp-rise/.gp-fade/.gp-scale-in/.gp-float`、曲线 `--gp-ease-spring`，内置 `prefers-reduced-motion` 降级
- **JS 能力**（`window.gp`）：`gp.toast(msg, icon)`、`gp.applyTheme/toggleTheme`；自动初始化折叠面板/分段选择器/开关/数字滚动/亮暗切换
- **React 组件对齐率**：约 15%（2/13），多数降级为 Tailwind 原生控件——后续提升视觉精致度的空间在此

---

## 6. 坑位与注意事项（踩过，别再踩）

| # | 坑 | 状态 |
|---|---|---|
| 1 | JS 注释里写路径通配符 `*/` 提前闭合块注释 → 整页白渲染 | 已修 |
| 2 | shared.js 主题持久化：初始化时**不得**写回 localStorage（否则「跟随系统」失效），只有用户主动切换才持久化 | 已知 |
| 3 | python http.server 无 Cache-Control → 旧 shared.js 缓存；引用已加 `?v=1`，改 shared.css/js 后记得 bump | 已知 |
| 4 | 主题背景图装饰集中在底部，缩略图必须 `object-cover object-bottom` | 已对齐 |
| 5 | git 双仓库不要嵌套提交（会形成 gitlink）；外层 .gitignore 已配置 | 已配置 |
| 6 | Windows Git Bash 的 `find` 对中文路径 + `-path` 有 bug，用 `ls -R` 代替 | 已知（Windows） |
| 7 | Pillow 版本敏感，锁定 12.2.0 + Python 3.13.14（.python-version） | 已锁定 |
| 8 | 大量硬编码魔数遍布 engine/grid_wrap/watermark | 已知未修 |
| 9 | server/main.py 全局变量 themes/library，阻碍热重载和测试注入 | 已知 |
| 10 | CORS 全开 `allow_origins=["*"]` | 已知 |
| 11 | engine.py font_song 避让时硬编码降 34（魔数，应来自 CanvasSpec 或插件声明） | 已知 |
| 12 | content_offset 硬编码基准 1920，换画布比例（小红书 3:4 等）会出错 | 已知 |
| 13 | draw_mist 底边坐标硬编码（1498/1410+OFF），换画布高度柔光错位 | 已知 |
| 14 | grid_wrap page_capacity=1920 类属性硬编码，设计要求按画布动态计算 | 已知 |
| 15 | 预览图缓存用 t=renderKey 破坏，未利用 HTTP 缓存；/api/render/etag 坏端点已删除；背景层有 _BG_CACHE 加速 | 已知 |
| 16 | 学歌 5 首身份不一致（设计文档 vs 实际迁移） | 已决策：demo 数据，保留现状 |
| 17 | 设计文档状态模型不一致（§4.1 四态 vs §4.2 两态） | 文档需统一 |
| 18 | 项目结构设计 §5.1 CanvasSpec 仍有 r_below，但设计结论 §3.3 说已下沉 | 文档需同步 |
| 19 | 无 logging 体系，themes/loader.py 用 print | 工程化缺口 |
| 20 | **金标准循环论证**：参照图曾由引擎自举生成，diff=0 成恒等式 | 已修：独立预言机（旧脚本 178 首版）生成 16 张随 git 版本化；regenerate_golden.py 需 --confirm-rebaseline；**禁止再改回引擎自举** |
| 21 | uvicorn.run("server.main:app") 字符串引用不被 PyInstaller 静态分析收编 → 入口必须显式 `from server.main import app`（packaging/backend_entry.py 已示范） | spike 已踩 |
| 22 | PyInstaller _MEIPASS 是进程级临时目录，退出即销毁 → 正式打包时可写路径（songs.json/settings/backups/output）必须解析到用户目录；只读资源（themes/fonts）留 _MEIPASS | spike 已踩 |
| 23 | npm 装 electron 需 `ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/`（直连超时） | spike 已踩 |
| 24 | macOS 本机 GitHub HTTPS 443 不通，git 走 SSH；api.github.com 需代理 127.0.0.1:7890 | 已知（本机网络） |

---

## 7. 开发与验证命令

```bash
# 环境（macOS，项目根 = playlist-poster-generator）
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd ui && npm install && cd ..

# 测试（Makefile 封装：make test / make test-unit / make test-golden）
PYTHONPATH=. .venv/bin/python tests/test_unit.py              # 单元测试 42 项
PYTHONPATH=. .venv/bin/python tests/test_golden.py            # 金标准 16 张，diff=0
cd ui && npx tsc --noEmit                                     # TS 编译检查

# 开发
source .venv/bin/activate && uvicorn server.main:app --reload --port 8000  # 后端
cd ui && npm run dev                                                       # 前端 :5173
```

### 设计稿 agent-browser 验证工作流（仓库 A）

```bash
cd "song-list/playlist-poster-design/歌单海报生成器-界面设计"
python -m http.server 8931 --bind 127.0.0.1          # 后台起静态服务
npx agent-browser set viewport 1600 900
npx agent-browser open "http://127.0.0.1:8931/pages/workspace.html"
npx agent-browser wait 2400 && npx agent-browser screenshot out.png
npx agent-browser set media dark                      # 模拟系统暗色
npx agent-browser snapshot -i                         # 拿交互元素 @eN ref 后 click/fill
npx agent-browser eval 'localStorage.clear()'         # 测暗色前先清 gp-theme
```
页面内联脚本语法检查：提取 `<script>` 内容后 `node --check`。

---

## 8. 打包 spike 结论（Phase 3，2026-07-26）

- **PyInstaller onefile 后端可跑通**：`--add-data themes/fonts/data` 进 _MEIPASS 后渲染结果与开发版**逐像素一致**（diff bbox=None）
- **Electron 链路打通**：spawn 后端 + HTTP 就绪轮询 + BrowserWindow 加载渲染结果；`setAlwaysOnTop(true, "screen-saver")` 实测生效 → 速查小窗（压全屏直播软件）技术前提成立
- 坑位见 §6 的 #21-23

---

## 9. 下一步行动清单

### Phase 5：数据时间维度（进行中，最高优先）

> **规格文档（必读）**：仓库 B `design/roadmap-data-stats.md`——事件 schema、迁移 v4、API 契约、统计口径、验收标准全部在内。
> 关联设计稿：仓库 B `design/redesign-v2.html`（UI/UX 重设计提案 v2，暗色「演出后台」，含统计视图的方向指引，未落地）。

- [x] **S1 事件日志地基** ✅ `05ac6e7`：core/data/events.py + 迁移 v4（learned_at/tab_files）+ 五端点埋点 + /api/events feed
- [x] **S2 点歌双写上报** ✅ `403165c`：/api/events/report + QuickView 双写（localStorage 为现场真相，失败 localStorage 保序补报）
- [x] **S3 曲谱管理** ✅ `42fc392`：core/data/tabs.py + 上传/列表/删除 API + TabsPanel 共享组件 + 曲库/学歌/直播 T 键三触点
- [ ] **S4 学歌打卡**：POST /api/practice/log（写 practice_logged 事件，report 端点已预留该类型）+ 学歌卡片「打卡」按钮（note+可选时长+自评）+ 卡片展开练习时间线 + 累计打卡天数
- [ ] **S5 统计视图**：/api/stats/overview|learning|live（从 events 现算，只算不存）+ 导航第五视图「统计」（总览卡/趋势图/排行榜，口径见规格文档 §8）

### Phase 4：正式 Electron 壳（5-8 天）

- [ ] electron-builder 工程化：可写目录外置（用户目录）+ Vite 静态产物进壳 + 菜单栏原生快捷键
- [ ] 速查小窗 Electron 化（置顶 + 全局热键，Web 版 /quick 已就绪）

### 产品方向（2026-07-25 晚用户确认）

- 使用场景：**手机直播，电脑运行本软件**
- Song 弹唱字段已开始回填（artists 141/178、key/capo 27/178），是速查 2.0 / 专场筛选 / 调式推荐的地基
- 候选方向（未排期）：互动点歌版排版提前、「很久没唱」提醒（可用 song_sung 事件实现 last_sung_at）、专场筛选出图、导出后扫码传手机（局域网二维码）
- 已落地：速查小窗 Web 版、「今晚歌单」点歌队列、曲谱管理、事件流数据沉淀
- UI/UX 重设计提案 v2（暗色「演出后台」）已出交互稿待评审落地，落地顺序：token+组件 → 歌曲库/学歌 → 工作台 → 直播模式

### 工程债（按需）

- 3 个占位视图（主题/预设/历史）
- React 暗态令牌 + gp-* 组件对齐（现约 15%）
- 引擎魔数清理（坑 8/11-14）、logging 体系（坑 19）、性能基准脚本
- 文档统一：状态模型四态/两态（坑 17）、CanvasSpec r_below 表述（坑 18）

---

> **本文档为 Agent 专用交接文档。** 完整设计决策请参阅《歌单海报生成器-设计结论.md》和《歌单海报生成器-项目结构设计.md》。
