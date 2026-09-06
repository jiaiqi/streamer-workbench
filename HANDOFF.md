# 主播工作台 · 执行交接（HANDOFF）

> **读者**：接手开发的 AI 或人类工程师。
> **日期**：2026-09-06 ｜ **基线**：master @ R0-R9/M0-M3/L1-L2 全部收口（详见 §9 与 AGENTS.md）。
> **使用方法**：从「4. 当前状态」确认起点，按「6. 执行计划」自上而下逐项实施；每项完成后按「5. 工作协议」提交合并。
>
> ⚠️ **本文件 §4 / §6 严重过期**（保留作为历史快照）。当前真相以 **AGENTS.md 顶端最后更新行** + `design/产品优化方案终版-0727/路线图.md` R0-R8 阶段表 + 本文件 **§9 会后增量** 为准。

---

## 1. 项目一句话

个人音乐主播的本地优先工作台：Python(Pillow) 渲染引擎 + FastAPI 后端（唯一数据写入权威）+ React 19 前端 + 薄 Electron 壳（未做）。产品名「主播工作台 / streamer-workbench」，**不要再叫「歌单海报生成器」**。

## 2. 必读文档（按顺序）

| 顺序 | 文件 | 作用 |
|---|---|---|
| 1 | `AGENTS.md` | 铁律、技术栈、目录结构、命令速查（本文件不重复其内容） |
| 2 | `design/开发任务清单-0730.md` | P0–P7 任务清单与勾选状态，每完成一项去勾选 |
| 3 | `design/产品优化方案终版-0727/路线图.md` | R0–R7 阶段定义与退出条件（执行顺序唯一真相） |
| 4 | `design/产品优化方案终版-0727/产品与技术规格-v3.md` | UI/直播/海报/乐理的详细契约（PosterDocument、点歌规则等类型定义在此） |
| 5 | `design/产品优化方案终版-0727/产品优化方案终版.md` | 完整主规格，遇到清单没写清的交互细节时查 |
| 6 | `design/roadmap-data-stats.md` | 事件 Schema 与统计口径（S1–S5 唯一真相） |

`design/archive/` 与 `.archive/` 是只读历史，**不得**作为实现依据；`.archive/` 不得修改。

## 3. 环境与命令

```bash
# Python：永远用项目 .venv，不用系统 python
PY=.venv/bin/python                    # Windows: .venv\Scripts\python.exe

# 测试（统一入口，已内化 UTF-8/PYTHONPATH）
$PY tools/run_tests.py                 # 全部 13 个测试文件，须 13/13
$PY tools/run_tests.py test_golden     # 金标准必须 16/16 diff=0

# 前端（ui/ 目录）
cd ui && npx tsc --noEmit              # TS 检查
cd ui && npm test                      # 16 单测 + 6 React 交互测试
cd ui && npm run build                 # 构建验证

# 改完后端 API 必须重新生成前端类型并提交 diff
$PY tools/generate_api_types.py        # 产出 ui/src/api/generated.ts

# 运行
$PY -m server --reload --port 8000     # 后端
cd ui && npm run dev                   # 前端（5173，代理 /api 到 8000）
```

## 4. 当前状态（已验证事实）

> ⚠️ **本节已严重过期**（最后更新 2026-07-30）。当前 R0-R9/M0-M3/L1-L2/P1 阶段二部分已收口，**最新基线见 §9 + AGENTS.md 顶端最后更新行 + 路线图**。下方保留为历史快照。

- **R0 全部 ✅**：渲染正确性、Song v5/Event v2 身份、AppContext、Repository/Application Service、API 契约、数据目录契约（R0.9）、安全地基（R0.10）、工具链（R0.12）。
- **测试基线**：Python 13 个测试文件全绿（含 13 项数据目录测试）；金标准 16/16 diff=0；前端 22 项；tsc/build 干净。
- **前端栈已定**：React 19 + Vite 6 + Tailwind 4 + **shadcn/ui 优先**（`ui/src/components/ui/`，new-york 风格）+ **Motion**（`motion/react`，已完成预览 crossfade POC：`ui/src/components/PreviewCrossfade.tsx`）。
- **现有页面**：海报工作台（grid-wrap 单布局）/ 歌曲库 / 学歌 / 设置 / `/quick` 速查。
- **数据目录契约**：`server/services/data_dir.py` + `GET/POST /api/settings/data-dir(/inspect)`，设置页面板 `DataDirPanel.tsx`。
- **Git**：master 为唯一集成分支；已有提交全部本地，推远程走 `git push git@github.com:jiaiqi/streamer-workbench.git HEAD:master`（HTTPS 不通，用 SSH；不 force push）。

