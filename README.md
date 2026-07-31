# 主播工作台 / streamer-workbench

面向音乐主播的内容与直播运营工作台。日常面管歌曲与学歌，创作面做海报与预设，直播面支持速查与点歌。**先可用、后惊艳**，前期保证拓展性。

> **进度快照（2026-07-30 末）**：R0（数据/应用/服务契约）、R1a（海报闭环）、R1b（magazine-flow 自动分页）、R3（直播核心纵切）全闭合并 push origin/master。Electron 桌面壳 dev 模式已落地。
>
> **测试基线（push 验证）**：Python 31/31（含 13 端到端 ASGI 测试）+ vitest 34/34（UI） + node:test 16/16 + grid-wrap 金标准 16/16 + magazine-flow 代表性 PNG 6 张；TSC 干净，build 干净。
>
> **已上线能力**：
> - **P1 R1a 海报闭环** — PosterDocument 领域 + 仓储（CAS/原子写/恢复）+ 服务（resolve/写穿）+ HTTP `/api/posters*` + 样例曲库 + 能力声明 + RenderDocument；前端 `usePosterStore` 状态机 + 自动保存 + Bridge；最近海报 3 动作内可导出。
> - **P2 R1b magazine-flow** — 刊头 + 双/三栏 + `pages=auto`；6 种分类轴 (chars/artist/genre/language/initial/status)；`/api/layouts/magazine-flow/analyze` 返回容量/页数/溢出；前端 `LayoutPicker` + 缩略图组件。
> - **P3 R2 直播闭环** — LiveSession/SongRequest/QueueEntry/PerformanceRecord/RequestPolicy/EntitlementGrant 6 个 dataclass；EntitlementService 幂等核销（command_id）+ 返还；RequestPolicyService 决策 + 公平保护；LiveService 状态机 + duplicate_merged；LiveRepository（CAS/原子写/恢复）；LiveSessionPersistenceService 写穿 + 重启恢复；HTTP `/api/live-sessions*` 7 端点；lifespan 启动自动 load 已存会话。
> - **P3 Electron 桌面壳（dev 模式）** — `electron/main.js` 启动时按需 spawn Vite (5174 strictPort) + Python uvicorn (8765)；主窗口加载工作台；菜单「窗口 → 打开置顶速查 (Cmd/Ctrl+Shift+U)」在子进程内开 alwaysOnTop + screen-saver 层级窗口（可压 OBS 全屏投影）；子进程异常退出 → 弹错并退出；quit 杀子进程无孤儿。**不打包**（PyInstaller/electron-builder 留 R7）。
>
> **未做**：P4 S4 学歌打卡 + 统计 + 乐理；P5 统计页（前端页面）；P6 R5 工作台系统化（动效 + 无障碍 + 响应式）；Electron 正式打包。
>
> 文档入口见 [`HANDOFF.md`](HANDOFF.md) 与 [`design/产品优化方案终版-0727/README.md`](design/产品优化方案终版-0727/README.md)。
>
> **单仓库说明（2026-07-27 合并）**：原 `playlist-poster-design` 设计仓库已并入本仓库 `.archive/design-docs/`（原 `design-docs/`，点号开头表示已归档；完整历史保留，GitHub 旧仓库已归档只读）。金标准预言机位于 `.archive/design-docs/歌单-排版一/`，随仓库检出，无需软链。

## 技术栈
- **渲染引擎**：Python + PIL（纯函数，金标准：与现有成品逐像素一致，当前 16/16 diff=0）
- **后端**：FastAPI 本地服务（`server/`，开发期 uvicorn 8765 端口）；Electron 桌面壳（`electron/`，dev 模式不打包）spawn Python 作 child_process，引擎不重写
- **前端**：React 19 + Vite 6 + Tailwind 4 + shadcn/ui（`ui/`）；组件优先使用 shadcn/ui（`ui/src/components/ui/`），shadcn 不满足需求再自写组件；开发期另有 `web/index.html` 原生验证页
- **视觉系统**：`design/design-tokens.json` v3 是当前单源真值；React 工作台支持画廊白/暗色舞台与独立可选应用主色，应用主色不影响海报 Theme/Palette；`.archive/design-docs/歌单海报生成器-界面设计/` 仅作历史参考
- **铁律**：`core/` 禁止 import 任何 UI/服务器框架；React 只通过 FastAPI 访问核心业务和渲染能力
- ~~PySide6 (Qt)~~：已移除（2026-07-23 晚决策，理由见设计结论）

