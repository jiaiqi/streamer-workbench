# 数据时间维度路线图：事件日志 · 曲谱管理 · 学歌记录 · 数据统计（主播工作台 / streamer-workbench）

> **状态**：进行中（2026-07-28 更新）——S1 ✅ S2 ✅ S3 ✅；S3.5 中 Song v5 ✅、Event v2 与关系迁移待完成；S4 / S5 等待完整前置
> **关联文档**：`redesign-v2.html`、`../ADR-004.md`、`产品优化方案终版-0727/路线图.md` R0/R3（事件类型与统计口径仍以本文为唯一真相）
> **前置阅读**：`core/data/songs.py`（数据层与迁移链）、`server/main.py`（API 现状）

---

## 1. 背景与目标

用户（主播本人）提出的四个需求：

1. **曲谱管理** —— 和弦谱/六线谱的附件化存储与快速查看（直播、练习时调用）
2. **歌单更新记录** —— 人类可读的变更时间线（谁/何时/改了什么/导出了什么）
3. **学歌记录** —— 练习打卡、学习周期、卡点追踪
4. **数据统计** —— 曲库趋势、点歌排行、练习热力等聚合视图

**核心判断**：四个需求本质是同一件事——现有系统只有"当前状态"，没有"时间维度"。因此不立四个独立项目，而是先打共同地基（事件日志），四个功能作为地基上的应用层分期交付。

**2026-07-28 补充判断**：时间维度必须建立在不可变身份上。歌名是可修改显示字段，不能继续作为事件、曲谱、直播队列和 Preset 的长期关联键。S4/S5 开工前先完成 ADR-004。

## 2. 现状差距

| 需求 | 现状 | 差距 |
|---|---|---|
| 曲谱管理 | `Song.tabs` 为纯文本字段（`songs.py:28`） | 无文件附件、无预览、直播时调不出 |
| 更新记录 | `data/backups/` 有全量快照（灾难恢复用） | 无字段级、人类可读的事件流 |
| 学歌记录 | 「标记学会」= status 翻转，不记时间；无 `learned_at` | 无法回答"学了几天/本月学会几首/哪首卡最久" |
| 数据统计 | 仅 toolbar 即时计数（已会/未会/弹唱完整度） | 无趋势、无排行、无历史 |
| 直播点歌数据 | 今晚歌单仅存浏览器 localStorage（`QuickView.tsx`） | 换设备即丢，点歌排行数据在流失 |

## 3. 架构决策：事件日志做地基

```
┌─────────────────────────────────────────────────┐
│ songs.json（保留）= 当前状态的唯一真相             │
├─────────────────────────────────────────────────┤
│ events.jsonl（新增）= 追加式事件流，一切历史       │
│ data/tabs/（新增）= 曲谱文件目录（图片/PDF）       │
├─────────────────────────────────────────────────┤
│ 统计 = events + 当前状态 现算的"视图"，不落库      │
└─────────────────────────────────────────────────┘
```

### 决策：JSONL 事件流，不引入 SQLite（2026-07-27 定）

理由：
- 与项目既有哲学一致（个人单机工具、JSON 持久化、原子写、版本迁移链；参见 `songs.py` 头部注释"增加状态复杂度应在有真实用户行为数据后再做"）；
- 追加写抗崩溃截断（一行一事件，坏行不毁全文件）；`data/backups` 滚动备份机制可直接复用；
- 个人使用量级（每日数十事件、每年数千行）顺序扫描足够；
- **撤退路线**：事件量破万或需多设备同步时，事件流可整体导入 SQLite，schema 无需重设计——事件先行，存储可换。

### 决策：点歌事件不分"场次"（2026-07-27 定，方案 A）

不加「开始今晚」会话按钮。所有点歌事件平铺带时间戳，排行按全部时间/近 30 天聚合。未来需要按场分析时，按时间窗口事后切分即可，现在不付交互成本。

### 决策：歌曲使用不可变 ID（2026-07-28 定）

- `Song.id` 是长期身份，`title` 可修改；
- 所有新事件按 `song_id` 聚合，并保存 `title_snapshot` 供历史展示；
- 曲谱目录、QuickView 队列和 Preset 手动集合改用 `song_id`；
- 旧 v1 事件只读兼容，不批量改写历史；
- 完整裁决见 `../ADR-004.md`。

## 4. 事件流规格

**文件**：`data/events.jsonl`，每行一个 JSON 对象。当前代码兼容 Schema v1，新写入目标为 Schema v2：

```json
{"schema_version":2,"event_id":"evt_...","occurred_at":"2026-07-28T21:03:11+08:00","recorded_at":"2026-07-28T21:03:12+08:00","type":"song_learned","song_id":"song_...","title_snapshot":"凄美地","source":"learning-view","meta":{"days_in_learning":12}}
```

