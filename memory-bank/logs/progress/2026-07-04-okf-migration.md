# 会话进度日志

> 🔥 HOT 知识 — 记录每次 Agent 会话的摘要。每次对话开始时读取，了解项目历史。

---

## 会话记录

### 2026-06-17 22:01 - 统一 memory-bank 命名与时间戳规则

**完成事项**:
- [x] 将 `memory_bank/` 目录重命名为 `memory-bank/`，并更新全项目路径引用
- [x] 在 `AGENT_RULES.md` 与 `.cursor/rules/memory-bank-protocol.mdc` 中要求日志时间戳须通过工具获取，精确到分钟
- [x] 同步更新 `progress.template.md`、`decisions.template.md`、`known-issues.template.md` 的时间格式说明
- [x] 修复 README 中「4 行/4 个文件」与实际操作（5 个 runtime 文件）不一致的描述
- [x] 在 cursor rules 的 COLD 层补充 `manuals/*.md`

**踩坑记录**:
- 项目内 `memory_bank`（目录）与 `memory-bank`（文档引用）长期混用，以目录重命名为最终统一方案

**遗留问题**:
- [x] ~~HOT 层占位文件问题~~（已在 0.2.1 解决）
- [x] ~~AGENT_RULES 与 mdc 不同步~~（已在 0.2.1 解决）

**下一步建议**:
- 考虑发布 0.2.1 tag

---

### 2026-06-17 22:14 - HOT 层模板化与协议同步（v0.2.1）

**完成事项**:
- [x] 新增 `architecture.template.md`、`active-task.template.md`、`data-contracts.template.md`、`roadmap.template.md`、`domains/module_1.template.md`
- [x] 删除空占位 runtime 文件，扩展 `.gitignore` 覆盖全部 runtime `.md`
- [x] 同步 `AGENT_RULES.md` 与 `memory-bank-protocol.mdc`（模板回退、时间戳、Update Phase）
- [x] 统一跨平台时间戳命令与格式（`YYYY-MM-DD HH:mm`）
- [x] `conventions.md` 新增 Paradigma 模板库自身 SemVer 规则
- [x] 版本号升至 `0.2.1`，更新 README / INIT_PROMPT

**踩坑记录**:
- 无

**遗留问题**:
- [ ] 衍生项目若从旧版 0.2.0 升级，需手动补充新模板文件的复制步骤

**下一步建议**:
- 用户确认后可提交本次变更

---

### 2026-07-04 22:18 - Memory-Bank 模板目录拆分（v0.2.2）

**完成事项**:
- [x] 将空白 `.template.md` 模板从 `memory-bank/` 迁移到 `memory-bank-template/`
- [x] 移除 `.gitignore` 中对 `memory-bank/*.md` 运行时文件的排除规则
- [x] 同步更新 `AGENT_RULES.md`、`.cursor/rules/memory-bank-protocol.mdc`、`INIT_PROMPT.md` 和 README 的模板回退路径
- [x] 新增 Paradigma 自身的 `architecture.md`、`data-contracts.md`、`decisions.md`、`active-task.md`、`changelog.md`
- [x] 按模板库结构变更规则将版本号从 `0.2.1` 升至 `0.2.2`

**踩坑记录**:
- `AGENT_RULES.md` 原文件使用双 CR 换行风格，首次编辑产生整文件 diff；已恢复原换行风格以减少无关变更。
- `memory-bank/progress.md` 此前被 `.gitignore` 排除但实际承担 Paradigma 自身历史记录，本次移除忽略规则后可开始进入版本控制。

**遗留问题**:
- [ ] 等待用户确认后，再以 `paradigma-okf-draft.md` 为纲启动 OKF-compatible 迭代。

**下一步建议**:
- 用户确认模板拆分结果后，进入 OKF 结构与协议迭代阶段。
