---
type: paradigma-contract
title: Memory Query and Explain Adapter Contract
description: Defines the public query flags, rich result projection, canonical explain behavior, exclusion warnings, and stale-catalog handling.
tags: [contract, memory, query, explain, cli, provenance]
timestamp: 2026-07-24T04:30:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: evolving
  update_policy: requires-human-confirmation
  epistemic_status: confirmed
  contract_kind: cli-application-api
  retrieval_hints:
    zh:
      - Memory Explain 契约
      - 查询结果解释字段
      - exclusion warnings
    en:
      - memory explain contract
      - query explanation fields
      - exclusion warnings
  symbols:
    - MemoryExplanation
    - explain_memory
    - memory_query_outcome
    - memory_explain_outcome
    - pd memory query
    - pd memory explain
  relations:
    depends_on:
      - /contracts/memory-query-contract.md
      - /contracts/memory-mutation-contract.md
      - /decisions/adr-015-canonical-first-memory-explain.md
    constrains:
      - /contracts/repository-contract.md
---

# Scope

本契约覆盖 Phase 2 Batch 2.6 的 `pd memory query`、`pd memory explain`、rich structured response 和 exclusion warnings。底层检索组合、排序和一跳关系仍由 `memory-query-contract.md` 定义；本契约不引入 embedding、reranking 或多跳推理。

# Contract

`pd memory query` 是 catalog-backed query 的公共 adapter。它接受 text/FTS 或 keyword mode，以及 ID、path、tag、scope、status、validity、relation 和 limit flags。Query 必须拒绝 missing/corrupt/stale catalog，不能从不一致的派生数据返回结果。

每条 query result 必须包含：

- canonical memory ID、type、title、content、path、revision 和 tags；
- match reasons、matched fields 和适用 score；
-完整 scope 与 inclusive validity；
-status、完整 provenance、confidence 与 sensitivity；
-relations 与 relation expansion source；
-exclusion warnings。

显式返回非 active status 时必须警告 `excluded from ordinary queries: status <status>`。若 record 有 validity interval 而 query 未提供稳定的 `valid_at`，必须警告 `validity not evaluated`；系统不得偷偷注入 wall-clock time 破坏相同结构化 Query 的稳定性。

`pd memory explain MEMORY_ID` 直接读取并验证 canonical Markdown，再附加 catalog freshness。即使 catalog 缺失、损坏或漂移，只要目标 canonical record 有效，explain 仍返回事实并在 warnings/catalog issues 中说明派生层问题。Explain 不从 SQLite 修复 Markdown，也不把 catalog failure 当作目标 record 不存在。

# Request Schema

```text
pd memory query [TEXT]
  [--text-mode keyword|fts]
  [--memory-id ID ...] [--path PATH ...] [--tag TAG ...]
  [--scope-namespace NAME] [--workspace-id ID] [--project-id ID]
  [--task-id ID] [--session-id ID] [--entity-id ID ...]
  [--status STATUS ...] [--valid-at ISO_DATETIME]
  [--include-related] [--relation-type TYPE ...] [--limit N]

pd memory explain MEMORY_ID [--at ISO_DATETIME]
```

`--valid-at` 与 `--at` 必须带 timezone。任何其它 scope filter 要求 `--scope-namespace`。Relation type 要求显式 `--include-related`。所有 leaves 支持 `--project`、`--format text|json` 和无副作用 `--dry-run`。

# Response Schema

Query JSON data 为 `{count, results}`，results 顺序就是稳定 retrieval order。Explain JSON data 另外包含 content/source hash、canonical、evaluated_at、ordinary_status_eligible、valid_at_evaluation、catalog_current 和 catalog_issues。

Text output 提供可扫描的 ID/status/title/reason/warning 行；explain 至少显示 ID、status、revision、path、scope、validity、confidence、catalog freshness 和 warnings。Windows redirected stdout 继续使用 UTF-8。

# State Transitions

```text
query request -> current catalog required -> rich MemoryResult projection

explain ID -> canonical read/validate
           -> evaluate status + requested/current explanation time
           -> best-effort catalog verification
           -> canonical facts + freshness/exclusion warnings
```

# Compatibility Notes

- Query 的 `TEXT` 默认解释为 raw FTS5 expression；literal substring 使用 `--text-mode keyword`。
- Explain 的 wall-clock evaluation 只影响 `valid_at_evaluation`/warning，不改变 record 或 query ranking。
- 新增 response 字段可以向后兼容；删除、重命名或改变现有字段语义需要 adapter contract review。

# Breaking Change Policy

改变 query flag mapping、required explanation fields、warning conditions、catalog-stale behavior 或 text/JSON encoding 是兼容性变更。未来模型生成的自然语言解释只能作为附加字段，不能替代结构化事实与 reasons。

# Citations

- Formal Phase 2 plan: `docs/devplan/paradigma_dev_5+.md`
- [Memory query contract](memory-query-contract.md)
- [ADR-015](../decisions/adr-015-canonical-first-memory-explain.md)
