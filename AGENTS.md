# Agent 项目规则

> 此文件供 AI 编码助手（Agent）读取并遵守。每次接手时首先读取本文。
> 最后更新：2026-07-27

---

## 项目身份

- **中文名**：主播工作台
- **英文名**：streamer-workbench
- **旧名**：歌单海报生成器 / playlist-poster-generator（GitHub 远程仓仍为旧名，推送走 SSH）
- **定位**：音乐主播的内容与直播运营工作台。对外可称"主播演出后台"。
- **不再称"歌单海报生成器"**——所有新文档、代码注释、UI 文字均使用新名。

---

## 不可违反的铁律

1. **`.archive/` 目录是只读归档**。该目录下的任何文件（HANDOFF.md / 设计结论 / 项目结构设计 / 设计稿等）**不得修改、删除或移动**。它们是原设计仓库的历史快照。
2. **`core/` 禁止 import 任何 UI/服务器框架**（FastAPI / Electron / React / PySide6 均不可在此出现）。
3. **金标准 16/16 diff=0 是回归死线**。禁止用新引擎自举覆盖旧基线。金标准参照图位于 `tests/golden/`，独立预言机位于 `.archive/design-docs/歌单-排版一/build_playlist.py`。
4. **`Song.pinned` 不新增**。主推使用 Preset 手动集合、最近学会或点歌热度规则。
5. **`grid-wrap` 固定 2 页兼容模式**（ADR-002）。新布局使用 `pages=auto`。去魔数不改变旧金标准输出。
6. **Palette v1 只包含 5 个颜色角色**（text/label/pill/line/mist）+ font_roles（title/label/song/note）。不把 UI token（surface/border/accent）混入海报 Palette。
7. **Anchors/subjects 使用 0–1 归一化坐标**。像素输入仅作为兼容层。
8. **`halo` 和 `vinyl-rings` 已统一为 `subject-orbit`**，不重复实现。
9. **编辑器（P8）只在 3 套新布局上线并被真实使用后启动**，不提前造完整图片编辑器。

---

## 当前活跃规格与状态

### 规格文档

| 文档 | 路径 | 用途 |
|---|---|---|
| **唯一执行主规格** | `design/产品优化方案终版-0727/产品优化方案终版.md` | 产品/UI/架构/多布局完整规格 |
| **唯一路线图** | `design/产品优化方案终版-0727/路线图.md` | P0–P9 执行路径与阶段门 |
| **差异裁决** | `design/产品优化方案终版-0727/三方案差异分析.md` | 前序方案合并记录 |
| **数据路线图（S1–S5）** | `design/roadmap-data-stats.md` | 事件 Schema/统计口径唯一真相 |
| **架构决策记录** | `ADR-001.md`（产品边界）、`ADR-002.md`（grid-wrap 兼容） |
| **项目 README** | `README.md` | 运行命令/目录结构/API 列表 |
| **设计系统** | `.archive/design-docs/歌单海报生成器-界面设计/` | shared.css / design-tokens.json / 7 页设计稿（只读引用） |

### 当前完成状态

```
引擎层    100% ✅    金标准 16/16 diff=0
数据层    S1-S3 ✅   S4 学歌打卡 ⬜  S5 统计视图 ⬜
产品主线  P0 ✅      P1 ✅           P2 ⬜（见路线图）
桌面壳    spike 已过  正式壳 ⬜
UI        ~80%       工作台/歌曲库/学歌/速查可用
```

### 技术栈

| 层 | 技术 | 说明 |
|---|---|---|
| 渲染引擎 | Python 3.12.10 + Pillow 12.3.0 | 纯函数，金标准保护 |
| 后端 | FastAPI 0.135.3 + uvicorn | `server/`，已拆分为 deps + routers（6 个） |
| 前端 | React 19 + Vite 6 + Tailwind 4 | `ui/` |
| 数据 | JSON + JSONL 本地文件 | songs.json v4（178 首）、events.jsonl、settings.json |
| 桌面壳 | Electron（spike） | Python 作 child_process，正式壳未完成 |
| 字体 | MaokenAssortedSans.ttf（猫啃糖圆体） | `fonts/` |
| 测试 | 47 项单元测试 + 16 张金标准逐像素 + tsc --noEmit | |

---

## 目录结构速览