## 5. 工作协议（每项任务都要遵守）

1. **分支**：`feature/<名>` 或 `fix/<名>` 从最新 master 切出；不在 master 直接开发。
2. **质量门（提交前必跑）**：
   - 动了 `core/`、渲染、`server/` → `$PY tools/run_tests.py` 全绿（金标准 16/16 是死线，不得用新引擎自举覆盖旧基线）；
   - 动了 `ui/` → `npx tsc --noEmit` + `npm test` + `npm run build`；
   - 动了后端 API → 重跑 `tools/generate_api_types.py` 并提交 `generated.ts`。
3. **提交**：原子提交，Conventional Commits 中文摘要，如 `feat(server): R1a.1 PosterDocument 领域模型与仓储`。
4. **合并**：分支质量门全绿后 `git checkout master && git merge --no-ff <分支>`，然后继续下一项。
5. **文档同步**：完成清单条目时勾选 `design/开发任务清单-0730.md` 对应复选框；阶段完成时更新路线图状态标记。
6. **组件策略**：新 UI 优先 shadcn/ui（缺组件用 `cd ui && npx shadcn@latest add <名>` 安装）；动效用 Motion 且必须处理 `prefers-reduced-motion`（参考 PreviewCrossfade 用法）；shadcn/Motion 不满足才自写。
7. **禁止**：`.archive/` 只读；`core/` 不得 import FastAPI/React/Electron；不新增 `Song.pinned`；grid-wrap 保持固定 2 页；不为假想能力预建通用抽象。

## 6. 执行计划（P1 → P6）

> ⚠️ **本节已过期**（P1-P6 顺序在 2026-07-30 是未来规划；至 2026-09-06 实际已完成 R0-R9/M0-M3/L1-L2）。**当前执行计划见 `design/产品优化方案终版-0727/路线图.md` R0-R8 阶段表**。下方保留为历史快照。

> 每项都按「后端领域/仓储 → 服务 → API+类型 → 测试 → 前端 UI → 质量门 → 合并」的纵切顺序做，不要横切（先全后端再全前端）。

### P1 · R1a 海报兼容闭环（分支前缀 `feature/poster-document` 等）

**目标**：海报成为可保存/恢复的独立文档，预览渲染可选歌曲集合，Preset 接入工作台；grid-wrap 行为不变。

1. **PosterDocument 领域模型**（R1a.1）
   - 新建 `core/data/posters.py`：`PosterDocument`（schemaVersion/id/name/song_source/selected_song_ids/grouping/sorting/layout_id/theme_id/canvas_id/page_policy/parameters/export_settings/created_at/updated_at/optional_session_ref），类型定义抄 v3 规格 §5.1。
   - SongSource 首批只实现：`all_active`（全部已会）、`manual`（selected_song_ids）；`artist`（指定歌手）可顺手做。song_id 引用，禁止 title 主键。
   - 测试：往返序列化、schemaVersion 缺失拒绝。
2. **仓储** `server/repositories/posters.py`：仿 `FilePresetRepository`（`data/posters/<id>.json`，原子写+备份+revision CAS）。
3. **服务** `server/services/posters.py`：`PosterApplicationService`——CRUD + 把 SongSource 解析为确定 song_id 列表（读 SongRepository，draft 排除）。
4. **API** `server/routers/posters.py`：`GET/POST /api/posters`、`GET/PATCH/DELETE /api/posters/{id}`、`POST /api/posters/{id}/resolve`（返回解析后的歌曲快照列表）。Pydantic 模型进 `server/api/` 合适文件；注册进 `server/app.py`；重生成前端类型。
   - 测试：HTTP 边界（参考 `tests/test_api_contract.py` 的 `_request` 模式与 `tests/test_data_dir_service.py` 的 app 构造）。
