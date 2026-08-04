# 主播工作台 / streamer-workbench

面向音乐主播的内容与直播运营工作台。日常面管歌曲与学歌，创作面做海报与预设，直播面支持速查与点歌。**先可用、后惊艳**，前期保证拓展性。

> **进度快照（2026-08-04 下午）**：R0–R8 + R4 Runtime v1 + R9 吉他手特化首批 + M9.6b 5 秒撤销 toast + M0 蓝图 v0.1 首批 + M1 本地最小可用首批 + M2.1 加密备份 AES-256 真加密 + L1 体验打磨全 7 子项 + M2.5 综合洞察 + M2.6 错误全局 toast 化两批 + L2.1 批量操作第一批 + L2.2 批量导出 + L2.3 曲库导入导出 + M2.3 自动快照 + M2.7 在线元数据层骨架 + M2.8 NeteaseProvider 第一实现 + **M2.9 LibraryView 在线补全 UI**（SongEditDialog「在线补全」按钮 + MetadataSearchDialog 子对话框 + 离线降级 + 21 vitest）全部收口。待推：R8.2.x 弹唱录屏 / M2.2 WebDAV 同步 / M2.4 点歌条件 / M2.10 QQProvider 多源回退 / M2.11 网易云/QQ 歌单导入 / M3 SQLite FTS5 / M4 Tauri 2 + PWA / R4 Runtime v2 / R7 桌面正式发布门。
>
> **测试基线**：Python 759 passed / 1 skipped（56 个测试文件）+ vitest 340/340（31 个测试文件）+ node:test 16/16 + 5 套金标准 35/35（grid-wrap 16 + magazine-flow 5 + live-set 5 + learning-report 5 + fullscreen-flow 4）；TSC 干净。
>
> **已上线能力**：
> - **R1a 海报闭环** — PosterDocument 领域 + 仓储 + 服务 + HTTP `/api/posters*` + 样例曲库 + 能力声明 + RenderDocument；`usePosterStore` 状态机 + 自动保存 + 撤销重做（Cmd+Z）+ Bridge；最近海报 3 动作内可导出。
> - **R1b magazine-flow** — 刊头 + 双/三栏 + `pages=auto`；6 种分类轴 (chars/artist/genre/language/initial/status)；`/api/layouts/magazine-flow/analyze` 返回容量/页数/溢出。
> - **R2 直播闭环** — LiveSession/SongRequest/QueueEntry/PerformanceRecord/RequestPolicy/EntitlementGrant；EntitlementService 幂等核销；RequestPolicyService 决策；LiveService 状态机；LiveRepository CAS/原子写/恢复；HTTP `/api/live-sessions*` 7 端点。
> - **R2.5 live-set 复盘海报** — `LiveSessionSnapshot` 数据通道；5 PNG 金标准；工作台左栏"专用海报"区 + LiveView 双入口。
> - **R3 学歌闭环** — S4 打卡（note/minutes/self_rating）+ 学会周期 + 乐理辅助（Key/Capo/原调/和声进行/结构/音域/移调）+ 智能推荐。
> - **R3.5 learning-report 学歌海报** — `LearningReportSnapshot` 数据通道；5 PNG 金标准；7d/30d/90d 预设 + 自定义窗口。
> - **R4 数据统计** — 4 端点（overview/feed/top-songs/distribution） + 5 tab UI；Top 歌曲 → 创建海报 + 时间线 → 创建 Preset。
> - **R5 工作台系统化** — focus-visible + stagger fade + aria + 响应式 + 撤销重做。
> - **R4.0 Phase 1+2 收口** — 4 套 layout 公共 helper 抽离（`core/layouts/_common.py`，8 个）；App.tsx god 拆解（686 → 572 行，`useWorkspaceState` 接管工作台状态机）；专用海报区把 4 套 layout 入口同视图可达；海报真保存路径（Electron 原生 dialog / 浏览器 `<a download>`，3 路径统一）；暗色 hardcode 收口（实际为空集，已确认）。
> - **R4.1 视觉与体验统一** — 4 个统一组件（`EmptyState` / `Spinner` / `StatusBadge` / `ErrorBanner`）；`CommandPalette` Cmd+K 跨 5 视图命令面板；`lib/narrow.ts` 公共 narrow helper 取代散落的 `asXxx` 函数；`localStorage` key 改 `sw-workspace`（兼容读 `gp-workspace`）。
> - **R4.2 数据反哺创作补全** — StatsView Top tab「据此创建海报」/Feed tab「据此创建 Preset」；导出历史：live.py / learning_report.py 完成后写 `type=poster_exported` 事件，3 种 kind（`grid-export` / `live-poster` / `learning-report`）走同一 `GET /api/exports/recent`；`ExportLogPanel` 嵌入 4 处（SpecialPostersPanel / ExportDialog / LiveView SessionDetail / StatsView），含 30 秒静默轮询 + kind 过滤 + 相对时间。
> - **R4 Runtime v1 抽象** — `DataChannel` Literal 枚举（`song_library` / `live_session` / `learning_report`）；4 套 layout 显式声明 `supported_channels`，engine 不再 duck-typing；`get_layout(id, channel=...)` / `list_layouts(channel=...)` 按 channel 过滤；30 项测试 + 31/31 金标准复跑。**v2 待做**：统一 `LayoutPlan` / `Palette-Skin` 接线 / Path 排文。
> - **R8 弹唱播放器 R8.0 + R8.1 + R8.2 联动** — R8.0：Song 增量 5 字段（`lyrics_lrc` / `lyrics_plain` / `audio_vocal_path` / `audio_instrumental_path` / `audio_duration_ms`）；`core/lrc.py` + `core/chordpro.py` + `core/audio.py` 3 个核心模块；`LyricsPanel` + `TabsPanel` + `PlayerBar` + `PlayView` 4 个组件；歌曲库 ▶ 弹唱按钮；LRC 时间滚动 + chordpro chord 高亮。R8.1：5 个音频端点（POST 上传 / GET 列出 / DELETE 删除 / GET 元信息 / GET 流式 `/file`）+ HTML5 `<audio>` 接入 PlayView + vocal/instrumental 切轨（仅当两轨都有时显示）+ `POST /api/playback/events` 上报 `playback_started/paused/completed`。R8.2 联动：LiveView 队列项行尾 ▶ 弹唱按钮 → 调 `onPlaySong(songId, { sessionId, requestId, requesterName })` → App.tsx 进 PlayView 联动模式；顶栏显示「联播 · {name}」标签 + 「已唱 ✓」按钮；`audio.ended` 或按钮 → 自动 `POST /api/live-sessions/{sid}/record (result=sung)` + 切回 live 视图。
> - **R9 吉他手特化首批** — R9.1 联动「↻ 再唱一遍」按钮（重置 audio + recordSubmittedRef，可再次 mark sung）。R9.2 chord/歌词远观模式 toggle 1x/1.3x/1.6x（弹唱时屏幕 1-2m 远，inline style 字号 + toFixed(3) 避浮点精度）。R9.3 顶栏大字 Capo 标识「Capo X / 实际 Key: Y」（C + Capo 2 = D 等半音循环，含小调 m 保留 + Db/Eb/Gb/Ab/Bb 降号）+ 升降 Capo 大按钮 + 快捷键 ↑↓（INPUT/TEXTAREA 聚焦时跳过）。R9.4 个人 Capo 库：Song 增量 `capo_options: list[int]` + `capo_default: int`（v6→v7 迁移 + CURRENT_VERSION 5→7）；顶栏「+ 习惯」按钮 → PATCH `/api/songs/{id}` 把当前 Capo 加入 options + 设 default。R9.5 「今晚歌单」工作台首屏左栏卡片：拉活跃 LiveSession 队列 Top 5（排除 sung/skipped 等）+ 每项 ▶ 弹唱按钮触发 R8.2 联动 + 「完整队列 →」按钮。R9.6a 软删除垃圾桶：Song 增量 `deleted_at: str`（v7→v8 迁移 + CURRENT_VERSION 7→8）；`cleanup_expired(days=30)` 自动真删过期；`GET /api/songs/list?include_deleted=False` 默认排除；`GET /api/songs/trash` 列出；`DELETE /api/songs/{id}` 默认软删除 + `?permanent=true` 真删；`POST /api/songs/{id}/restore` 恢复；LibraryView 加「垃圾桶」tab + TrashView 列表/恢复/永久删除（window.confirm 二次确认）。**M9.6b 全局 toast 系统 + 5 秒撤销**：ToastProvider + useToast hook（`ui/src/components/Toast.tsx`），13 项 vitest 覆盖 show/dismiss/clear/action 变体/倒计时/抛错不卡死；App 顶层 Provider 包裹；LibraryView 删除接入 → 显示「已删除《X》」+ 撤销按钮（5s 倒计时）→ 点撤销调 `POST /api/songs/{id}/restore` + 「已恢复」toast。
> - **M0 蓝图 v0.1 首批** — 178 首曲库已在 data/songs.json（蓝图 §3.5 真实样本：一字 2 / 二字 36 / 三字 41 / 四字 41 / 五字 22 / 六字 14 / 长歌名 19）。`fullscreen-flow` 第 5 套版式（1080×2400 全屏 9:20 + 全避让 + 2 页字数目录；强制 9:20 画布）+ 金标准 4 张（卡通音符 + 海洋柔光 × 2 页）。月夜星河第 8 套主题（深蓝紫黑渐变 + 散布星点 + 暖白月光 + 6 颗带十字光芒的亮星 + 暖琥珀当前行；PIL 程序生成无外部素材）。加密备份包 MVP：`.songworkbench` 格式 + `manifest.json` + `manifest.hmac` 签名 + 4 子命令 `export/import/verify/list` + 错密码 / 篡改 / 缺 HMAC 全部拒绝；M2.1 已接 pyzipper WZ_AES 256 真加密解决 MVP 警告。
> - **M2.1 加密备份 AES-256 真加密** — `tools/backup.py` 升级：密码模式用 `pyzipper.AESZipFile` WZ_AES nbits=256 替代 M0.4 stdlib ZipCrypto；错密码在 AES 层真拒绝（不解密就拿不到 manifest/HMAC，比 HMAC 拒绝更强）；向后兼容 M0.4 v1 备份（schema_version 升级到 2）；无密码导出仍走 stdlib zipfile。`requirements.txt` 加 `pyzipper==0.4.0`。7 项新 vitest 覆盖 round-trip / 错密码 / 不传密码 / stdlib 拒绝 / 无密码兼容 / v1 兼容。
> - **L1 体验打磨首批** — L1.1 Toast 增强（`kind` 字段 info/success/warning/error + 左侧色条 + 头部 icon + 便捷方法 `toast.error/success/warning`；error 默认不自动消失，role=alert），8 项新 vitest。L1.2 全局快捷键面板（`ui/src/components/ShortcutsPanel.tsx`，`?` 键打开，5 组：全局/视图/工作台/歌曲库/弹唱，单源真值 `SHORTCUTS` 常量），9 项新 vitest + App 集成 1 项。L1.3 首次启动 Onboarding（3 步引导 modal，localStorage `sw-onboarded` v1 控制；markOnboarded/resetOnboarded/isOnboarded 辅助函数），12 项新 vitest。L1.4 草稿保护（通用 ConfirmDialog 组件 + SongEditDialog 集成：useRef 锁定 initial form，JSON 对比 dirty；关闭 Esc/取消/X/backdrop 有改动弹「放弃未保存的改动？」destructive 确认），11 项新 vitest。L1.5 离线检测（`ui/src/components/OnlineStatusBadge.tsx` 顶栏在线绿点 / 离线红点 animate-pulse；App 监听 online/offline 事件 + 状态变化 toast；Cmd+E 离线阻止导出 + CommandPalette act-export 加 disabledReason），7 + 2 = 9 项新 vitest。L1.6 状态栏（`ui/src/components/StatusBar.tsx` 底部 5 分块：当前视图 / 操作状态 / 渲染耗时 / 上次保存时间 / 错误重试），13 项新 vitest。L1.7 帮助中心（`ui/src/components/HelpCenter.tsx`，Cmd+Shift+? 打开，5 入口卡片：快捷键面板 / 重看引导 / 命令面板 / 项目主页 / 加密备份），10 项新 vitest。CommandPalette 加 3 条帮助命令（查看快捷键 / 重看引导 / 帮助中心）。
> - **M2.5 综合洞察** — 后端 `StatsService.insights()` 聚合 `queue_added`（top_requested 点歌热度 Top N + 最近点歌时间）+ `performance_sung`（recently_sung 最近演唱 Top N + 演唱次数）；`GET /api/stats/insights?request_limit=N&sung_limit=N` 端点；6 项新 vitest 覆盖空数据/单条/排序/limit clamp/时间字段兼容。`StatsView` 加「洞察」tab（`InsightsPanel` 组件 2 卡片：点歌热度 Top 10 + 最近演唱 Top 10），2 项新 vitest。M2.5 反哺 M1 找歌：`searchSongs` 新增 `eventsHeat?: Map<string, number>` option，`heatBonus` 工具（log2 压缩加成，count=1→+5, 5→+13, 100→+33, 上限 50）；纯函数 `buildEventsHeat` 抽离便于测试；App 拉 `/api/events?type=queue_added&limit=200` → `buildEventsHeat` → 透传 searchSongs；+10 项 vitest。
> - **M2.6 错误全局 toast 化** — 新增 `useApiError` hook（`ui/src/async/useApiError.ts`）：`runWithToast(fn, label)` 自动 try/catch + 失败 `toast.error("${label}：${message}")` + 抛 `RequestFailure`（让上层 catch 仍可 `setError` → ErrorBanner）；AbortError 不弹 toast；无 ToastProvider 时 no-op（QuickView 独立窗口等场景）。`ToastContext` 导出便于 useContext 拿取；6 项新 vitest 覆盖成功/失败/无 label/Abort/RequestFailure 抛出/无 Provider。两批接入共 8 组件 21 处 catch：第一批 LibraryView 3（seedSample/toggleStatus/deleteSong+restore）/ LiveView 6（loadDetail/handleCreate/handleClose/handleManualQueue/handleRecord/handleExportPoster）/ StatsView 4（Overview/Feed/Top/Distribution + Preset/海报创建）；第二批 SettingsView 2（load/save）/ LearningView 1（learn 单曲；doImport 批量保留行级 error 避免 toast 噪声）/ TonightSetCard 1（sessions；detail/歌曲名静默）/ TrashView 3（refresh/restore/purge）/ PracticeLogDialog 1（打卡）。
> - **L2.1 批量操作第一批** — LibraryView 多选 + 批量删除/改状态：state `selectMode / selectedTitles / batchPending`；工具栏「选择」/「退出选择」toggle 按钮（绿/灰主题态）；select 模式下卡片显示 checkbox（已选用 SVG ✓ 填充）+ emerald 高亮 + 点击行为从「展开」改为「toggle 选中」；底部 action bar 显示「已选 N 首」+ 全选当前筛选/清空 + 3 动作（标记已会 / 标记未会 / 批量删除）+ 取消（退 select 模式）；`handleBatchDelete` 循环 `/api/songs/delete` + 聚合 toast（单条走 M9.6b 5s 撤销 + restore 端点；多条弹「已删除 N 首」+ 失败附注）；`handleBatchStatus` 循环 `/api/songs/status` + 「已标记 N 首为已会/未会」+ 失败附注；复用 M2.6 `useApiError` 自动 toast 单条失败。11 项新 vitest。
> - **L2.2 批量导出** — 后端 `POST /api/export/by-ids` 端点，body `{ theme, song_ids, layout, canvas, avoid }`，循环每首选中歌曲：构造临时 `StoredSnapshot(SongLibrary(songs=[one_song]))` + `build_render_document(page=1)` + 渲染 PNG + 写盘到 `settings.output_dir`；文件名 `<theme_prefix>-<layout_id>-<tag>-<title_slug>-<song_id>.png`（slug 32 字限制）；不存在的 song_id 静默跳过；draft 不在按 ID 导出范围（只导 active）；`ExportByIdsResult { total, files, total_ms }`；LibraryView 加「批量导出」按钮复用工作台 `usePosterStore.current` 的 layout/theme/canvas + `runWithToast` + `exportBySongIds` 客户端；成功 toast「已导出 N 张海报到输出目录」（部分跳过附「（跳过 M 首）」）；失败自动 `toast.error`（via M2.6 `useApiError`）。6 项 Python 端到端 + 4 项 vitest。
> - **L2.3 曲库导入导出** — 后端 `GET /api/songs/export` 返回完整曲库 JSON（schema_version + version + songs + exported_at，含 active + draft + 软删）；`POST /api/songs/import` body `{ mode: "merge" | "replace", songs: [...] }`，merge 跳过 title 重复返回 `{ added, skipped, errors, active, draft }`，replace 用 `purge_by_id` 真删所有现有再 add；LibraryView 加「导入」+「导出」按钮：导出 fetch → blob → a.download (`streamer-workbench-library-{date}.json`)；导入 file input change → FileReader → parse JSON → POST import (merge)，错误路径（非法 JSON/缺 songs）走 M2.6 `useApiError` 自动 error toast。9 项 Python 端到端 + 4 项 vitest。
> - **M2.3 自动快照** — 底层 `AtomicJsonWriter` 每次 `save` 自动备份旧 bytes 到 `backups/songs/songs-<ts>-<uuid>.json`（保留最近 20 个，settings.backup_count 待联动）；上层：后端 `GET /api/songs/snapshots` 列出（filename + size_bytes + modified_at 倒序）+ `POST /api/songs/snapshots/restore` 覆盖 songs.json；LibraryView 新增「快照」tab + `SnapshotsView` 组件（空状态提示 + 列表 + 「恢复」按钮 + confirm 二次确认 + 恢复后自动 refresh 曲库）。5 项 Python 端到端。
> - **M2.7 在线元数据层骨架** — 新增 `core/metadata/` 模块（types/errors/protocols/http_client/cache/router 六文件）：Provider 协议（`typing.Protocol`，duck typing 友好）+ Router 多源回退（首选命中即返回；缓存命中跳过；preferred_provider 临时调整）+ HttpClient（stdlib `urllib.request` + User-Agent + 超时 + 5xx 指数退避 + 429 `MetadataRateLimited` + 同 provider 速率限制 ≥200ms）+ Cache（envelope `{fetched_at, payload}` + 原子写 + key sanitize 防路径穿越 + TTL 30 天）+ 三类错误（`MetadataNotFound` / `MetadataUnavailable` / `MetadataRateLimited`）；**零新增依赖**（用 stdlib，不用 requests/httpx）；`core/` 铁律保持。借鉴 UnblockNeteaseMusic 多 provider 路由 + api-enhanced/QQMusicApi API 表面广度；UI/库实现推迟到 M2.8+。61 项新测试（协议 duck typing / types frozen / errors 构造 / http_client 4xx-5xx-429-retry-throttle / cache miss-put-TTL-force-sanitize-clear-atomic / router first/fallthrough/all-fail/cache-hit/force-refresh/preferred/attach-cache/empty-keyword/limit-clamp/lyric-None-sentinel）。
> - **M2.8 NeteaseProvider 第一实现** — `core/metadata/providers/netease.py` 实现网易云 8 套公开 API（`/api/search/get` + `/api/song/detail` + `/api/song/lyric` + `/api/v1/artist/{id}` + `/api/v1/album/{id}` + `/api/v6/playlist/detail` + `/api/toplist` + `/api/v1/discovery/simiSong`），全部基于 M2.7 HttpClient 复用其 UA/重试/限流能力；业务码 `!= 200` 视作 `MetadataUnavailable`；缺字段容错；零凭证（不需要登录态）。`server/services/metadata.py` 包装 `MetadataApplicationService`；`server/routers/metadata.py` 暴露 9 个端点（`GET /api/metadata/providers` + `POST /api/metadata/search|song|lyric|artist|album|playlist|charts|similar`），错误分 404 not_found / 429 rate_limited（带 Retry-After）/ 503 unavailable（带 errors 明细）/ 422 validation。`server/app.py` lifespan 装配 `build_default_router([NeteaseProvider()])`；`AppContext.metadata_router` + `AppPaths.metadata_dir`。45 provider 单元测试（mock HttpClient 喂样本，覆盖正常/边界/业务码/URL/字段映射）+ 24 API 端到端（mock router 验 9 端点 + 真 router 验 cache hit 链路）= 69 新测试。
> - **M2.9 LibraryView 在线补全 UI** — 新增 `ui/src/components/MetadataSearchDialog.tsx`（打开自动 search / 列表展示时长 / 点击 hit 调 song API / onPick 回调；错误 toast + 行内双通道）；修改 `SongEditDialog.tsx` 歌名 input 旁加「在线补全」按钮（三态 disabled：离线 / 保存中 / title 为空；hover title 提示原因），点击打开搜索对话框；选中后填回 `title` + `artists`（`'A / B'` → `'A，B'`） + 在 `notes` 追加 `[meta:netease song_id=999 2026-08-04]` 行（已有 notes 换行追加不覆盖）。`getOnlineState()` 监听 online/offline 事件实时同步按钮状态（L1.5 联动）。13 项 MetadataSearchDialog 测试（auto-search / 列表 / 时长格式 / 点击 pick / 错误双通道 / 刷新 / 关闭 / 离线）+ 8 项 SongEditDialog 在线补全测试（按钮三态 / 选中填回 / 多歌手 / 已有 notes 追加）= 21 新 vitest。`vitest 48 files / 548 tests passed`（527 → 548）。
> - **M1 本地最小可用首批** — M1.1 全局找歌 8 字段加权排序（title 完全匹配 100 / 前缀 80 / artists 60 / pinyin 50 / lyrics 40 / tags 30 / key 20 / 兜底 10），13 项 vitest。M1.2 CommandPalette 加 `songResults` slot（虚拟 Command 与命令并列），5 项 vitest。M1.3 PlayerContext 顶层 Provider（`PlayerProvider` + `usePlayer` hook + 3 模式 `live / practice / browse` + state `currentSongId / mode / isPlaying / currentTimeMs`），8 项 vitest；App 拆 `App` + `AppInner`，handlePlaySong 接受可选 `mode` 覆盖。M1.4 MiniPlayer 全局底栏（`ui/src/components/MiniPlayer.tsx`：模式徽章 + 歌名 + mm:ss 进度 + 「打开弹唱 →」/ ✕ 两按钮），9 项 vitest；非 play 视图 + 无模态时常驻。M1.5 LibraryView 展开面板加「试听」按钮（与小 ▶ 图标互补），6 项 vitest。M1.6a LRC 同步验证（audio.timeupdate → LyricsPanel.findActiveLine 链路已在 R8.1 走通，补 3 项 PlayView 测试），3 项 vitest。M1.6b 吉他谱锚点（TabsPanel 接受 `lyricsActiveIndex` prop，优先用 LRC 索引，LyricsPanel 与 TabsPanel 共用 activeIndex → chord 高亮真正跟歌词同步），TabsPanel 5 项 + PlayView 3 项 = 8 项 vitest。M1.7 渐进式海报（`useWorkspaceState` 导出 `nextPreviewSrc / prevPreviewSrc`，App 挂两个 hidden `<img>` 触发浏览器预取 → 翻页 0ms 切换），hook 5 项 + App 1 项 = 6 项 vitest。
> - **R2.5+Electron** — 桌面壳（macOS arm64）+ PyInstaller 后端单文件 + electron-builder 打包 + 置顶速查窗 (Cmd/Ctrl+Shift+U)。
>
> **下一步**：R8.2.x 弹唱录屏；M2.2 WebDAV 同步（凭证加密 + 拉/推/列表 + 自动同步策略）；M2.4 点歌条件；M2.10 QQProvider 多源回退（基于 UnblockNeteaseMusic 架构，再加一个 provider 即可自动容错）；M2.11 网易云/QQ 歌单导入（输入公开歌单 ID → 预览 → 入库）；M3 SQLite FTS5 全文检索 + 学习看板 + 精力分级；M4 Tauri 2 桌面壳 + PWA；R4 Runtime v2；R7 桌面正式发布门。
>
> 文档入口见 [`AGENTS.md`](AGENTS.md)、[`HANDOFF.md`](HANDOFF.md) 与 [`design/产品优化方案终版-0727/README.md`](design/产品优化方案终版-0727/README.md)。
>
> **单仓库说明（2026-07-27 合并）**：原 `playlist-poster-design` 设计仓库已并入本仓库 `.archive/design-docs/`（原 `design-docs/`，点号开头表示已归档；完整历史保留，GitHub 旧仓库已归档只读）。金标准预言机位于 `.archive/design-docs/歌单-排版一/`，随仓库检出，无需软链。