```
.
├── AGENTS.md                       ← 本文件
├── README.md                       项目入口
├── ADR-001.md / ADR-002.md         架构决策记录
├── P0_现状快照.md                  P0 基线快照
│
├── design/                         活跃设计文档（可修改）
│   ├── 产品优化方案终版-0727/       唯一执行主规格
│   ├── roadmap-data-stats.md        S1-S5 数据规格
│   └── redesign-v1/v2.html          UI 交互稿
│
├── .archive/                       只读归档（不可修改）
│   └── design-docs/                原设计仓库全部内容
│
├── core/                           纯函数引擎（不 import 任何 UI/服务框架）
│   ├── engine.py                   渲染管线（87 行）
│   ├── spec.py                     CanvasSpec
│   ├── mist.py / watermark.py      柔光/水印
│   ├── context.py                  DrawContext
│   ├── layouts/                    grid-wrap（唯一内置布局）
│   ├── themes/                     model/loader/palette/skin
│   └── data/                       songs/events/tabs/presets
│
├── server/                         FastAPI 后端
│   ├── main.py                     app 装配（~50 行）
│   ├── deps.py                     依赖注入 + 路径常量
│   └── routers/                    songs/render/export/events/settings/presets
│
├── ui/src/                         React 前端
│   ├── App.tsx                     工作台
│   ├── QuickView.tsx               直播速查
│   └── views/                      Library/Learning/Settings
│
├── tools/                          benchmark.py / migrate_data.py / regenerate_golden.py
├── tests/                          test_golden.py / test_unit.py / golden/（16 PNG）
├── themes/                         7 套主题（theme.json + 背景图）
└── docs/                           GitHub Pages 落地页（构建产物，非文档）
```

---

## 用户数据目录

| 平台 | 默认路径 |
|---|---|
| Windows | `%APPDATA%\streamer-workbench\` |
| macOS | `~/Library/Application Support/streamer-workbench/` |
| 开发期 | 项目根 `data/` |

用户可在设置页自由修改路径。Web 端（Chrome/Edge 86+）使用 `showDirectoryPicker` 选择目录；Electron 端使用原生文件对话框。不支持 File System Access API 的浏览器降级为文本输入。

---

## 分支与提交流程

- 每次 feature / bug fix 走分支（`feature/xxx`、`fix/xxx`），**不在 master 上直接开发**。
- 原子提交，中文摘要，Conventional Commits 风格：`feat/fix/docs/refactor(scope): 中文描述`
- 触及引擎输出时必须先跑 `PYTHONPATH=. python tests/test_golden.py`
- Python 改动运行 `PYTHONPATH=. python tests/test_unit.py`
- React 改动运行 `cd ui && npx tsc --noEmit`
- 允许纯本地提交，不强制推远程。
- 推远程走 SSH：`git push git@github.com:jiaiqi/playlist-poster-generator.git HEAD:master`
- **不 force push，不改写已发布历史**。

---

## 已完成的魔数治理（P0）

| 魔数 | 位置 | 去向 |
|---|---|---|
| `OFF = (CH - 1920) // 2` | `engine.py:33` | `spec.content_offset` |
| 避让字号硬编码 34 | `engine.py:79` | `spec.font_song_avoid` |
| 禁文矩形 ×3 重复 | `server/main.py:341/413/521` | `spec.AVOID_ZONES_X*` |
| 柔光底边 1498/1410 | `mist.py:12` | 参数化到函数签名 |
| `page_capacity` 双位置 | `base.py:35` + `grid_wrap.py:42` | `get_page_capacity(spec)` 动态计算 |
| font 无缓存 | `engine.py` | `@lru_cache` 32 条目 |
| benchmark 无工具 | 新增 | `python tools/benchmark.py` |

---

## 已知环境问题

| 问题 | 应对 |
|---|---|
| GitHub HTTPS 443 不通 | 走 SSH：`git push git@github.com:...` |
| `pypinyin` 未安装 | `pip install pypinyin`（迁移测试依赖） |
| Windows Git Bash `grep` 中文路径 bug | 用 `ls -R` 代替 `find` |
| 主题背景图命名不统一 | 6 套用 `bg1.png`，海洋柔光独用 `background-1.png`，以各自 `theme.json` 为准 |
| 缩略图 `object-cover` | 背景装饰集中在底部，必须 `object-cover object-bottom` |

---

## 关键命令速查

```bash
# 测试
PYTHONPATH=. python tests/test_golden.py     # 金标准 16/16
PYTHONPATH=. python tests/test_unit.py        # 单元测试 47 项
cd ui && npx tsc --noEmit                    # TS 编译检查

# 运行
uvicorn server.main:app --reload --port 8000  # 后端
cd ui && npm run dev                          # 前端

# 基准测试
PYTHONPATH=. python tools/benchmark.py        # 渲染性能

# 推送
git push git@github.com:jiaiqi/playlist-poster-generator.git HEAD:master
```