5. **样例数据**（R1a.2）：`core/data/sample_songs.py` 内置 ~12 首样例；`POST /api/songs/seed-sample` 仅在曲库为空时可用；前端空曲库空态给「载入示例数据」按钮。
6. **工作台 UI 改造**（R1a.6–R1a.8）
   - 左栏改为「海报文档」区：最近海报列表 + 新建 + 当前文档名/保存状态；「歌曲来源」区：全部已会 / 手动选歌（从歌曲库多选，shadcn Checkbox）/ 指定歌手。
   - 预览请求带歌曲集合：扩展 `GET /api/render` 接受 `song_ids` 或新增 `POST /api/render/document`（推荐后者，v3 §10 API 表）；**预览与导出必须消费同一份解析结果**。
   - 自动保存：文档变更防抖 500–1000ms PATCH；保存状态机（已保存/未保存/保存中/失败）显示在顶栏。
   - Preset 接入：应用 Preset = 恢复其保存的文档字段；保存 Preset = 快照当前文档（后端 API 已齐，只做 UI）。
   - 验收：重复打开最近海报 ≤3 个动作导出；grid-wrap 金标准不变。
7. **grid-wrap 能力声明**（R1a.3）：`GET /api/layouts` 返回能力元数据（支持主题、画布、`legacy-fixed-2`）；超容量（>2 页容量）导出返回明确错误而非静默丢歌。
8. **预览缓存治理**（R1a.4 简版）：去掉预览 URL 的 `&t=` 时间戳，改为渲染输入（含歌曲集合 hash）的查询参数；手动刷新仍强制重取。

### P2 · R1b magazine-flow 自动分页（分支 `feature/magazine-flow`）

- 新建 `core/layouts/magazine_flow.py`：刊头（标题/期号/日期）+ 双/三栏 + `pages=auto`；分类（不分类/歌手/字数/标签 + 空值桶「其他」）在分析层实现，不硬编码进渲染器。
- 分析阶段返回容量/页数/溢出/降级原因；导出按钮显示实际页数；预览与导出页数一致。
- 能力匹配：`GET /api/layouts/{id}/capabilities`，UI 只展示合法主题/比例组合。
- 测试：0/1/临界/临界+1/超量分页、长标题、空分类字段；新布局代表金标准（用 `tools/regenerate_golden.py` 的模式另建，**不动旧 16 张**）。
- 退出条件见路线图 R1b 表格；R1 总退出条件在路线图 §R1，逐条核对。

### P3 · R2 直播闭环 + Desktop Beta（分支 `feature/live-session`、`feature/electron-shell`）

1. **领域** `core/data/live.py`：LiveSession / SongRequest / QueueEntry / PerformanceRecord / RequestPolicy / EntitlementGrant（类型抄 v3 §6）；规则版本化 `rule_version`。
2. **服务/API**：`/api/live-sessions*`、`/api/request-policies*`、`/api/entitlements`（v3 §10）；核销幂等（command_id/event_id）；插队申请→主播确认两态 + 公平保护。
3. **结果状态机**：sung/unknown/postponed/skipped/cancelled/duplicate_merged + 补偿事件；unknown 自动生成待学线索。
4. **QuickView v2**：登记点歌人/权益（可空）、当前歌曲区/本场历史、快捷键 Space/U/P/R；断网待同步不冻结队列（现有 event_id 幂等补报直接复用）。
5. **live-set 布局**：直播信息 + 待唱/已唱 + 完整清单；空队列降级可导出。
6. **薄 Electron 壳**：参考 `github.com/guasam/electron-react-app` 的 electron-builder/IPC 结构（只借鉴，不迁移）；Python sidecar spawn/ready/exit、会话令牌、置顶速查窗、原生目录选择器（接 R0.9 的 data-dir API）、无孤儿进程。

### P4 · R3 学歌闭环（分支 `feature/learning-loop`）

1. **S4 打卡**：practice_logged 事件已有雏形；补 note/minutes/self_rating 字段、时间线 API、离线补报幂等；学歌页打卡 UI（shadcn）。
2. **统计**：`/api/stats/*`（口径查 `roadmap-data-stats.md`）；最近动态/本月新学/练习频次/点歌与已唱 TOP；**数据不足显示「如何积累」，禁止伪趋势**。
3. **数据→创作**：统计结果一键创建 Preset/海报（接 P1 的 posters API）。
4. **乐理辅助**：转调助手（原调/演唱调/半音差/Capo 建议）；Song 专业字段（tempo_bpm/duration/energy/preferred_key）按迁移规范逐步加，允许未知。

