# Agent 项目规则

> 此文件供 AI 编码助手（Agent）读取并遵守。每次接手时首先读取本文。
> 最后更新：2026-07-30

---

## 项目身份

- **中文名**：主播工作台
- **英文名**：streamer-workbench
- **旧名**：歌单海报生成器 / playlist-poster-generator（已迁移至 streamer-workbench）
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
9. **三套新布局各走独立数据通道**：
   - `live-set`（R2.5）→ `LiveSessionSnapshot`（一场直播的事件流）
   - `learning-report`（R3.5）→ `LearningReportSnapshot`（一段时间窗口的事件聚合）
   - 不与 grid-wrap / magazine-flow 共享 `SongLibrary` 路径
10. **编辑器（R7）只在 3 套新布局上线并被真实使用后启动**，不提前造完整图片编辑器。
11. **`design/archive/` 中的文档已退役**。只允许追溯历史，不得据此判断当前状态或执行顺序；当前真相以主规格、路线图、数据路线图和 ADR 为准。

---

## 当前活跃规格与状态

### 规格文档

| 文档 | 路径 | 用途 |
|---|---|---|
| **唯一执行主规格** | `design/产品优化方案终版-0727/产品优化方案终版.md` | 产品/UI/架构/多布局完整规格 |
| **2026-07-29 详细增量规格** | `design/产品优化方案终版-0727/产品与技术规格-v3.md` | 独立海报、点歌规则、直播台账、乐理辅助和 UI/技术契约 |
| **唯一路线图** | `design/产品优化方案终版-0727/路线图.md` | R0–R7 执行路径与阶段门；P 编号仅作历史能力分组 |
| **数据路线图（S1–S5）** | `design/roadmap-data-stats.md` | 事件 Schema/统计口径唯一真相 |
| **架构决策记录** | `ADR-001.md`–`ADR-008.md`；ADR-005 负责应用边界与安全，ADR-006 负责独立海报与能力匹配，ADR-007 负责点歌规则/权益/优先队列，ADR-008 负责应用主色与海报颜色隔离 |
| **项目 README** | `README.md` | 运行命令/目录结构/API 列表 |
| **设计系统** | `design/design-tokens.json` | 双品牌 UI 令牌的当前单源真值；归档设计稿只作历史参考 |
| **归档索引** | `design/产品优化方案终版-0727/README.md` | 活跃文档唯一真相表与退役文档清单 |

### 当前完成状态

```
引擎兼容  ✅          avoid/cache 正确性已修复，金标准 16/16 diff=0；环境复现待 R0 收口
数据层    S1-S3.5 ✅ Song v5/Event v2、Tabs/Queue/Preset song_id 关系迁移完成
              S4     ✅ 打卡 + 统计 + 乐理辅助（接入 R3 学歌闭环 + R4 数据统计）
产品主线  R0 ✅      R0.1-R0.12 全部收口
              R1a ✅ 海报闭环（领域/仓储/服务/API/样例/能力/RenderDocument/UI 接入 + 自动保存）
              R1b ✅ magazine-flow 自动分页（6 分类轴 + analyze HTTP + 新金标准 6 PNG + LayoutPicker）
              R2     ✅ 直播核心纵切（领域 + 核销 + 决策 + LiveService + 持久化 + 7 端点）
              R2.5 ✅ live-set 直播复盘海报（LiveSessionSnapshot 数据通道 + 5 PNG 金标准 + 复盘海报按钮）
              R3     ✅ 学歌发现 + 智能推荐 + 乐理辅助
              R3.5 ✅ learning-report 学歌报告海报（LearningReportSnapshot 数据通道 + 5 PNG 金标准 + 导出学习报告按钮）
              R4     ✅ 数据统计 4 端点 + 5 tab UI
              R5     ✅ 工作台系统化（focus-visible / stagger / aria / 响应式）
              R4.0 🟡  v3 新增：三套新布局凑齐后的减债与新布局接入（P0 进行中：抽 _common.py / 导出反馈 / streak 修相对时间 / settings.json 写 .gitignore）
              R4-R7 ⬜  Layout Runtime v1 抽象 + 数据反哺 + 桌面发布门（参见 [`HANDOFF.md`](HANDOFF.md) §8.3）
桌面壳    spike 已过  正式壳 ⬜
UI        ~92%       工作台/歌曲库/学歌/速查/海报/直播会话/复盘海报/数据统计/学习报告 均可用
```

### 技术栈

