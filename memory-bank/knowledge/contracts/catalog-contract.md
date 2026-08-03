---
type: paradigma-contract
title: Derived SQLite Memory Catalog Contract
description: Defines the rebuildable SQLite and FTS5 catalog schema, source verification, statistics, and canonical-data priority.
tags: [contract, memory, sqlite, fts5, catalog, derived-data]
timestamp: 2026-07-24T00:25:40+08:00
paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: evolving
  update_policy: requires-human-confirmation
  epistemic_status: confirmed
  contract_kind: storage
  retrieval_hints:
    zh:
      - SQLite memory catalog
      - FTS5 派生索引
      - catalog rebuild verify stats
    en:
      - SQLite memory catalog
      - derived FTS5 index
      - catalog rebuild verify stats
  symbols:
    - SQLiteMemoryCatalog
    - CATALOG_SCHEMA_VERSION
    - pd catalog rebuild
    - pd catalog verify
    - pd catalog stats
  relations:
    depends_on:
      - /contracts/memory-document-contract.md
      - /decisions/adr-012-rebuildable-sqlite-catalog.md
    constrains:
      - /contracts/repository-contract.md
      - /contracts/memory-query-contract.md
      - /contracts/memory-mutation-contract.md
---

# Scope

本契约覆盖从 canonical Memory Markdown 派生的本地 SQLite + FTS5 catalog。Catalog 只提供快速检索投影和统计，不是长期知识事实源；删除或损坏后必须能从 Markdown 完整重建。

# Contract

## Paths and versions

- config schema 0.4 默认 `memory_root: memory-bank/memories`。
- 默认 `catalog_path: .paradigma/cache/catalog.sqlite3`，必须位于 ignored/disposable cache 中。
- SQLite 内部 `catalog_schema_version` 首期为 `0.1`，与 distribution、config、OKF、document 和 memory schema version 分离。
- 旧 config 0.3 未声明新路径时使用上述默认值。

## Stored projection

主表保存 memory ID、repository-relative path、title、首个非标题正文摘要、完整 content、memory type、tags JSON、status、完整 scope 与常用 scope columns、validity、confidence、sensitivity、provenance JSON/summary、relations JSON、content/source hash、revision 和 created/updated time。

Catalog 另外维护：

- `memory_tags`：有序 tags 与 tag lookup index；
- `memory_relations`：有序一跳关系与 target lookup index；
- `memory_fts`：memory ID、title、description、content 和 tags 的 FTS5 unicode61 projection；
- `catalog_meta`：catalog schema、canonical source digest 和 record count。

## Rebuild and verification

Rebuild 按 canonical filename 顺序读取并完整验证每个 Markdown 文档，在 catalog 同目录构建临时 SQLite，启用 foreign keys、FULL synchronous 和 integrity check，flush/`fsync` 后 atomic replace。任何失败保留旧 catalog 并清理 SQLite 临时 sidecars。

Verify 不修改 Markdown 或 SQLite。它重新读取 canonical source，并逐项比较 meta、主表、normalized tags、normalized relations 和 FTS rows；不能只信任 catalog 自己保存的 digest。空 memory root 是合法的零记录 catalog。

# Request Schema

```text
pd catalog rebuild [--dry-run] [--format text|json] [--project PATH]
pd catalog verify [--dry-run] [--format text|json] [--project PATH]
pd catalog stats [--dry-run] [--format text|json] [--project PATH]
```

`rebuild --dry-run` 解析并验证全部 canonical Markdown、计算 source digest，但不创建或替换 SQLite 文件。普通 rebuild 发布新 catalog。Verify 和 stats 始终只读。

# Response Schema

Rebuild 返回 catalog path、record count、source digest 和 written。Verify 返回 current、source/catalog counts、digest 与具体 issues。Stats 返回 record/tag/relation counts 以及按 status 和 memory type 的稳定排序计数。

缺失或漂移通过 `PD_CATALOG_DRIFT` 使 verify 非零；读取/Schema 错误使用 `PD_CATALOG_ERROR`，重建 I/O 或 SQLite publication 错误使用 `PD_CATALOG_WRITE_ERROR`。Canonical document/parser/integrity 错误保留原错误码。

# State Transitions

```text
Canonical Markdown set
  -> validate and project in stable order
  -> temporary SQLite + FTS5
  -> integrity check + fsync
  -> atomic replace catalog.sqlite3

Markdown change
  -> catalog verify reports drift
  -> catalog rebuild restores current projection
```

# Compatibility Notes

- Catalog 文件不提交 Git，也不参与 Markdown revision。
- 增加纯派生 column/index 可以升级 catalog schema 后直接 rebuild，不要求修改 canonical documents。
- Query 语义、稳定排序和 relation expansion 由 `memory-query-contract.md` 定义；catalog query 前必须重新验证 canonical freshness。
- Canonical mutation 成功后完整 rebuild catalog；若 refresh 失败，Markdown 保持权威且 query 拒绝 stale catalog，恢复方式是显式 rebuild。
- FTS5 是 Python 3.11+ runtime 的必需 SQLite capability；缺失时 rebuild 明确失败。

# Breaking Change Policy

改变 canonical path 解释、source digest 输入、verify coverage 或现有 query-facing column semantics 需要 catalog schema 和兼容性评估。Catalog schema 改变本身不要求数据迁移，只要旧文件可安全删除重建。

# Citations

- Formal Phase 2 plan: `docs/devplan/paradigma_dev_5+.md`
- [Canonical Memory Markdown contract](memory-document-contract.md)
- [ADR-012](../decisions/adr-012-rebuildable-sqlite-catalog.md)
- [Memory Query contract](memory-query-contract.md)
