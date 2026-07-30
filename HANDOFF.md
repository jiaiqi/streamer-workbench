# 主播工作台 · 执行交接（HANDOFF）

> **读者**：接手开发的 AI 或人类工程师。
> **日期**：2026-07-30 ｜ **基线**：master @ R0 全部完成，Motion/shadcn 已合并。
> **使用方法**：从「4. 当前状态」确认起点，按「6. 执行计划」自上而下逐项实施；每项完成后按「5. 工作协议」提交合并。

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
