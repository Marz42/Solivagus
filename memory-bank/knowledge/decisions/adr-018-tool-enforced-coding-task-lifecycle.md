---
type: paradigma-decision
title: ADR-018 Enforce CodingTask Transitions in a Pure Domain Service
description: Defines one authoritative Task transition table, dry-run-first CLI mutations, recoverable YAML write ordering, and terminal active-pointer cleanup.
tags: [adr, coding, task, lifecycle, transition, recovery, cli]
timestamp: 2026-07-24T01:43:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: cold
  lifecycle: append-only
  update_policy: append-only
  epistemic_status: decision
  status: accepted
  retrieval_hints:
    zh:
      - Task 生命周期状态机
      - 非法状态迁移
      - 中断恢复 task mutation
    en:
      - coding task lifecycle
      - illegal task transition
      - recoverable task mutation
  symbols:
    - TaskAction
    - transition_task
    - start_task_outcome
    - transition_task_outcome
    - pd task start
  relations:
    constrains:
      - /architecture.md
      - /contracts/coding-task-lifecycle-contract.md
    follows:
      - /decisions/adr-017-yaml-runtime-facts-markdown-projections.md
---

# Context

Batch 3.2 已把 YAML 设为 Task/Session 事实源，但 enum 只说明可能状态，不能说明合法迁移。若 CLI、store 或 Agent 直接替换 `status`，pending 可以跳到 completed、terminal task 可以复活，blocked/suspended reason 也会丢失。

Task mutation 同时涉及 task snapshot、active pointer 和 Markdown projection。单文件可原子写，但本地文件系统没有跨文件事务；必须定义中断后可识别、可重试的写入顺序。

# Decision

1. `transition_task()` 是唯一 Task transition table，位于 storage-neutral Coding Integration，接收 immutable task/action/time/reason 并返回 next value，不执行 I/O。
2. 合法路径为 pending→active；active→blocked/suspended/completed/aborted；blocked→active/suspended/aborted；suspended→active/aborted。completed/aborted 是 terminal。
3. block/suspend/abort 必须有 trimmed reason；start/unblock/resume/complete 不接受 reason。任何 transition time 不得早于 snapshot `updated_at`。
4. `pd task start/status/block/unblock/suspend/resume/complete/abort` 只调用 Application service；mutation 默认 dry-run，只有 `--write` 发布。
5. Start 先写 active task snapshot，再 CAS 设置 active pointer，最后重建 projection。pointer 写失败留下可识别的 orphan active snapshot；相同 start 可重试并接上 pointer。
6. Terminal transition 先 CAS 写 terminal task，再清空 active pointer，最后重建 projection。清 pointer 失败时 pointer 指向 terminal snapshot；重复相同 terminal command 只完成 cleanup。
7. active session 存在时拒绝 terminal task；Batch 3.4 必须先结束 session。
8. YAML runtime 启用后禁用 legacy Markdown archive，防止它覆盖 generated projection 并制造双事实源。

# Consequences

- 所有公开 Task command 使用同一可单元测试的状态机，非法跳转获得稳定错误码。
- 文件系统中断不会回滚已写事实，但会留下有限、可分类并可重复命令恢复的中间状态。
- 完成 Task 后历史 snapshot 保留，active pointer 变为 null；progress narrative 仍单独 append-only。
- 多 Agent 同时写同一 snapshot/pointer 时由 exact-byte CAS 和 managed lock 拒绝过期更新。

# Alternatives Considered

1. 允许 CLI 直接设置任意 status：拒绝，因为无法强制 lifecycle。
2. 把 transition table 放进 YAML store：拒绝，因为 persistence 不应拥有领域政策。
3. 失败时删除已写 task snapshot：拒绝，因为删除扩大破坏面，也使中断恢复不可审计。
4. 继续使用 `pd task archive` 完成 YAML task：拒绝，因为它以 generated Markdown 为输入，会反转事实源方向。

# Status

Accepted for Phase 3 Batch 3.3.

# Related Documents

- `docs/devplan/paradigma_dev_5+.md`
- `memory-bank/knowledge/contracts/coding-task-lifecycle-contract.md`
- `memory-bank/knowledge/contracts/coding-runtime-contract.md`
- `memory-bank/knowledge/decisions/adr-006-transactional-task-archive.md`