### P5 · 统计页（新页面）

- 导航第六入口（窄屏收进「更多」）；总览/学习/直播三视图；冷启动解释卡；「用这些歌曲创建海报」按钮。
- 纯前端 + 复用 P4 的 stats API；图表少而精，shadcn + 语义令牌。

### P6 · R5 工作台系统化

1. **令牌收敛**：消灭组件内 `dark ? ... : ...` 三元（App.tsx/Library/Learning/QuickView 仍有大量），亮暗全部由 `.app-shell[data-mode]` 令牌层驱动；暗色令牌从 design-tokens.json 同源生成。
2. **动效系统化**：规格 §4.8 时长表；队列 FLIP（Motion layout）；面板/对话框过渡；全局 reduced-motion（含设置页开关持久化到 `/api/settings`）。
3. **无障碍**：删除确认换 shadcn AlertDialog（`npx shadcn add alert-dialog`）替代 `window.confirm`；快捷键查看/修改/冲突检测；焦点归还审查；WCAG AA 对比。
4. **响应式**：1440/1100/800/375 四档；窄屏「更多」收纳统计与设置。
5. **状态可靠性**：WorkspaceDocument 与 UI 状态分离、撤销重做（仅文档状态）、离开保护、导出历史 + ExportSnapshot 重生成（`/api/export/history`、`/api/export/replay/{id}`）。

## 7. 常见坑（接手者最易犯）

- 用系统 python 跑测试报 `No module named 'fastapi'` → 必须 `.venv/bin/python`。
- 改了 API 没跑 `tools/generate_api_types.py` → 前端类型漂移，CI 挂。
- shadcn CLI 把组件写到字面 `@/` 目录 → 根 `tsconfig.json` 的 paths 已修好，若复发检查该文件。
- vitest 单独用 `vitest.config.ts`，别名要两边都配。
- grid-wrap 固定 2 页是 ADR-002 兼容模式，不是 bug；新分页逻辑只属于新布局。
- 预览 URL 的 `&t=` 是缓存破坏者，P1 第 8 项治理，不要提前删（歌曲库变化目前靠它刷新）。

## 8. 会后增量（2026-07-30 末追加）

R1a 完成会后又闭环了 R1b 与 R3 整段核心纵切，向 origin/master push 6 个 commit。本节交代增量，避免读旧 handoff 时漏掉。

### 8.1 R1b magazine-flow（已完成）

- `core/layouts/magazine_flow.py` — 刊头流式分页布局，6 种分类轴（chars/artist/genre/language/initial/status），`pages=auto` 时调用 `analyze(library, axis, canvas)` 返回 `total_songs / page_count / per_page_max / categories / overflow / degrade_reason`。
- `core/engine.py:render_pages(theme, layout, library, spec, font_path, *, page_count=None)` 适配 `layout.pages=None` 自动分页；截断到 `max(theme.styles)` 兜底。
- `server/routers/render.py:POST /api/layouts/magazine-flow/analyze` — UI 预估页数/分桶前端反馈。
- `tests/golden_magazine/` — 6 张 PNG + `manifest.json`（sha256/size_bytes）独立目录，**不动 grid-wrap 16 张金标准**。测试用 `test_magazine_golden.py` 验证指纹 + 画布尺寸差异（防御过夜回归）。
- `tools/generate_magazine_golden.py --confirm-baseline` — 重建工具，**必须 `--confirm-baseline` 标志**才生成（防误操作）。
- UI：`ui/src/posters/LayoutPicker.tsx` radiogroup，切换联动 `page_policy`（grid-wrap → legacy-fixed-2；magazine-flow → auto）。

### 8.2 R2 P3 直播核心（已完成 6/7 子项；剩余 Electron 壳）

后续读 HANDOFF 时务必注意：**R1a 是 100%，R3 直播核心纵切也是 100%**。两者都没做完的是「Electron 桌面壳 + 置顶速查窗口 + 离线去重补报」，这部分挂在 P3-Electron 而不是 R3。

#### R3 落地模块

