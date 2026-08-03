---
type: paradigma-contract
title: CodingSession Checkpoint and Handoff Contract
description: Defines Session lifecycle, append-only checkpoint facts, deterministic evidence collection, and last-session handoff recovery.
tags: [contract, coding, session, checkpoint, evidence, handoff, yaml]
timestamp: 2026-07-24T02:00:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: evolving
  update_policy: requires-human-confirmation
  epistemic_status: confirmed
  contract_kind: application-lifecycle
  retrieval_hints:
    zh: [CodingSession Checkpoint 契约, handoff build, Git test evidence]
    en: [coding session checkpoint contract, handoff build, checkpoint evidence]
  symbols: [CodingCheckpointStore, ActiveSessionPointer, checkpoint_session_outcome, pd session checkpoint]
  relations:
    depends_on:
      - /contracts/coding-runtime-contract.md
      - /contracts/coding-task-lifecycle-contract.md
      - /decisions/adr-019-append-only-checkpoints-and-last-session-handoff.md
    constrains: [/architecture.md, /contracts/repository-contract.md]
---

# Scope

本契约覆盖 Phase 3 Batch 3.4 的 Session start/status/checkpoint/end、Checkpoint YAML、Git/test/build evidence 和 handoff projection。不定义 Context Builder、自动 test selection、远程 CI ingestion 或并发 active Sessions。

# Contract

- Session 只能在 active Task 上启动；首期最多一个 active Session。
- Start 创建 active snapshot 后设置 pointer；end 写 ended snapshot后清 active identity并保存 `last_session_id`。
- Checkpoint 位于 `runtime/checkpoints/CHECKPOINT-....yaml`，schema 0.1、revision 1、append-only create。
- Checkpoint identity 必须匹配 active task/session；时间不得早于当前状态；Git repository ID 必须等于 Task repository。
- 工具事实包括 IDs/time/status、Git HEAD/branch/dirty/worktree、touched paths、test/build command/status/exit/duration/output hash。
- Agent narrative 仅包括 summary、completed_work、remaining_work、blockers、next_steps，并使用 exact keys。
- Checkpoint create 后 attach 失败时，同一 ID 重试读取既有事实并完成 Session update，不覆盖文件。
- Handoff 优先 active Session，否则读取 last Session；Markdown 不反向导入 YAML。

# Request Schema

```text
pd session start --session-id SESSION-... [--agent-id ID] [--write] ...
pd session status ...
pd session checkpoint --checkpoint-id CHECKPOINT-... [--input narrative.yaml]
  [--test-command COMMAND] [--build-command COMMAND] [--write] ...
pd session end [--write] ...
pd handoff build [--dry-run] [--format text|json] [--project PATH]
```

Mutation 默认 dry-run。Checkpoint dry-run 不执行 test/build 或写文件；`--write` 显式授权无 shell本地命令执行。

# Response Schema

Session status 返回 active、identity、status、agent、timestamps、checkpoint、revision 和 source hash。Checkpoint 返回 ID/source hash/Session revision/written。稳定错误包括 `PD_SESSION_*`、`PD_CHECKPOINT_*` 和 `PD_EVIDENCE_COLLECTION_ERROR`。

# State Transitions

```text
active Task + no Session -> active Session
active Session -> append Checkpoint -> Session points to Checkpoint
active Session -> ended Session -> active null + last_session_id
active/last Session + Checkpoint -> handoff.md
```

# Compatibility Notes

- `active-session.yaml` schema 0.1 在 v0.7 前补充 `last_session_id`；旧 null pointer 需补字段后 rebuild。
- Failed test/build 是成功保存的 evidence，不等于 checkpoint 写入失败。
- stdout/stderr 不进入 YAML，只保存 SHA-256 digest。

# Breaking Change Policy

改变 append-only policy、fact/narrative boundary、command opt-in、last-session handoff、exact fields、recovery precedence 或 stable errors 是 breaking。

# Citations

- Formal Batch 3.4: `docs/devplan/paradigma_dev_5+.md`
- [Coding runtime contract](coding-runtime-contract.md)
- [ADR-019](../decisions/adr-019-append-only-checkpoints-and-last-session-handoff.md)
