---
type: paradigma-decision
title: ADR-001 Split Template Source and Runtime Memory
description: Decision to separate blank templates from Project Paradigma runtime memory.
tags: [adr, memory-bank, templates]
timestamp: 2026-07-04T22:33:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: cold
  lifecycle: append-only
  update_policy: append-only
  epistemic_status: decision
  status: accepted
  retrieval_hints:
    zh:
      - 模板拆分
      - 运行记忆
      - 初始化流程
    en:
      - template split
      - runtime memory
      - bootstrap flow
  relations:
    superseded_by:
      - /decisions/adr-002-okf-compatible-memory-runtime.md
---

# Context

Project Paradigma originally mixed blank `.template.md` files with the repository's own active memory files. This made new-project bootstrap less direct and made it harder to track Paradigma's own development history as repository state.

# Decision

Move blank templates into `memory-bank-template/` while reserving `memory-bank/` for actual project memory. Runtime files are copied from templates during bootstrap instead of being mixed with template sources.

# Consequences

- Derived projects can copy templates into active memory locations with fewer `.gitignore` exceptions.
- Paradigma itself can version its active memory as part of repository history.
- Later OKF migration can split `memory-bank/` into runtime/logs/knowledge without colliding with blank templates.

# Alternatives Considered

- Keep templates and runtime memory together: lowest migration cost, but bootstrap remains noisy.
- Move templates into a generic `templates/memory-bank/` path: clearer spelling, but it did not match the user-requested `memory-bank-template` directory.

# Status

Accepted.

# Related Documents

- `memory-bank/knowledge/decisions/adr-002-okf-compatible-memory-runtime.md`
- `memory-bank/knowledge/architecture.md`
- `INIT_PROMPT.md`

---

## 附录：原始草案 (2026-06-02)

> 📜 以下内容从 pre-OKF 时代的 `memory_bank/decisions.md` 归档恢复。彼时尚未有三态结构，本决策编号为 ADR-002（旧）。2026-07-04 OKF 迁移后重编号为 ADR-001，内容经过格式化和补充。此处保留原始措辞以记录决策时的思维过程。

### ADR-002 (旧): 模板与运行时分离

**日期**: 2026-06-02
**状态**: 已采纳

**背景**
Memory-bank 内的部分文件会累积项目特定的开发历史数据（如 progress.md 中的会话日志、decisions.md 中的架构决策）。如果直接将这些文件跟踪进 git，clone 本项目的下游用户会拿到携带上游项目历史的受污染模板。需要一种机制让下游用户拿到干净的模板，同时上游开发者能保留自己的开发历史。

**决策**
采用 `.template.md` + `.gitignore` 模式：
- 会累积项目特定数据的文件（progress, decisions, known-issues, glossary）提供 `.template.md` 副本
- `.template.md` 跟踪进 git（含格式说明和占位符）
- 对应的 `.md` 由 `.gitignore` 排除
- 用户 clone 后需按 README 指引 `cp *.template.md *.md` 激活

**备选方案**
- 方案 A — 全部 gitignore，用户自行创建: 用户不知道需要哪些文件、什么格式，学习成本高
- 方案 B — 全部跟踪，用户 clone 后手动清理: 容易遗漏，且清理脚本容易出错
- 方案 C — 单独的 `templates/` 子目录: 增加目录层级，与 Agent 读取路径不一致（Agent 需要读到 `memory_bank/progress.md` 而非 `memory_bank/templates/progress.md`）

**后果**
- ✅ 下游用户 clone 后拿到完全干净的模板
- ✅ 上游开发者保留自己的开发历史（本地文件，不受 git 影响）
- ✅ Agent 始终读取 `memory_bank/progress.md` 等实际文件，路径无需改变
- ⚠️ 新增了"复制模板"这一步操作，需要在 README 和 INIT_PROMPT 中明确指引
- ⚠️ 每次新增会累积运行时数据的文件类型时，需要同步创建 `.template.md` 并更新 `.gitignore`
