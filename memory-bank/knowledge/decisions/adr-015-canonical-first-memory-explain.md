---
type: paradigma-decision
title: ADR-015 Explain Canonical Memory Even When the Catalog Is Unavailable
description: Chooses structured explain fields, deterministic query warnings, and canonical-first behavior under catalog drift or corruption.
tags: [adr, memory, explain, query, provenance, resilience]
timestamp: 2026-07-24T04:30:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: cold
  lifecycle: append-only
  update_policy: append-only
  epistemic_status: decision
  status: accepted
  retrieval_hints:
    zh:
      - canonical-first explain
      - 查询排除警告
      - catalog 损坏解释
    en:
      - canonical-first explain
      - query exclusion warning
      - explain with corrupt catalog
  symbols:
    - MemoryExplanation
    - explain_memory
    - memory_query_outcome
    - pd memory explain
  relations:
    constrains:
      - /architecture.md
      - /conventions.md
      - /contracts/memory-explain-contract.md
    follows:
      - /decisions/adr-014-canonical-candidate-mutation-lifecycle.md
---

# Context

Batch 2.4 已产生结构化 MemoryResult，Batch 2.5 已形成 mutation 闭环，但用户还需要知道为何命中、为何普通查询排除、记录来自哪里，以及 catalog 故障是否影响 canonical truth。若 explain 依赖可用 catalog，最需要诊断 drift/corruption 时反而无法查看记录。

# Decision

1. Query adapter 完整投影结构化 MemoryResult 和 MemoryRecord，不生成不可审计的自由文本理由。
2. 非 active 显式结果携带 ordinary-query exclusion warning；未提供 valid_at 时只警告 validity 未评估，不注入当前时间改变确定性。
3. Explain 以 canonical Markdown 为第一输入，返回 scope、validity、status、provenance、confidence、relations、hashes 和 revision。
4. Explain 对 catalog 只做 best-effort verification。缺失、损坏或 drift 进入 catalog issues/warnings，但有效 canonical record 仍成功返回。
5. Explain 可使用显式 `--at` 或当前时间评估 validity；该 evaluation 只影响 explain 字段，不改变稳定 query 行为。
6. Query 继续 strict freshness：catalog 不 current 时明确失败，因为排序/命中依赖派生 projection。
7. Public CLI 与 Python Application API 使用同一结果构造逻辑，text 只是 JSON/object outcome 的 adapter view。

# Consequences

- 用户在 catalog 故障期间仍能审计单条 canonical record，并获得明确恢复方向。
- Query response 较大，但完整事实和解释字段支持后续 MCP adapter 无需复制业务逻辑。
- “当前是否有效”与“相同 query 是否稳定”被明确分离：前者属于 explain time，后者只由显式 structured query 决定。
- 自然语言总结或 LLM explanation 后续只能建立在这些字段之上。

# Alternatives Considered

1. Explain 只读取 catalog：拒绝，因为派生层损坏会遮蔽 canonical truth。
2. Query 默认使用当前时间过滤 validity：拒绝，因为相同结构化 request 随时间产生不同结果。
3. 只返回一段自然语言：拒绝，因为 adapter、测试和审计无法验证字段完整性。
4. Catalog stale 时继续 query 并加 warning：拒绝，因为 warning 不能修复错误命中或漏召回。

# Status

Accepted for Phase 2 Batch 2.6.

# Related Documents

- `docs/devplan/paradigma_dev_5+.md`
- `memory-bank/knowledge/contracts/memory-explain-contract.md`
- `memory-bank/knowledge/contracts/memory-query-contract.md`
- `memory-bank/knowledge/contracts/memory-mutation-contract.md`
