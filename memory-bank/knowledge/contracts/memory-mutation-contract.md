---
type: paradigma-contract
title: Canonical Memory Mutation Lifecycle Contract
description: Defines proposal payloads, lifecycle transitions, revision CAS, CLI mutation safety, tombstones, and derived catalog refresh behavior.
tags: [contract, memory, mutation, lifecycle, revision, concurrency]
timestamp: 2026-07-24T03:35:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: evolving
  update_policy: requires-human-confirmation
  epistemic_status: confirmed
  contract_kind: application-api
  retrieval_hints:
    zh:
      - Memory Mutation 生命周期
      - propose commit revise supersede forget
      - source hash 并发保护
    en:
      - memory mutation lifecycle
      - propose commit revise supersede forget
      - source hash concurrency
  symbols:
    - propose_memory
    - validate_memory
    - commit_memory
    - revise_memory
    - supersede_memory
    - forget_memory
    - MemoryTransitionError
  relations:
    depends_on:
      - /contracts/memory-document-contract.md
      - /contracts/catalog-contract.md
      - /decisions/adr-014-canonical-candidate-mutation-lifecycle.md
    constrains:
      - /contracts/repository-contract.md
      - /contracts/memory-query-contract.md
      - /contracts/memory-explain-contract.md
---

# Scope

本契约覆盖 Phase 2 Batch 2.5 的 `propose → validate → commit → revise → supersede → forget` canonical lifecycle、Python Application API 和 `pd memory` CLI。`forget` 首期只写 tombstone；物理 `purge` 不在本契约范围。

# Contract

Proposal 作为 status=`candidate`、revision=1 的 canonical Memory Markdown 保存。它具有稳定 memory ID、完整 provenance、content/source hash 和原子创建语义，但普通 active-only query 不可见。`validate` 重新解析 canonical 文档并返回 caller 必须用于后续 mutation 的 exact-byte `source_hash`。

所有既有文档 mutation：

- 必须提供 canonical `expected_source_hash`；
- 先比较 caller-observed hash，再执行 managed-writer lock 下的 store CAS；
- revision 严格增加 1，created_at 不变，updated_at 不倒退；
- dry-run 构造并编码完整 next record，但不写 Markdown 或 catalog；
- write 成功后从全部 canonical Markdown rebuild 派生 catalog。

## State transitions

```text
propose:     absent -> candidate (revision 1)
commit:      candidate -> active
revise:      candidate|active -> same status
supersede:   active -> superseded + superseded_by(replacement)
forget:      any non-tombstoned status -> tombstoned
purge:       not implemented
```

Commit 不能重复激活 active record。Revise 不能修改 memory ID、status、revision、created/updated time，且 patch 必须提供本 revision 的 provenance。Supersede replacement 必须是另一条已存在的 active memory；旧 record 保留并追加 outgoing `superseded_by` relation。Forget 不删除文件、provenance 或关系，且对 tombstone 重复调用明确失败。

# Request Schema

```yaml
memory_type: semantic
title: Stable title
content: Canonical body
scope:
  namespace: project
  workspace_id: null
  project_id: project-1
  task_id: null
  session_id: null
  entity_ids: []
provenance:
  - source_type: user_statement
    source_uri: null
    source_id: conversation-1
    observed_at: 2026-07-24T03:00:00+00:00
    excerpt_hash: null
    actor: user
validity:
  from: null
  until: null
confidence: 1.0
sensitivity: internal
tags: []
relations: []
```

Proposal 必需 memory_type、title、content、scope 和非空 provenance。其它字段使用明确默认；所有层级拒绝 unknown fields。Revision input 是上述 mutable fields 的非空 patch，并必须包含 provenance。

```text
pd memory propose --input proposal.yaml [--memory-id ID] [--write]
pd memory validate MEMORY_ID
pd memory commit MEMORY_ID --expected-source-hash HASH [--write]
pd memory revise MEMORY_ID --input revision.yaml --expected-source-hash HASH [--write]
pd memory supersede MEMORY_ID --replacement-id ID --expected-source-hash HASH [--write]
pd memory forget MEMORY_ID --expected-source-hash HASH [--write]
```

Mutating CLI commands 默认 dry-run；只有 `--write` 且未同时指定 `--dry-run` 才应用。Proposal preview 若未指定 memory ID 会生成一次性 ID；希望 preview/write 保持身份时必须显式传同一 `--memory-id`。

# Response Schema

Mutation 返回 memory ID、status、revision、repository-relative path、content/source hashes、written 和 catalog_refreshed。Validate 另返回 canonical flag。输入错误使用 `PD_MEMORY_INPUT_ERROR`，非法 transition 使用 `PD_MEMORY_MUTATION_ERROR`，store CAS 保留 `PD_MEMORY_CONFLICT`。

若 canonical write 成功但 catalog rebuild 失败，命令返回 `PD_MEMORY_CATALOG_REFRESH` 并明确说明 mutation 已提交；不得回滚或从旧 catalog 覆盖 Markdown。恢复步骤是重新 validate canonical state，然后运行 `pd catalog rebuild`。

# State Transitions

```text
payload -> strict parse -> candidate preview/write
canonical read -> validate -> source_hash
source_hash + requested transition -> next immutable record
  -> atomic Markdown CAS
  -> full derived catalog rebuild
  -> query sees only allowed current statuses
```

# Compatibility Notes

- Candidate 位于 canonical root，但不是 active 长期记忆；因此备份、Git 与人工审计可看到它，普通 query 看不到。
- `superseded` 和 `tombstoned` 文档继续参与 catalog rebuild 与显式 status query。
- Batch 2.5 不保存同一 ID 的历史文件快照；revision/CAS 保护当前 canonical 状态，supersede 通过保留旧 ID 维持跨记录历史。

# Breaking Change Policy

改变 payload required/default fields、transition graph、revision increment、CAS token、tombstone 物理语义或 catalog refresh failure behavior，需要兼容性评估。`purge` 必须另立不可恢复操作契约，不能复用 forget。

# Citations

- Formal Phase 2 plan: `docs/devplan/paradigma_dev_5+.md`
- [Memory document contract](memory-document-contract.md)
- [ADR-014](../decisions/adr-014-canonical-candidate-mutation-lifecycle.md)