## 技术栈
- **渲染引擎**：Python + PIL（纯函数，金标准：与现有成品逐像素一致，当前 16/16 diff=0）
- **后端**：FastAPI 本地服务（`server/`，开发期 uvicorn 8765 端口）；Electron 桌面壳（`electron/`，dev 模式不打包）spawn Python 作 child_process，引擎不重写
- **前端**：React 19 + Vite 6 + Tailwind 4 + shadcn/ui（`ui/`）；组件优先使用 shadcn/ui（`ui/src/components/ui/`），shadcn 不满足需求再自写组件；开发期另有 `web/index.html` 原生验证页
- **视觉系统**：`design/design-tokens.json` v3 是当前单源真值；React 工作台支持画廊白/暗色舞台与独立可选应用主色，应用主色不影响海报 Theme/Palette；`.archive/design-docs/歌单海报生成器-界面设计/` 仅作历史参考
- **铁律**：`core/` 禁止 import 任何 UI/服务器框架；React 只通过 FastAPI 访问核心业务和渲染能力
- ~~PySide6 (Qt)~~：已移除（2026-07-23 晚决策，理由见设计结论）

## 目录
```
core/        领域数据与纯渲染核心（禁止依赖 UI/服务框架）
server/      FastAPI 本地服务（AppContext + Repository adapters + services + routers）
electron/    Electron 桌面壳（dev 模式；不打包）— 主窗口 + 置顶速查子窗口
web/         原生验证页（开发期）
ui/          React + Vite 前端工作台
design/      活跃规格、数据路线图、设计令牌；design/archive/ 为已退役文档
.archive/    原设计仓库不可变历史；除金标准预言机外不作为当前规格
tools/       迁移、样例渲染与 benchmark 脚本
```

