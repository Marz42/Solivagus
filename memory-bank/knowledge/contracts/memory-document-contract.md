---
type: paradigma-contract
title: Canonical Memory Markdown Contract
description: Defines the v0.1 one-record-per-document schema, hashes, revision checks, and atomic filesystem store behavior.
tags: [contract, memory, markdown, storage, integrity]
timestamp: 2026-07-24T00:07:33+08:00
paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: evolving
  update_policy: requires-human-confirmation
  epistemic_status: confirmed
  contract_kind: storage
  retrieval_hints:
    zh:
      - canonical Memory Markdown
      - 记忆文档 Schema
      - content hash 与手工修改
    en:
      - canonical memory Markdown
      - memory document schema
      - content hash and manual edits
  symbols:
    - MemoryMarkdownCodec
    - MarkdownMemoryStore
    - StoredMemory
    - memory_schema_version
  relations:
    depends_on:
      - /decisions/adr-010-stable-memory-domain-values.md
      - /decisions/adr-011-canonical-memory-markdown-store.md
    constrains:
      - /contracts/repository-contract.md
      - /contracts/catalog-contract.md
      - /contracts/memory-mutation-contract.md
---

# Scope

本契约覆盖 MemoryRecord 的 canonical Markdown 表达和本地原子文件 store。首期一个受管理 Markdown 文件只表示一个 MemoryRecord；legacy knowledge 文档不自动重写，由未来兼容 adapter 提供 MemoryRecord view。

# Contract

## Document identity

- 文件名固定为 `<memory_id>.md`，例如 `MEM-01J....md`。
- frontmatter `type` 固定为 `paradigma-memory`。
- `memory_schema_version` 首期固定为字符串 `0.1`，与 distribution、OKF 和现有 concept-document schema version 相互独立。
- canonical 文本使用 UTF-8 无 BOM、LF、frontmatter 后一个空行和文件末尾一个 LF。

## Frontmatter fields

v0.1 要求且只接受以下顶层字段：

| Field | Shape | Meaning |
|---|---|---|
| `type` | string | 固定 `paradigma-memory` |
| `memory_schema_version` | string | 固定 `0.1` |
| `memory_id`, `memory_type`, `title` | string | Kernel identity and type |
| `status` | string | MemoryStatus value |
| `revision` | integer | 从 1 开始；store update 严格递增 1 |
| `scope` | mapping | namespace、workspace/project/task/session ID、entity IDs |
| `provenance` | list of mappings | 完整 ProvenanceRef 列表 |
| `validity` | mapping | `from` / `until` ISO 8601 time or null |
| `confidence` | number or null | Kernel confidence |
| `sensitivity` | string | Sensitivity label |
| `tags` | list of strings | Ordered unique tags |
| `relations` | list of mappings | relation type and target memory ID |
| `created_at`, `updated_at` | ISO 8601 string | UTC-normalized timestamps |
| `content_hash` | string | `sha256:` + 64 lowercase hex digits |

Markdown body is the MemoryRecord `content`. Nested mappings also use exact v0.1 key sets; unknown and missing fields fail Schema validation. YAML syntax, duplicate-key and encoding errors retain shared parser diagnostic codes.

## Integrity and manual edits

`content_hash` is SHA-256 over deterministic UTF-8 JSON containing every MemoryRecord semantic field, including body content, but excluding YAML formatting, document type/schema fields and the hash itself. Datetimes normalize to UTC and confidence normalizes to a JSON number so equivalent values have the same digest. A semantic edit without a matching hash fails with `PD_MEMORY_INTEGRITY_ERROR`.

`source_hash` is SHA-256 over the exact source bytes and is returned in `StoredMemory` rather than written into the document. Update requires the caller's previously observed `source_hash`; BOM, line-ending or YAML-format-only changes therefore produce `PD_MEMORY_CONFLICT` instead of being silently overwritten.

# Request Schema

`MemoryMarkdownCodec` provides deterministic `encode(record)`, validated `decode(text)`, `inspect(text)`, `content_hash(record)` and source-hash operations.

`MarkdownMemoryStore` provides:

- `read(memory_id)` — validate filename, schema and both integrity boundaries;
- `create(record)` — require revision 1 and atomically create without overwrite;
- `update(record, expected_source_hash=...)` — serialize managed writers, compare exact source state, require revision `+1`, preserve `created_at`, then atomically replace;
- `paths()` — return sorted canonical-ID Markdown paths and ignore unmanaged files.

# Response Schema

`StoredMemory` returns the immutable MemoryRecord, semantic `content_hash`, exact-byte `source_hash`, canonical path and a `canonical` flag. A valid but noncanonical document remains readable; writing it with the current source hash canonicalizes its representation.

Stable storage errors include `PD_MEMORY_SCHEMA_ERROR`, `PD_MEMORY_INTEGRITY_ERROR`, `PD_MEMORY_CONFLICT`, `PD_MEMORY_NOT_FOUND` and `PD_MEMORY_STORAGE_ERROR`. Shared parser and atomic writer failures preserve their existing structured codes.

# State Transitions

```text
missing + revision 1
  -> atomic create
  -> stored revision 1

read source hash H + next revision
  -> exclusive managed-writer lock
  -> re-read and compare H
  -> atomic replace
  -> stored revision N+1
```

Replace failure preserves the previous bytes and removes temporary/lock artifacts. A surviving lock is not automatically broken because ownership and process liveness cannot be inferred safely.

# Compatibility Notes

- Reordering YAML or changing quoting is semantically compatible but marks the document noncanonical and changes `source_hash`.
- Adding a new optional field still requires a new `memory_schema_version`, because v0.1 uses exact key sets.
- Existing legacy documents are outside this codec and remain readable through a future compatibility adapter.
- SQLite catalog content is derived under `catalog-contract.md` and is not part of this canonical contract.
- Candidate、active、superseded 与 tombstoned records 均使用同一 canonical document/store contract；lifecycle transition 由 `memory-mutation-contract.md` 约束。

# Breaking Change Policy

Changing document identity, hash input, required fields, body semantics, revision increment, filename mapping or compare-and-swap behavior is compatibility-impacting and requires a schema-version and migration evaluation.

# Citations

- Formal Phase 2 plan: `docs/devplan/paradigma_dev_5+.md` (upstream planning source; not required in derived workspaces)
- [Repository contract](repository-contract.md)
- [ADR-010](../decisions/adr-010-stable-memory-domain-values.md)
- [ADR-011](../decisions/adr-011-canonical-memory-markdown-store.md)
- [Memory mutation contract](memory-mutation-contract.md)
