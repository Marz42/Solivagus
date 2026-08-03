---
type: paradigma-contract
title: CodingTask Lifecycle Contract
description: Defines legal Task transitions, reason policy, dry-run/write behavior, stable errors, and interruption recovery over YAML runtime facts.
tags: [contract, coding, task, lifecycle, transition, cli, recovery]
timestamp: 2026-07-24T01:43:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: evolving
  update_policy: requires-human-confirmation
  epistemic_status: confirmed
  contract_kind: application-lifecycle
  retrieval_hints:
    zh:
      - CodingTask 生命周期契约
      - task block suspend complete
      - 状态迁移恢复
    en:
      - coding task lifecycle contract
      - task transition commands
      - recoverable task mutation
  symbols:
    - TaskAction
    - TaskTransitionError
    - transition_task
    - CodingTaskLifecycleError
    - pd task status
  relations:
    depends_on:
      - /contracts/coding-runtime-contract.md
      - /decisions/adr-018-tool-enforced-coding-task-lifecycle.md
    constrains:
      - /architecture.md
      - /contracts/repository-contract.md
---

# Scope

本契约覆盖 Phase 3 Batch 3.3 的 CodingTask state machine、Application mutation ordering 和 public task CLI。Session lifecycle/checkpoint、自动 Git evidence、progress narrative archive 和 context builder 不在本批范围。

# Contract

合法 transition table：

| Action | Source | Target | Reason |
|---|---|---|---|
| start | pending | active | forbidden |
| block | active | blocked | required |
| unblock | blocked | active | forbidden |
| suspend | active, blocked | suspended | required |
| resume | suspended | active | forbidden |
| complete | active | completed | forbidden |
| abort | pending, active, blocked, suspended | aborted | required |

Terminal completed/aborted 不允许任何新 transition。blocked/suspended/aborted 保存当前 `status_reason`；回到 active 或 completed 时清空 transient reason。Transition 是 pure immutable operation，必须使用 timezone-aware time 且不得倒退。

Application mutation 默认 dry-run。`--write` 使用 YAML source-hash CAS 和以下 recoverable order：

```text
start:    active snapshot -> active pointer -> Markdown projections
terminal: terminal snapshot -> null active pointer -> Markdown projections
other:    next snapshot -> Markdown projections
```

Projection failure不回滚 canonical YAML；运行 `pd runtime rebuild` 恢复。Start pointer failure 可以用相同 identity/title/goal/repository 重试。Terminal pointer failure可以重复同一 complete/abort，只执行剩余 cleanup。Active session 非 null 时 complete/abort 必须拒绝。

# Request Schema

```text
pd task start --task-id TASK-... --title TEXT --goal TEXT
  --workspace-id ID --repository-id ID
  [--repository-path PATH] [--remote-url URL] [--parent-task-id TASK-...]
  [--write] [--dry-run] [--format text|json] [--project PATH]

pd task status [--dry-run] [--format text|json] [--project PATH]
pd task block --reason TEXT [--write] ...
pd task unblock [--write] ...
pd task suspend --reason TEXT [--write] ...
pd task resume [--write] ...
pd task complete [--write] ...
pd task abort --reason TEXT [--write] ...
```

# Response Schema

Status 返回 active flag 及当前 task projection，包括 identity、title/goal、status/reason、repository scope、timestamps、snapshot revision 和 source hash。Mutation 返回 planned/committed task、written 和 terminal 后 active flag。

稳定错误至少包括 `PD_TASK_ALREADY_ACTIVE`、`PD_TASK_NOT_ACTIVE`、`PD_TASK_INVALID_TRANSITION`、`PD_TASK_ACTIVE_SESSION`、`PD_TASK_INPUT_ERROR`、runtime CAS/storage errors，以及 YAML runtime 下 legacy archive 的 `PD_ARCHIVE_YAML_RUNTIME`。

# State Transitions

```text
pending --start--> active --block--> blocked --unblock--> active
                     |                  |
                     +--suspend---------+--> suspended --resume--> active
                     |
                     +--complete--> completed

pending/active/blocked/suspended --abort--> aborted
```

# Compatibility Notes

- Pre-YAML workspace 没有 `active-task.yaml` 时，legacy `pd task archive` 继续可用。
- YAML workspace 中 `active-task.md` 是 generated projection，`pd task archive` 明确拒绝。
- Existing completed Markdown archives and progress logs remain append-only history。
- `TaskStatus` 的 suspended 值同步进入 legacy Markdown parser，仅用于 generated projection/hot-size compatibility，不授权旧 archive 做新 transition。

# Breaking Change Policy

改变 transition table、reason policy、default dry-run、write ordering/recovery condition、terminal pointer semantics、response fields 或 stable error codes 是 breaking。未来新增 transition 必须更新 pure service、contract、failure injection 和 CLI tests。

# Citations

- Formal Batch 3.3: `docs/devplan/paradigma_dev_5+.md`
- [Coding runtime contract](coding-runtime-contract.md)
- [ADR-018](../decisions/adr-018-tool-enforced-coding-task-lifecycle.md)
