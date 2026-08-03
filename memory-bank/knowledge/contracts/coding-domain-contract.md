---
type: paradigma-contract
title: Coding Domain Model Contract
description: Defines immutable repository, task, session, checkpoint, and deterministic tool-evidence values above the Memory Kernel.
tags: [contract, coding, task, session, checkpoint, git, test, build]
timestamp: 2026-07-24T01:22:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: evolving
  update_policy: requires-human-confirmation
  epistemic_status: confirmed
  contract_kind: domain-integration
  retrieval_hints:
    zh:
      - Coding Domain Model 契约
      - Task Session Checkpoint 字段
      - Git Test Build Evidence
    en:
      - coding domain model contract
      - task session checkpoint schema
      - coding evidence values
  symbols:
    - RepositoryScope
    - CodingTask
    - CodingSession
    - CodingCheckpoint
    - TaskStatus
    - SessionStatus
    - EvidenceStatus
  relations:
    depends_on:
      - /decisions/adr-016-coding-integration-domain-boundary.md
      - /decisions/adr-010-stable-memory-domain-values.md
    constrains:
      - /architecture.md
      - /contracts/repository-contract.md
---

# Scope

本契约覆盖 Phase 3 Batch 3.1 的 storage-neutral Coding Integration values。它定义后续 YAML runtime、task/session lifecycle、checkpoint collector 和 context builder 共享的语义边界；不定义文件格式、CLI、Git subprocess、自动状态迁移或 Memory 写入政策。

# Contract

- 所有公开值均为 frozen dataclass，不允许构造后原地改变。
- Coding Integration 位于 `paradigma.integrations.coding`，只依赖标准库和公开 Memory Kernel。
- 所有时间必须带 timezone；`updated_at` 不得早于创建/开始时间；terminal session 必须有 `ended_at`，active session 禁止有结束时间。
- `TASK-...`、`SESSION-...`、`CHECKPOINT-...` 是稳定运行态 identity。Task 状态为 pending/active/blocked/suspended/completed/aborted；Session 状态为 active/ended/aborted。
- blocked 或 suspended task 必须提供 `status_reason`；blocked checkpoint 必须列出 blocker。
- repository、report、artifact、worktree 和 touched paths 使用仓库相对 POSIX 形式，不接受绝对路径、反斜杠或 `..` escape。
- GitEvidence 允许 detached/unborn repository，commit 若存在则为 7–64 位小写 hex；clean snapshot 不得同时声明 worktree paths。
- TestEvidence 和 BuildEvidence 保存 command、status、observed time、exit code、duration 和可选 output hash。passed evidence 不得同时报告非零 exit 或失败测试数。
- CodingCheckpoint 中 `git/tests/builds/touched_paths/task_status` 为工具确定区；`summary/completed_work/remaining_work/blockers/next_steps` 为 Agent 候选叙述区。

`RepositoryScope.memory_scope()` 固定产生 `namespace=coding`，并映射 workspace、repository/project、task、session 与 entity IDs；映射不得修改 Kernel 类型或枚举。

# Request Schema

Batch 3.1 的 request 是 Python value construction。主要字段为：

```text
RepositoryScope(workspace_id, repository_id, repository_path=".", remote_url=None)
CodingTask(task_id, repository, title, goal, status, created_at, updated_at, ...)
CodingSession(session_id, task_id, repository, status, started_at, updated_at, ...)
GitEvidence(repository_id, observed_at, head_commit, branch, dirty, worktree_paths=())
TestEvidence(command, status, observed_at, exit_code=None, counts..., report_path=None)
BuildEvidence(command, status, observed_at, exit_code=None, artifact_paths=())
CodingCheckpoint(checkpoint_id, task_id, session_id, created_at, task_status, evidence..., narrative...)
```

String enum values are accepted and canonicalized to their enum members. Collection fields require tuples to preserve immutable, deterministic snapshots.

# Response Schema

Successful construction returns the immutable value itself. `RepositoryScope.memory_scope(...)` returns a Kernel `MemoryScope`. Invalid values raise `ValueError` with a field-oriented reason; there is no I/O, printing or mutation result in this batch.

YAML and CLI adapters introduced later must translate parse diagnostics into stable application errors without weakening these domain invariants.

# State Transitions

Batch 3.1 values describe snapshots but do not perform transitions. The authoritative transition table and commands are deferred to Batch 3.3. Callers must not treat enum membership alone as permission to move between arbitrary states.

```text
platform observation -> adapter normalization -> immutable Coding value
RepositoryScope + task/session IDs -> explicit projection -> MemoryScope
```

# Compatibility Notes

- Existing `memory-bank/runtime/active-task.md` remains the active human projection until Batch 3.2 introduces YAML facts and rebuildable Markdown projection.
- Existing archive behavior and `pd task archive` are unchanged by these models.
- Repository paths serialize with `/` even when collected on Windows; adapters are responsible for normalization before construction.
- Evidence output hash uses `sha256:` plus 64 lowercase hex digits and represents captured output, not canonical Memory content hash.

# Breaking Change Policy

Renaming fields, changing enum values, weakening identity/path/time invariants, changing the RepositoryScope-to-MemoryScope mapping, or moving Coding semantics into Kernel is breaking. Adding optional evidence or narrative fields is compatible when older snapshots retain deterministic defaults.

# Citations

- Formal Phase 3 plan: `docs/devplan/paradigma_dev_5+.md`
- [ADR-016](../decisions/adr-016-coding-integration-domain-boundary.md)
- [Canonical Memory Markdown contract](memory-document-contract.md)
