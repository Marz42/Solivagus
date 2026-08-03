---
type: paradigma-decision
title: ADR-019 Keep Checkpoints Append-Only and Handoff Addressable After Session End
description: Separates deterministic checkpoint facts from Agent narrative, uses IDs as idempotency keys, and retains the last ended Session for handoff.
tags: [adr, coding, session, checkpoint, handoff, evidence, recovery]
timestamp: 2026-07-24T02:00:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: cold
  lifecycle: append-only
  update_policy: append-only
  epistemic_status: decision
  status: accepted
  retrieval_hints:
    zh: [Session Checkpoint Handoff, append-only checkpoint, 结束会话后恢复上下文]
    en: [session checkpoint handoff, append-only checkpoint, last session recovery]
  symbols: [CodingCheckpointCodec, CodingCheckpointStore, ActiveSessionPointer, pd handoff build]
  relations:
    constrains: [/architecture.md, /contracts/coding-session-checkpoint-contract.md]
    follows: [/decisions/adr-018-tool-enforced-coding-task-lifecycle.md]
---

# Context

Task lifecycle 已可恢复，但 Agent Session 仍缺少稳定 checkpoint。若 checkpoint 只写进 handoff Markdown，Git/test/touched paths 与 Agent 总结会混为一体；若 Session end 把 pointer 全清空，下一 Session 又必须扫描 progress logs。

# Decision

1. Checkpoint 使用独立、版本化、append-only YAML：`runtime/checkpoints/CHECKPOINT-....yaml`；ID 是幂等键，既有文件永不覆盖。
2. YAML 分开工具事实（task/session/time/status、Git、touched paths、test/build）与 Agent narrative（summary、completed、remaining、blockers、next steps）。
3. CLI 读取 Git HEAD/branch/worktree；显式 test/build command 使用无 shell subprocess，记录 exit、duration 和 output hash。非零退出作为 failed evidence 保存。
4. Checkpoint 默认 dry-run，不执行 test/build；`--write` 才采集和发布。
5. 写入顺序为 checkpoint create → Session attach → handoff rebuild。attach 失败时重复相同 ID，以第一次 canonical checkpoint 为准完成恢复。
6. Session end 清 active identity，但 pointer 保留 `last_session_id`。Handoff 优先 active Session，否则使用 last ended Session。
7. Markdown 只从 Session/Checkpoint YAML 单向重建。

# Consequences

- 新 Session 读取 pointer 和一个 checkpoint 即可恢复，不必扫描全部日志。
- Agent 叙述不会覆盖工具采集事实；中断重试不会改写第一次 checkpoint。
- test/build 执行是显式且可能耗时的 `--write` 行为，dry-run 保持无执行副作用。

# Alternatives Considered

1. 覆盖单一 checkpoint 文件：拒绝，历史与恢复证据会丢失。
2. Session end 后完全清空 pointer：拒绝，handoff 无法定位最近 checkpoint。
3. 保存完整 stdout/stderr：拒绝，体积和敏感信息风险高，首期只存 hash。
4. 由 Agent 填 Git/test status：拒绝，这些字段应由工具确定。

# Status

Accepted for Phase 3 Batch 3.4.

# Related Documents

- `docs/devplan/paradigma_dev_5+.md`
- `memory-bank/knowledge/contracts/coding-session-checkpoint-contract.md`
- `memory-bank/knowledge/contracts/coding-runtime-contract.md`
- `memory-bank/knowledge/known-issues/session-context-fragmentation.md`
