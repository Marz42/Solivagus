---
type: paradigma-decision
title: ADR-012 Keep SQLite and FTS5 Strictly Rebuildable from Markdown
description: Adopts an atomic derived SQLite catalog whose complete searchable state is verified against canonical memory documents.
tags: [adr, memory, sqlite, fts5, catalog, derived-data]
timestamp: 2026-07-24T00:25:40+08:00
paradigma:
  schema_version: "0.1"
  temperature: cold
  lifecycle: append-only
  update_policy: append-only
  epistemic_status: decision
  status: accepted
  retrieval_hints:
    zh:
      - SQLite catalog 派生边界
      - FTS5 重建
      - canonical Markdown 优先
    en:
      - derived SQLite catalog
      - FTS5 rebuild
      - canonical Markdown priority
  symbols:
    - SQLiteMemoryCatalog
    - catalog.sqlite3
    - CATALOG_SCHEMA_VERSION
  relations:
    constrains:
      - /architecture.md
      - /conventions.md
      - /contracts/catalog-contract.md
      - /contracts/repository-contract.md
    follows:
      - /decisions/adr-011-canonical-memory-markdown-store.md
---

# Context

Canonical Markdown 适合人工审阅和 Git history，但不适合高频全文、scope、status、validity 和 relation 查询。SQLite/FTS5 可以提供确定性本地查询，却容易在增量更新失败、数据库损坏或人工编辑 Markdown 后与事实源漂移。

# Decision

1. SQLite catalog 永远是 ignored、可删除、可完整重建的派生物；canonical Markdown 优先。
2. config schema 0.4 明确 `memory_root` 与 `catalog_path`，旧配置缺字段时使用安全默认值；canonical root 不得位于 disposable cache，catalog 必须位于 cache。
3. rebuild 不在现有数据库上逐行修改，而是在同目录生成完整临时数据库，完成 foreign-key/SQLite integrity 验证和 `fsync` 后 atomic replace。
4. 主表保存完整 query projection；tags 与 relations 同时规范化，title/description/content/tags 写入 FTS5。
5. verify 从 Markdown 重新生成期望 projection，比较 meta、主表、tag/relation tables 和 FTS rows。数据库内部 digest 只是快速证据，不能代替源对比。
6. `pd catalog rebuild/verify/stats` 通过同一 Application API 暴露 text/JSON/dry-run 契约；CI 在运行主门禁前 rebuild，并单独 verify。
7. Batch 2.3 不实现 retrieval ranking，也不允许 catalog 反向修改 Markdown。

# Consequences

- catalog 损坏、丢失或 schema 升级可通过一次 rebuild 恢复，无需数据迁移或回滚 canonical 文件。
- rebuild 成本与 canonical record 数量线性相关；首期用全量重建换取简单、可证明的一致性。
- FTS5 成为 runtime SQLite 的必需能力；不支持时会在临时构建阶段明确失败，旧 catalog 不受影响。
- 未来增量更新只能作为保持同一验证语义的优化，不能改变 Markdown-first recovery 原则。

# Alternatives Considered

1. SQLite 作为主存储：拒绝，降低人工可读性、Git diff 和离线修复能力。
2. 原地清表再重建：拒绝，失败时会留下空或半成品 catalog。
3. 只比较 record count 和 source digest：拒绝，catalog rows 或 FTS projection 可在 meta 未变化时损坏。
4. 立即做增量 catalog update：推迟，mutation lifecycle 尚未稳定，全量重建更易验证。
5. 引入外部搜索服务或向量数据库：拒绝，超出 Phase 2 的确定性本地检索目标。

# Status

Accepted for Phase 2 Batch 2.3.

# Related Documents

- `docs/devplan/paradigma_dev_5+.md`
- `memory-bank/knowledge/contracts/catalog-contract.md`
- `memory-bank/knowledge/contracts/memory-document-contract.md`
- `src/paradigma/storage/catalog/`