## 开发期运行

### 浏览器模式（手动启前后端）
```bash
# 后端（项目根目录）
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m server --port 8765

# 前端（React 工作台）
cd ui && npm install && npm run dev                  # http://localhost:5174 (strictPort)，/api 已代理到 8765
```

### Electron 桌面壳（dev 模式）
```bash
# 1) 首次安装 Electron 依赖
cd electron && npm install

# 2) 启动桌面壳 — 会自动探测并 spawn 8765 (Python) / 5174 (Vite)
npm start
```
Electron 启动行为：
- 若 8765 / 5174 已被外部占用 → 复用，不重复启动
- 若空闲 → spawn 子进程；quit 时 kill（无孤儿）
- 启动后子进程异常退出 → 弹错并退出 Electron
- 菜单「窗口 → 打开置顶速查」或 `Cmd/Ctrl+Shift+U` → 打开 alwaysOnTop + screen-saver 层级子窗口
- 环境变量（可选）：
  - `STREAMER_REPO_ROOT` 自定义仓库根
  - `STREAMER_VENV_PYTHON` 自定义 venv python
  - `STREAMER_VITE_BIN` 自定义 vite 可执行
  - `STREAMER_VITE_PORT` (默认 5174) / `STREAMER_PY_PORT` (默认 8765)
  - `STREAMER_NO_SPAWN=1` 强制不 spawn（用户自行起 8765/5174）

