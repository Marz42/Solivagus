---
type: paradigma-domain
title: Protocol Domain
description: CLI-driven Agent operation discipline, IDE adapters, bootstrap prompts, and protocol synchronization rules.
tags: [domain, protocol, agent, cli, context]
timestamp: 2026-07-24T02:44:33+08:00
paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: evolving
  update_policy: agent-editable
  epistemic_status: confirmed
  retrieval_hints:
    zh: [Agent 操作协议, CLI 运行纪律, Context Manifest, 适配器]
    en: [agent operation protocol, CLI discipline, context manifest, adapter]
  symbols: [AGENT_RULES.md, INIT_PROMPT.md, memory-bank-protocol.mdc, pd runtime init]
  relations:
    depends_on: [/architecture.md, /contracts/agent-operation-protocol-contract.md]
    related_to: [/contracts/repository-contract.md, /contracts/coding-context-contract.md]
---

# Responsibility

Protocol Domain 负责 L3 Agent Operation Protocol。它划清 YAML runtime facts、generated projections、长期 knowledge 和审计 logs 的边界，并规定 Agent 如何通过 `pd` 恢复 Task/Session、构建 Context、记录 Checkpoint、验证和交接。

# Public Interfaces

| Artifact | Role | Update Rule |
|----------|------|-------------|
| `AGENT_RULES.md` | IDE-agnostic 协议真相源 | 先修改；首期人工维护 |
| `.cursor/rules/memory-bank-protocol.mdc` | Cursor always-on 压缩适配器 | 与 source 的最小 CLI 操作保持 parity |
| `INIT_PROMPT.md` | Bootstrap/工作模式入口 | 不得指导手工维护 runtime facts/projections |
| `README.md` | 用户设置与命令说明 | Bootstrap 必须使用 `pd runtime init` |
| `tests/golden/agent-operation-protocol.txt` | 最小操作集合 golden | 协议命令发生兼容变化时审查更新 |

# Internal Flow

```text
pd task/session status
  -> pd context build/verify
  -> read selected documents + reasons
  -> implement and test
  -> update authored knowledge
  -> pd index/check/runtime/catalog verify
  -> pd session checkpoint/end
  -> pd task complete (only when finished)
```

新 Session 从 handoff + latest Checkpoint + bounded Context Manifest 恢复，不默认扫描全部 progress logs。HOT/WARM/COLD 是 retrieval metadata；Agent 规划显式 path/symbol/keyword/budget，retrieval execution 由 Context Builder 确定性完成。

# Bootstrap

衍生项目只复制 logs/knowledge 模板。`pd runtime init` 默认 dry-run；`--write` 只创建缺失的 null Task/Session pointers 并重建 Markdown projections，不覆盖既有 facts。初始化可在单个 pointer 写入后中断并安全重试。

# Synchronization

```text
AGENT_RULES.md -> Cursor adapter
AGENT_RULES.md -> INIT_PROMPT.md
AGENT_RULES.md -> README.md
golden minimal operations -> architecture parity test
```

首期不自动生成协议或 adapter，以保留人类可读性和 IDE 差异；architecture test 只锁定最小操作和过期指令禁区。

# Dependencies

- Coding Task/Session/Checkpoint lifecycle application services。
- Deterministic Context Builder 与 canonical Memory/OKF sources。
- `.paradigma/config.yaml` 提供 runtime、knowledge、memory 和 catalog 路径。

# Related Contracts

- `agent-operation-protocol-contract.md`：最小 Agent 行为和 adapter parity。
- `coding-runtime-contract.md`：YAML facts、null pointers 和 projections。
- `coding-context-contract.md`：ContextRequest/Manifest 的确定性与 reasons。

# Known Risks

- 协议与 adapter 仍是人工同步；golden 只能检测关键命令 parity，不能证明语义逐句一致。
- `runtime init` 的多文件初始化不是单事务，但写入顺序和“只补缺失”语义保证可重试。
- 自动消费 plan task queue、多 Agent slots 和协议版本协商仍未实现。
