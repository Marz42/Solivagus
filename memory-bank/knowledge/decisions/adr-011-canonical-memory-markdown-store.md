---
type: paradigma-decision
title: ADR-011 Use Canonical Markdown with Semantic and Source Hashes
description: Adopts a deterministic one-record Markdown codec and atomic compare-and-swap filesystem store for canonical memory.
tags: [adr, memory, markdown, storage, integrity, revision]
timestamp: 2026-07-24T00:07:33+08:00
paradigma:
  schema_version: "0.1"
  temperature: cold
  lifecycle: append-only
  update_policy: append-only
  epistemic_status: decision
  status: accepted
  retrieval_hints:
    zh:
      - canonical Markdown store
      - 双哈希修改检测
      - revision 原子写入
    en:
      - canonical Markdown store
      - semantic and source hashes
      - atomic revision update
  symbols:
    - MemoryMarkdownCodec
    - MarkdownMemoryStore
    - content_hash
    - source_hash
  relations:
    constrains:
      - /architecture.md
      - /conventions.md
      - /contracts/memory-document-contract.md
      - /contracts/repository-contract.md
    follows:
      - /decisions/adr-010-stable-memory-domain-values.md
---

# Context

Phase 2 需要让 Markdown 成为唯一长期记忆事实源，同时保持人工可读、Git diff 清晰、SQLite 可重建和并发写入不静默覆盖。只校验正文或只比较业务字段都无法发现 YAML 元数据、换行、BOM 或排版被外部修改；只对整文件做 hash 又会让无语义的排版变化破坏 record identity。

# Decision

1. 一个 canonical Markdown 文件表示一个 MemoryRecord，文件名由 memory ID 决定；v0.1 frontmatter 使用 exact-key Schema，正文直接保存 record content。
2. codec 通过稳定排序、无空白差异的 UTF-8 JSON 计算 semantic `content_hash`，覆盖全部 MemoryRecord 字段而不覆盖 YAML 表达细节；datetime 统一为 UTC，confidence 统一为 JSON number。
3. store 读取时另计算 exact-byte `source_hash`。更新者必须提交先前读取的 source hash，store 在 managed-writer lock 内重新读取并比较后才发布新 revision。
4. 创建只接受 revision 1；更新只接受当前 revision `+1`，保持 memory ID 与 created_at，并拒绝倒退的 updated_at。
5. 文件发布复用同目录临时文件、flush、`fsync` 和 atomic create/replace。失败保留旧 canonical 文件并清理临时文件。
6. 格式不同但 semantic hash 正确的文档允许读取并标为 noncanonical；持有当前 source hash 的下一次更新可将其规范化。
7. legacy concept documents 不进入该 codec；兼容 view 与迁移另批实现。

# Consequences

- 语义完整性、原始文件并发状态与 canonical formatting 被清楚分离。
- 人工修改可以被验证，但修改语义字段后必须同步 content hash；未来 `pd memory validate/commit` 将提供正式工作流。
- managed writers 由 lock file 串行化；不自动清除残留锁，避免把仍在工作的进程误判为 stale。
- v0.1 exact-key Schema 便于尽早发现漂移，但任何字段扩展都要显式升级 memory schema。

# Alternatives Considered

1. 只 hash Markdown 原始字节：拒绝，因为 YAML 排版变化会被误认为 MemoryRecord 语义变化。
2. 只 hash 正文：拒绝，因为 scope、status、provenance、revision 等关键元数据可被无痕修改。
3. 更新时无 expected hash 直接 atomic replace：拒绝，因为 atomicity 不等于并发安全，会覆盖人工或另一个进程的修改。
4. 首期把每个 revision 存在同一文档：拒绝，违背已确认的文档级记忆和清晰 Git history 决策。
5. 直接把 legacy concept schema 当 canonical memory schema：拒绝，两者生命周期和必填字段不同，会把集成适配语义注入 storage。

# Status

Accepted for Phase 2 Batch 2.2.

# Related Documents

- `docs/devplan/paradigma_dev_5+.md`
- `memory-bank/knowledge/contracts/memory-document-contract.md`
- `memory-bank/knowledge/decisions/adr-010-stable-memory-domain-values.md`
- `src/paradigma/storage/markdown/`
