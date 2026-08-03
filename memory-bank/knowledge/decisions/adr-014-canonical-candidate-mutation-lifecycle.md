---
type: paradigma-decision
title: ADR-014 Store Candidates Canonically and Mutate with Source-Hash CAS
description: Chooses canonical candidate documents, immutable lifecycle transitions, explicit writes, tombstones, and recoverable catalog refresh.
tags: [adr, memory, mutation, lifecycle, concurrency, tombstone]
timestamp: 2026-07-24T03:35:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: cold
  lifecycle: append-only
  update_policy: append-only
  epistemic_status: decision
  status: accepted
  retrieval_hints:
    zh:
      - canonical candidate 决策
      - memory lifecycle CAS
      - forget tombstone
    en:
      - canonical candidate decision
      - memory lifecycle CAS
      - forget tombstone
  symbols:
    - MemoryTransitionError
    - propose_memory
    - commit_memory
    - revise_memory
    - supersede_memory
    - forget_memory
  relations:
    constrains:
      - /architecture.md
      - /conventions.md
      - /contracts/memory-mutation-contract.md
    follows:
      - /decisions/adr-013-deterministic-catalog-query.md
---

# Context

Batch 2.5 需要把候选、正式记忆、revision、supersede 与 forget 连接成可恢复闭环。若 proposal 只存在于进程内或临时 JSON，跨 session 会丢失；若 update 不绑定已读 bytes，会覆盖人工编辑；若把 SQLite 与 Markdown 当成双写事务，catalog 失败可能诱使系统回滚 canonical truth。

# Decision

1. Proposal 直接保存为 canonical candidate Memory Markdown。Candidate 可审计但默认 query 不可见，commit 通过新 revision 激活。
2. Lifecycle transition 是 Kernel 中的纯函数，返回新的 immutable MemoryRecord；Application 层负责 payload、store CAS、catalog refresh 和 adapter outcome。
3. 所有既有 record mutation 必须提交 validate 返回的 exact-byte source hash，并由 store 在 managed lock 内再次比较。
4. Commit 仅 candidate→active；revise 仅 candidate/active 且要求本 revision provenance；supersede 仅 active→superseded 并追加 outgoing replacement relation；forget 对任何非 tombstone 状态写 tombstone。
5. Mutating CLI 默认 preview，显式 `--write` 才发布。每次 canonical write 后完整 rebuild catalog，以保持后续 query current。
6. Markdown 与 SQLite 不伪装成原子双写。若 catalog refresh 失败，canonical mutation 保持成功并返回专用恢复错误；用户从 Markdown rebuild。
7. Forget 不做物理删除。未来 purge 需要独立的授权、引用完整性和不可恢复风险设计。

# Consequences

- Candidate 跨 session、崩溃和 Git 操作可恢复，但会增加 canonical root 中非 active 文档数量。
- Source-hash CAS 同时检测语义修改和纯格式人工编辑，调用方必须在冲突后重新 validate。
- Full catalog rebuild 成本随 memory 数量增长；当前优先正确性，后续可以在不改变 freshness/failure contract 的前提下优化增量发布。
- 同一 ID 的早期 revision 内容不单独保存；需要完整 revision history 时必须新增 append-only history contract，而不是从 catalog 推断。

# Alternatives Considered

1. Proposal 只输出 stdout 或临时 cache：拒绝，因为 session 中断会丢失尚未 commit 的工作。
2. Propose 直接创建 active：拒绝，因为绕过 validate/commit 和默认查询隔离。
3. Update 自动读取最新 hash、不要求 caller token：拒绝，因为不能证明调用方基于哪个版本做决策。
4. Catalog refresh 失败时回滚 Markdown：拒绝，因为跨文件回滚本身可能失败，且违反 canonical-source priority。
5. Forget 立即 unlink：拒绝，因为首期无法保证 relation/provenance 审计与不可恢复授权。

# Status

Accepted for Phase 2 Batch 2.5.

# Related Documents

- `docs/devplan/paradigma_dev_5+.md`
- `memory-bank/knowledge/contracts/memory-mutation-contract.md`
- `memory-bank/knowledge/contracts/memory-document-contract.md`
- `memory-bank/knowledge/contracts/catalog-contract.md`
