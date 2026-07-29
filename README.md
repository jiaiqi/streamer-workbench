# 主播工作台 / streamer-workbench

面向音乐主播的内容与直播运营工作台。日常面管歌曲与学歌，创作面做海报与预设，直播面支持速查与点歌。**先可用、后惊艳**，前期保证拓展性。

> **进度快照（2026-07-29）**：旧 `grid-wrap` 金标准保持 16/16 diff=0；S1–S3.5、R0.1–R0.6 已完成。R0.7 已完成四类文件 Repository、Preset 崩溃恢复、EventStore 索引、跨 app 组合可靠性，以及导出 Application Service/不可变 ExportSnapshot 纵向切片；歌曲、Preset、设置等写操作仍需逐步迁入应用服务，因此 R0.7 继续标为进行中。R0.8 仅完成错误/API 合约基础，用户数据目录和本地服务安全仍待后续阶段。R1a 将用 `grid-wrap` 跑通独立海报固定两页兼容闭环；R1b 再用具体的 `magazine-flow` 验证自动分页，避免破坏旧金标准或提前建设通用运行时。海报不依赖直播场次；直播点歌使用独立的规则、权益、队列和结果台账。文档入口见 [`design/产品优化方案终版-0727/README.md`](design/产品优化方案终版-0727/README.md)。
>
> **单仓库说明（2026-07-27 合并）**：原 `playlist-poster-design` 设计仓库已并入本仓库 `.archive/design-docs/`（原 `design-docs/`，点号开头表示已归档；完整历史保留，GitHub 旧仓库已归档只读）。金标准预言机位于 `.archive/design-docs/歌单-排版一/`，随仓库检出，无需软链。

## 技术栈
- **渲染引擎**：Python + PIL（纯函数，金标准：与现有成品逐像素一致，当前 16/16 diff=0）
- **后端**：FastAPI 本地服务（`server/`，开发期 uvicorn 8000 端口）；MVP 后期由 Electron 打包成桌面 App（Python 作 child_process，引擎不重写）
- **前端**：React 19 + Vite 6 + Tailwind 4（`ui/`）；开发期另有 `web/index.html` 原生验证页
- **视觉系统**：`design/design-tokens.json` v3 是当前单源真值；React 工作台支持画廊白/暗色舞台与独立可选应用主色，应用主色不影响海报 Theme/Palette；`.archive/design-docs/歌单海报生成器-界面设计/` 仅作历史参考
- **铁律**：`core/` 禁止 import 任何 UI/服务器框架；React 只通过 FastAPI 访问核心业务和渲染能力
- ~~PySide6 (Qt)~~：已移除（2026-07-23 晚决策，理由见设计结论）

## 目录
```
core/        领域数据与纯渲染核心（禁止依赖 UI/服务框架）
server/      FastAPI 本地服务（AppContext + Repository adapters + services + routers）
electron/    Electron 壳 spike（正式 Desktop Beta 未完成）
web/         原生验证页（开发期）
ui/          React + Vite 前端工作台
design/      活跃规格、数据路线图、设计令牌；design/archive/ 为已退役文档
.archive/    原设计仓库不可变历史；除金标准预言机外不作为当前规格
tools/       迁移、样例渲染与 benchmark 脚本
```

## 开发期运行
```bash
# 后端（项目根目录）
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn server.main:app --reload --port 8000

# 前端（React 工作台）
cd ui && npm install && npm run dev                  # http://localhost:5173，/api 与 /bg 已代理到 8000

# 或打开原生验证页 web/index.html（python -m http.server 起静态服务）
```

## 金标准测试
```bash
# 金标准参照图（tests/golden/）随 git 提交；独立预言机（旧脚本）已并入本仓库
# `.archive/design-docs/歌单-排版一/`，重建方式见 tools/regenerate_golden.py
PYTHONPATH=. python tests/test_golden.py             # 目标：16/16 逐像素 diff=0
```

Windows PowerShell：

```powershell
$env:PYTHONPATH='.'
$env:PYTHONUTF8='1'
& '.venv\Scripts\python.exe' tests/test_golden.py
& '.venv\Scripts\python.exe' tests/test_unit.py
cd ui; npx tsc --noEmit
```

当前 CI 质量基线为 Python 测试 148 项、前端测试 12 项、金标准 16/16 diff=0，并检查 OpenAPI TypeScript 类型漂移、`tsc --noEmit` 与前端 build。Windows 控制台 UTF-8 和统一测试入口仍属于 R0.12。

## 后端 API

当前路由按能力拆在 `server/routers/`：

- 健康与资源：`GET /api/health`、`/api/themes`、`/api/layouts`、`/api/layouts/{id}/params`；
- 歌曲与曲谱：`/api/songs*`、`/api/songs/{identity}/tabs`（`song_id` 优先，title 仅为迁移期兼容）；
- 渲染与导出：`GET /api/render`、`POST /api/export`、`POST /api/export/batch`；
- 事件、设置、预设：`/api/events*`、`/api/settings`、`/api/presets*`。

目标 API 契约和迁移阶段见主规格 §10.3 与路线图 R0；README 不重复维护完整参数表。

## git 工作流
- 每次 feature / bug fix 走分支（feature/xxx、fix/xxx），原子提交，信息有意义。
- 可先纯本地提交，**不强制推远程**。

## 文档状态

- 当前目标：`design/产品优化方案终版-0727/产品优化方案终版.md`；2026-07-29 详细增量规格：`design/产品优化方案终版-0727/产品与技术规格-v3.md`；
- 当前顺序：`design/产品优化方案终版-0727/路线图.md`；
- 数据口径：`design/roadmap-data-stats.md`；
- 架构决策：`ADR-001.md`–`ADR-008.md`；
- `design/archive/` 和 `.archive/` 中的文档均已退役，不得作为当前执行依据。
