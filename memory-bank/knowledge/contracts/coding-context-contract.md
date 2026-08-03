---
type: paradigma-contract
title: Coding Context Builder and Manifest Contract
description: Defines ContextRequest, deterministic dual-source matching, filtering, relation expansion, budget trim, manifest checksums, and public context commands.
tags: [contract, coding, context, retrieval, manifest, budget, checksum]
timestamp: 2026-07-24T02:30:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: evolving
  update_policy: requires-human-confirmation
  epistemic_status: confirmed
  contract_kind: application-retrieval
  retrieval_hints:
    zh: [Coding Context 契约, ContextRequest Manifest, path symbol keyword 选择理由]
    en: [coding context contract, context request manifest, path symbol keyword reasons]
  symbols: [ContextRequest, ContextDocument, ContextManifest, CodingContextManifestCodec, pd context build]
  relations:
    depends_on:
      - /contracts/memory-query-contract.md
      - /contracts/coding-session-checkpoint-contract.md
      - /decisions/adr-020-deterministic-explainable-context-manifest.md
    constrains: [/architecture.md, /contracts/repository-contract.md]
---

# Scope

本契约覆盖 Phase 3 Batch 3.5 的 Coding `ContextRequest`、OKF knowledge + canonical Memory 双源 retrieval、Manifest YAML、预算和 `pd context build/verify`。它不定义 LLM query planning、prompt 拼装、embedding/reranking、自动 symbol extraction、Research Profile 或多 Agent context merge。

# Contract

Retrieval execution 必须按以下固定顺序运行：

```text
Mandatory Memory/Knowledge
  -> Path Match
  -> Symbol Match
  -> Literal Keyword Match
  -> Status/Scope/Validity Filter
  -> Outgoing One-hop Relation Expansion
  -> Deduplicate
  -> Stable Budget Trim
  -> Context Manifest
```

- knowledge 来源是 configured knowledge roots 中的 canonical concept documents；`temperature: hot` 产生 `mandatory_hot_document`。
- Memory 来源必须通过 current SQLite catalog 的 ordinary active/valid query，再以 canonical Markdown 构建 Manifest；`mandatory` tag 产生 `mandatory_memory`。
- path 对 document path、knowledge path-like symbols 和 `path:` Memory tags 做 canonical prefix match；symbol 对 metadata symbols 和 `symbol:` tags 做 Unicode casefold exact match；keyword 对 title/description/hints/symbols/body/tags 做 casefold literal substring match。
- Memory 的非空 workspace/project/task/session scope 字段必须匹配 requested Task 与当前/last Session；status、scope、validity 或 epistemic filter 必须在 matched excluded item 中给出理由。
- relation expansion 只从 direct eligible items 出发一次，不递归。Identity map 在 expansion 前后去重，并合并稳定排序后的 reasons。
- HOT/path/symbol priority 是 `required`；keyword 是 `relevant`；仅 relation 是 `related`。Required 永不被 budget trim；其他项按 stage、path、identity 稳定排序后纳入。
- token estimate 是 canonical exact UTF-8 bytes 的 `ceil(n/4)`；selected total 必须等于 Manifest `estimated_tokens`。
- source digest 覆盖 catalog digest、全部候选 exact source hashes 和 Task/Session/Checkpoint runtime hashes。Manifest checksum 覆盖除 checksum 本身外的全部字段。

# Request Schema

```python
ContextRequest(
    intent="implement deterministic context",
    task_id="TASK-...",
    explicit_paths=("src/paradigma",),
    explicit_symbols=("ContextRequest",),
    keywords=("context manifest",),
    budget_tokens=12000,
)
```

Intent 和 Task ID 必填；signals 可全部为空，此时只返回 mandatory/related context。Paths 使用无 traversal 的 repository-relative POSIX 形式，signals 不得重复，budget 范围为 1–1,000,000。

```text
pd context build --intent TEXT --task-id TASK-... [--path PATH]...
  [--symbol SYMBOL]... [--keyword WORD]... [--budget N] [--write]
pd context verify
```

Build 默认计算并返回 Manifest 但不写；`--write` 才 atomic publish `memory-bank/runtime/context-manifest.yaml`。相同内容的重复 write 不重写且 `changed=false`；损坏 projection 可由 write 重建。

# Response Schema

Manifest schema 0.1 包含 profile、完整 Request、session/checkpoint IDs、source digest、estimated tokens、documents、excluded、warnings 和 checksum。每个 document 必须有 identity/path/source kind/title/priority/token estimate/reasons；selected/excluded identity 必须唯一且互斥。

Stable errors 包括 `PD_CONTEXT_INPUT_ERROR`、`PD_CONTEXT_TASK_MISMATCH`、`PD_CONTEXT_SESSION_MISMATCH`、`PD_CONTEXT_CATALOG_STALE`、`PD_CONTEXT_CATALOG_LIMIT`、`PD_CONTEXT_MANIFEST_STALE` 及 Coding runtime schema/storage errors。

# State Transitions

```text
canonical knowledge + current catalog/canonical Memory + runtime YAML + ContextRequest
  -> deterministic in-memory Manifest
  -> optional atomic context-manifest.yaml projection
repository state changes
  -> verify stale
same Request + --write
  -> replace derived projection
```

当没有 active Task 时，可为仍存在的 completed/aborted Task snapshot 重建最终 Manifest，并使用属于该 Task 的 `last_session_id`。若另一个 Task active，则拒绝为旧 Task 构建，避免跨焦点污染。

# Compatibility Notes

- 不修改 Memory Kernel；Context values 位于 Coding Integration，Application 才依赖 indexing/storage/runtime。
- 不改变稳定的六项 `pd check` 聚合门禁；`pd context verify` 在 v0.7 前保持显式实验门禁。
- 根 knowledge index 继续是 bounded human navigation；Builder 从 configured roots 读取 canonical concepts，不要求根索引无限扩张。
- 1000 条 Memory 是当前 CatalogQuery contract 的显式边界，首期超限失败而非截断。

# Breaking Change Policy

改变 stage 顺序、mandatory/priority 规则、scope hierarchy、validity clock、token estimate、relation hop 数、budget ordering、source/checksum payload 或 stable reasons/errors 是 breaking。

# Citations

- Formal Batch 3.5: `docs/devplan/paradigma_dev_5+.md`
- [ADR-020](../decisions/adr-020-deterministic-explainable-context-manifest.md)
- [Memory query contract](memory-query-contract.md)
- [Session/Checkpoint contract](coding-session-checkpoint-contract.md)
