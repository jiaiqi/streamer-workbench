# 主播工作台 / streamer-workbench

面向音乐主播的内容与直播运营工作台。日常面管歌曲与学歌，创作面做海报与预设，直播面支持速查与点歌。**先可用、后惊艳**，前期保证拓展性。

> **进度快照（2026-07-30）**：旧 `grid-wrap` 金标准保持 16/16 diff=0；S1–S3.5、R0.1–R0.8 已完成。四类文件 Repository、恢复与索引、跨 app 组合可靠性，以及导出、歌曲、曲谱附件、Preset 和 Settings 五条 Application Service 纵向切片均已闭合。全部 React 业务视图已统一走 `apiClient`，具备加载、空、错误、重试、取消、竞态和写失败反馈；设置持久化 `appearanceMode`、`applicationAccentId`，应用主色不进入海报 Theme/Palette。R0.11 Preset/API 欠账已关闭。R0.10 后端边界已拒绝非 loopback 配置、任意 CORS 来源和未授权写请求，Electron 令牌注入、CSP/导航边界随 R2.6 壳层闭合；用户数据目录仍待 R0.9。R1a 将用 `grid-wrap` 跑通独立海报固定两页兼容闭环；R1b 再用具体的 `magazine-flow` 验证自动分页，避免破坏旧金标准或提前建设通用运行时。海报不依赖直播场次；直播点歌使用独立的规则、权益、队列和结果台账。文档入口见 [`design/产品优化方案终版-0727/README.md`](design/产品优化方案终版-0727/README.md)。
>
> **单仓库说明（2026-07-27 合并）**：原 `playlist-poster-design` 设计仓库已并入本仓库 `.archive/design-docs/`（原 `design-docs/`，点号开头表示已归档；完整历史保留，GitHub 旧仓库已归档只读）。金标准预言机位于 `.archive/design-docs/歌单-排版一/`，随仓库检出，无需软链。

## 技术栈
- **渲染引擎**：Python + PIL（纯函数，金标准：与现有成品逐像素一致，当前 16/16 diff=0）
- **后端**：FastAPI 本地服务（`server/`，开发期 uvicorn 8000 端口）；MVP 后期由 Electron 打包成桌面 App（Python 作 child_process，引擎不重写）
- **前端**：React 19 + Vite 6 + Tailwind 4 + shadcn/ui（`ui/`）；组件优先使用 shadcn/ui（`ui/src/components/ui/`），shadcn 不满足需求再自写组件；开发期另有 `web/index.html` 原生验证页
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
python -m server --reload --port 8000

# 前端（React 工作台）
cd ui && npm install && npm run dev                  # http://localhost:5173，/api 与 /bg 已代理到 8000

```

后端配置只接受 `127.0.0.1`、`::1` 或 `localhost` 等 loopback 地址。开发模式默认仅放行
`http://localhost:5173` 与 `http://127.0.0.1:5173`；如 Vite 使用其他本机端口，可通过
`STREAMER_WORKBENCH_ALLOWED_ORIGINS` 提供逗号分隔的明确 Origin。桌面模式必须设置每次启动
随机生成的 `STREAMER_WORKBENCH_SESSION_TOKEN`，写请求通过 `X-Streamer-Session` 传递；
令牌不得持久化或写入日志。

`web/index.html` 是旧版诊断页，不再作为默认运行入口。如需追溯验证，可在固定本机端口启动，
并把该端口的完整 Origin 显式加入 `STREAMER_WORKBENCH_ALLOWED_ORIGINS` 后重启后端。

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

当前 CI 质量基线为 Python 测试 189 项、前端测试 22 项（含 6 项 React 交互测试）、金标准 16/16 diff=0，并检查 OpenAPI TypeScript 类型漂移、`tsc --noEmit` 与前端 build。前端已接入画廊白/暗色舞台、跟随系统及 8 种应用主色；这些应用令牌不影响海报 Palette。Windows 控制台 UTF-8 和统一测试入口仍属于 R0.12。

## 后端 API

当前路由按能力拆在 `server/routers/`：

- 健康与资源：`GET /api/health`、`/api/themes`、`/api/layouts`、`/api/layouts/{id}/params`；
- 歌曲与曲谱：`/api/songs*`、`/api/songs/{identity}/tabs`（`song_id` 优先，title 仅为迁移期兼容）；
- 渲染与导出：`GET /api/render`、`POST /api/export`、`POST /api/export/batch`；
- 事件、设置、预设：`/api/events*`、`/api/settings`、`/api/presets*`；预设支持复制、软删除与 `POST /api/presets/{id}/default` 默认切换。

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