## 目录
```
core/        领域数据与纯渲染核心（禁止依赖 UI/服务框架）
server/      FastAPI 本地服务（AppContext + Repository adapters + services + routers）
electron/    Electron 桌面壳（dev 模式；不打包）— 主窗口 + 置顶速查子窗口
web/         原生验证页（开发期）
ui/          React + Vite 前端工作台
design/      活跃规格、数据路线图、设计令牌；design/archive/ 为已退役文档
.archive/    原设计仓库不可变历史；除金标准预言机外不作为当前规格
tools/       迁移、样例渲染与 benchmark 脚本
```

## 开发期运行

### 浏览器模式（手动启前后端）
```bash
# 后端（项目根目录）
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m server --port 8765

# 前端（React 工作台）
cd ui && npm install && npm run dev                  # http://localhost:5174 (strictPort)，/api 已代理到 8765
```

### Electron 桌面壳（dev 模式）
```bash
# 1) 首次安装 Electron 依赖
cd electron && npm install

# 2) 启动桌面壳 — 会自动探测并 spawn 8765 (Python) / 5174 (Vite)
npm start
```
Electron 启动行为：
- 若 8765 / 5174 已被外部占用 → 复用，不重复启动
- 若空闲 → spawn 子进程；quit 时 kill（无孤儿）
- 启动后子进程异常退出 → 弹错并退出 Electron
- 菜单「窗口 → 打开置顶速查」或 `Cmd/Ctrl+Shift+U` → 打开 alwaysOnTop + screen-saver 层级子窗口
- 环境变量（可选）：
  - `STREAMER_REPO_ROOT` 自定义仓库根
  - `STREAMER_VENV_PYTHON` 自定义 venv python
  - `STREAMER_VITE_BIN` 自定义 vite 可执行
  - `STREAMER_VITE_PORT` (默认 5174) / `STREAMER_PY_PORT` (默认 8765)
  - `STREAMER_NO_SPAWN=1` 强制不 spawn（用户自行起 8765/5174）

后端配置只接受 `127.0.0.1`、`::1` 或 `localhost` 等 loopback 地址。开发模式默认仅放行
`http://localhost:5173` 与 `http://127.0.0.1:5173`；如 Vite 使用其他本机端口，可通过
`STREAMER_WORKBENCH_ALLOWED_ORIGINS` 提供逗号分隔的明确 Origin。桌面模式必须设置每次启动
随机生成的 `STREAMER_WORKBENCH_SESSION_TOKEN`，写请求通过 `X-Streamer-Session` 传递；
令牌不得持久化或写入日志。

`web/index.html` 是旧版诊断页，不再作为默认运行入口。如需追溯验证，可在固定本机端口启动，
并把该端口的完整 Origin 显式加入 `STREAMER_WORKBENCH_ALLOWED_ORIGINS` 后重启后端。

## 金标准测试
```bash
# 统一入口（推荐）：自动注入 PYTHONUTF8/PYTHONPATH，Windows 控制台无需手工设环境变量
python tools/run_tests.py                        # 全部 13 个测试文件
python tools/run_tests.py test_golden test_unit  # 只跑指定文件
# 单跑金标准：目标 16/16 逐像素 diff=0（tests/golden/ 随 git 提交；独立预言机在
# `.archive/design-docs/歌单-排版一/`，重建方式见 tools/regenerate_golden.py）
PYTHONPATH=. python tests/test_golden.py
```

Windows PowerShell：

```powershell
& '.venv\Scripts\python.exe' tools\run_tests.py   # 统一入口，已内化 UTF-8
cd ui; npx tsc --noEmit
```

当前 CI 质量基线为 Python 测试 202 项（13 个测试文件）、前端测试 22 项（含 6 项 React 交互测试）、金标准 16/16 diff=0，并检查 OpenAPI TypeScript 类型漂移、`tsc --noEmit` 与前端 build。前端已接入画廊白/暗色舞台、跟随系统及 8 种应用主色；这些应用令牌不影响海报 Palette。

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
