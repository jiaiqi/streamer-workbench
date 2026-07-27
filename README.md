# 歌单海报生成器

把 `歌单-排版一\build_playlist.py` 的 PIL 海报能力升级为桌面 App。**先可用、后惊艳**，前期保证拓展性。

> **进度快照（2026-07-27 晚）**：引擎 100%（金标准 16/16 diff=0）；UI 工作台/歌曲库/学歌/设置/速查（/quick）可用；数据时间维度 Phase 5 进行中——事件日志、点歌双写、曲谱管理已上线（S1-S3），学歌打卡（S4）与统计视图（S5）待开发。**接手开发请读 `design/roadmap-data-stats.md` + `design-docs/歌单海报生成器-界面设计/HANDOFF.md`。**
>
> **单仓库说明（2026-07-27 合并）**：原 `playlist-poster-design` 设计仓库已并入本仓库 `design-docs/`（完整历史保留，GitHub 旧仓库已归档只读）。金标准预言机位于 `design-docs/歌单-排版一/`，随仓库检出，无需软链。

## 技术栈（2026-07-25 定稿，决策过程见设计仓库《歌单海报生成器-设计结论.md》第一节）
- **渲染引擎**：Python + PIL（纯函数，金标准：与现有成品逐像素一致，当前 16/16 diff=0）
- **后端**：FastAPI 本地服务（`server/`，开发期 uvicorn 8000 端口）；MVP 后期由 Electron 打包成桌面 App（Python 作 child_process，引擎不重写）
- **前端**：React 19 + Vite 6 + Tailwind 4（`ui/`，按「晨光纸感」设计稿改造中）；开发期另有 `web/index.html` 原生验证页
- **视觉蓝本**：设计仓库 `歌单海报生成器-界面设计\`（shared.css 设计令牌/组件 + 7 页静态设计稿）
- **铁律**：`core/` 禁止 import 任何 UI/服务器框架，UI 只通过 `engine.render_page()` 拿 PIL.Image
- ~~PySide6 (Qt)~~：已移除（2026-07-23 晚决策，理由见设计结论）

## 目录
```
core/        纯函数引擎（spec/style/engine/watermark/mist/context + themes/ + layouts/ + data/）
server/      FastAPI 渲染后端
web/         原生验证页（开发期）
ui/          React + Vite 前端工作台
design/      UI/UX 重设计提案交互稿（redesign-v1/v2.html）+ 数据时间维度路线图（roadmap-data-stats.md）
design-docs/ 原设计仓库全部内容（设计结论/项目结构设计/HANDOFF/7 页设计稿/歌单-排版一 预言机）
prototype/   高保真 UI 原型 + 7 主题背景 + 14 张成品海报
themes/      主题包（从 歌单-排版一 复制背景图 + theme.json）
fonts/       字体 MaokenAssortedSans.ttf
tests/       test_golden.py 金标准逐像素对比
tools/       迁移与样例渲染脚本
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
# design-docs/歌单-排版一/，重建方式见 tools/regenerate_golden.py
PYTHONPATH=. python tests/test_golden.py             # 目标：16/16 逐像素 diff=0
```

## 后端 API（server/main.py）
`GET /api/health`、`/api/themes`、`/api/layouts`（含 pages/supports_avoidance）、`/api/layouts/{id}/params`（ParamSpec 参数描述）、`/api/songs`、`/api/render?theme=&page=&canvas=&avoid=&layout=&margin=&font_song=&row_h=&sec_gap=`（支持排版参数覆盖）、`/bg/<主题>/<文件>` 静态背景。

## git 工作流
- 每次 feature / bug fix 走分支（feature/xxx、fix/xxx），原子提交，信息有意义。
- 可先纯本地提交，**不强制推远程**。

## MVP 阻塞项（2026-07-25 已全部完成）
- ~~数据补齐~~：已补「奇妙能力歌」→ 178 首。金标准 14/14 diff=0。
- ~~tools/migrate_data.py~~：已完成。双源校验通过，已产出 data/songs.json（178 首）。
- React `ui/` 按「晨光纸感」设计稿改造（设计稿即视觉蓝本；API 已就绪）。
- ~~后端 API 缺口~~（2026-07-25 已补）。
