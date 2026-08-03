---
type: paradigma-decision
title: ADR-021 Use a CLI-Driven but Human-Authored Agent Protocol
description: Removes Persona and manual runtime bookkeeping while retaining a small human-authored operating discipline with tested adapter parity.
tags: [adr, agent, protocol, cli, runtime, context]
timestamp: 2026-07-24T02:44:33+08:00
paradigma:
  schema_version: "0.1"
  temperature: cold
  lifecycle: append-only
  update_policy: append-only
  epistemic_status: decision
  status: accepted
  retrieval_hints:
    zh: [Agent Rules 收缩, 移除 Persona, CLI 操作纪律]
    en: [agent rules contraction, remove persona, CLI operation discipline]
  symbols: [AGENT_RULES.md, pd runtime init, agent-operation-protocol.txt]
  relations:
    constrains: [/architecture.md, /domains/protocol.md, /contracts/agent-operation-protocol-contract.md]
    follows: [/decisions/adr-020-deterministic-explainable-context-manifest.md]
---

# Context

旧协议同时承担 Persona、知识教程、手工状态清单和工具说明。它要求 Agent 固定扫描 HOT/index/progress，直接维护 active-task checklist，并调用 legacy archive 脚本。这与 Phase 3 已交付的 YAML facts、Task/Session lifecycle、Checkpoint/handoff 和 deterministic Context Manifest 冲突，也让协议比运行时更容易漂移。

# Decision

1. 删除 Persona；协议只规定事实源边界、最小操作纪律、质量与安全。
2. Task/Session/Checkpoint/Context 等确定性状态交给 `pd`；Agent 不手工编辑 YAML facts 或 generated projections。
3. Read Phase 改为 Task/Session status + structured ContextRequest + Manifest selected documents/reasons，不默认扫描全量 progress logs。
4. Update Phase 用 Checkpoint、Session end 和 terminal Task command 建立可恢复顺序；progress log 降为可选审计交付物。
5. 增加 `pd runtime init`，以 dry-run-first、只补缺失、不覆盖事实、可重试的方式初始化新 workspace。
6. `AGENT_RULES.md` 与 IDE adapters 首期继续人工编写，不立即生成；golden minimal operation set 和 architecture tests 检测关键 parity/旧指令回流。

# Consequences

- Agent 提示更短，状态恢复和上下文选择可验证，不依赖模型记得维护 checklist。
- 新项目无需复制带 placeholder 的 runtime 模板或手工替换时间戳。
- 人类仍可为不同 IDE 压缩表达；代价是完整语义同步仍需评审，测试只锁住最小兼容面。
- Legacy migration 文档可保留为输入说明，但迁移完成后必须进入 CLI/YAML runtime。

# Alternatives Considered

1. 保留 Persona 和旧四阶段全文：拒绝，混淆行为风格与可执行状态协议。
2. 立即从 schema 自动生成所有 IDE instructions：推迟，尚未证明不同 IDE 的表达差异可以无损生成。
3. 继续复制 runtime templates：拒绝，placeholder timestamp 和文件重命名仍要求手工确定性维护。

# Status

Accepted for Phase 3 Batch 3.6 and closes the Phase 3 protocol switch.

# Related Documents

- `docs/devplan/paradigma_dev_5+.md`
- `AGENT_RULES.md`
- `.cursor/rules/memory-bank-protocol.mdc`
- `memory-bank/knowledge/contracts/agent-operation-protocol-contract.md`
