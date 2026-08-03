---
type: paradigma-decision
title: ADR-006 Make Task Status Strict and Archive Recovery Idempotent
description: Defines the active-task status enum and a recoverable two-file archive mutation protocol with stable failures.
tags: [adr, task-state, archive, atomic-write, idempotency]
timestamp: 2026-07-23T00:14:11+08:00
paradigma:
  schema_version: "0.1"
  temperature: cold
  lifecycle: append-only
  update_policy: append-only
  epistemic_status: decision
  status: accepted
  retrieval_hints:
    zh:
      - 严格任务状态
      - 安全归档
      - 原子写入
      - 幂等恢复
    en:
      - strict task status
      - safe archive
      - atomic write
      - idempotent recovery
  symbols:
    - TaskStatus
    - _task_state.py
    - ArchivePlan
    - archive_id
    - pd-archive-task.py
  relations:
    constrains:
      - /architecture.md
      - /conventions.md
      - /contracts/repository-contract.md
      - /domains/tooling.md
    follows:
      - /decisions/adr-005-unified-safe-yaml-parser.md
---

# Context

旧归档器通过 `completed`、`done`、`已完成` 或 `完成` 子串和 checklist 猜测任务是否结束。因此“未完成”也可能被识别为完成，而一个仍标记 active 但 checklist 全勾选的任务会被归档。写入时先直接创建日志，再直接覆盖 active-task；进程在两步之间中断会留下无法识别的半完成状态，重试还会创建带序号的重复日志。

# Decision

`Current Status` 必须恰好是以下小写枚举之一：`pending`、`active`、`blocked`、`completed`、`aborted`。共享 `_task_state.py` 是状态真相源；未知值在质量门禁返回 `PD_TASK_INVALID_STATUS`，在归档入口返回 `PD_ARCHIVE_INVALID_STATUS`。只有 `completed` 可默认归档，`--force` 只能绕过可归档状态限制，不能接受未知状态。

归档器先生成并显示不可变 `ArchivePlan`。默认和 `--dry-run` 只显示计划；`--write` 才执行。计划绑定 active-task 的 SHA-256，执行前必须再次核对，避免计划生成后覆盖用户修改。

执行顺序固定为：原子创建 archive 文件，再原子替换 active-task。`archive_id` 等于源内容 SHA-256，并写入 archive frontmatter。若 archive 已创建而 reset 未完成，重试通过 `archive_id` 找到并复用原文件，只执行 reset。reset 记录 last archive marker；成功后再次归档空的 pending state 返回成功且不产生新日志。

写入使用同目录临时文件、flush、`fsync` 和原子文件系统操作。失败诊断使用稳定 `PD_ARCHIVE_*` code；进程退出码分为成功 0、任务输入错误 1、I/O/parser 错误 2、并发冲突 3。

# Consequences

- 自然语言和 checklist 不再决定生命周期状态，旧 `Completed.` / `In progress.` 值需要迁移为枚举。
- dry-run 会完整展示 create/keep 和 replace 操作，不创建目录或临时文件。
- 单文件写入不会暴露部分内容；跨文件中断可通过确定性 archive ID 恢复。
- archive 成功后 active-task 明确回到 `pending`，不会残留为 active。
- 外部调用者可以根据诊断 code 和退出码可靠区分输入、I/O 与冲突失败。

# Alternatives Considered

1. 继续接受自然语言别名：拒绝，因为多语言子串不可形成稳定状态机。
2. 只把 active-task 写入放在 archive 之前：拒绝，因为中断可能丢失唯一任务内容。
3. 依赖 Git 回滚半归档：拒绝，因为工具契约不能假设工作区已提交或 Git 可用。
4. 引入数据库事务：推迟到 Memory Kernel 阶段；Phase 0 用内容寻址 ID 和恢复协议即可满足两文件操作。

# Status

Accepted for Phase 0 Batch 0.3.

# Related Documents

- `docs/devplan/paradigma_dev_5+.md`
- `AGENT_RULES.md`
- `docs/rfc/paradigma-okf-compatible-runtime.md`
- `memory-bank/knowledge/contracts/repository-contract.md`
- `memory-bank/knowledge/domains/tooling.md`