| 层 | 技术 | 说明 |
|---|---|---|
| 渲染引擎 | Python 3.12+ + Pillow 12.2.0（requirements） | 纯函数，金标准保护；grid-wrap 16/16 + magazine-flow 6 PNG |
| 后端 | FastAPI 0.115.0（requirements）+ uvicorn | AppContext + Repository adapters + services + routers；边界见 ADR-005；含 `/api/live-sessions*` 7 端点 |
| 前端 | React 19 + Vite 6 + Tailwind 4 + shadcn/ui | `ui/`；组件优先用 shadcn/ui（`ui/src/components/ui/`），shadcn 不满足需求再自写组件；`usePosterStore` 状态机 + `WorkspacePosterBridge` 接入工作台左栏 |
| 数据 | JSON + JSONL 本地文件 | songs.json v4 落盘（178 首，加载时确定性迁移至 v5）、events.jsonl v1/v2 兼容、settings.json、live-sessions/<id>/state.json（P3 增量） |
| 桌面壳 | Electron（spike） | Python 作 child_process；正式壳未完成 |
| 字体 | MaokenAssortedSans.ttf（猫啃糖圆体） | `fonts/` |
| 测试 | 31 项 Python 测试文件 + 34 项 vitest + 16 项 node:test + 16/16 grid 金标准 + 6/6 magazine PNG + OpenAPI 类型漂移/tsc/build | 当前 CI 质量门；Windows 控制台 UTF-8 与依赖锁定已逐步收口 |

---

## 目录结构速览

```
.
├── AGENTS.md                       ← 本文件
├── README.md                       项目入口
├── ADR-001.md ... ADR-008.md       架构决策记录
│
├── design/                         活跃设计文档（可修改）
│   ├── 产品优化方案终版-0727/       唯一执行主规格
│   ├── roadmap-data-stats.md        S1-S5 数据规格
│   └── archive/                     已退役文档（只读参考，不再执行）
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

Python 后端是核心用户数据的唯一写入权威（ADR-003）。Electron 使用原生目录对话框选择路径并交给后端；浏览器开发模式通过后端设置 API、启动参数或配置文件指定。`showDirectoryPicker` 仅用于显式导入/导出，不直接管理 songs/events/tabs/presets。

---

## 分支与提交流程

- 每次 feature / bug fix 走分支（`feature/xxx`、`fix/xxx`），**不在 master 上直接开发**。
- 原子提交，中文摘要，Conventional Commits 风格：`feat/fix/docs/refactor(scope): 中文描述`
- 触及引擎输出时必须先跑 `PYTHONPATH=. python tests/test_golden.py`
- Python 改动运行 `PYTHONPATH=. python tests/test_unit.py`
- React 改动运行 `cd ui && npx tsc --noEmit`
- 允许纯本地提交，不强制推远程。
- 推远程走 SSH：`git push git@github.com:jiaiqi/streamer-workbench.git HEAD:master`
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
| Windows 控制台 GBK 无法输出 ✅/❌ | 已收口：统一入口 `python tools/run_tests.py` 自动注入 PYTHONUTF8 |
| 本地 `.venv` 与 requirements 版本漂移 | 已收口：2026-07-30 核对 fastapi 0.115.0 / pillow 12.2.0 / uvicorn 0.30.6 / python-multipart 0.0.32 / pypinyin 0.53.0 全部对齐 |
| Windows Git Bash `grep` 中文路径 bug | 用 `ls -R` 代替 `find` |
| 主题背景图命名不统一 | 6 套用 `bg1.png`，海洋柔光独用 `background-1.png`，以各自 `theme.json` 为准 |
| 缩略图 `object-cover` | 背景装饰集中在底部，必须 `object-cover object-bottom` |

---

## 关键命令速查

```bash
# 测试
PYTHONPATH=. python tests/test_golden.py     # 金标准 16/16
PYTHONPATH=. python tests/test_unit.py        # 核心兼容单元测试 87 项；CI 另跑 55 项边界/可靠性测试
cd ui && npx tsc --noEmit                    # TS 编译检查

# 运行
python -m server --reload --port 8000         # 后端（受控 loopback 入口）
cd ui && npm run dev                          # 前端

# 基准测试
PYTHONPATH=. python tools/benchmark.py        # 渲染性能

# 推送
git push git@github.com:jiaiqi/streamer-workbench.git HEAD:master
```

Windows PowerShell 当前兼容命令：

```powershell
$env:PYTHONPATH='.'
$env:PYTHONUTF8='1'
& '.venv\Scripts\python.exe' tests/test_golden.py
& '.venv\Scripts\python.exe' tests/test_unit.py
cd ui; npx tsc --noEmit
```