后端配置只接受 `127.0.0.1`、`::1` 或 `localhost` 等 loopback 地址。开发模式默认仅放行
`http://localhost:5173` 与 `http://127.0.0.1:5173`；如 Vite 使用其他本机端口，可通过
`STREAMER_WORKBENCH_ALLOWED_ORIGINS` 提供逗号分隔的明确 Origin。桌面模式必须设置每次启动
随机生成的 `STREAMER_WORKBENCH_SESSION_TOKEN`，写请求通过 `X-Streamer-Session` 传递；
令牌不得持久化或写入日志。

`web/index.html` 是旧版诊断页，不再作为默认运行入口。如需追溯验证，可在固定本机端口启动，
并把该端口的完整 Origin 显式加入 `STREAMER_WORKBENCH_ALLOWED_ORIGINS` 后重启后端。

## 金标准测试
```bash
# 统一入口（推荐）：自动注入 PYTHONUTF8/PYTHONPATH，Windows 控制台无需手工设环境变量
python tools/run_tests.py                        # 全部 13 个测试文件
python tools/run_tests.py test_golden test_unit  # 只跑指定文件
# 单跑金标准：目标 16/16 逐像素 diff=0（tests/golden/ 随 git 提交；独立预言机在
# `.archive/design-docs/歌单-排版一/`，重建方式见 tools/regenerate_golden.py）
PYTHONPATH=. python tests/test_golden.py
```