**新模块**：`core/data/events.py`（预计 ~100 行）

- `append_event(type, song_id=None, title_snapshot=None, meta=None, occurred_at=None, event_id=None)` —— 追加一行（open-append-close）
- `iter_events(type=None, since=None, until=None)` —— 顺序扫描生成器
- `tail(n)` —— 更新记录 feed 用
- `event_id` 用于离线补报去重；`occurred_at` 与 `recorded_at` 分离；
- 遵守铁律：`core/` 不 import 任何服务器/UI 框架；`server/` 调用它

**事件类型**：

| type | 触发点 | 支撑功能 |
|---|---|---|
| `song_added` / `song_deleted` | /api/songs/add、/api/songs/delete | 更新记录 |
| `song_edited` | /api/songs/update（meta 记字段级 diff：`{"field":"key","old":"","new":"G"}`） | 更新记录 |
| `song_learned` / `song_unlearned` | /api/songs/status（draft⇄active） | 更新记录 + 学歌统计 |
| `practice_logged` | 学歌打卡（meta：`{note, minutes?, self_rating?}`） | 学歌记录 |
| `queue_added` / `song_sung` | 直播模式加入歌单/标记唱完时上报 | 点歌排行、演唱频次 |
| `poster_exported` | /api/export、/api/export/batch（meta：`{theme,layout,canvas,pages,duration_ms}`） | 海报更新记录 |

## 5. 数据模型变更

### 已完成：迁移 v3→v4

`Song` 新增两个字段，默认值兼容旧数据：

```python
learned_at: str = ""          # 学会日期（song_learned 时回填；旧 active 歌曲留空）
tab_files: List[str] = []     # 曲谱文件相对路径，如 "tabs/知足/主歌.png"
```

- 迁移函数 `_migrate_v3_to_v4`：补两个字段默认值，注册进 `MIGRATIONS` 链；
- `tabs` 文本字段**保留**：记和弦进行简记、谱子来源链接，与文件附件互补；
- 单元测试按既有纪律同步增加（参照 v1→v2、v2→v3 的测试写法）。

### 已完成代码：迁移 v4→v5

已新增不可变 `Song.id`：v4 旧数据使用确定性 UUIDv5，新歌使用 UUIDv4；加载时拒绝空 ID、重复 ID 和重复 title，API 列表返回 `id`。首次持久化仍沿用 `SongLibrary.save()` 的写前备份与原子替换。曲谱目录迁移到 `data/tabs/{song_id}/{文件名}`、Event v2 和其他关系切换仍属于后续 R0.4/R0.5。

## 6. API 增量（server/main.py）

| 端点 | 方法 | 说明 |
|---|---|---|
| /api/songs/{song_id}/tabs | POST | 上传曲谱文件（兼容期保留 title 旧路由） |
| /api/songs/{song_id}/tabs | GET | 列出该曲谱文件 |
| /api/songs/{song_id}/tabs/{file} | DELETE | 删除单个谱文件 |
| /tabs/{song_id}/{file} | GET | 静态访问（StaticFiles 挂载 data/tabs/） |
| /api/practice/log | POST | 学歌打卡，写 practice_logged |
| /api/events | GET | 事件 feed（参数：type/since/limit），更新记录视图用 |
| /api/stats/overview | GET | 总览聚合（现算）：曲库规模、选调完整度、本月学会、本月演唱次数 |
| /api/stats/learning | GET | 学歌聚合：学习周期分布、打卡热力、卡最久 draft 榜 |
| /api/stats/live | GET | 直播聚合：点歌 TOP10（全时段/近30天）、演唱频次 |

**埋点位置**：add/update/status/delete/export 五个现有端点各加一行 `append_event`（`_save_library()` 调用处旁），不改现有响应契约。

**QuickView 上报**：今晚歌单使用 `song_id + title_snapshot` 本地缓存并上报 Event v2。上报失败存本地待补；后端按 `event_id` 去重，直播现场不能因为后端挂了就丢队列。

## 7. UI 触点（对照 redesign-v2.html）

| 功能 | 触点 |
|---|---|
| 曲谱 | 歌曲库展开面板加「曲谱」区（缩略图墙+上传+lightbox）；学歌卡片加谱子入口；直播模式焦点区加 `T` 键看谱弹层 |
| 更新记录 | 新「统计」视图内"最近动态"时间线（事件 feed 直渲） |
| 学歌记录 | 学歌卡片加「打卡」按钮（note+可选时长+自评）+ 展开练习时间线（倒序）+ 累计打卡天数 |
| 数据统计 | **导航加第五项「统计」**（4 一等公民 + 统计 + 设置 = 6 图标位，仍在导航上限内）。三板块：总览卡 / 趋势图（近 12 周学会数、曲库增长，纯 CSS 柱状，不引图表库）/ 排行榜（点歌 TOP10、练习最勤、卡最久未会） |

