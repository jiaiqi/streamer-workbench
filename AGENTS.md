# Agent 项目规则

> 此文件供 AI 编码助手（Agent）读取并遵守。每次接手时首先读取本文。

## 不可违反的铁律

1. **`.archive/` 目录是只读归档**。该目录下的任何文件（`HANDOFF.md`/设计结论/设计稿等）**不得修改、删除或移动**。它们是原设计仓库的历史快照。
2. **`core/` 禁止 import 任何 UI/服务器框架**（FastAPI / Electron / React 均不可在此出现）。
3. **金标准 16/16 diff=0 是回归死线**。禁止用新引擎自举覆盖旧基线。
4. **`Song.pinned` 不新增**。主推使用 Preset 手动集合或热度规则。

## 当前活跃规格

- **唯一执行主规格**：`design/产品优化方案终版-0727/产品优化方案终版.md`
- **唯一路线图**：`design/产品优化方案终版-0727/路线图.md`
- **数据路线图（S1–S5）**：`design/roadmap-data-stats.md`
- **架构决策记录**：`ADR-001.md`、`ADR-002.md`

## 持久格式要求

- 所有用户持久格式必须带 `schemaVersion`
- 内置只读资源与用户可写数据必须分离
- API 拆分时路径兼容优先

## 提交规范

- 原子提交，中文摘要，Conventional Commits 风格（`feat/fix/docs/refactor`）
- 触及引擎输出必须先跑 `PYTHONPATH=. python tests/test_golden.py`
- 允许纯本地提交，不强制推远程
