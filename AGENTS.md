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
11. **R8 弹唱播放器不与 R0-R7 路径共用**：PlayView 走 `core/player/` 模块而非 `core/layouts`（弹唱屏幕不是海报）；音频本地优先，避免在线版权；chordpro 曲谱优先于 tab_files 图片（图片仅作 fallback 全屏放大镜）。
11. **`design/archive/` 中的文档已退役**。只允许追溯历史，不得据此判断当前状态或执行顺序；当前真相以主规格、路线图、数据路线图和 ADR 为准。

---

## 当前活跃规格与状态

### 规格文档

| 文档 | 路径 | 用途 |
|---|---|---|
| **唯一执行主规格** | `design/产品优化方案终版-0727/产品优化方案终版.md` | 产品/UI/架构/多布局完整规格 |
| **2026-07-29 详细增量规格** | `design/产品优化方案终版-0727/产品与技术规格-v3.md` | 独立海报、点歌规则、直播台账、乐理辅助和 UI/技术契约 |
| **唯一路线图** | `design/产品优化方案终版-0727/路线图.md` | R0–R8 执行路径与阶段门（v5 新增 R8 弹唱）；P 编号仅作历史能力分组 |
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
              R4.0 ✅  Phase 1 收口（6dbdc63 — layout helper + 导出反馈 + streak + .gitignore）
              R4.0 ✅  Phase 2 收口（feat-0801 — useWorkspaceState 拆解 + 专用海报区 + 海报真保存 + 暗色 hardcode 收口发现是空集）
              R4.1 ✅  视觉与体验统一（4 组件 + Cmd+K + narrow helper + selLayout 已删）
              R4.2 ✅  数据反哺创作补全（R4.2.1+2 收口：Top 歌曲/时间线 → 创建海报/Preset；R4.2.3 导出历史：复用 events.jsonl + ExportLogPanel 嵌入 4 处）
              R4-R7 🟡  Layout Runtime v1 抽象已交付（最小化：DataChannel 契约 + supported_channels 声明 + 30 项测试 + 32/32 金标准）；v2 待做（统一 LayoutPlan / Palette-Skin 接线 / 桌面发布门）
              R8     🟡  弹唱播放器 R8.0/R8.1/R8.2 联动收口；R8.2.x 录屏 待推
              R9     ✅  吉他手特化首批收口（R9.1 联动「再唱一遍」/ R9.2 chord 远观模式 1-1.6x / R9.3 顶栏 Capo 大字 + 升降快捷键 ↑↓ + 实际 Key 反推 / R9.4 个人 Capo 库 capo_options+capo_default / R9.5 今晚歌单工作台首屏卡片 / R9.6a 软删除垃圾桶 30 天 / R9.6b 5 秒撤销 toast 全局系统）
              M0     ✅  蓝图 v0.1 首批（5 子项；数据 178 首已在）/ fullscreen-flow 全屏柔光绕排版式 + 金标准 4 张 / 月夜星河主题第 8 套 / 加密备份包 MVP（.songworkbench + HMAC-SHA256）/ 178 首曲库验证
              M1     ✅  本地最小可用首批（M1.1 全局找歌 8 字段加权 + 13 测试 / M1.2 CommandPalette 找歌 + 5 测试 / M1.3 PlayerContext 顶层 Provider + 8 测试 / M1.4 MiniPlayer 全局底栏 + 9 测试 / M1.5 LibraryView 试听入口 + 6 测试 / M1.6a LRC 同步 3 测试 / M1.6b 吉他谱锚点 8 测试 / M1.7 渐进式海报相邻页预加载 6 测试）
              M2     ✅  加密备份完整（5 子项；M2.1 AES-256 真加密 + 错密码真拒绝 + 向后兼容 v1 备份 + pyzipper 依赖）+ M2.5 综合洞察（后端 GET /api/stats/insights + StatsView「洞察」tab + eventsHeat 反哺 M1 找歌，log2 压缩加成上限 50）+ M2.6 错误全局 toast 化（useApiError hook + 8 组件 21 处 catch）
              L1     ✅  体验打磨首批（L1.1 toast 4 kind + 8 测试 / L1.2 全局快捷键面板 `?` + 10 测试 / L1.3 首次启动 Onboarding 3 步 + 12 测试 / L1.4 草稿保护 ConfirmDialog + 11 测试 / L1.5 离线检测 OnlineStatusBadge + 9 测试 / L1.6 状态栏 5 分块 + 13 测试 / L1.7 帮助中心 Cmd+Shift+? + 10 测试）
              L2     ✅  工具箱完整性第一批（L2.1 批量操作：LibraryView 多选 + 批量删除/改状态 + 11 测试）+ 第二批 L2.2 批量导出（/api/export/by-ids 端点 + LibraryView 批量导出按钮 + 6 Python + 4 vitest）
              M1     ✅  本地最小可用首批（M1.1 全局找歌 8 字段加权 + 13 测试 / M1.2 CommandPalette 找歌 + 5 测试 / M1.3 PlayerContext 顶层 Provider + 8 测试 / M1.4 MiniPlayer 全局底栏 + 9 测试 / M1.5 LibraryView 试听入口 + 6 测试 / M1.6a LRC 同步 3 测试 / M1.6b 吉他谱锚点 8 测试 / M1.7 渐进式海报相邻页预加载 6 测试）