| 模块 | 文件 | 用途 |
|---|---|---|
| 领域 6 个 dataclass | `core/data/live.py` | LiveSession / SongRequest / QueueEntry / PerformanceRecord / RequestPolicy / EntitlementGrant |
| EntitlementService | `server/services/entitlements.py` | 幂等核销（command_id）+ 返还；InMemoryEntitlementLedger 持久化在 R3-Persistence |
| RequestPolicyService | `server/services/request_policy.py` | 决策（普通权益队尾入/插队权益申请）+ 公平保护 + 规则 diff |
| LiveService | `server/services/live.py` | 状态机：start/queue/record/close；duplicate_merged 自动合并；skipped/unknown/cancelled 触发 entitlement 退还 |
| LiveRepository | `server/repositories/live.py` | 原子写 + revision CAS + 备份 + 软删除 + 恢复；manifest 跟踪 |
| LiveSessionPersistenceService | `server/services/live_persistence.py` | 写穿：每次 LiveService 命令立即 save_to_repo；启动期 `load_session()` 重建 |

#### HTTP 路由 7 端点

| Method | Path | 用途 |
|---|---|---|
| `GET` | `/api/live-sessions` | 列表（摘要 + queue_size）|
| `POST` | `/api/live-sessions` | 创建（rule_version + title + poster_id 可选）|
| `GET` | `/api/live-sessions/{id}` | 详情（queue + performances）|
| `POST` | `/api/live-sessions/{id}/queue` | 入队（duplicate_merged 标记）|
| `POST` | `/api/live-sessions/{id}/record` | 记录结果（sung / skipped / unknown / cancelled / postponed）|
| `POST` | `/api/live-sessions/{id}/close` | 关闭（仅 SESSION_ACTIVE 可关闭）|
| `POST` | `/api/live-sessions/{id}/entitlements` | 授予权益 |

`LiveServiceError` 统一翻译 `400 live_service_error`；`SESSION_CLOSED` 后入队返回 400。

#### 重启恢复

lifespan 启动期自动 `list_sessions()` + `load_session()` → 新 LiveService 实例与已存数据完整对齐。
`tests/test_live_api.py:test_restart_app_recovers_sessions` 是端到端验证。

#### 测试基线（handoff 增量参考）

| 类型 | 数量 |
|---|---|
| Python | 31/31（其中 P3 新增 88+ 用例：领域 31 + Entitlement 16 + Policy 14 + Live 14 + LiveRepo 12 + Persistence 8 + Live API 13）|
| 单元 | P3 子模块可单独 `python tests/test_live_service.py` 等 |
| 端到端 | `tests/test_live_api.py` 13 个 ASGI 用例 |

#### 设计契约（接手必读）

- **核销幂等**：`command_id` 在账目里唯一；重复 `consume(ent_id, cmd)` 不重复扣。`refund(ent_id, cmd)` 必须用 `refund:<原cmd>` 前缀，命名空间隔离。
- **rule_version 不回写**：每次 grant / 创建 LiveSession 都绑定 `rule_version`。修改规则版本=生成新 RequestPolicy 快照。`RequestPolicyService.rule_differs(new)` 用于升级检测。
- **BUMP_UNLOCK_KINDS**=`{high_value_gift, manual_bump}`：插队申请资格。主播空 kind 视为 `manual_add`：主播直接加歌，不消耗额度，不需主播确认。
- **duplicate_merged**：同 `(session, song_id, requester_id_or_name)` 二次入队合并，账目只一次扣，事件区分。
- **公平保护 trigger**：`recent_bumps_in_a_row >= policy.fairness_max_consecutive_bumps` → decision `degraded=True + reason=已达插队上限`；仍允许但需主播说明。

#### 接手常踩坑（HANDOFF §7 已有部分 + R3 新增）

- 改 Live 端点忘了 `LiveServiceError` 翻译 → FastAPI 返 500 而非 400；router 必须同时捕获 `LiveServiceError` + `EntitlementServiceError` + `ValueError`。
- 在 R3-Electron 加入 **之前**不要把 LiveService 当 QuickView sole source — QuickView 离线队列 + `event_id` 幂等补报是后续会话领域，目前端到端只在 FastAPI 上工作。

### 8.3 R4-R6 后续路径

- P4 R3 学歌闭环：S4 打卡（`practice_logged`）+ 统计口径（最近动态/本月新学/TOP）+ 乐理辅助（转调 / 和弦 / 音域）— 下一会话起点
- P5 统计页：纯前端 + 复用 P4 stats API；导航第六入口
- P6 R5 工作台系统化：令牌收敛（消灭 dark 三元）+ 动效系统化 + 无障碍 + 响应式 + WorkspaceDocument 状态可靠性

