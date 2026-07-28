# 主播工作台 / streamer-workbench

面向音乐主播的内容与直播运营工作台。日常面管歌曲与学歌，创作面做海报与预设，直播面支持速查与点歌。**先可用、后惊艳**，前期保证拓展性。

> **进度快照（2026-07-28）**：旧 `grid-wrap` 金标准仍为 16/16 diff=0；S1–S3 代码已完成。当前唯一活跃阶段为 **R0 正确性与应用边界收口**：avoid/cache、Song v5、Event v2 已完成；tabs/queue/Preset 的 `song_id` 迁移、AppContext、Repository 写入可靠性、类型化 API、用户数据目录和本地服务安全待完成。下一条用户可见主线是使用现有 `grid-wrap` 跑通“样例数据 → 本场 → 歌曲集合 → 模板 → 导出”。文档入口见 [`design/产品优化方案终版-0727/README.md`](design/产品优化方案终版-0727/README.md)。
>
> **单仓库说明（2026-07-27 合并）**：原 `playlist-poster-design` 设计仓库已并入本仓库 `.archive/design-docs/`（原 `design-docs/`，点号开头表示已归档；完整历史保留，GitHub 旧仓库已归档只读）。金标准预言机位于 `.archive/design-docs/歌单-排版一/`，随仓库检出，无需软链。

## 技术栈
- **渲染引擎**：Python + PIL（纯函数，金标准：与现有成品逐像素一致，当前 16/16 diff=0）
- **后端**：FastAPI 本地服务（`server/`，开发期 uvicorn 8000 端口）；MVP 后期由 Electron 打包成桌面 App（Python 作 child_process，引擎不重写）
- **前端**：React 19 + Vite 6 + Tailwind 4（`ui/`）；开发期另有 `web/index.html` 原生验证页
- **视觉系统**：`design/design-tokens.json` v2 是当前单源真值；React 工作台默认使用画廊白 Art Gallery，QuickView/演出模式使用暗色舞台 Cinematic Stage；`.archive/design-docs/歌单海报生成器-界面设计/` 仅作历史参考
- **铁律**：`core/` 禁止 import 任何 UI/服务器框架；React 只通过 FastAPI 访问核心业务和渲染能力
- ~~PySide6 (Qt)~~：已移除（2026-07-23 晚决策，理由见设计结论）

## 目录
```
core/        领域数据与纯渲染核心（禁止依赖 UI/服务框架）
server/      FastAPI 本地服务（当前 main/deps + routers；目标 AppContext + services）
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

当前 Windows 直接单元测试 runner 为 56/56；Preset 测试已改用平台临时目录。金标准保持 16/16 diff=0。

## 后端 API

当前路由按能力拆在 `server/routers/`：

- 健康与资源：`GET /api/health`、`/api/themes`、`/api/layouts`、`/api/layouts/{id}/params`；
- 歌曲与曲谱：`/api/songs*`、`/api/songs/{title}/tabs`（title 路由为待迁移兼容接口）；
- 渲染与导出：`GET /api/render`、`POST /api/export`、`POST /api/export/batch`；
- 事件、设置、预设：`/api/events*`、`/api/settings`、`/api/presets*`。

目标 API 契约和迁移阶段见主规格 §10.3 与路线图 R0；README 不重复维护完整参数表。

## git 工作流
- 每次 feature / bug fix 走分支（feature/xxx、fix/xxx），原子提交，信息有意义。
- 可先纯本地提交，**不强制推远程**。

## 文档状态

- 当前目标：`design/产品优化方案终版-0727/产品优化方案终版.md`；
- 当前顺序：`design/产品优化方案终版-0727/路线图.md`；
- 数据口径：`design/roadmap-data-stats.md`；
- 架构决策：`ADR-001.md`–`ADR-005.md`；
- `design/archive/` 和 `.archive/` 中的文档均已退役，不得作为当前执行依据。