Windows PowerShell：

```powershell
& '.venv\Scripts\python.exe' tools\run_tests.py   # 统一入口，已内化 UTF-8
cd ui; npx tsc --noEmit
```

当前 CI 质量基线为 Python 测试 202 项（13 个测试文件）、前端测试 22 项（含 6 项 React 交互测试）、金标准 16/16 diff=0，并检查 OpenAPI TypeScript 类型漂移、`tsc --noEmit` 与前端 build。前端已接入画廊白/暗色舞台、跟随系统及 8 种应用主色；这些应用令牌不影响海报 Palette。

## 后端 API

当前路由按能力拆在 `server/routers/`：

- 健康与资源：`GET /api/health`、`/api/themes`、`/api/layouts`、`/api/layouts/{id}/params`；
- 歌曲与曲谱：`/api/songs*`、`/api/songs/{identity}/tabs`（`song_id` 优先，title 仅为迁移期兼容）；
- 渲染与导出：`GET /api/render`、`POST /api/export`、`POST /api/export/batch`；
- 事件、设置、预设：`/api/events*`、`/api/settings`、`/api/presets*`；预设支持复制、软删除与 `POST /api/presets/{id}/default` 默认切换。
- 直播：`/api/live-sessions*`（7 端点）+ `POST /api/live-sessions/{id}/poster`（R2.5 live-set 复盘海报，事件驱动数据通道，绕开曲库）。
- 学歌发现 & 数据统计：`/api/discovery/{recent-learned,request-hot,recommend}`、`/api/stats/{overview,feed,top-songs,distribution}`。
- 学歌报告：`POST /api/learning-report/poster` + `GET /api/learning-report/analyze`（R3.5 learning-report 海报，事件聚合数据通道）。

目标 API 契约和迁移阶段见主规格 §10.3 与路线图 R0；README 不重复维护完整参数表。

## git 工作流
- 每次 feature / bug fix 走分支（feature/xxx、fix/xxx），原子提交，信息有意义。
- 可先纯本地提交，**不强制推远程**。

## 文档状态

- 当前目标：`design/产品优化方案终版-0727/产品优化方案终版.md`；2026-07-29 详细增量规格：`design/产品优化方案终版-0727/产品与技术规格-v3.md`；
- 当前顺序：`design/产品优化方案终版-0727/路线图.md`；
- 数据口径：`design/roadmap-data-stats.md`；
- 架构决策：`ADR-001.md`–`ADR-008.md`；
- `design/archive/` 和 `.archive/` 中的文档均已退役，不得作为当前执行依据。
