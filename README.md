# 歌单海报生成器

把 `歌单-排版一\build_playlist.py` 的 PIL 海报能力升级为桌面 App。**先可用、后惊艳**，前期保证拓展性。

## 技术栈（2026-07-23 确认）
- **渲染引擎**：Python + PIL（纯函数，金标准：与现有 14 张成品逐像素一致）
- **后端**：FastAPI 本地服务（开发期）；MVP 后期由 Tauri 2.0 打包成单 exe（Python 作 sidecar）
- **前端**：Web（React/Vue + Vite，惊艳 UI 后期）；开发期先用 `web/index.html` 原生验证页
- **铁律**：`core/` 禁止 import 任何 UI 框架，UI 只通过 `engine.render_page()` 拿 PIL.Image

## 目录
```
core/        纯函数引擎（spec/style/engine/watermark/mist/context + themes/ + layouts/ + data/）
server/      FastAPI 渲染后端
web/         前端（先可用：index.html 原生验证页；惊艳 React 后期）
themes/      主题包（从 歌单-排版一 复制背景图 + theme.json）
fonts/       字体 MaokenAssortedSans.ttf
```

## 开发期运行
```bash
cd 歌单海报生成器
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
# 复制资源：fonts/MaokenAssortedSans.ttf、themes/<名称>/ 背景图（从 歌单-排版一）
uvicorn server.main:app --reload --port 8000
# 浏览器打开 web/index.html（或 python -m http.server 起静态服务）
```

## git 工作流
- 每次 feature / bug fix 走分支（feature/xxx、fix/xxx），原子提交，信息有意义。
- 可先纯本地提交，**不强制推远程**。

## 待补（MVP 前应完成）
- 数据：脚本 177 首 vs 目标 178 首（缺「奇妙能力歌」），补齐后重跑金标准。
- tools/migrate_data.py：双源校验生成 songs.json 唯一数据源。
- tests/test_golden.py：新引擎 vs 现有 14 张成品逐像素 diff = 0。
