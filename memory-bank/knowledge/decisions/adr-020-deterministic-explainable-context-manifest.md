---
type: paradigma-decision
title: ADR-020 Build Coding Context Deterministically from Canonical Sources
description: Makes ContextRequest model-plannable but Context retrieval model-free, explainable, budgeted, and bound to exact repository state.
tags: [adr, coding, context, retrieval, manifest, deterministic, budget]
timestamp: 2026-07-24T02:30:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: cold
  lifecycle: append-only
  update_policy: append-only
  epistemic_status: decision
  status: accepted
  retrieval_hints:
    zh: [Coding Context Builder, Context Manifest 选择理由, 确定性上下文预算]
    en: [coding context builder, explainable context manifest, deterministic context budget]
  symbols: [ContextRequest, ContextManifest, build_context_manifest, pd context build]
  relations:
    constrains: [/architecture.md, /contracts/coding-context-contract.md]
    follows: [/decisions/adr-019-append-only-checkpoints-and-last-session-handoff.md]
---

# Context

Task/Session/Checkpoint 已能恢复运行状态，但 Agent 仍需自行扫描 HOT 文档、相关 contracts 和 Memory。若由模型直接挑选文档，同一请求会随模型、提示或会话上下文改变；若一律加载全部知识，长期规模和 token 成本都不可控。

# Decision

1. Query planning 可以由 Agent/LLM 产生结构化 `ContextRequest`；正式 retrieval execution 只接受显式 task、path、symbol、keyword 和 token budget，不调用模型、embedding 或 reranker。
2. Builder 同时读取 canonical OKF knowledge 与 canonical Memory。HOT knowledge 和 `mandatory` Memory 是 mandatory stage；Memory catalog 必须 current，status/scope/validity 继续服从 Memory contract。
3. 顺序固定为 mandatory → path → symbol → keyword → scope/validity filter → outgoing one-hop relation → deduplicate → budget trim。
4. HOT、显式 path 和显式 symbol 是 `required`，即使超预算也不静默删除；keyword 和 relation 可被裁剪。每个 selected/excluded 项都保留稳定理由。
5. Memory scope 按 coding global→workspace→repository→task→session 层级兼容；非空 scope 字段必须等于当前 Task/Session。Validity 使用 Task snapshot 的 `updated_at`，禁止注入 wall clock。
6. token estimate 固定为 canonical UTF-8 exact bytes 的 `ceil(bytes/4)`。它是可复现预算近似，不声称等于任一模型 tokenizer。
7. Manifest 保存完整 Request、source digest、estimated tokens、选择项、排除项、warnings 和 payload checksum。相同 Request 与相同 canonical/runtime state 必须产生 exact 相同 YAML。
8. `runtime/context-manifest.yaml` 是 atomic replace 的 derived projection；损坏可由 `pd context build --write` 覆盖重建，`pd context verify` 检查当前状态。

# Consequences

- 新 Session 只需消费 bounded Manifest，不再由模型递归扫描全部 knowledge 或 progress logs。
- 显式输入不会因预算被悄悄丢弃；required over-budget 会产生 warning，调用方可增大预算或缩小请求。
- 任一 canonical knowledge、Memory、Task、Session 或 Checkpoint 改变都会改变 source digest；verify 能发现陈旧 Manifest。
- 当前 catalog/query contract 单次上限为 1000 条 Memory；超过时明确失败，不截断后伪装为完整结果。

# Alternatives Considered

1. 让 LLM 直接选择和排序文件：拒绝，无法稳定复现，也无法提供可信 checksum。
2. 只使用 HOT knowledge：拒绝，忽略 path/symbol、task-scoped Memory 和关系证据。
3. required 项也硬裁剪：拒绝，显式用户信号和基础契约可能静默消失。
4. 使用当前时间做 validity：拒绝，同一 Request 会随运行时刻漂移。
5. 首期引入 embedding：拒绝，尚无 measured recall failure 证明其必要性。

# Status

Accepted for Phase 3 Batch 3.5.

# Related Documents

- `docs/devplan/paradigma_dev_5+.md`
- `memory-bank/knowledge/contracts/coding-context-contract.md`
- `memory-bank/knowledge/contracts/memory-query-contract.md`
- `memory-bank/knowledge/known-issues/session-context-fragmentation.md`
