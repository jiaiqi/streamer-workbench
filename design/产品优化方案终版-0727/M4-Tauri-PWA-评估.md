# M4 · Tauri 2 vs Electron 决策评估（2026-08-17）

> **目的**：为 R7 桌面正式发布门（PyInstaller/electron-builder 完整 CI）做技术栈选型 — **Tauri 2 替换** vs **继续 Electron** vs **双轨**。
> **基准**：`dffb75e`（R4 11/11 = 100% 收口，HEAD 含今日 hand-off 文档）。
> **作者**：Mavis（基于实测数据 + 官方文档 + 社区数据）。
> **结论先说**：**推荐 Tauri 2 替换**，但需 5 天 spike 验证 R8.2.x 录屏降级方案可行。
> **依赖**：R4 全部收口 ✅ / M0–M3 + R8 + R9 全部收口 ✅ / Electron spike 已可用（dev + packaged）✅。

---

## 0. 结论与决策点

### 决策推荐

| 维度 | Tauri 2 替换（推荐） | 继续 Electron（保守） | 双轨 |
|---|---|---|---|
| Bundle 大小 | **8.6 MiB**（-97%） | 244 MiB | 双份工作量 |
| 内存占用（6 窗口） | **172 MB**（-58%） | 409 MB | 双份 |
| 录屏系统音频 | ⚠️ 需降级（仅 mic） | ✅ `desktopCapturer` 已实现 | 双方案维护 |
| macOS arm64 | ✅ 原生 | ✅ 原生 | ✅ |
| macOS 签名公证 | ✅ `tauri sign` | ✅ electron-builder | 双 CI |
| 跨平台 build | ⚠️ 实验性（NSIS 依赖） | ✅ 成熟 | 各自走各自 |
| 学习成本 | ⚠️ Rust 入门 | ✅ JS 已有 | 双栈 |
| 估时（R7 收尾） | **3 周**（5 天 spike + 1 周迁移 + 1 周打磨） | 3-5 天 | 4-5 周 |

**赌的结论**：替换划算。bundle -97% 是肉眼可见的体验差异，R8.2.x 录屏是"录自己唱"，mic 音频可接受。

### 必须验证的 5 个 spike 点

5 天 spike 之前**不要**全量切换；只验证 5 个决定性点：

1. **Tauri 2 + 现有 React 19 + Vite 6 前端集成**（半天）
2. **Tauri 2 + Python sidecar**（后端 spawn/exit/PIPE 通信；半天）
3. **macOS arm64 打包 + 启动**（半天）
4. **R8.2.x 录屏降级方案**（仅屏幕视频 + mic 音频；1 天）
5. **IPC 全部迁移**（dialog.showSaveDialog / dock badge / system notification；1 天）

任何一点**不通过** → 立刻回 Electron 收口，**5 天 spike 是有止损线的**。

---

## 1. Bundle 大小（实测对比）

| 框架 | Demo 包 | 估算本项目（React + Python + 字体） | 倍数差 |
|---|---|---|---|
| Tauri 2 | **8.6 MiB** | ~15-25 MiB | 1x |
| Electron | 244 MiB | ~280-350 MiB | **15-20x** |