桌面壳    ✅ dev + packaged  PyInstaller/electron-builder 已落地，macOS arm64
UI        ~99%       工作台/歌曲库（含垃圾桶 tab）/学歌/速查/海报/直播会话/复盘海报/数据统计（含「洞察」tab 点歌热度+最近演唱）/学习报告/专用海报/命令面板（Cmd+K 全局找歌，含 eventsHeat 热度反哺排序） + 4 嵌入点导出历史 + 弹唱视图（PlayView：v8.1 接入 <audio> + vocal/instrumental 切轨 + 进度联动 + R9 大字 Capo + 远观模式 + 再唱一遍 + 习惯 Capo） + MiniPlayer 全局底栏（M1.4：模式徽章 + 一键回弹唱） + 5 套 layout（grid/magazine/live-set/learning-report/fullscreen）+ 8 套主题（含月夜星河） + 5 嵌入 toast（M9.6b 删除撤销 + L1.1 4 kind + 状态变化） + ShortcutsPanel（?）+ Onboarding（首次启动）+ OnlineStatusBadge + StatusBar + HelpCenter（Cmd+Shift+?）均可用
```

### 蓝图 v0.1 跨场景播放器（M1）

- **数据通道**：`PlayerContext` 顶层 Provider（App.tsx 包）；state `{ currentSongId, mode, isPlaying, currentTimeMs }`；3 模式 `live / practice / browse`
- **入口**：LibraryView 试听按钮（`mode="browse"`）/ LiveView 弹唱按钮（`mode="live"`，R8.2 联动）/ CommandPalette 全局找歌（`mode="browse"`）
- **常驻展示**：MiniPlayer（`ui/src/components/MiniPlayer.tsx`）— 固定底栏；非 play 视图 + 无模态时显示；✕ 清 context，回上一视图
- **质量门**：vitest 372 passed（M1.1 +13 / M1.2 +5 / M1.3 +8 / M1.4 +9 / M1.5 +6）

### 技术栈

| 层 | 技术 | 说明 |
|---|---|---|
| 渲染引擎 | Python 3.12+ + Pillow 12.2.0（requirements） | 纯函数，金标准保护；grid-wrap 16/16 + magazine-flow 6 PNG + live-set 5 PNG + learning-report 5 PNG |
| 后端 | FastAPI 0.115.0（requirements）+ uvicorn | AppContext + Repository adapters + services + routers；边界见 ADR-005；含 `/api/live-sessions*` 7 端点 |
| 前端 | React 19 + Vite 6 + Tailwind 4 + shadcn/ui | `ui/`；组件优先用 shadcn/ui（`ui/src/components/ui/`），shadcn 不满足需求再自写组件；`usePosterStore` 状态机 + `WorkspacePosterBridge` 接入工作台左栏；R4.1 新增 4 统一组件（`EmptyState`/`Spinner`/`StatusBadge`/`ErrorBanner`）+ `CommandPalette`（Cmd+K） |
| 数据 | JSON + JSONL 本地文件 | songs.json v4 落盘（178 首，加载时确定性迁移至 v5）、events.jsonl v1/v2 兼容、settings.json、live-sessions/<id>/state.json（P3 增量）、data/tabs/{song_id}/（曲谱附件）、data/audio/{song_id}/（R8 音频，v8.1+） |
| 桌面壳 | Electron（spike） | Python 作 child_process；正式壳未完成 |
| 字体 | MaokenAssortedSans.ttf（猫啃糖圆体） | `fonts/` |
| 测试 | 56 项 Python 测试文件（759 passed / 1 skipped） + 31 项 vitest（340/340） + 16 项 node:test + 16/16 grid 金标准 + 5/5 magazine PNG + 5/5 live-set PNG + 5/5 learning-report PNG + 4/4 fullscreen PNG（35/35 0 像素差异）+ OpenAPI 类型漂移/tsc/build | 当前 CI 质量门；Windows 控制台 UTF-8 与依赖锁定已逐步收口 |

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
| 本地 `.venv` 与 requirements 版本漂移 | 已收口：2026-07-30 核对 fastapi 0.115.0 / pillow 12.2.0 / uvicorn 0.30.6 / python-multipart 0.0.32 / pypinyin 0.53.0 全部对齐；M2.1 新增 pyzipper==0.4.0（WinZip AES-256 真加密） |
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