### 8.4 测试运行入口

> ⚠️ **本节命令已过期**（2026-07-30 写）。`npx tsc --noEmit` 因根 tsconfig `files:[]` 恒绿，**已废弃改用 `npx tsc -b`**（真门，纳入测试文件类型检查）。详见 §9.4 今晚更新后的命令。

```bash
# 全栈（推荐）
.venv/bin/python tools/run_tests.py                     # 31 个测试文件全部
cd ui && npm test                                        # 16 单测 + 6 React 交互
cd ui && npx tsc --noEmit && npm run build               # 前端质量门

# 单 P 模块（精细诊断）
.venv/bin/python tests/test_live_api.py                 # R3 端到端
.venv/bin/python tests/test_render_document.py          # R1 渲染
.venv/bin/python tests/test_golden.py                     # 金标准
```

实际边界仍然由 `tools/run_tests.py` 守门（自动 glob `tests/test_*.py`）。

---

## 9. 会后增量（2026-09-06 P1 阶段二 4 刀收口）

> 承接 §8 R0-R6 增量。本节是 2026-09-06 一次会话的 5 个 commit（4 feature + 1 docs）入档，
> 全部已推 origin/master。基线：R0-R9/M0-M3/L1-L2 已收口；本节新增 P1 阶段二 2.5/6 项。
>
> 设计动机来自 `design/prototypes/2026-09-06-功能与UIUX优化分析.md`（项目自审报告，229 行）。

### 9.1 R5c WCAG AA 颜色审计修复 + stagger reduce-motion 兜底

**Commit**：`4b85e71 feat(r5c-a11y)` ｜ 5 文件 / 134 增 9 改

R5c 三件套之「WCAG AA」与「动效规范」首批收口：

- **颜色 token 化**：新增 `--color-danger-text`（亮 #b23c3c on faf8f5 = 5.50 / 暗 #e08585 on 141c18 = 6.50）+ `--color-accent-text`（亮 #1f6756 = 5.74 / 暗 #49b89c = 7.93）
- **亮主题**：`muted-fg` 4.17→**5.19** / `warning` 文字 2.32→**5.31** / `danger` 文字 4.11→**5.50**（11-13px 全过 AA 4.5）
- **暗主题**：`destructive` 底色白字 4.11→**4.69** / `danger` 文字 7.23 on bg / 6.50 on card
- **硬编码颜色接入 dark 感知**：`App.tsx` / `StatusBar.tsx` / `ParamInspector.tsx` / `TabsPanel.tsx` 4 处 `text-red-500` / `text-amber-500` 改 dark 状态
- **动效**：`prefers-reduced-motion` 下 `.stagger-list > *` 直接 `opacity:1` + `animation:none`（解决 stagger 列表在 reduce 模式下依赖动画基态、可见性被延迟的 WCAG 2.3.3 违规）
- **配套契约测试**：`ui/src/design-tokens.a11y.test.tsx` 8 项
  - 纯数学无 DOM，解析 `:root` → `.app-shell` → `[data-mode]` 三层 token 块
  - 断言 8 类关键「文字/背景」对比度全部 ≥ 4.5（AA normal text）
  - 含 reduce-motion stagger 兜底契约断言
  - **修改任何 `--color-*` 令牌前必须先跑本测试**（写在文件头注释里）

### 9.2 P1-A1.1 今晚动线升格首屏

**Commit**：`9d604e6 feat(p1-a1.1)` ｜ 5 文件 / 302 增 7 改

设计动机：原 IA 把海报工作台放在首屏，TonightWorkbench 是 256px 侧栏里的"塞进海报台的 guest"。
真实动线是「白天备演 → 夜间直播 → 下播复盘」（ADR-008 / v3 §6.6），海报是产出物而非入口。

最小切片 v0.1（一次只动 IA，不动核心交互、不接新端点）：