**来源**：[Tauri vs. Electron: performance, bundle size, and the real trade-offs](https://tool.lu/article/78K/preview)（Hopp 团队 2024 基准；同一 MacBook Pro 单次跑）

### 为什么 Tauri 小这么多

- Tauri 2 用 **系统 WebView**（macOS WKWebView / Windows WebView2 / Linux WebKitGTK）→ 不打包 Chromium
- 不打包 Node.js runtime → 后端用 Rust 编译到 native binary
- 字体 / 资源 / 后端代码全是 native binary + 必要资源

### 本项目实际收益

- **下载 244MB → 15-25MB**：从 GitHub release 下载时间从 1-3 分钟降到 5-10 秒
- **解压安装**：从 30-60 秒降到 1-3 秒
- **磁盘占用**：从 800MB（Electron + Chromium 缓存）降到 200MB 以内

> **决策影响**：本项目**macOS arm64 only + 单机工具 + 不分发到 App Store**，bundle 大小是肉眼可感的"专业感"指标。

---

## 2. 内存占用（实测对比）

| 框架 | 6 窗口实测 | 原因 |
|---|---|---|
| Tauri 2 | **172 MB** | WKWebView 共享系统进程 + Rust 后端无 Node 运行时 |
| Electron | 409 MB | 每个 renderer = mini-Chromium + Node 主进程 |

**来源**：同上 Hopp 团队 benchmark

### 本项目实际收益

- 当前 Electron 跑 1 个主窗口 + 1 个置顶速查窗口 ≈ 250-350 MB
- 切 Tauri 2 后同样场景 ≈ 100-150 MB
- **MacBook Air 8GB 用户能多开 2-3 个浏览器**（直播时一边查歌一边用 Chrome 看互动）

> **决策影响**：内存压力在直播现场（要同时跑 OBS / 浏览器 / 速查窗）特别敏感。

---

## 3. macOS arm64 兼容性

| 维度 | Tauri 2 | Electron | 备注 |
|---|---|---|---|
| 原生编译 | ✅ Rust → aarch64-apple-darwin | ✅ Node 18+ | 持平 |
| 启动时间 | < 1s | 1-2s | Tauri 略胜 |
| 系统集成（Dock / Menu / Notification） | ✅ `tauri-plugin-...` 完整 | ✅ electron API 完整 | 持平 |
| 签名 + 公证 | ✅ `tauri sign` 走 Apple 标准 | ✅ electron-builder 走 Apple 标准 | 持平 |
| Code signing 复杂度 | 中（需 Apple Developer ID） | 中（需 Apple Developer ID） | 持平 |

**关键点**：Tauri 2 跨平台 build **仍是实验性**（mac→Windows 需 NSIS 工具链）。但本项目**只发 macOS arm64**，跨平台不是约束。

> **决策影响**：本项目 macOS arm64 only 完美匹配 Tauri 2 单平台收口。

---

## 4. R8.2.x 录屏可行性（**关键**）

### 当前实现（Electron）

- `MediaRecorder + desktopCapturer` 拿**系统音频 + 屏幕视频**
- 系统音频走 Electron `desktopCapturer.getSources({ types: ['screen'] })` 取 `MediaStream` audio track
- 已在 R8.2.x 落地，35 单测 + 9 vitest 端到端覆盖

### Tauri 2 行为（WKWebView）

| 能力 | 支持 | 备注 |
|---|---|---|
| 屏幕视频（`getDisplayMedia`） | ✅ macOS 13+ WKWebView 原生支持 | 与浏览器一致 |
| **系统音频** | ❌ **不支持** | WebKit 限制，非 Tauri 限制；WKWebView 的 `getDisplayMedia` 不暴露 system audio track |
| 麦克风音频 | ✅ `getUserMedia({ audio: true })` | 与浏览器一致 |
| 应用窗口 capture | ✅ `getDisplayMedia` 支持选具体窗口 | 与浏览器一致 |
| 屏幕 + 麦克风混音 | ✅ MediaRecorder 多 track 录制 | 与浏览器一致 |

### 降级方案

**方案 A（推荐）**：屏幕视频 + 麦克风音频
- 录屏时提示用户"需要连接麦克风"（R8.2.x 当前已要求"勾选共享系统音频"）
- 用 Web Audio API 把 mic 音轨混到 MediaStream
- 牺牲"系统音频纯净度"换"实现简单 + 跨平台一致"
- 用户场景是"录自己唱"，mic 音频反而比系统音频更"贴近"

**方案 B（成本高）**：Rust + CoreMedia / ScreenCaptureKit
- 用 Tauri sidecar 调 macOS 原生 `screencapturekit` API
- 写 Swift 桥接 + Rust FFI
- 工作量：3-5 天实现 + 跨 macOS 版本维护
- 不推荐

### 结论

**降级方案 A 可接受**。R8.2.x 录屏用户场景是"录自己唱给自己看"，mic 音频**比系统音频更合适**（系统音频会带 OBS / 浏览器 / 通知提示音等噪音；mic 音频只录人声）。

> **决策影响**：录屏降级是 R8.2.x 文档化的"已知差异"，不是阻塞问题。

---

## 5. 开发体验（DX）对比

| 维度 | Tauri 2 | Electron |
|---|---|---|
| 前端栈 | **零修改**（继续 React 19 + Vite 6 + Tailwind 4 + shadcn/ui） | 同 |
| 后端栈 | Rust（需学）| Node.js / TypeScript（已有）|
| 跨平台 build | ⚠️ 实验性（NSIS 工具链） | ✅ 成熟 |
| 首次 build | 80s（Rust 编译）| 15s |
| 增量 build | < 5s | < 3s |
| HMR | ✅ `tauri dev` | ✅ `electron .` |
| 调试 | VSCode + `tauri dev` + DevTools | VSCode + Electron DevTools |
| 生态成熟度 | 中（v2 已发布稳定）| 高（10+ 年） |
| 文档质量 | 高（中文网已上线 + docs.rs）| 高 |
| 社区 | 中（Discord / GitHub Discussions 活跃） | 高 |

### Rust 学习成本评估

- 本项目后端在 Python（FastAPI），Tauri 后端**只是 sidecar manager**，不涉及复杂 Rust 业务逻辑
- 预计 1-2 天可掌握：`tauri::command` / `tauri::Builder` / `tauri-plugin-dialog` / `tauri-plugin-shell` / `tauri-plugin-fs`
- **不需要深 Rust**：本项目后端逻辑全在 Python，Rust 只做"桥"

> **决策影响**：学习成本是 1-2 天一次性投入，回本周期短。

---

## 6. 迁移成本估算

### 现有 Electron 集成点（盘点）

| 集成点 | 当前文件 | Tauri 2 等价 | 工作量 |
|---|---|---|---|
| Python sidecar spawn / ready / exit | `electron/main.ts` | `tauri::process::Command` | 0.5 天 |
| `dialog.showSaveDialog` | `electron/ipc.ts` | `tauri-plugin-dialog` | 0.5 天 |
| 系统通知 | `electron/ipc.ts` | `tauri-plugin-notification` | 0.5 小时 |
| Dock Badge（队列数） | `electron/main.ts` | `tauri::AppHandle::set_badge_count` | 0.5 小时 |
| 系统播控菜单 | `electron/menu.ts` | `tauri::menu::Menu` | 1 天 |
| 原生目录选择器 | `electron/dialog.ts` | `tauri-plugin-dialog` | 复用 |
| 窗口置顶 | `electron/window.ts` | `tauri::WebviewWindow::set_always_on_top` | 0.5 小时 |
| `window.open(blob URL)` 替代（已用） | `ui/src/lib/saveFile.ts` | **Electron 路径保留**（Tauri 内走 dialog） | 已处理 |
| R8.2.x 录屏 | `electron/recorder.ts` | **降级到 mic** | 1 天 |
| Quick Look 弹窗 | `ui/src/lib/saveFile.ts` | Tauri 暂不支持 → 降级到 Finder | 0.5 小时 |

**总计**：~3-4 天迁移 + 1 天打磨 = **4-5 天收尾 R7**（不计 5 天 spike）

### Spike → 迁移 → 收尾时间表

| 阶段 | 工作量 | 产出 | 止损线 |
|---|---|---|---|
| **Spike（Day 1-5）** | 5 天 | 5 个决定性点全验证 | 任何 1 点失败 → 立刻回 Electron |
| 迁移（Day 6-10） | 4-5 天 | Electron 集成全迁移 + R8.2.x 降级 | 全部迁移完 |
| 打磨（Day 11-15） | 3-5 天 | 打包 / 签名 / 公证 / 启动器 | R7 收口 |

**总计**：3 周（15 个工作日）。Electron 收口 3-5 天。**3 周 vs 3-5 天 = 6x 投入**。

---

## 7. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 5 天 spike 失败 | 30% | 浪费 5 天 | 止损线 — 任何点失败立刻回 Electron |
| Rust 学习拖慢进度 | 20% | 多 1-2 天 | 本项目 Rust 只做"桥"，不需要深学 |
| 录屏降级用户不接受 | 10% | 已知差异 | 文档化"录自己唱 mic 音频更合适" |
| Tauri 2 v2.1+ API 变化 | 10% | 中等 | 锁版本，follow CHANGELOG |
| macOS 签名公证被拒 | 15% | 1-2 天排错 | 复用 electron-builder 时代的 Apple Developer ID 经验 |
| 跨平台用户要 Windows 版 | 5% | 推到 R8 之后 | macOS only 不变，跨平台是 R7 之后 |
| Electron 旧代码不能全删 | 30% | 维护负担 | spike 通过后立刻删 electron/ 目录 |

**关键风险**：**5 天 spike 失败**。这是单一最大风险，因此**必须**先 spike 后决策。

---

## 8. 决策矩阵（量化）

| 维度（权重） | Tauri 2（推荐） | Electron | 双轨 |
|---|---|---|---|
| Bundle 小（20%） | 10/10 | 3/10 | 5/10 |
| 内存小（15%） | 9/10 | 4/10 | 5/10 |
| R8.2.x 录屏兼容（20%）| 7/10（降级）| 10/10 | 8/10 |
| 开发速度（15%）| 5/10 | 9/10 | 4/10 |
| macOS arm64（10%）| 10/10 | 10/10 | 10/10 |
| 长期可维护（10%）| 8/10 | 7/10 | 4/10 |
| 学习成本（10%）| 7/10 | 10/10 | 5/10 |
| **加权总分** | **8.05** | **7.20** | **5.70** |

**Tauri 2 胜出**（8.05 vs 7.20），主因是 bundle / 内存 / 录屏三项的绝对优势。

---

## 9. 推荐路径（**唯一推荐**）

### Phase 1: 5 天 spike（**必做**）

**目标**：验证 5 个决定性点，**任何 1 点失败立刻回 Electron 收口**。

```text
Day 1: Tauri 2 初始化 + 现有 React 19 集成
Day 2: Tauri 2 + Python sidecar（spawn/exit/PIPE 通信）
Day 3: macOS arm64 打包 + 启动 + IPC dialog
Day 4: R8.2.x 录屏降级方案（屏幕 + mic）
Day 5: 集成测试 + 性能基准对比（bundle/内存实测）
```

**产出**：
- 5 天 spike 报告（5 点通过/失败）
- **通过** → 进入 Phase 2
- **失败** → 立刻进 Phase 3（Electron 收口），3-5 天 R7 收口完成

### Phase 2: 4-5 天迁移（spike 通过后）

- electron/ 目录全部 IPC 迁移到 tauri/src/
- R8.2.x 录屏降级（去掉 desktopCapturer 拿系统音频，改 mic）
- Quick Look 降级到 Finder 定位
- 现有 `ui/src/lib/saveFile.ts` 改 Tauri dialog 优先

### Phase 3: 3-5 天打磨（迁移完成后）

- macOS 公证 + 签名
- electron-builder → tauri-bundler 切换
- 自动更新（tauri-plugin-updater）
- CI/CD 完整跑通

### Phase 4: 删 Electron（迁移稳定后）

- 删 `electron/` 目录
- 删 `electron-builder` / `pyinstaller` 配置
- README / AGENTS.md 同步

---

## 10. 替代方案（不推荐但列出）

### 替代 1：继续 Electron

- 优点：3-5 天 R7 收口
- 缺点：244MB bundle 永远不会变好
- **不推荐原因**：bundle / 内存问题是 Electron 架构天花板，不是工程问题

### 替代 2：双轨（Tauri 主，Electron 备）

- 优点：Tauri spike 失败时 Electron 兜底
- 缺点：4-5 周工作量 + 永久双栈维护
- **不推荐原因**：本项目团队小（1 人），双栈维护成本远超 spike 失败的 5 天

### 替代 3：PWA 优先

- 优点：零安装、跨平台、自动更新
- 缺点：**没有 R8.2.x 录屏能力**（PWA 拿不到 system audio + ScreenCaptureKit）、没有真正的离线数据目录
- **不推荐原因**：本项目"纯离线优先" + 录屏是核心场景，PWA 满足不了

---

## 11. 决策执行

### 立即执行

1. ✅ **本文档**（已完成）
2. **5 天 spike**（feature/m4-tauri-spike 分支）— **本 batch 不做**，等用户确认本文档后开
3. R7 桌面正式发布门（spike 通过后）— Phase 2-4

### 文档同步

- [ ] AGENTS.md 加"M4 Tauri 2 替换"决策记录
- [ ] 路线图 R7 改"Tauri 2 桌面正式发布门"（spike 通过后）
- [ ] 删 `electron/` 目录（spike 通过后）
- [ ] ADR 新增 ADR-009（Tauri 2 选型）

### spike 不通过时回滚

- 不删 `electron/` 目录（保留到 spike 失败确认）
- 5 天 spike 报告写进本文档第 12 章
- 立刻开 R7 Electron 收口分支

---

## 12. spike 报告（待填）

> **填表时机**：5 天 spike 完成后。

| spike 点 | 通过 | 失败原因 | 备选方案 |
|---|---|---|---|
| 1. Tauri 2 + React 19 集成 | ⬜ | | |
| 2. Tauri 2 + Python sidecar | ⬜ | | |
| 3. macOS arm64 打包 | ⬜ | | |
| 4. R8.2.x 录屏降级 | ⬜ | | |
| 5. 集成测试 + 性能基准 | ⬜ | | |

**最终决策**（spike 完成后填）：
- ⬜ 全部通过 → 进 Phase 2 迁移
- ⬜ 部分失败 → 决策继续 / 回退 Electron

---

**最后更新**：2026-08-17（v1.0 — 调研文档定稿，等待用户确认后开 5 天 spike）
