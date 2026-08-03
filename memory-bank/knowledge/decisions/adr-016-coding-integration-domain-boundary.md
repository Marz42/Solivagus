---
type: paradigma-decision
title: ADR-016 Keep Coding Runtime Semantics Outside the Memory Kernel
description: Places repository, task, session, checkpoint, and tool evidence values in a one-way Coding Integration over the generic Memory Kernel.
tags: [adr, coding, integration, kernel, task, session, checkpoint, evidence]
timestamp: 2026-07-24T01:22:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: cold
  lifecycle: append-only
  update_policy: append-only
  epistemic_status: decision
  status: accepted
  retrieval_hints:
    zh:
      - Coding Integration 领域边界
      - Task Session Checkpoint 模型
      - Kernel 不含编程语义
    en:
      - coding integration boundary
      - task session checkpoint model
      - domain-neutral kernel
  symbols:
    - RepositoryScope
    - CodingTask
    - CodingSession
    - CodingCheckpoint
    - GitEvidence
    - TestEvidence
    - BuildEvidence
  relations:
    constrains:
      - /architecture.md
      - /contracts/coding-domain-contract.md
    follows:
      - /decisions/adr-015-canonical-first-memory-explain.md
---

# Context

Phase 2 已建立领域中立的 Memory Kernel。Phase 3 需要表达 repository、task、session、checkpoint、Git、test 和 build，但这些词对 Research / OSINT 等其它领域没有通用含义。若直接加入 Kernel，后续领域会被迫继承 Coding 假设，破坏 Phase 2 的抽象边界。

同时，Batch 3.2 将以 YAML 保存当前运行状态，Batch 3.4 将由工具采集 checkpoint facts。若没有先定义不可变、可严格校验且不依赖存储的值模型，YAML、CLI 和 Git/test adapters 容易各自复制状态与证据规则。

# Decision

1. `RepositoryScope`、`CodingTask`、`CodingSession`、`CodingCheckpoint`、`GitEvidence`、`TestEvidence` 和 `BuildEvidence` 位于 `src/paradigma/integrations/coding/`。
2. Coding Integration 只能单向依赖 Memory Kernel 与标准库；Kernel、storage 和通用 application service 不得反向依赖 Coding。
3. `RepositoryScope.memory_scope()` 是 Coding identity 到通用 `MemoryScope` 的显式投影：repository 映射到 project，task/session 保持通用 scope 字段，namespace 固定为 `coding`。
4. Task 使用计划规定的六态枚举；Session 单独使用 active/ended/aborted，避免把任务阻塞语义误用于一次 Agent 会话。
5. ID 使用可读、稳定且可序列化的 `TASK-...`、`SESSION-...` 和 `CHECKPOINT-...` 格式；时间必须带 timezone，repository paths 必须为仓库相对 POSIX 形式。
6. Checkpoint 将工具确定的 Git/test/build/touched-path/status evidence 与 Agent 候选的 summary/completed/remaining/blockers/next steps 分字段保存，不把自然语言叙述伪装成工具事实。
7. 本批只定义 immutable values 和不变量；YAML codec/store、状态迁移服务、Git 命令采集和 context builder 分别留给后续 Batch。

# Consequences

- Research / OSINT 可以复用 Memory Kernel 而不理解 repository、commit 或 test。
- 后续 YAML snapshot 和 CLI 可以围绕同一组值对象实现，不必再定义第二套状态枚举或证据结构。
- 严格路径、时间、ID 和结果一致性会拒绝部分松散输入；adapter 必须先规范化平台路径和命令输出。
- CodingCheckpoint 可以同时保留可验证事实与 Agent handoff 叙述，但真实性边界清晰可审计。

# Alternatives Considered

1. 把 repository/task/session 字段加入 MemoryRecord：拒绝，因为会污染领域中立 Kernel。
2. 直接把现有 active-task Markdown 当作领域模型：拒绝，因为它是人类投影，状态和字段不够稳定，无法作为 YAML runtime schema。
3. 用一个自由结构 dictionary 表示所有 evidence：拒绝，因为 test/build/Git 的一致性无法被工具验证。
4. 在 Batch 3.1 同时实现生命周期和 YAML persistence：拒绝，因为会把模型、状态机和存储风险合并成不可独立验收的大批次。

# Status

Accepted for Phase 3 Batch 3.1.

# Related Documents

- `docs/devplan/paradigma_dev_5+.md`
- `memory-bank/knowledge/architecture.md`
- `memory-bank/knowledge/contracts/coding-domain-contract.md`
- `memory-bank/knowledge/decisions/adr-010-stable-memory-domain-values.md`
