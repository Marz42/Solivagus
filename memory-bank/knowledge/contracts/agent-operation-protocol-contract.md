---
type: paradigma-contract
title: Agent Operation Protocol Contract
description: Defines the minimal CLI-driven discipline for Coding runtime recovery, deterministic context, execution, and handoff.
tags: [contract, agent, protocol, cli, context, runtime]
timestamp: 2026-07-24T02:44:33+08:00
paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: evolving
  update_policy: requires-human-confirmation
  epistemic_status: confirmed
  contract_kind: agent-operation
  retrieval_hints:
    zh: [Agent 最小操作契约, CLI 驱动协议, 状态禁止手工维护]
    en: [agent minimal operations, CLI-driven protocol, no manual runtime state]
  symbols: [AGENT_RULES.md, pd task status, pd context build, pd session checkpoint]
  relations:
    depends_on:
      - /contracts/coding-task-lifecycle-contract.md
      - /contracts/coding-session-checkpoint-contract.md
      - /contracts/coding-context-contract.md
    constrains: [/domains/protocol.md, /architecture.md]
---

# Scope

本契约覆盖 Coding profile 的 Agent 操作纪律和协议文档 parity，不定义模型 Persona，也不将协议语义放入 Memory Kernel。

# Contract

1. Task/Session/Checkpoint YAML 是 runtime facts；`active-task.md`、`handoff.md` 和 Context Manifest 是 generated projections。
2. 确定性操作通过 `pd task/session/handoff/context/runtime/catalog/index/check` 执行。Mutation 默认 dry-run，只有显式 `--write` 才可持久化。
3. Agent 不得直接编辑 runtime YAML、Checkpoint、generated projections、generated index block 或 machine cache。
4. Bootstrap 使用 `pd runtime init`；该命令只补充缺失的 null pointers、重建投影、不覆盖既有 runtime facts，并可重试。
5. 新 Session 运行 Task/Session status 后构建并验证 Context Manifest，只读取 selected documents/reasons；progress logs 仅用于历史审计或故障调查。
6. 可恢复边界写 append-only Checkpoint；结束工作先 end Session，完成 Task 时再执行 terminal Task transition。
7. 协议源与 IDE adapter 首期人工维护，但必须共享 golden minimal operation set，并由 architecture test 阻止旧式手工状态指令回流。

# Public Commands

```text
pd runtime init [--write]
pd task status/start/.../complete
pd session status/start/checkpoint/end
pd context build/verify
pd runtime rebuild/verify
pd catalog rebuild/verify
pd index rebuild/verify
pd check
```

# Request Schema

Agent 将用户意图转成明确的 Task/Session lifecycle arguments 与 `ContextRequest(intent, task_id, paths, symbols, keywords, budget_tokens)`。写操作必须先提交无 `--write` 的 preview；确认后使用同一 identity/scope 参数显式写入。

# Response Schema

所有 `pd` 命令返回统一 `CommandOutcome` text/JSON projection。Agent 必须根据 `ok`、`changed`、`dry_run`、diagnostics 和 Context selected/excluded reasons 决策，不从自然语言投影猜测事实。

# State Transitions

```text
no runtime -> runtime init preview -> null pointers + projections
no task -> task start preview/write -> active task
active task -> session start -> checkpoints -> session end
ended session + finished work -> task complete
source/projection drift -> verify failure -> rebuild -> verify
```

# Compatibility Notes

- 删除 Persona 不影响 runtime/schema/API compatibility。
- 将手工 Markdown 状态维护切换为 CLI 是协议行为变更；旧模板仍可作为迁移输入，但不得复制到新 runtime 作为事实源。
- 完全自动生成 Agent rules、改变 minimal operation set 或允许覆盖既有 runtime facts，均需新的兼容性评估。

# Verification

- `tests/golden/agent-operation-protocol.txt` 固定最小命令集合。
- `tests/architecture/test_agent_protocol.py` 检查 source/adapter parity、Bootstrap 使用 CLI，以及工作模式不再要求手工 HOT/runtime 扫描。
- runtime init 的 dry-run、幂等与部分初始化恢复由 integration/failure-injection tests 覆盖。

# Breaking Change Policy

改变 CLI command meaning、mutation default、generated boundary、Task/Session terminal order、runtime init overwrite policy 或 minimal-operation golden set 都需要协议兼容性与 SemVer 评估。

# Citations

- `docs/devplan/paradigma_dev_5+.md` Phase 3 Batch 3.6。
- `memory-bank/knowledge/decisions/adr-021-cli-driven-human-authored-agent-protocol.md`。
