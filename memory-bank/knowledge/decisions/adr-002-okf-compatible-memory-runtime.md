---
type: paradigma-decision
title: ADR-002 Adopt OKF-Compatible Memory Runtime Structure
description: Decision to evolve Paradigma into a runtime/logs/knowledge OKF-compatible Agent Memory Runtime.
tags: [adr, okf, memory-runtime]
timestamp: 2026-07-04T22:38:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: cold
  lifecycle: append-only
  update_policy: append-only
  epistemic_status: decision
  status: accepted
  retrieval_hints:
    zh:
      - OKF 迁移
      - runtime logs knowledge
      - 三态结构
    en:
      - OKF migration
      - runtime logs knowledge
      - three-state memory
  relations:
    constrains:
      - /architecture.md
      - /contracts/repository-contract.md
---

# Context

Paradigma 已完成空模板与项目运行记忆拆分，但长期知识、运行状态和日志仍需要更明确的语义边界。用户确认以 RFC 草案为纲推进 OKF 迭代，并要求将草案本身作为 OKF 文档纳入 `docs/rfc/`。

# Decision

采用 runtime/logs/knowledge 三态结构：

- `memory-bank/runtime/` 存放当前运行状态。
- `memory-bank/logs/` 存放 session progress 和 changelog。
- `memory-bank/knowledge/` 存放长期 OKF-compatible concept 文档。
- `docs/rfc/` 存放 Paradigma 自身的 OKF-compatible RFC 文档。
- `.paradigma/tools/` 存放最小确定性工具链。

# Consequences

- Agent 的 Read Phase 从读取平铺 HOT 文件改为读取 active task、knowledge index 和 HOT knowledge。
- 长期知识必须具备 OKF frontmatter 和非空 `type`。
- 运行状态不再污染长期知识 bundle。
- 后续可以逐步增强 link check、archive、compact、schema validation 等工具。

# Alternatives Considered

- 继续沿用平铺 `memory-bank/*.md`：迁移成本最低，但无法表达 OKF knowledge bundle 边界。
- 一次实现完整 RFC 工具链：目标完整，但会显著增加本轮改造范围和风险。

# Status

Accepted.

# Related Documents

- `docs/rfc/paradigma-okf-compatible-runtime.md`
- `memory-bank/knowledge/architecture.md`
- `memory-bank/knowledge/contracts/repository-contract.md`
