# Agent 项目规则

> 此文件供 AI 编码助手（Agent）读取并遵守。每次接手时首先读取本文。
> 最后更新：2026-09-06（P0 续作 2 项：P0-2b outbox 接入 lifespan 启动 drain + 移除重复 /api/health 死路由 / P0-3b posters manifest 派生索引推广；P1 阶段二 a1-a4 四项补录路线图）
> 最后更新：2026-08-30（P0 收口 4 项：WebDAV 主密码 → 系统 Keychain / 本地 outbox / Manifest 派生索引 / Electron smoke + P1 主线纵切 2 项：PlayView 待确认卡片 / StatsView 下一步建议）
> 最后更新：2026-08-16（R4 退出条件 #2 草稿/手动分页 UI V3 收口 → R4 11/11 = 100%）

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

## 产品核心约束（不可妥协）

> **铁律级**：本项目是"主播工作台 + 工具箱 + **纯离线优先**"。除显式标注"在线可选"的功能外，其他一切**必须能离线工作**。

### 离线可用的功能域（默认范围）

下列所有功能在 `navigator.onLine === false` / 网络断开 / 飞行模式下**必须 100% 工作**，断网时不应出现任何"网络不可用"提示、不可用遮罩或能力降级：

- 曲库 CRUD：新增、编辑、删除、状态切换（draft/active/trash）
- 曲库查询、排序、过滤、批量操作（L2.1）
- 曲库导入导出（L2.3，本地 JSON 文件）
- 自动快照 + 恢复（M2.3，本地 `data/backups/songs/`）
- 加密备份包（M2.1，本地 `.songworkbench` 文件）
- 海报工作台：创建 / 预览 / 渲染 PNG / 调参 / 切主题 / 切画布
- 海报真保存（dialog:saveFile，原生 save 对话框，零网络）
- 5 套布局：grid-wrap / magazine-flow / live-set / learning-report / fullscreen
- 8 套主题（含月夜星河）— 全部本地字体 + 本地背景图
- 直播会话（LiveSession）：创建 / 入队 / 标记已唱 / 关闭 / 复盘海报
- 弹唱播放器（PlayView）：本地音频文件、ChordPro 曲谱、本地 LRC 歌词、Capo 转调、R9 全套吉他手特化
- 速查子窗口（QuickView，Cmd+Shift+U）
- 统计页（StatsView）：事件流、洞察 tab、点歌热度、最近演唱
- 命令面板（Cmd+K）、全局快捷键、Onboarding、状态栏、帮助中心
- M2.13 系统集成：播控菜单、系统通知、Dock Badge、LiveView 队列数联动
- R4 Runtime v2（V2.1 + V2.2 + V2.3 + V2.4 + V2.5 全部收口）：
  - **V2.1** LayoutPlan / LayoutAnalysis / PagePlan / SectionPlan 数据结构 + LayoutContext
  - **V2.2** 4 套 layout `analyze(library, ctx)` 统一签名 + `engine.render_pages` 解耦写死 magazine_flow import
  - **V2.3** Palette/Skin 真实接线（`Palette.to_style()` + `Skin.from_palette_and_layout()` 工厂 + `Skin.apply_to_style()` + `DrawContext.effective_style` 双轨过渡 `skin > palette > style`）
  - **V2.4** Parameters 真正流到 `ctx.parameters`（`engine.render_page` 接受 `parameters` 可选参 + `render_document` 透传 + 3 套 layout 删除 `getattr(ctx, "parameters", {})` fallback 改用 `ctx.parameters` 直读）
  - **V2.5** 能力矩阵 + UI 灰显（`Theme.compatible_layouts` 字段 + `LayoutPlugin.compatible_themes()` 方法 + `core/layouts/compat.py` 4 函数 + 4 端点 `/api/compatibility` 系列 + 月夜星河 theme.json 演示字段 + grid_wrap override 排除月夜星河 + LayoutPicker 警告 banner）
  - 共 95 项新测试（25 plan + 26 runtime_v2 + 21 palette_skin_wiring + 22 compatibility + 8 LayoutPicker.compat）
  - 1261 Python + 742 vitest 全过，16/16 金标准 0 像素差异，0 新依赖
