# 主播工作台 · 活跃产品文档入口

> **状态**：活跃
> **最后更新**：2026-08-01
> **规则**：本目录只保留当前执行文档。评审过程、阶段快照和旧交互稿统一放在 `../archive/`，仅供追溯，不得作为开发依据。

## 唯一真相

| 主题 | 唯一文档 | 职责 |
|---|---|---|
| 完整目标 | [`产品优化方案终版.md`](产品优化方案终版.md) | 产品、UI/UX、领域模型、渲染与桌面端完整目标 |
| 详细增量规格 | [`产品与技术规格-v3.md`](产品与技术规格-v3.md) | 2026-07-29 UI、独立海报、直播点歌、乐理辅助与技术契约 |
| 执行顺序 | [`路线图.md`](路线图.md) | R0–R7 当前状态、依赖、阶段门和退出条件（**v4 — 2026-08-01**） |
| **整体分析** | [`项目整体分析-0801.md`](项目整体分析-0801.md) | **v4 新增 — 4 维度（功能/交互/UI/细节）盘点，路线图 v4 基于此** |
| 数据与统计 | [`../roadmap-data-stats.md`](../roadmap-data-stats.md) | Event Schema、统计口径和 S1–S5 状态 |
| 架构决策 | [`../../ADR-001.md`](../../ADR-001.md)–[`../../ADR-008.md`](../../ADR-008.md) | 已批准且不可被普通规格静默覆盖的决策；ADR-006/007/008 是本轮新增裁决 |
| 项目入口 | [`../../README.md`](../../README.md) | 运行、测试、目录和 API 快速入口 |
| Agent 规则 | [`../../AGENTS.md`](../../AGENTS.md) | 自动化开发必须遵守的铁律和当前状态 |

出现冲突时按以下优先级裁决：

```text
AGENTS 铁律 / 已批准 ADR
        ↓
路线图当前阶段与退出条件
        ↓
产品优化方案终版完整目标
        ↓
数据路线图中的事件与统计口径
        ↓
其他说明文档
```

数据路线图只在事件 Schema 和统计口径上高于主规格；执行先后仍以 `路线图.md` 为准。

## 当前结论

- 不重写技术栈，继续采用 Python + Pillow、FastAPI、React + Vite 和 Electron；
- R0–R5 + R2.5 + R3.5 全部完成；R4.0 Phase 1 已收口（6dbdc63）；**当前活跃阶段：R4.0 Phase 2 — 4 项 P0 收口**（路线图 v4）；
- R0 重点是 `song_id` 全链路、AppContext、Repository 写入可靠性、类型化 API、用户目录和本地服务安全；
- 导出纵向切片已由 Application Service 接管：Router 只映射 HTTP，ExportSnapshot 冻结文档、绝对目标和来源修订，后台任务不再回读 Repository；
- 歌曲核心写用例已由 SongApplicationService 接管：不可变 ID 为主、标题路由仅作兼容，保存使用 Repository revision/CAS，成功后追加身份完整事件；
- 曲谱附件已由 TabApplicationService 接管：journal 协调文件、歌曲元数据和固定事件 ID，支持 CAS 失败回滚与启动恢复；详细状态机见 [`../contracts/R0.7-tab-transactions.md`](../contracts/R0.7-tab-transactions.md)；
- Preset 已由 PresetApplicationService 接管：服务端持有 ID/时间/默认状态和 CAS，Router 仅映射 CRUD、复制、软删除与默认切换；详细契约见 [`../contracts/R0.7-preset-application-service.md`](../contracts/R0.7-preset-application-service.md)；
- R1a 使用 `grid-wrap` 验证独立海报兼容闭环并保持固定两页；R1b 用具体的 `magazine-flow` 验证自动分页，不提前建设通用运行时；
- R2.5 / R3.5 交付 live-set / learning-report 两套新布局，分别走 `LiveSessionSnapshot` / `LearningReportSnapshot` 独立数据通道（铁律 #9）；
- 海报由独立 PosterDocument 持有；LiveSession 只管理规则、点歌、队列和演唱结果；
- Layout 与 Theme 多对多，比例和分页由 Layout 能力声明；旧 `grid-wrap` 仍固定两页兼容；
- 点歌规则可配置且版本化，点歌人/权益来源可选，高价值礼物默认仅申请插队并由主播确认；
- 应用支持独立可选主色，默认竹月青；主色不改海报 Theme/Palette 或成功/警告/危险语义色；
- R4.0 Phase 1 抽出 8 个公共 helper（`core/layouts/_common.py`）— `format_date` / `truncate` / `safe_label` / `result_glyph` / `draw_section_label` / `draw_pill` / `horizontal_rule` + streak 算法统一；
- R4.0 Phase 2 收口 4 项 P0：App.tsx 拆解 / 三套新布局接工作台 / 海报真保存 / 暗色 hardcode 收口；
- 完整自定义编辑器继续后置（铁律 #10 — 3 套新布局真实使用后才能启动）。

## 子系统文档

| 文档 | 状态 | 用途 |
|---|---|---|
| [`../../site/landing/README.md`](../../site/landing/README.md) | 活跃子系统说明 | `site/landing/` 的运行、构建、部署和维护方式 |
| [`assets/colors/README.md`](assets/colors/README.md) | 活跃资产说明 | 落地页配色样张和复现方式 |
| [`../design-tokens.json`](../design-tokens.json) | 活跃设计令牌 | 工具界面和落地页颜色/字体语义源 |

## 已归档且不再使用

以下文件已移动到 [`../archive/2026-07-28/`](../archive/2026-07-28/)。它们只解释历史，不得用于判断当前功能、架构或执行顺序：

| 文件 | 归档原因 | 替代文档 |
|---|---|---|
| `P0_现状快照.md` | 阶段快照已过期，包含旧文件位置和旧完成度 | README、AGENTS、路线图 R0 |
| `三方案差异分析.md` | 合并过程已完成，部分代码事实和 P 阶段已失效 | 主规格、路线图、ADR |
| `UI-UX评审与实施裁决.md` | 有效结论已合并进主规格；“场景”已升级为“本场” | 主规格 §3–§5、路线图 R1/R2 |
| `redesign-v1.html` / `redesign-v2.html` | 静态交互探索稿与当前 IA、状态契约不一致 | 主规格 §4、真实 React UI |
| `落地页设计方案.md` | 落地页已工程化，旧阶段、日期和布局承诺已失效 | `site/landing/README.md` 与源码 |

## 历史只读区

`.archive/` 是原设计仓库的不可变历史快照。它可以用于：

- `grid-wrap` 独立预言机和像素级兼容依据；
- 查询早期设计背景和迁移历史；
- 审计过去的技术选择。

除金标准预言机外，`.archive/` 中的产品计划、UI 页面和项目状态均不是当前执行规格，且该目录内任何文件不得修改、删除或移动。
