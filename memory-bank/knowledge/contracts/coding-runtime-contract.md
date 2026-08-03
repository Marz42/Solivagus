---
type: paradigma-contract
title: Coding YAML Runtime State Contract
description: Defines schema-versioned Task and Session snapshots, active pointers, CAS updates, and rebuildable Markdown projections.
tags: [contract, coding, runtime, yaml, task, session, projection]
timestamp: 2026-07-24T02:44:33+08:00
paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: evolving
  update_policy: requires-human-confirmation
  epistemic_status: confirmed
  contract_kind: runtime-state
  retrieval_hints:
    zh:
      - Coding YAML Runtime 契约
      - active task session pointer
      - Markdown projection drift
    en:
      - coding YAML runtime contract
      - active pointers
      - runtime projection drift
  symbols:
    - CodingRuntimeCodec
    - CodingRuntimeStore
    - StoredTaskSnapshot
    - StoredSessionSnapshot
    - pd runtime rebuild
    - pd runtime verify
    - pd runtime init
  relations:
    depends_on:
      - /contracts/coding-domain-contract.md
      - /decisions/adr-017-yaml-runtime-facts-markdown-projections.md
    constrains:
      - /architecture.md
      - /contracts/repository-contract.md
---

# Scope

本契约覆盖 Phase 3 Batch 3.2 的 Coding Task/Session YAML runtime、active pointers、source-hash CAS 和 Markdown projections。它不授权任意状态迁移，不采集 Git/test/build，不生成 checkpoint narrative，也不定义 task/session lifecycle CLI。

# Contract

Canonical runtime facts 使用以下路径：

```text
memory-bank/runtime/tasks/TASK-....yaml
memory-bank/runtime/sessions/SESSION-....yaml
memory-bank/runtime/active-task.yaml
memory-bank/runtime/active-session.yaml
memory-bank/runtime/checkpoints/CHECKPOINT-....yaml
```

每个 task/session snapshot 必须包含 `coding_runtime_schema_version: "0.1"`、固定 kind、从 1 开始的 `snapshot_revision` 和 exact domain value mapping。文件名 identity 必须等于 snapshot identity。Active pointer 使用显式 null 表示无 active object，并携带 timezone-aware `updated_at`；Session pointer 另保留 `last_session_id` 供 ended Session handoff 恢复。

Codec 只接受 exact field sets，使用共享 duplicate-safe YAML parser，并产生 deterministic UTF-8/LF YAML。Store 拒绝 symlink、缺失引用和 filename mismatch。Update 必须：

1. 获取 managed per-file lock；
2. 重新读取当前 exact bytes；
3. 比较 caller-observed `sha256:` source hash；
4. 保留 task `created_at` 或 session `task_id/started_at`；
5. 自动将 snapshot revision 加一；
6. atomic replace，失败保留旧 snapshot 并清理 lock。

Task update 还必须保留 repository scope；Session 的 repository 必须始终等于所属 Task。存在 active session 时，必须先清空 session pointer，才能切换或清空 active task pointer。

`active-task.md` 和 `handoff.md` 是 derived projections。它们必须标记 `update_policy: generated` 和 YAML source，手工编辑只产生 drift，不改变事实。空 pointers 生成稳定 pending/no-active projection。

# Request Schema

Python store request：

```text
create_task(CodingTask)
update_task(CodingTask, expected_source_hash=...)
create_session(CodingSession)
update_session(CodingSession, expected_source_hash=...)
set_active_task(ActiveTaskPointer, expected_source_hash=...|None)
set_active_session(ActiveSessionPointer, expected_source_hash=...|None)
rebuild_projections(dry_run=False)
verify_projections()
```

Public deterministic adapter：

```text
pd runtime init    [--write] [--project PATH] [--format text|json] [--dry-run]
pd runtime rebuild [--project PATH] [--format text|json] [--dry-run]
pd runtime verify  [--project PATH] [--format text|json] [--dry-run]
```

`pd runtime init` 默认只返回 mutation plan。`--write` 只创建缺失的 null pointers，校验但不覆盖既有 pointer facts，然后从 YAML 重建 projections。若在两个 pointer 写入之间中断，重复执行只补充缺失部分。

# Response Schema

Stored snapshot 返回 domain value、snapshot revision、exact-byte source hash、canonical path 和 canonical serialization flag。Stored pointer 返回 pointer value、source hash、path 和 canonical flag。

Projection verify 返回 aggregate current 以及 active-task/handoff 独立状态。CLI stale failure 使用稳定 code `PD_CODING_RUNTIME_PROJECTION_STALE`；Schema、conflict、not-found 和 storage errors 分别使用 `PD_CODING_RUNTIME_SCHEMA_ERROR`、`PD_CODING_RUNTIME_CONFLICT`、`PD_CODING_RUNTIME_NOT_FOUND` 和 `PD_CODING_RUNTIME_STORAGE_ERROR`。

# State Transitions

本批只允许 snapshot create/update 和 pointer replacement，不定义 Task lifecycle permission：

```text
immutable domain value -> strict YAML -> atomic canonical snapshot
YAML snapshots + active pointers -> deterministic Markdown projection
manual Markdown edit -> verify stale -> rebuild from YAML
```

Batch 3.3 必须在调用 store 之前验证 transition，并为多文件 mutation 定义可恢复顺序。

# Compatibility Notes

- 迁移时先归档最后一个 Markdown-source task，再初始化 null YAML pointers 并 rebuild projections。
- `.paradigma/config.yaml` 既有 `runtime_root` 继续决定 runtime 根路径，无需 config schema bump。
- 旧 `.paradigma/tools/pd-archive-task.py` 不得用于 YAML-source 新任务；Batch 3.3 将替换公共 task lifecycle。
- 新 workspace 不复制 runtime placeholder 作为事实源；安装 package 后用 `pd runtime init --write` 生成 canonical null pointers 和 projections。旧 template runtime 只保留为迁移参考。

# Breaking Change Policy

改变 runtime schema version、snapshot/pointer exact fields、source-hash CAS、revision increment、canonical paths、projection source direction 或 stable error codes 是 breaking。新增可选 YAML 字段仍需 schema version review，因为当前 codec 使用 exact field sets。

# Citations

- Formal Batch 3.2: `docs/devplan/paradigma_dev_5+.md`
- [Coding Domain Model contract](coding-domain-contract.md)
- [ADR-017](../decisions/adr-017-yaml-runtime-facts-markdown-projections.md)