- SettingsView：output_dir / default_canvas / default_theme / font_path / 备份设置 / 外观

### 明确**在线可选**的功能域（不是离线故障，是设计如此）

只有下列功能允许依赖外网，**且必须支持离线降级**（关掉 / 隐藏 / 提示 + 不阻塞）：

| 功能 | 离线时行为 |
|---|---|
| M2.8/2.10 在线元数据（搜索、歌曲详情、艺人、专辑、歌单、歌词、榜单、相似） | 按钮 disabled（SongEditDialog「在线补全」）/ 列表空 + 提示 |
| M2.11 公开歌单导入 | 「预览」按钮 disabled |
| M2.12 榜单浏览 | 「榜单浏览」按钮 disabled / 列表显示"离线状态无法浏览" |
| R8.2.x 录屏（如未来引入） | 不影响弹唱播放；录屏按钮 disabled |

**重要**：在线元数据**不允许**反向写入到本地曲库时变成"必填"。Song 模型的 `title / artists / status / notes / tabs / audio_*` 等所有字段在离线时**必须能手工填完**。在线元数据只作为可选的"快速补全"加速器。

### 离线检测与降级约定

- 在线状态来源：`navigator.onLine`（L1.5 OnlineStatusBadge）
- 全局 hook：`getOnlineState()` 同步读 + 监听 `online/offline` 事件实时更新
- 渲染层按钮三态 disabled：`getOnlineState() === "online" && !saving && (title.trim() !== "")`
- 后端 metadata 端点失败时：M2.6 `useApiError().runWithToast(fn, label)` 弹 toast + 行内错误双通道
- 错误是"网络不可用"时用 `MetadataUnavailable` 错误三元（MetadataNotFound / MetadataUnavailable / MetadataRateLimited），不抛网络异常

### CI 质量门要求

任何新 PR 必须保证：
1. 关闭网络（mock `navigator.onLine = false`）后所有"离线可用"功能的核心流程仍能跑通
2. 浏览器开发模式（`cd ui && npm run dev`，无后端）打开后所有非元数据功能可用
3. 引入新的在线依赖必须明确文档化"为什么离线不行 / 离线降级是什么"

### 违反约束的判定

如果你发现某功能：
- 离线时直接报红 / 弹"网络错误" / 渲染失败
- 把"在线可选数据"反向变成"必填"（如在线补全的封面 URL 没拉到导致保存失败）
- 静默上传本地数据到云端而没明文用户授权