- **新增 `views/TonightView.tsx`**：屏幕标题「开播前 · 准备」+ 复用 TonightWorkbench 全部 5 区 + 右侧 w-72 WorkspacePosterBridge + 「需要专门做一张海报？」CTA 跳到工作台
- **`App.tsx` 装配层**：
  - 默认 view `'workspace'` → `'tonight'`（首屏 = 今晚动线）
  - `navItems` 第一项改为 `tonight`（新 `Icon.tonight` = 月相 + 星），原 `workspace` 改名"海报"挪到第二位
  - 新增 `view === 'tonight'` 渲染分支
  - 命令面板新增 `view-tonight` 命令；快捷键标注的 `'1'` / `'2'` 全部移除（与 `⌘1-7` 切主题冲突，统一走 `⌘K`）
  - `statusView` 加 tonight → workspace 状态位复用
- **`icons.tsx`**：新增 `Icon.tonight`（月相 + 一颗小星，避与 live/music 重复）
- **`App.react.test.tsx`**：原"next-preload img 挂载"测试改为先点侧栏"海报"切到 workspace 再断言（默认首屏变了）
- **`views/TonightView.test.tsx`**（3 spec）：渲染 / 透传 7 回调 / CTA 触发

**显式不在本次范围**（避免 scope creep，留作 P1 阶段二后续切片）：
- ❌ keep-alive / URL 路由
- ❌ 接 entitlements / lyric 端点
- ❌ 不动 TonightWorkbench 内部 925 行
- ❌ 不动 R5c 还债线（648 处硬编码调色板、3 处 hex）

### 9.3 P1-A1.2 就绪度 4 徽章全局化

**Commit A** `7715edb feat(p1-a1.2 步骤 1)`：lib 抽离 ｜ **Commit B** `5130bb7 feat(p1-a1.2 步骤 2)`：组件 + 接入 ｜ 6 文件 / 478 增 10 改

设计动机：178 首歌里 0 首有音频、0 首有 LRC、2 首有曲谱 — 没有全局徽章，弹唱完整度 15% 只孤立地显示在歌曲库页头。本提交让主播打开 LibraryView 时每首歌行内即见就绪度，一瞥即知"今晚能不能弹唱"。

**步骤 1（独立可提交）**：

- `ui/src/lib/readiness.ts` — 共享纯函数 + 类型
  - `READINESS_FIELDS = ['tabs', 'lyrics', 'audio', 'key']` 常量
  - `READINESS_FIELDS_LOOKUP` 4 字段中文标签
  - `ReadinessField` 字面量联合类型
  - `ReadinessFields` 5 字段最小窄类型（`evaluateReadiness` / `isFullyReady` / `buildReadinessChips` 入参；避免强制 import 完整 Song 模型）
  - `SongForReadiness extends ReadinessFields` 7 字段（`aggregateReadiness` 用，含 id + title 报告）
  - `evaluateReadiness` / `isFullyReady` / `buildReadinessChips` 纯函数（行为与原 TonightWorkbench 925 行内部 `evaluateReadiness` 完全一致：`lyrics_plain` 与 `lyrics_lrc` 二选一即可）
- `ui/src/lib/readiness.test.tsx`（12 spec）：全齐 / 全空 / 半空 / lyrics 二选一 / 字段顺序 / 聚合报告 / 常量覆盖 等

**步骤 2（独立可提交）**：

- `ui/src/components/ReadinessBadge.tsx` — 4 枚徽章渲染组件
  - 接受 5 字段（与 `generated.ts` SongResponse 自然兼容，内部 `undefined` → `""` / `null` 防御）
  - `size: 'xs' | 'sm'`（xs = 9px 行内紧凑 / sm = 10px 报告用）
  - 已就绪 → 绿勾 ✓，缺失 → 灰叉 ✗（line-through）
  - 暗/亮两套色（与 R5c 视觉测试一致：`emerald-500/15`/`emerald-50` vs `zinc-800/60`/`muted-60`）
  - `data-testid` + `data-ready` + `role="group"` + `aria-label`（无障碍）
  - 容器 `data-ready-count` / `data-total-count` 便于聚合断言
- `ui/src/lib/readiness.ts` 拆分：`ReadinessFields` 5 字段 vs `SongForReadiness` 7 字段（让 ReadinessBadge 不强制要求 id/title）
- `ui/src/views/LibraryView.tsx` 接入：元数据行（行 870-890）插入 `<ReadinessBadge song={s} size='xs' dark={dark} />` 在 tags 之后、KeyCapo 之前；容器加 `flex-wrap` 窄屏适配
- `ui/src/components/ReadinessBadge.test.tsx`（8 spec）：4 枚徽章 data-testid 各自命中 / 全齐 / 全空 / 半空 / undefined 防御 / size='sm' / role+aria-label / 暗色 line-through

