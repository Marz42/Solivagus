---
type: paradigma-contract
title: Stable Memory Query Contract
description: Defines deterministic catalog-backed memory lookup, filters, text modes, one-hop relation expansion, and explainable results.
tags: [contract, memory, query, retrieval, sqlite, fts5]
timestamp: 2026-07-24T02:25:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: evolving
  update_policy: requires-human-confirmation
  epistemic_status: confirmed
  contract_kind: application-api
  retrieval_hints:
    zh:
      - Memory Query 查询契约
      - 稳定查询排序
      - 一跳关系扩展
    en:
      - memory query contract
      - deterministic retrieval order
      - one-hop relation expansion
  symbols:
    - MemoryQuery
    - MemoryResult
    - CatalogQuery
    - CatalogTextMode
    - SQLiteMemoryCatalog.query
    - query_memories
  relations:
    depends_on:
      - /contracts/catalog-contract.md
      - /decisions/adr-013-deterministic-catalog-query.md
    constrains:
      - /contracts/repository-contract.md
      - /contracts/memory-explain-contract.md
---

# Scope

本契约覆盖 Phase 2 Batch 2.4 的领域中立查询：memory ID、canonical path、keyword、FTS、tag、scope、status、inclusive validity 和 outgoing relation 一跳扩展。它不定义 CLI、embedding、向量检索、LLM reranking、自动 chunk 或多跳图推理。

# Contract

`MemoryQuery` 保持存储无关，承载 text、memory IDs、tags、scope、statuses、valid_at、relation types、expansion 开关和总 limit。`CatalogQuery` 仅在 catalog 边界补充 repository-relative paths 与 `keyword|fts` text mode。所有直接选择器按 AND 组合；多个 ID/path 是各自集合内 OR，多个 tag 和 scope entity IDs 必须全部满足。

普通 query 的 status 默认严格为 `active`。Validity 只在提供 timezone-aware `valid_at` 时按闭区间求值；`valid_from` 或 `valid_until` 为空代表该方向无界。Scope 必须匹配 namespace，query 中非空 workspace/project/task/session 字段是精确约束，entity IDs 使用子集语义。

Canonical candidate、superseded、expired、rejected 和 tombstoned 只有在 caller 显式传入对应 statuses 时才可返回；普通 query 不得因 relation expansion 绕过 status filter。

## Text modes

- `keyword`：对 title、派生 description、content、tags 做 Unicode `casefold` 后的 literal substring 匹配，不解释查询语法。
- `fts`：把 text 作为 SQLite FTS5 expression，在 unicode61 projection 上检索；非法表达式以 `PD_CATALOG_QUERY_ERROR` 明确失败。

FTS 的 matched fields 来自各 column 的实际 highlight，不把未命中的字段写入解释。Keyword score 为匹配字段数；FTS score 为非负的 `-bm25`。无 text 的结构化结果不设置 score。

## Ordering and relation expansion

直接结果按 score 降序、memory ID 升序稳定排序；无 text 时等价于 memory ID 升序。Relation expansion 必须显式启用，只沿直接结果自身声明的 outgoing relation 走一跳。Related 结果排在全部直接结果之后，按 direct source order、target memory ID、relation type 排序；同一 target 首次出现后去重。

Related target 继续受 status、scope 和 valid_at 约束，但不要求再次匹配 direct ID/path/text/tag selectors。扩展结果记录 `relation_source_id` 与 `relation:<type>`，不会递归扩展。`limit` 作用于 direct + related 的最终序列。

# Request Schema

```python
CatalogQuery(
    memory=MemoryQuery(...),
    paths=("memory-bank/memories/MEM-....md",),
    text_mode=CatalogTextMode.FTS,
)
```

Path 必须是无 traversal、无反斜杠的 canonical repository-relative POSIX path。Query 前 catalog 必须完整通过 canonical verification；缺失、损坏或漂移均拒绝查询并要求 rebuild。

# Response Schema

`SQLiteMemoryCatalog.query` 与 Application API `query_memories` 返回 `tuple[MemoryResult, ...]`。每个 result 包含 canonical `MemoryRecord`，以及适用的 score、matched fields、match reasons、relation source 和 warnings。结果不得从 SQLite 反向修改或修复 Markdown。

Public `pd memory query` 与 rich response projection 由 `memory-explain-contract.md` 定义。非 active 显式结果必须携带 ordinary-query exclusion warning；存在 validity 但未提供 valid_at 时必须说明尚未评估。

# State Transitions

```text
CatalogQuery
  -> verify catalog against canonical Markdown
  -> direct selectors and text match
  -> scope/status/validity evaluation
  -> stable direct ordering
  -> optional outgoing one-hop expansion
  -> stable total limit
  -> explainable MemoryResult tuple
```

# Compatibility Notes

- Batch 2.4 提供 Python Application API，不提前冻结 Batch 2.6 的 `pd memory query/explain` CLI。
- 相同 canonical source、catalog schema 和结构化 request 必须产生相同 ID 顺序、matched fields 与 reasons。
- Ranking 算法、relation 方向、filter composition 或 path canonicalization 的改变属于查询契约变更。

# Breaking Change Policy

改变默认 status、validity 边界、AND/OR 组合、related filter、稳定排序、limit 位置或解释字段，需要兼容性评估和 golden query 更新。未来 embedding/reranking 必须作为新的显式 retrieval mode 引入，不能静默替换现有 keyword/FTS 语义。

# Citations

- Formal Phase 2 plan: `docs/devplan/paradigma_dev_5+.md`
- [Catalog contract](catalog-contract.md)
- [ADR-013](../decisions/adr-013-deterministic-catalog-query.md)
- [Memory Explain contract](memory-explain-contract.md)
