# 歌单海报生成器

把 `歌单-排版一\build_playlist.py` 的 PIL 海报能力升级为桌面 App。**先可用、后惊艳**，前期保证拓展性。

## 技术栈（2026-07-25 定稿，决策过程见设计仓库《歌单海报生成器-设计结论.md》第一节）
- **渲染引擎**：Python + PIL（纯函数，金标准：与现有成品逐像素一致，当前 16/16 diff=0）
- **后端**：FastAPI 本地服务（`server/`，开发期 uvicorn 8000 端口）；MVP 后期由 Tauri 2.0 打包成桌面 App（Python 作 sidecar，引擎不重写）
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
# 前提：金标准参照图在设计仓库的 歌单-排版一/，测试以 ../歌单-排版一 相对路径引用——
# 两个仓库并列克隆，或在本仓库上级目录建软链：ln -s playlist-poster-design/歌单-排版一 ../歌单-排版一
PYTHONPATH=. python tests/test_golden.py             # 目标：16/16 逐像素 diff=0
```

## 后端 API（server/main.py）
`GET /api/health`、`/api/themes`、`/api/layouts`（含 pages/supports_avoidance）、`/api/layouts/{id}/params`（ParamSpec 参数描述）、`/api/songs`、`/api/render?theme=&page=&canvas=&avoid=&layout=&margin=&font_song=&row_h=&sec_gap=`（支持排版参数覆盖）、`/bg/<主题>/<文件>` 静态背景。

## git 工作流
- 每次 feature / bug fix 走分支（feature/xxx、fix/xxx），原子提交，信息有意义。
- 可先纯本地提交，**不强制推远程**。

## 待补（MVP 前应完成）
- 数据：脚本 177 首 vs 目标 178 首（缺「奇妙能力歌」），补齐后重跑金标准。
- tools/migrate_data.py：双源校验生成 songs.json 唯一数据源。
- React `ui/` 按「晨光纸感」设计稿改造（设计稿即视觉蓝本；API 已就绪）。
- ~~后端 API 缺口~~（2026-07-25 已补：layouts 元数据、params 端点、render 参数覆盖、vite /bg 代理）。