**显式不在本次范围**（避免 scope creep）：
- ❌ 替换原 TonightWorkbench 925 行内部 ReadinessCheck 为共享 lib（保留行为不变）
- ❌ 学歌 / 弹唱 / 速查等其他视图接入
- ❌ 徽章点击触发"补什么"动作（v0.2 计划：右击弹动作菜单）
- ❌ LibraryView 列表行以外的视图（grid 行、详情面板、筛选条等）接入

### 9.4 测试入口与质量门（2026-09-06 21:00 实测）

> 替换 §8.4 旧命令。

```bash
# 全栈（推荐）
.venv/bin/python tools/run_tests.py                     # 自动 glob tests/test_*.py
PYTHONPATH=. python3 tests/test_unit.py                 # 95 passed（test_unit.py 主文件）
PYTHONPATH=. python3 tests/test_golden.py               # 16/16 金标准 0 像素差异
cd ui && npx vitest run                                 # 70 文件 849 passed
cd ui && npx tsc -b                                     # 0 错（注意：旧 npx tsc --noEmit 已废弃，恒绿假门）
cd ui && npx tsc -b && npm run build                    # 完整前端质量门

# 关键测试点（精细诊断）
cd ui && npx vitest run src/lib/readiness.test.tsx           # 12 spec：就绪度 lib
cd ui && npx vitest run src/components/ReadinessBadge.test.tsx  # 8 spec：徽章组件
cd ui && npx vitest run src/views/TonightView.test.tsx       # 3 spec：今晚视图容器
cd ui && npx vitest run src/App.react.test.tsx               # 8 spec：App 装配回归
cd ui && npx vitest run src/design-tokens.a11y.test.tsx      # 5 spec：WCAG AA 契约
cd ui && npx vitest run src/components/TonightWorkbench.test.tsx  # 5+1 spec：5 区组件（保持未动）
```

**质量门**（2026-09-06 21:00 实测，今晚 P1 阶段二 4 刀收口后）：
- `tsc -b`：0 错
- `vitest`：70 文件 **849 passed**（+12 readiness + 8 ReadinessBadge + 3 TonightView + 5 a11y）
- `pytest test_unit.py`：**95 passed**（已 R0-R8 全部收口）
- 金标准：5 套布局 **36/36** 0 像素差异（grid 16 + magazine 6 + live-set 5 + learning-report 5 + fullscreen 4）
- 新依赖：0

### 9.5 当前未追踪的本地资产（不入库，按你之前选过）

- `.zcode/plans/plan-sess_64dc7272-48ff-4bd4-a033-8e416fa28a68.md` — 本地 zcode 计划
- `design/prototypes/2026-09-06-功能与UIUX优化分析.md` — 项目自审报告（229 行）
- `design/prototypes/tonight-flow-v1.html` — 1252 行单文件原型（4 屏 + 标注模式）

3 个文件保持 untracked；是本会话参考资料与设计文档，不进版本库。

### 9.6 P1 阶段二剩余路线（建议后续切片）

按自审报告 §5 顺序，本会话完成 2.5/6：

1. ✅ **TonightHome 重组**（首屏切今晚动线）— §9.2
2. ✅ **就绪度 4 徽章全局化** — §9.3
3. ⏳ **就绪度补全泵 · 音频批量导入**（端到端 / scope 较大 / 让 R8/R9 真正可弹唱）
4. ⏳ **演出模式权益审计**（LiveView 接 entitlements 端点；演中已被 QuickView 独立路由取代事实作业面，价值打折）
5. ⏳ **收口清单 + 复盘海报推荐**
6. ⏳ **还债批**：URL 路由/keep-alive → token 收敛（648 处）→ 弹窗治理 → 动效/无障碍

### 9.7 推荐分支与提交流程

- master 仍为唯一集成分支；按既有节奏延续（不在 master 上开 feature 分支）
- 提交粒度按"原子 + 一项一 commit"，如 `feat(p1-a1.2 步骤 1)` + `feat(p1-a1.2 步骤 2)`
- Conventional Commits 中文摘要
- 推远程走 `git push git@github.com:jiaiqi/streamer-workbench.git HEAD:master`（HTTPS 443 不通，用 SSH）
- **不 force push，不改写已发布历史**