那它就违反本节，**必须**修。改不动就先从"离线可用功能域"剔除该功能到"在线可选"，并在路线图里标 ✅降级。

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
              R8     ✅  弹唱播放器 R8.0/R8.1/R8.2 联动收口 + **R8.2.x 录屏首批**（观众号视角全屏+系统音频+MediaRecorder VP9/Opus webm+1GB 自动切片+PlayView 顶栏红点+RecordingDialog 4 状态机+useRecording hook 共享 module-level store+preload 9 IPC 暴露+R8.2.x 不破坏 R0-R7 路径依旧走 core/player/；35 单测+9 vitest 端到端覆盖 idle/recording/paused/stopped/unsupported/error + 33 Python 单元（通过 Node 子进程驱动 recorder.js 内部函数覆盖 SRT 时间格式/path traversal 防御/pause-resume 状态机/appendLrc 过滤/listFiles/listAllSessions/deleteFolder/_writeSrt）
              R9     ✅  吉他手特化首批收口（R9.1 联动「再唱一遍」/ R9.2 chord 远观模式 1-1.6x / R9.3 顶栏 Capo 大字 + 升降快捷键 ↑↓ + 实际 Key 反推 / R9.4 个人 Capo 库 capo_options+capo_default / R9.5 今晚歌单工作台首屏卡片 / R9.6a 软删除垃圾桶 30 天 / R9.6b 5 秒撤销 toast 全局系统）
              M0     ✅  蓝图 v0.1 首批（5 子项；数据 178 首已在）/ fullscreen-flow 全屏柔光绕排版式 + 金标准 4 张 / 月夜星河主题第 8 套 / 加密备份包 MVP（.songworkbench + HMAC-SHA256）/ 178 首曲库验证
              M1     ✅  本地最小可用首批（M1.1 全局找歌 8 字段加权 + 13 测试 / M1.2 CommandPalette 找歌 + 5 测试 / M1.3 PlayerContext 顶层 Provider + 8 测试 / M1.4 MiniPlayer 全局底栏 + 9 测试 / M1.5 LibraryView 试听入口 + 6 测试 / M1.6a LRC 同步 3 测试 / M1.6b 吉他谱锚点 8 测试 / M1.7 渐进式海报相邻页预加载 6 测试）
              M2     ✅  加密备份完整（5 子项；M2.1 AES-256 真加密 + 错密码真拒绝 + 向后兼容 v1 备份 + pyzipper 依赖）+ **M2.2 WebDAV 同步**（core/webdav.py 零新依赖客户端 urllib + xml.etree + 6 类错误；server/services/webdav_sync.py 复用 M0.4/M2.1 .songworkbench 备份包 + pyzipper AES 加密存 settings.json.webdav_config_encrypted；6 HTTP 端点 GET/PUT /config + clear + test + test-saved + list + push + pull；SettingsView WebDavPanel 3 状态机 unconfigured/locked/unlocked + 离线禁用 + 主密码解锁；34 客户端单测 + 41 service 单测 + 15 HTTP e2e（http.server mock 全链路）+ 14 vitest；1099 Python + 621 vitest 全过 + tsc 0 错 + 16/16 金标准 0 像素差异）+ M2.5 综合洞察（后端 GET /api/stats/insights + StatsView「洞察」tab + eventsHeat 反哺 M1 找歌，log2 压缩加成上限 50）+ M2.6 错误全局 toast 化（useApiError hook + 8 组件 21 处 catch）+ M2.3 自动快照（底层 AtomicJsonWriter 每次 save 备份 + LibraryView 快照 tab 列出/恢复 + 5 Python 端到端）+ M2.7 在线元数据层骨架（core/metadata/ 协议 + Router + Cache + HttpClient + 6 类错误 + 61 测试；零新增依赖）+ M2.8 NeteaseProvider 第一实现（公开 API 全套 search/song/artist/album/playlist/lyric/charts/similar + 9 个 /api/metadata/* 端点 + 45 provider 单元测试 + 24 API 端到端）+ M2.9 LibraryView 在线补全 UI（SongEditDialog「在线补全」按钮 + MetadataSearchDialog 子对话框 + 离线降级 + 21 vitest）+ M2.10 QQProvider 多源回退（4 个核心方法 + base64 歌词解码 + Router 默认装 netease+qq 两个 provider + 37 provider 单元测试含 2 个 router 集成）+ M2.11 网易云/QQ 公开歌单导入（PlaylistImportDialog + LibraryView 工具栏「从歌单导入」按钮 + 16 vitest；复用 M2.8 /api/metadata/playlist + M2.3 /api/songs/import）+ M2.12 榜单浏览 + 一键入库（ChartsBrowseDialog + LibraryView 工具栏「榜单浏览」按钮 + 12 vitest；复用 M2.8 /api/metadata/charts + playlist + M2.3 /api/songs/import，零新增端点）+ **M2.13 macOS 桌面平台特性首批**（主进程播控菜单 + 系统通知 + Dock Badge 队列数 + PlayView ⇄ PlayerContext 双向同步；useSystemIntegration hook 1Hz 节流 + 7 vitest；PlayerContext no-op 降级；vitest.config 接入 hooks/；583 全量 0 回归 + tsc 0 错；零新依赖）+ **M2.14 R3 回归 hotfix**（TheoryHelper isHover 块作用域 ReferenceError 导致点学歌管理白屏 — 改用 `hoverKey && COMMON_CHORDS_BY_KEY[hoverKey]` 直接判断 + 5 vitest 回归覆盖；588 全量 0 回归 + tsc 0 错）+ **M2.16 海报分享**（跨平台剪贴板 + Finder 定位 + macOS 原生 Share Sheet — 3 IPC + osascript 桥接 NSSharingServicePicker；ExportDialog 完成态三按钮 + 非 macOS 平台 disabled；11 vitest；599 全量 0 回归）+ **M2.17 点歌条件**（4 字段 cooldown / max_queue / per_song / per_user 0=不限；QueueSnapshot 3 统计 + RequestPolicyService 4 检查 + LiveService 端到端联动 + GET/POST /api/live-sessions/{id}/policy + PolicyDialog UI；纯本地规则计算零外部 API 依赖；607 vitest + 25+ Python 测试；纯离线优先） + **M2.4 WebDAV 自动同步**（让 M2.2 push/pull 真正落地，跨设备备份刚需）：`server/services/auto_sync.py` AutoSyncScheduler 后台 asyncio 循环 + 间隔 1-1440 分钟可配 + 方向 push/pull/both + 启动时根据 settings 决定启停 + run_now 立即触发 + 失败不中断下个 tick + 每次写 last_at/last_status/last_error/last_remote_name 到 settings；`webdav_sync.py` 新增 `push_internal/list_remote_internal/pull_internal/auto_run_once`（用已解密 cfg 直接调用，省一次用户输密码）；3 端点：`GET /api/backup/webdav/auto-sync` 读状态 + `POST /api/backup/webdav/auto-sync` 启用/关闭/改间隔/改方向（启用时必传主密码） + `POST /api/backup/webdav/auto-sync/run` 立即同步；`AppContext.auto_sync_scheduler` + lifespan 启动 await + finally await stop 完整收口避免 RepositoryClosed；settings 字段 webdav_auto_sync_enabled/interval_minutes/direction/last_* 6 字段；主密码 base64 存 settings.webdav_auto_sync_master_password_b64（关闭时清空）；前端 WebDavPanel 加自动同步 section（状态文本 + 间隔下拉 7 档 + 方向下拉 3 档 + 启用/关闭/立即同步 3 按钮 + 失败错误信息 + useState lazy + refreshAutoSync）；10 vitest + 11 pytest 新增；零新依赖；1069 pytest + 706 vitest 全过 + tsc 0 错 + 16/16 金标准 0 像素差异）
              L1     ✅  体验打磨首批（L1.1 toast 4 kind + 8 测试 / L1.2 全局快捷键面板 `?` + 10 测试 / L1.3 首次启动 Onboarding 3 步 + 12 测试 / L1.4 草稿保护 ConfirmDialog + 11 测试 / L1.5 离线检测 OnlineStatusBadge + 9 测试 / L1.6 状态栏 5 分块 + 13 测试 / L1.7 帮助中心 Cmd+Shift+? + 10 测试）
              L2     ✅  工具箱完整性第一批（L2.1 批量操作：LibraryView 多选 + 批量删除/改状态 + 11 测试）+ 第二批 L2.2 批量导出（/api/export/by-ids 端点 + LibraryView 批量导出按钮 + 6 Python + 4 vitest）+ 第三批 L2.3 曲库导入导出（/api/songs/export + /api/songs/import merge/replace + LibraryView 按钮 + 9 Python + 4 vitest）
              M3 ✅     海报 UI/UX 打磨 **全部收口**（P0 缩略图/搜索/排序/右键/inline rename/ExportDialog 三段式 + P1.1 快速预览放大镜 + P1.3 批量操作 + P2 拖拽排序 + Quick Look 预览 + P3 ExportLogDrawer + **P3 续 智能推荐主题 + IntersectionObserver 主题缩略图懒加载** — `core/themes/recommender.py` PosterContext/ThemeScore/score_theme 启发式（tag × 3 + scene × 2 + mood × 2 + count_in_range +1/-0.5）+ `GET /api/themes/recommend?poster_id=&title=&song_titles=&tags=&scene=&song_count=&top_n=3` + `GET /api/themes` 加 metadata；前端 `useIntersection` zero-dep hook（SSR/旧浏览器兜底 visible）+ `ThemeLazyThumb` 严格 IntersectionObserver（rootMargin 100px + once: true）替换原 `loading="lazy"`；8 套 theme.json 全量补 metadata（tags/scenes/mood/language_friendly/song_count_range）；`scripts/fill_theme_metadata.py` 一键填；23 Python + 9 vitest 新增；1284 pytest + 751 vitest + 16/16 金标准 0 像素差异 + tsc 0 错 + 0 新依赖）（后端：`/api/posters/{id}/thumb` 200x200 懒生成 + LANCZOS 缓存 `data/posters/{id}/.thumb.png` + mtime 失效 + PATCH /name + POST /duplicate + DELETE /api/export/jobs/{id} 取消；前端：PostersSidebar 重写 缩略图+搜索+排序+右键菜单+inline rename+撤销/重做图标+「×N 首·日期 时间」+「删除当前」；ExportDialog 三段式引导（idle 范围选择 / running 进度+取消 / done 顶部✅+中部 ExportLogPanel 近 3 条+底部 6 动作分 2 行+再导一次+关闭 / error 重试+关闭）；usePosterStore +rename +duplicate；toast.info/warn 双通道 + path traversal `[A-Za-z0-9_.-]+` 防御；vitest 684 全过 + tsc 0 错 + 16/16 金标准 0 像素差异 + 10 Python 新端点 + 50 vitest 新增；M3 P1 待做：缩略图快速预览放大镜 + 拖拽排序 + 批量操作） + **M3 P1 收口**（快速预览放大镜：后端 `/thumb?size=200|400|600` 200 走磁盘缓存 + 400/600 内存即时放大 + size 白名单校验；前端 hover 300ms 浮层 400x400 右上角 + mouseEnter/Leave + setTimeout 取消 + thumb container onError 容错。批量操作：后端 `POST /api/posters/batch` action=delete/duplicate/set_theme + path traversal `[A-Za-z0-9_-]{1,64}` 防御 + 部分失败容错（failed 数组逐元素记录） + 422 invalid_poster_ids/missing_theme 校验；前端「☐ 选择」按钮切换多选模式 + 每项前 checkbox + 工具栏「全选/清空/复制/🎨 主题/删除」+ `🎨 主题` 子菜单列出 `/api/themes` 实时加载。`usePosterStore` +batch action 自动 refreshList + 当前被删时 newDraft 兜底。useToast 无 Provider 静默 no-op 容错（旧测试改 1 项）。1058 pytest + 696 vitest 全过 + tsc 0 错 + 16/16 金标准 0 像素差异 + 0 新依赖。M3 P1.2 拖拽排序 + ExportLogPanel 升级为可点历史抽屉 推 M3 P2）+ **M3 P2 收口**（拖拽排序：后端 `PosterDocument.order_index: int|None` 字段 + `PosterRepository.list` 多轮 stable sort（id desc → order_index asc, None→10^12 推末尾 → updated_at desc）+ `PosterRepository._refresh_summary_in_manifest` 写 order_index + batch endpoint 加 `reorder` action（按 ids 数组下标写 order_index）；前端 `PostersSidebar` HTML5 DnD 零依赖：li `draggable={!multiSelectMode}` + onDragStart/Over/Leave/Drop/End + getBoundingClientRect 中线判断 before/after + 蓝线插入指示 + 拖动项半透明 + drop 后调 `store.batch('reorder', newOrder)` + 默认排序模式（`sortBy='updated'`）用后端顺序，name/songs 客户端排；多选模式拖拽互斥 disabled。3 Python 单测（reorder 写 order_index / partial failure / 持久化到 manifest）+ 8 vitest（draggable 开关 / 多选互斥 / before-after 指示 / drop 调 batch / 3 个 id 全到位 / drop 后清理 / 拖自身不调）
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
