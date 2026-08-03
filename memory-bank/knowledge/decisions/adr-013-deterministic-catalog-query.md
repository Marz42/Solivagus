---
type: paradigma-decision
title: ADR-013 Use Deterministic Catalog-Backed Memory Queries
description: Fixes structured filter composition, text modes, stable ordering, catalog freshness, and one-hop relation semantics.
tags: [adr, memory, query, retrieval, sqlite, fts5]
timestamp: 2026-07-24T02:25:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: cold
  lifecycle: append-only
  update_policy: append-only
  epistemic_status: decision
  status: accepted
  retrieval_hints:
    zh:
      - 稳定 Memory Query 决策
      - keyword 与 FTS
      - relation 一跳扩展
    en:
      - deterministic memory query
      - keyword and FTS retrieval
      - one-hop relation query
  symbols:
    - CatalogQuery
    - CatalogTextMode
    - SQLiteMemoryCatalog.query
    - query_memories
  relations:
    constrains:
      - /architecture.md
      - /conventions.md
      - /contracts/memory-query-contract.md
    follows:
      - /decisions/adr-012-rebuildable-sqlite-catalog.md
---

# Context

Batch 2.3 建立了可删除重建的 SQLite/FTS5 projection，但没有固定 path/text 查询、组合过滤、排序和 relation expansion 语义。若 adapter 各自拼 SQL，默认状态、有效期边界、FTS 解释和结果次序会产生不可审计的差异。

# Decision

1. `MemoryQuery` 继续保持存储无关；catalog-specific `CatalogQuery` 只补充 canonical paths 和明确的 `keyword|fts` mode。
2. 查询必须先完整 verify catalog 对 canonical Markdown 的一致性。缺失、损坏或漂移拒绝服务，不返回可能过期的派生结果。
3. Direct selectors 使用 AND composition；statuses 默认只有 active；validity 是显式、timezone-aware 的闭区间过滤；scope 非空字段精确匹配，entity IDs 为子集约束。
4. Keyword 使用 literal Unicode casefold substring；FTS 使用明确的 SQLite FTS5 expression，并从 column highlight 产生 matched fields。
5. Direct 结果按 score 降序、memory ID 升序；related 结果在 direct 之后稳定排列。相同结构化 query 必须生成相同顺序和解释。
6. Relation expansion 仅 outgoing、opt-in、最多一跳。Target 继续受 status/scope/validity 约束，但不重新套用 direct ID/path/text/tag selectors。
7. Batch 2.4 只发布 object-returning Python Application API；CLI 与更完整 explain adapter 留给 Batch 2.6。

# Consequences

- 查询安全优先于当前规模下的极致性能；每次查询会验证 canonical/catalog 一致性，后续只能以保持相同失败语义的 snapshot/version 机制优化。
- Raw FTS5 expression 支持 phrase、boolean、prefix 等能力，同时非法语法稳定失败；literal 用户输入可选择 keyword mode。
- Outgoing-only 保持 `MemoryRelation` 的声明方向和 `relation_source_id` 含义清晰；需要 inbound 或多跳时必须显式扩展契约。
- Catalog 永远不能成为修复 canonical Markdown 的来源。

# Alternatives Considered

1. 把 path 和 FTS mode 放进 `MemoryQuery`：拒绝，因为会把 repository/SQLite 细节泄漏到 Kernel。
2. Query 时只信 catalog digest：拒绝，因为 canonical Markdown 可能在 rebuild 后变化。
3. 默认双向或递归关系扩展：拒绝，因为结果规模、权限边界和解释来源会变得不稳定。
4. 依赖 SQLite 隐式 row order：拒绝，因为相同 query 的顺序没有契约保证。

# Status

Accepted for Phase 2 Batch 2.4.

# Related Documents

- `docs/devplan/paradigma_dev_5+.md`
- `memory-bank/knowledge/contracts/memory-query-contract.md`
- `memory-bank/knowledge/contracts/catalog-contract.md`
- `memory-bank/knowledge/decisions/adr-010-stable-memory-domain-values.md`
