---
type: paradigma-decision
title: ADR-017 Make Versioned YAML the Coding Runtime Fact Source
description: Chooses strict CAS-protected Task and Session YAML snapshots, active pointers, and rebuildable Markdown projections.
tags: [adr, coding, runtime, yaml, snapshot, projection, atomicity]
timestamp: 2026-07-24T01:31:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: cold
  lifecycle: append-only
  update_policy: append-only
  epistemic_status: decision
  status: accepted
  retrieval_hints:
    zh:
      - YAML 运行态事实源
      - active task projection
      - Task Session 原子快照
    en:
      - YAML runtime source of truth
      - active task projection
      - task session atomic snapshots
  symbols:
    - CodingRuntimeCodec
    - CodingRuntimeStore
    - ActiveTaskPointer
    - ActiveSessionPointer
    - pd runtime rebuild
    - pd runtime verify
  relations:
    constrains:
      - /architecture.md
      - /contracts/coding-runtime-contract.md
    follows:
      - /decisions/adr-016-coding-integration-domain-boundary.md
---

# Context

现有 `active-task.md` 同时承担机器状态、人类说明和归档输入，字段可被自然语言或手工编辑改变。Phase 3 后续需要可靠恢复 Task/Session、拒绝并发覆盖并从 checkpoint 建立 handoff；继续把 Markdown 当当前状态事实源会迫使状态机解析人类文本。

Batch 3.1 已提供 immutable Coding values，但还没有持久化边界。直接让 YAML adapter 决定状态迁移又会把 Batch 3.3 的生命周期规则提前散落到 codec/store 中。

# Decision

1. `memory-bank/runtime/tasks/TASK-....yaml` 与 `sessions/SESSION-....yaml` 保存版本化完整 snapshot；`active-task.yaml`、`active-session.yaml` 只保存显式 active identity pointer。
2. 首期 `coding_runtime_schema_version` 为 `0.1`，与 distribution、config、Memory Markdown 和 catalog schema 独立。
3. Codec 要求 exact fields、timezone-aware ISO time、唯一 YAML keys 和确定性 UTF-8/LF serialization；未知、缺失或错误 kind/version 明确失败。
4. Snapshot envelope 维护从 1 开始的 `snapshot_revision`。更新绑定 caller-observed exact-byte source hash，使用 managed lock、单文件 atomic replace 并自动递增 revision。
5. Active session 必须引用已存在 session，且 session task 必须等于 active task；空 pointer 以显式 null 表示没有 active state。
6. `active-task.md` 与 `handoff.md` 仅为 YAML facts 的可重建人类投影。`pd runtime verify` 检测手工 drift，`pd runtime rebuild` 重新生成；投影不得反向修改 YAML。
7. Store 只验证 snapshot 内在一致性和引用完整性，不判断 Task 状态迁移是否合法；transition table 留给 Batch 3.3。
8. 旧 Markdown archive 仅用于迁移前任务的最后一次归档。仓库迁移到 YAML pointer 后，后续 task 命令必须以 YAML 为输入，不能继续把 Markdown 当事实源。

# Consequences

- 新 Session 可以从两个小 pointer 和对应 snapshot 恢复当前运行态，不必扫描 progress logs。
- 手工改坏 Markdown 不会损坏事实，且 CI 可以明确报告 projection stale。
- CAS 与 snapshot revision 可检测并发/过期写入，但跨多个 YAML 文件暂不承诺数据库式事务；后续 lifecycle service 必须设计可恢复的 mutation plan。
- Handoff 在 Batch 3.4 checkpoint narrative 出现前只投影最小 Session identity 和状态。

# Alternatives Considered

1. 继续使用 active-task Markdown：拒绝，因为人类文本无法成为严格状态机输入。
2. SQLite 保存当前运行态：拒绝，因为运行事实应可 Git 审查、可手工恢复且无需数据库。
3. 全量 Event Sourcing：拒绝，因为 Phase 3 当前只需要当前 snapshot 与独立审计，复杂度过高。
4. YAML 只保存 active document、不保留 task/session 历史 snapshot：拒绝，因为 session handoff 和恢复会失去稳定 identity。

# Status

Accepted for Phase 3 Batch 3.2.

# Related Documents

- `docs/devplan/paradigma_dev_5+.md`
- `memory-bank/knowledge/contracts/coding-domain-contract.md`
- `memory-bank/knowledge/contracts/coding-runtime-contract.md`
- `memory-bank/knowledge/decisions/adr-006-transactional-task-archive.md`