视觉全部套 v2 设计稿 token（surface 阶梯、amber/green/red 语义色、◆◆◇ 难度、三档按钮）。

## 8. 统计口径（提前定义，避免口径漂移）

- **弹唱完整度** = 有 key 的 active 歌曲数 / active 总数（与 toolbar 现口径一致，扩展为含 capo 的细分）
- **学习周期** = learned_at − added_at（天）；旧数据 learned_at 为空不参与均值
- **本月学会** = song_learned 事件当月计数（减同月 song_unlearned 净额另列）
- **点歌排行** = song_sung 事件按 song_id 计数；title_snapshot 只负责展示；点歌率 = song_sung / queue_added（约等于唱完率）
- **直播场次（估算）** = song_sung 事件按自然日聚类（无会话 id，事后按日切分）

## 9. 分期实施（S1→S5）

| 阶段 | 内容 | 状态 | 验收 |
|---|---|---|---|
| **S1 地基** | events.py + 五端点埋点 + 迁移 v4（learned_at/tab_files）+ /api/events feed | ✅ `05ac6e7` | 单元测试 27→37 通过；五动作逐行落 events.jsonl |
| **S2 点歌上报** | QuickView 双写（localStorage + 上报）+ 失败补报 | ✅ `403165c` | /api/events/report（仅三类可上报）；断网队列不丢、恢复保序补报 |
| **S3 曲谱** | tabs 上传/列表/删除/静态访问 + 曲库/学歌/直播三触点 | ✅ `42fc392` | core/data/tabs.py；TabsPanel 共享组件；直播 T 键看谱；42/42 测试 |
| **S3.5 身份升级** | Song v5 + Event v2 + tabs/queue/Preset 使用 song_id | 🟡 Song v5 ✅；其余待完成 | 改名不破坏附件、队列、历史和统计；旧数据可回退 |
| **S4 学歌打卡** | /api/practice/log + 卡片打卡 + 练习时间线 | ⬜ 等待 S3.5 | 打卡 → 时间线可见；离线补报不重复；学会周期正确 |
| **S5 统计视图** | /api/stats/* 三端点 + 第五导航视图 | ⬜ 待开发 | 口径与第 8 节一致；截图回归 |

**S4 开工提示**（下一任 agent 直接可用）：
- 先确认 S3.5 已通过，不再向长期事件写入纯 title 关联；
- `/api/events/report` 已预留 `practice_logged` 类型（S2 时开放），后端只需加专用端点或直接复用 report；
- `Song.learned_at` 已在「标记学会」时回填（S1），学习周期 = learned_at − added_at；
- 打卡 UI 落在 `ui/src/views/LearningView.tsx` 卡片（参照 S3「谱 n」按钮的展开面板模式）；
- 事件 meta 建议：`{note, minutes?, self_rating?}`（第 4 节）。

**S5 开工提示**：
- 聚合主键必须是 song_id，改名不得拆榜；
- 统计全部从 `core/data/events.py` 的 `iter_events()` 现算，**只算不存**（第 10 节纪律）；
- 导航第五视图直接按 `redesign-v2.html` 的 token 新写（surface 阶梯/语义色/◆◆◇/三档按钮）；
- 排行榜口径：点歌 TOP10 = `song_sung` 按 `song_id` 计数，使用最新歌名或 `title_snapshot` 展示（全时段/近 30 天两档）。

**已完成阶段排序回顾**：S1 解锁更新记录且让之后所有功能"白拿"历史数据；S2 尽早沉淀直播数据；S3 高频刚需但工程量最大放中间；S5 是全部数据的兑现，收尾。

## 10. 工程纪律（沿用项目既有约定）

- **统计只算不存**：每次请求从 events 现算，不引入缓存失效问题；
- 迁移 v4 走 `MIGRATIONS` 链 + 单元测试（现有 27 项基础上加）；
- 每阶段跑：`npx tsc --noEmit` + `make test-unit` + `make test-golden`（16/16 diff=0 不许破）+ 截图验证；
- 铁律不变：`core/` 不 import UI/服务器框架；UI 经 `engine.render_page()` 拿图；events.py 属 core/data，被 server 调用；
- events.jsonl 纳入 data/backups 备份节奏（追加式文件，备份即复制）。

## 11. 风险与开放问题

| 风险 | 应对 |
|---|---|
| events.jsonl 长期增长 | 个人量级无需处理；破万行时按撤退路线迁 SQLite |
| QuickView 双写一致性 | localStorage 为现场真相，后端事件为分析用，允许短暂不一致 |
| 曲谱版权文件混进 git | data/tabs/ 加 .gitignore（与 data/songs.json 现有策略核对后统一） |
| 统计视图与 v2 设计稿落地并行冲突 | 统计视图直接按 v2 token 新写，不碰旧视图改造分支 |
