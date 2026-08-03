---
type: paradigma-rfc
title: Paradigma OKF-Compatible Agent Memory Runtime
description: RFC proposal for evolving Project Paradigma into an OKF-compatible Agent Memory Runtime framework.
tags: [paradigma, okf, rfc, agent-memory, runtime]
timestamp: 2026-07-23T21:55:59+08:00
paradigma:
  schema_version: "0.1"
  layer: docs
  temperature: warm
  lifecycle: proposal
  update_policy: requires-human-confirmation
  epistemic_status: proposal
  retrieval_hints:
    zh:
      - OKF 兼容运行时
      - Agent Memory Runtime
      - 工具闭环
    en:
      - OKF compatible runtime
      - Agent Memory Runtime
      - deterministic tooling
  symbols:
    - OKF-compatible Agent Memory Runtime
    - L1 Format Layer
    - L2 Semantic Layer
    - L3 Runtime Protocol Layer
    - L4 Deterministic Tooling Layer
  relations:
    informs:
      - ../../memory-bank/knowledge/architecture.md
      - ../../memory-bank/knowledge/contracts/repository-contract.md
---

# Paradigma OKF-Compatible Agent Memory Runtime 方案草案

## 0. 方案定位

Paradigma 的目标不是成为一个单纯的文档模板库，也不是简单复制 OKF，而是成为一个面向 Agent 辅助开发的 **外部记忆运行框架**。

本方案将 Paradigma 定义为：

> **一个以 OKF-compatible Markdown 知识库为数据基础、以 Paradigma 语义模型定义文档角色、以 Agent Runtime Protocol 规定读取与维护行为、以确定性工具链保证闭环一致性的 Agent Memory Runtime Framework。**

OKF 的价值在于提供通用、可读、可解析、可版本化、可互操作的知识文件格式。OKF v0.1 将知识表示为带 YAML frontmatter 的 Markdown 文件目录，并要求每个 concept 文档至少包含非空 `type` 字段；它同时允许 producer 添加自定义字段，consumer 应宽容处理未知字段。 [\[github.com\]](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)

Paradigma 的价值则在于规定 Agent 在真实开发过程中如何读取、维护、压缩、更新这些文件，解决长期会话中的上下文腐化、注意力涣散、会话间不连续性等问题。当前 Paradigma 已经以 Memory-Bank 外部记忆系统为核心，并包含 HOT/WARM/COLD 文件温度体系、`AGENT_RULES.md`、`INIT_PROMPT.md`、`active-task.md`、`progress.md` 等运行协议元素。 [\[github.com\]](https://github.com/Marz42/Project_Sycamore)

因此，本方案的核心原则是：

> **OKF 负责知识格式互操作；Paradigma 负责语义约束、运行协议和工具闭环。**

***

# 1. 总体架构

Paradigma 采用四个协同层次：

```text
Paradigma
├── L1 Format Layer
│   └── OKF-compatible Markdown + YAML frontmatter
│
├── L2 Semantic Layer
│   └── Paradigma Memory-Bank 文档类型与语义模型
│
├── L3 Runtime Protocol Layer
│   └── Agent 启动、读取、更新、归档、审查规则
│
└── L4 Deterministic Tooling Layer
    └── 非 LLM 工具链：lint、link check、index sync、archive、compact
```

四层职责如下：

| 层级 | 名称                     | 核心问题                  | 典型产物                                                             |
| -- | ---------------------- | --------------------- | ---------------------------------------------------------------- |
| L1 | Format Layer           | 文件如何存储与交换             | Markdown、YAML frontmatter、links、index.md                         |
| L2 | Semantic Layer         | 这些文件在 Paradigma 中代表什么 | `paradigma-architecture`、`paradigma-contract`、`paradigma-manual` |
| L3 | Runtime Protocol Layer | Agent 如何读写和维护这些文件     | HOT/WARM/COLD、任务流程、更新权限、归档策略                                     |
| L4 | Tooling Layer          | 如何用确定性工具防止腐化          | `pd-lint-okf.py`、`pd-check-links.py`、`pd-index.py`          |

***

# 2. 核心设计原则

## 2.1 格式开放，生产严格

OKF 的宽容性适合互操作。OKF 规范中，consumer 不应因为缺失可选字段、未知 type、未知额外字段、断链或缺失 index 文件而拒绝整个 bundle。 [\[github.com\]](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)

Paradigma 内部则应采用更严格的生产规则：

```text
External Consumption:
  OKF-compatible, tolerant consumption

Internal Production:
  Paradigma-strict, deterministic validation
```

也就是说：

* 对外：Paradigma 知识库可以被普通 OKF consumer 尽力读取；
* 对内：Paradigma 自身的 Agent 和工具必须执行严格校验。

***

## 2.2 Runtime state 不等于长期知识

Paradigma 中存在三类信息：

1. **当前运行状态**
2. **过程日志**
3. **长期知识**

这三者不应混为一谈。

因此，本方案不再采用简单的：

```text
HOT = 非 OKF
WARM/COLD = OKF
```

而改为：

```text
Runtime State:
  当前任务状态，短生命周期，可覆盖，不作为 OKF 知识导出

Operational Logs:
  会话日志、变更日志，append-only，可归档，可摘要

Knowledge Base:
  长期知识，严格 OKF-compatible + Paradigma semantic schema
```

***

## 2.3 Agent 不手动维护可生成内容

凡是可以从结构化 metadata 推导的内容，都应由工具生成，而不是由 Agent 手动维护。

尤其包括：

* `index.md`
* link graph summary
* log summary
* retrieval route table
* schema inventory
* document registry

Agent 可以更新 source documents，但不应手写生成型索引。

***

## 2.4 One-shot retrieval 是第一跳，不是终点

`index.md` 应作为高信息密度路由表，帮助 Agent 快速找到候选文档。

但 Agent 不应只读一个命中文档就停止。  
正确流程是：

```text
1. 扫描 root index.md
2. 选择 top 1-3 个候选文档
3. 读取候选文档
4. 检查文档声明的 relations
5. 根据任务相关性继续读取必要依赖
6. 达到足够上下文后停止扩展
```

***

# 3. 推荐目录结构

建议将 Paradigma repo 分为 protocol、runtime、logs、knowledge、tools 几个区域。

```text
paradigma/
├── README.md
├── AGENT_RULES.md
├── INIT_PROMPT.md
├── VERSION
│
├── .cursor/
│   └── rules/
│       └── memory-bank-protocol.mdc
│
├── .paradigma/
│   ├── tools/
│   │   ├── pd-lint-okf.py
│   │   ├── pd-check-links.py
│   │   ├── pd-index.py
│   │   ├── pd-check-hot-size.py
│   │   ├── pd-archive-task.py
│   │   └── pd-compact-progress.py
│   │
│   ├── schemas/
│   │   ├── paradigma-architecture.schema.yaml
│   │   ├── paradigma-contract.schema.yaml
│   │   ├── paradigma-manual.schema.yaml
│   │   ├── paradigma-domain.schema.yaml
│   │   └── paradigma-decision.schema.yaml
│   │
│   └── config.yaml
│
└── memory-bank/
    ├── runtime/
    │   └── active-task.md
    │
    ├── logs/
    │   ├── progress/
    │   │   ├── index.md
    │   │   └── 2026-07-03-session-001.md
    │   ├── changelog.md
    │   └── log.md
    │
    └── knowledge/
        ├── index.md
        ├── project-brief.md
        ├── architecture.md
        ├── conventions.md
        ├── domains/
        │   ├── index.md
        │   └── auth.md
        ├── contracts/
        │   ├── index.md
        │   └── payment-api.md
        ├── manuals/
        │   ├── index.md
        │   ├── paradigma-deploy.md
        │   └── paradigma-baseline-test.md
        ├── decisions/
        │   ├── index.md
        │   └── adr-0001-auth-strategy.md
        ├── known-issues/
        │   ├── index.md
        │   └── payment-callback-race-condition.md
        └── glossary.md
```

***

# 4. L1 Format Layer：OKF-compatible 格式层

## 4.1 适用范围

L1 只强制适用于：

```text
memory-bank/knowledge/
```

也就是说，Paradigma 的 **知识库区域** 应是 OKF-compatible bundle。

以下区域不要求成为 OKF bundle：

```text
memory-bank/runtime/
memory-bank/logs/
.paradigma/
.cursor/
```

但 runtime 和 logs 仍可使用轻量 frontmatter，以便工具读取。

***

## 4.2 Knowledge 文档基本格式

每个长期知识文档必须是 Markdown 文件，并包含 YAML frontmatter。

最低要求：

```yaml
---
type: paradigma-architecture
title: System Architecture
description: Top-level system architecture and technical constraints.
tags: [architecture, system]
timestamp: 2026-07-03T00:00:00Z
---
```

OKF 规定 concept document 是 UTF-8 Markdown 文件，由 YAML frontmatter 和 Markdown body 组成；frontmatter 中 `type` 是必需字段，`title`、`description`、`resource`、`tags`、`timestamp` 是推荐字段。 [\[github.com\]](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)

***

## 4.3 Paradigma 扩展字段

Paradigma-specific metadata 应统一放入 `paradigma` namespace，避免污染通用 OKF 字段。

推荐格式：

```yaml
---
type: paradigma-contract
title: Payment Callback Contract
description: API contract for payment callback and order status transitions.
tags: [payment, api, contract]
timestamp: 2026-07-03T00:00:00Z

paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: stable
  owner_module: payment
  update_policy: requires-human-confirmation
  epistemic_status: confirmed
  retrieval_hints:
    zh:
      - 支付回调
      - 订单状态机
      - 订单生命周期
    en:
      - payment callback
      - order lifecycle
      - payment state transition
  symbols:
    - PENDING
    - PAID
    - FAILED
  relations:
    depends_on:
      - /memory-bank/knowledge/architecture.md
    constrains:
      - /memory-bank/knowledge/domains/payment.md
---
```

***

## 4.4 文件路径作为 concept identity

OKF 将 concept ID 定义为文件在 bundle 中的路径去掉 `.md` 后缀。  
Paradigma 应继承这一点。 [\[github.com\]](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)

例如：

```text
memory-bank/knowledge/contracts/payment-api.md
```

其 Paradigma concept identity 可视为：

```text
contracts/payment-api
```

因此，文件移动属于语义变更，应由工具记录或提示。

***

## 4.5 链接规范

知识库文档应使用标准 Markdown 链接。

推荐：

```markdown
See /contracts/payment-api.md.
```

OKF 支持 bundle-relative absolute links 和标准 relative links，其中以 `/` 开头的 absolute links 被解释为相对 bundle root 的路径。 [\[github.com\]](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)

Paradigma 建议：

* knowledge 内部链接优先使用 bundle-relative absolute links；
* 同目录短引用可以使用 relative links；
* runtime/logs 指向 knowledge 时应使用完整路径；
* 外部 URL 应放入 `# Citations` 或明确标注为 external reference。

***

## 4.6 Citations

当文档中的关键事实来自外部资料时，必须在正文中提供 citation section。

OKF 建议当 concept body 中的 claim 来自外部材料时，将来源列在 `# Citations` heading 下。 [\[github.com\]](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)

推荐：

```markdown
# Citations

https://example.com/api-gateway
https://www.rfc-editor.org/rfc/rfc6749
```

Paradigma 中尤其需要 citation 的文档包括：

* `architecture.md`
* `contracts/*.md`
* `manuals/*.md`
* `known-issues/*.md`
* `decisions/*.md`

***

# 5. L2 Semantic Layer：Paradigma 语义层

L2 的职责不是简单给 `type` 起名字，而是定义每类文档的：

1. 类型名称；
2. 必填 frontmatter 字段；
3. 推荐 frontmatter 字段；
4. 必填正文 section；
5. 可选正文 section；
6. 更新权限；
7. 生命周期；
8. 与其他文档的合法关系。

***

## 5.1 Type 命名规范

Paradigma type 应采用稳定、可机器识别的命名。

推荐格式：

```text
paradigma-project-brief
paradigma-architecture
paradigma-convention
paradigma-domain
paradigma-contract
paradigma-manual
paradigma-decision
paradigma-known-issue
paradigma-glossary
```

不推荐：

```text
architecture
system blueprint
系统蓝图
doc
manual
```

原因是这些名称过于泛化，不利于 Agent runtime 路由。

***

## 5.2 核心文档类型

### 5.2.1 `paradigma-project-brief`

用于定义项目愿景、核心受众、边界、非目标和成功标准。

推荐位置：

```text
memory-bank/knowledge/project-brief.md
```

必填 section：

```markdown
# Vision

# Target Users

# Scope

# Non-goals

# Success Criteria

# Constraints
```

推荐 frontmatter：

```yaml
---
type: paradigma-project-brief
title: Project Brief
description: Project vision, target users, scope, non-goals, and success criteria.
tags: [project, brief, scope]
timestamp: 2026-07-03T00:00:00Z

paradigma:
  temperature: hot
  lifecycle: stable
  update_policy: requires-human-confirmation
  epistemic_status: confirmed
---
```

说明：  
虽然它在 runtime 上属于 HOT 必读，但它是长期知识，应放在 knowledge 中，并严格遵守 OKF-compatible 格式。

***

### 5.2.2 `paradigma-architecture`

用于定义系统结构、技术栈、模块边界、关键约束。

推荐位置：

```text
memory-bank/knowledge/architecture.md
```

必填 section：

```markdown
# Overview

# Technology Stack

# Module Boundaries

# Data Flow

# Key Constraints

# Open Questions

# Citations
```

推荐 frontmatter：

```yaml
---
type: paradigma-architecture
title: System Architecture
description: Top-level architecture, technology stack, module boundaries, and key constraints.
tags: [architecture, system]
timestamp: 2026-07-03T00:00:00Z

paradigma:
  temperature: hot
  lifecycle: stable
  update_policy: requires-human-confirmation
  epistemic_status: confirmed
  relations:
    constrains:
      - /domains/
      - /contracts/
---
```

***

### 5.2.3 `paradigma-convention`

用于定义代码规范、命名约定、错误处理、测试风格等。

推荐位置：

```text
memory-bank/knowledge/conventions.md
```

必填 section：

```markdown
# Naming

# Code Style

# Error Handling

# Testing Conventions

# Documentation Conventions

# Prohibited Patterns
```

***

### 5.2.4 `paradigma-domain`

用于描述具体业务或技术模块。

推荐位置：

```text
memory-bank/knowledge/domains/<module>.md
```

必填 section：

```markdown
# Responsibility

# Public Interfaces

# Internal Flow

# Dependencies

# Related Contracts

# Known Risks
```

推荐 frontmatter：

```yaml
---
type: paradigma-domain
title: Auth Domain
description: Authentication and authorization module design.
tags: [auth, domain]
timestamp: 2026-07-03T00:00:00Z

paradigma:
  temperature: warm
  lifecycle: evolving
  owner_module: auth
  retrieval_hints:
    zh:
      - 登录
      - 注册
      - JWT
      - OAuth2
    en:
      - login
      - registration
      - JWT
      - OAuth2
  relations:
    depends_on:
      - /architecture.md
    related_to:
      - /contracts/auth-api.md
---
```

***

### 5.2.5 `paradigma-contract`

用于描述 API、数据库、事件、状态机、外部集成等契约。

推荐位置：

```text
memory-bank/knowledge/contracts/<name>.md
```

必填 section：

```markdown
# Scope

# Contract

# Request Schema

# Response Schema

# State Transitions

# Compatibility Notes

# Breaking Change Policy

# Citations
```

如果是数据库表契约，可替换为：

```markdown
# Scope

# Tables

# Columns

# Indexes

# Constraints

# Migration Notes

# Compatibility Notes
```

推荐 frontmatter：

```yaml
---
type: paradigma-contract
title: Payment API Contract
description: Payment callback API and order status transition contract.
tags: [payment, api, contract]
timestamp: 2026-07-03T00:00:00Z

paradigma:
  temperature: warm
  lifecycle: stable
  update_policy: requires-human-confirmation
  epistemic_status: confirmed
  contract_kind: api
  owner_module: payment
  retrieval_hints:
    zh:
      - 支付回调
      - 订单状态机
      - PENDING
      - PAID
    en:
      - payment callback
      - order state machine
      - payment webhook
  symbols:
    - PENDING
    - PAID
    - FAILED
---
```

***

### 5.2.6 `paradigma-manual`

用于部署、测试、排障、运维等操作手册。

推荐位置：

```text
memory-bank/knowledge/manuals/<name>.md
```

必填 section：

```markdown
# Purpose

# Preconditions

# Steps

# Verification

# Rollback

# Troubleshooting

# Citations
```

***

### 5.2.7 `paradigma-decision`

用于 Architecture Decision Record。

推荐位置：

```text
memory-bank/knowledge/decisions/adr-0001-xxx.md
```

必填 section：

```markdown
# Context

# Decision

# Consequences

# Alternatives Considered

# Status

# Related Documents
```

推荐 frontmatter：

```yaml
---
type: paradigma-decision
title: ADR-0001 Use JWT for Session Authentication
description: Decision record for choosing JWT-based authentication.
tags: [adr, auth, jwt]
timestamp: 2026-07-03T00:00:00Z

paradigma:
  temperature: cold
  lifecycle: append-only
  update_policy: append-only
  epistemic_status: decision
  status: accepted
  relations:
    constrains:
      - /domains/auth.md
      - /contracts/auth-api.md
---
```

***

### 5.2.8 `paradigma-known-issue`

用于记录已知问题、坑位、排障路径和 workaround。

推荐位置：

```text
memory-bank/knowledge/known-issues/<issue>.md
```

必填 section：

```markdown
# Symptom

# Impact

# Root Cause

# Workaround

# Permanent Fix

# Related Documents

# Status
```

***

### 5.2.9 `paradigma-glossary`

用于术语表。

推荐位置：

```text
memory-bank/knowledge/glossary.md
```

必填 section：

```markdown
# Terms

# Abbreviations

# Domain-specific Meanings
```

***

## 5.3 Epistemic Status

长期知识库必须区分事实、决策、假设、提案、废弃内容。

推荐字段：

```yaml
paradigma:
  epistemic_status: confirmed
```

允许值：

```text
confirmed
decision
proposal
assumption
deprecated
unknown
```

语义：

| 值            | 含义    | Agent 处理方式 |
| ------------ | ----- | ---------- |
| `confirmed`  | 已确认事实 | 可作为依据      |
| `decision`   | 已接受决策 | 必须遵守       |
| `proposal`   | 待评审方案 | 不得当作事实     |
| `assumption` | 当前假设  | 使用时需提醒     |
| `deprecated` | 已废弃   | 不得用于新实现    |
| `unknown`    | 未确认   | 需要查证       |

***

## 5.4 Update Policy

长期知识库必须定义更新权限。

推荐字段：

```yaml
paradigma:
  update_policy: requires-human-confirmation
```

允许值：

```text
agent-editable
requires-human-confirmation
append-only
generated
read-only
```

语义：

| 值                             | 含义                     |
| ----------------------------- | ---------------------- |
| `agent-editable`              | Agent 可直接修改            |
| `requires-human-confirmation` | Agent 可提出修改，但需要用户确认后落盘 |
| `append-only`                 | 只能追加，不得覆盖历史            |
| `generated`                   | 只能由工具生成                |
| `read-only`                   | 不允许 Agent 修改           |

建议默认策略：

| 文档类型            | 默认 update policy                                 |
| --------------- | ------------------------------------------------ |
| project brief   | `requires-human-confirmation`                    |
| architecture    | `requires-human-confirmation`                    |
| contract        | `requires-human-confirmation`                    |
| convention      | `requires-human-confirmation`                    |
| domain          | `agent-editable` 或 `requires-human-confirmation` |
| manual          | `agent-editable`                                 |
| decision        | `append-only`                                    |
| known issue     | `agent-editable`                                 |
| glossary        | `agent-editable`                                 |
| generated index | `generated`                                      |

***

# 6. L3 Runtime Protocol Layer：运行协议层

L3 规定 Agent 在不同场景下如何读取、更新、归档和校验 Memory-Bank。

***

## 6.1 文件温度体系

Paradigma 保留 HOT/WARM/COLD，但温度不等于目录。

```text
HOT:
  每次任务或会话启动时必须读取

WARM:
  根据任务路由按需读取

COLD:
  排查、审计、历史追溯、架构争议时读取
```

注意：

* HOT 可以是长期知识，如 `project-brief.md`、`architecture.md`；
* HOT 也可以是 runtime state，如 `active-task.md`；
* 是否 OKF-compatible 取决于文件属于 knowledge 还是 runtime，而不是温度本身。

***

## 6.2 Runtime State

### 6.2.1 active-task.md

位置：

```text
memory-bank/runtime/active-task.md
```

用途：

* 记录当前唯一焦点任务；
* 记录任务状态、阻塞点、涉及文件；
* 任务结束后应归档或清空。

推荐格式：轻量 frontmatter + 自由正文。

```yaml
---
type: paradigma-runtime-state
title: Active Task
description: Current active task state for the Agent session.

paradigma:
  layer: runtime
  temperature: hot
  lifecycle: ephemeral
  okf_export: false
  update_policy: agent-editable
  archive_to: /memory-bank/logs/progress/
---
```

正文模板：

```markdown
# Active Task

## Task ID

## User Request

## Current Status

pending

## Checklist

- [ ] Step 1
- [ ] Step 2

## Relevant Knowledge

- /memory-bank/knowledge/architecture.md
- /memory-bank/knowledge/contracts/payment-api.md

## Blockers

## Notes
```

规则：

1. 任一时刻只应有一个 active task；
2. 新任务开始前必须检查并处理旧 active task；
3. 任务完成后必须归档到 `logs/progress/`；
4. active task 不应积累长期知识；
5. 长期知识必须迁移到 `knowledge/` 对应文档。
6. `Current Status` 只允许 `pending`、`active`、`blocked`、`completed`、`aborted`，不得从自然语言或 checklist 推断。

***

## 6.3 Operational Logs

### 6.3.1 progress logs

建议采用 session 拆文件，而不是单个巨大 `progress.md`。

```text
memory-bank/logs/progress/
├── index.md
├── 2026-07-03-session-001.md
└── 2026-07-03-session-002.md
```

单个 session log 推荐格式：

```yaml
---
type: paradigma-session-log
title: Session 2026-07-03 001
description: Summary of one Agent work session.

paradigma:
  layer: log
  lifecycle: append-only
  okf_export: optional
  update_policy: append-only
---
```

正文：

```markdown
# Session Summary

## User Goal

## Actions Taken

## Files Read

## Files Modified

## Decisions Proposed

## Decisions Accepted

## Knowledge Updates

## Follow-ups
```

规则：

1. session log 只能追加，不建议改写历史；
2. session log 中的长期事实必须迁移到 knowledge；
3. session log 中的决策必须迁移到 `decisions/`；
4. session log 中的 bug 必须迁移到 `known-issues/`；
5. session log 不应成为 Agent 长期检索的主要入口。

***

### 6.3.2 changelog.md

用于记录面向用户或版本的变更。

```text
memory-bank/logs/changelog.md
```

规则：

* 可以半结构化；
* 应按版本或日期组织；
* 不应替代 session logs；
* 不应替代 architecture decisions。

***

### 6.3.3 log.md

OKF 允许 `log.md` 作为目录作用域内的变更历史，格式为按日期分组的条目。 [\[github.com\]](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)

Paradigma 中的 `log.md` 建议由工具生成，用于外部 OKF consumer 阅读概要，而不是手工维护。

***

## 6.4 Knowledge Retrieval Protocol

当 Agent 遇到新需求时，应按以下顺序读取：

```text
1. memory-bank/runtime/active-task.md
2. memory-bank/knowledge/index.md
3. HOT knowledge:
   - project-brief.md
   - architecture.md
   - conventions.md
4. 根据 index.md 路由选择 WARM 文档
5. 根据 relations 选择必要依赖
6. 必要时读取 COLD 文档
```

***

## 6.5 Task Execution Protocol

每次任务执行应遵循：

```text
Phase 1: Bootstrap
  - 读取 active-task
  - 读取 knowledge/index
  - 读取 HOT knowledge

Phase 2: Route
  - 根据用户需求从 index 中选择候选文档
  - 优先选择 top 1-3 个候选
  - 不进行无目标漫游

Phase 3: Execute
  - 读取必要 WARM/COLD 文档
  - 执行代码或文档修改
  - 避免将假设写成事实

Phase 4: Update Memory
  - 更新 active-task
  - 必要时更新 knowledge
  - 追加 session log
  - 若修改长期知识，运行校验工具

Phase 5: Validate
  - 运行 pd-lint-okf
  - 运行 pd-check-links
  - 运行 pd-index rebuild
  - 若失败，根据错误修正
```

***

## 6.6 Write Permission Protocol

Agent 修改文档时必须遵守 `update_policy`。

规则：

```text
agent-editable:
  Agent 可直接修改，但必须通过工具校验。

requires-human-confirmation:
  Agent 只能提出 patch 或建议，用户确认后才能写入。

append-only:
  Agent 只能追加新记录，不得改写旧记录。

generated:
  Agent 不得手动修改，只能调用生成工具。

read-only:
  Agent 不得修改。
```

***

# 7. L4 Deterministic Tooling Layer：确定性工具层

工具层是 Paradigma 防止记忆腐化的关键。

***

## 7.1 工具目录

```text
.paradigma/tools/
├── pd-lint-okf.py
├── pd-check-links.py
├── pd-index.py
├── pd-check-hot-size.py
├── pd-archive-task.py
└── pd-compact-progress.py
```

***

## 7.2 `pd-lint-okf.py`

用途：

* 校验 knowledge 文档是否符合 OKF-compatible 基本格式；
* 校验 Paradigma L2 schema；
* 校验必填 section；
* 校验 `paradigma` 扩展字段；
* 校验 update policy、epistemic status、temperature 合法性。

检查项：

```text
ERROR:
  - 缺少 YAML frontmatter
  - YAML 无法解析
  - 缺少 type
  - type 不属于 Paradigma 允许集合
  - 缺少 title 或 description
  - timestamp 格式非法
  - 必填 section 缺失
  - generated 文件被人工修改

WARNING:
  - description 过短
  - retrieval_hints 缺失
  - tags 为空
  - citations 缺失
  - relations 为空
```

***

## 7.3 `pd-check-links.py`

用途：

* 检查 Markdown links；
* 检查 `relations` 中声明的路径；
* 检查 index 中列出的路径；
* 检查 bundle-relative links。

建议分级：

```text
ERROR:
  - index.md 中链接不存在
  - HOT/WARM knowledge 内部链接断裂
  - relations.depends_on 目标不存在

WARNING:
  - COLD 文档存在断链
  - planned link 暂不存在
  - 外部 URL 无法校验
```

允许 planned link：

```yaml
paradigma:
  relations:
    planned:
      - /domains/future-billing.md
```

***

## 7.4 `pd-index.py`

用途：

* 保持 knowledge root `index.md` 为人工高层导航；
* 为子目录生成只含直接文档的局部索引；
* 将全部 knowledge 文档的递归元数据写入 `.paradigma/cache/knowledge-index.json`；
* 提供 `rebuild` 和 `verify`，机器 cache 可删除重建。

重要规则：

1. 根 index 不包含 auto-index 区域，由人类维护有限导航；
2. 子目录 generated block 只列本目录直接文档，Agent 不得手改；
3. 全量机器 index 位于 ignored cache，不是 canonical knowledge；
4. `pd-sync-index.py --write/--check` 仅作为 v0.5.x 兼容入口。

推荐 index 格式：

```markdown
# Paradigma Knowledge Index

Agent 路由指南：请根据 Type、Hints、Symbols 选择最相关的 1-3 个文档读取。
One-shot retrieval 是第一跳，不是终点。读取命中文档后，应检查其 relations。

## HOT Knowledge

* [Architecture](architecture.md)
* [Repository Contract](contracts/repository-contract.md)

## WARM Knowledge

* [Domains](domains/)
* [Manuals](manuals/)
```

***

## 7.5 `pd-check-hot-size.py`

用途：

* 防止 HOT 文件膨胀；
* 检查 `active-task.md`、HOT knowledge 是否过长；
* 提醒归档或压缩。

规则示例：

```text
WARNING:
  - active-task.md 超过建议长度
  - HOT knowledge 文件过大
  - progress index 过大

SUGGESTION:
  - 将历史内容归档到 logs/progress/
  - 将长期事实迁移到 knowledge/
  - 将模块细节拆入 domains/
```

***

## 7.6 `pd-archive-task.py`

用途：

* 校验严格任务状态并生成 dry-run mutation plan；
* 将 `completed` active task 归档为 content-addressed session log；
* 原子重置 active-task 为 `pending`；
* 使用 archive ID 恢复中断操作并保证重复调用不生成重复日志。

归档流程：

```text
1. 读取 active-task，严格解析状态并计算 source hash
2. 生成并展示 archive + reset mutation plan
3. 原子创建含 `archive_id` 的 progress session 文件
4. 原子替换 active-task 为带 last archive marker 的 `pending` 模板
5. 若在 3/4 之间中断，重试复用既有 archive，只完成 reset
```

***

## 7.7 `pd-compact-progress.py`

用途：

* 压缩长期 session logs；
* 将多条 session log 汇总为周期性摘要；
* 避免 progress 成为上下文黑洞。

规则：

```text
- 原始 session log 保留
- compact summary 由工具使用同目录临时文件、flush、fsync 和 atomic replace 生成
- 写入失败保留原 summary、清理临时文件并返回 `PD_COMPACT_IO_ERROR`
- compact summary 不替代 decisions 或 known issues
- 被确认的长期事实必须迁移到 knowledge
```

***

# 8. Index 设计：高信息密度路由表

OKF 的 `index.md` 用于列出目录内容，支持 progressive disclosure，让人或 Agent 在打开具体文档前了解可用内容。 [\[github.com\]](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)

Paradigma 在此基础上扩展为 **Agent Retrieval Route Table**。

***

## 8.1 分层 index

不建议所有内容都塞进根 index。

推荐：

```text
memory-bank/knowledge/index.md
memory-bank/knowledge/domains/index.md
memory-bank/knowledge/contracts/index.md
memory-bank/knowledge/manuals/index.md
memory-bank/knowledge/decisions/index.md
memory-bank/knowledge/known-issues/index.md
```

根 index 只列：

* HOT knowledge；
* 各领域目录；
* 关键 contract；
* 高优先级 known issue；
* 路由说明。

子 index 才列详细文件。

***

## 8.2 Retrieval Hints

每个 knowledge 文档应维护 retrieval hints。

```yaml
paradigma:
  retrieval_hints:
    zh:
      - 订单状态机
      - 支付回调
      - 订单生命周期
    en:
      - order state machine
      - payment callback
      - order lifecycle
  symbols:
    - PENDING
    - PAID
    - FAILED
  apis:
    - POST /api/payment/callback
```

这些字段是 `pd-index.py` 生成局部路由表和机器 inventory 的主要依据。

***

## 8.3 One-shot retrieval 规则

Agent 使用 index 时应遵守：

```text
1. 首先扫描 root index。
2. 根据用户任务选择 top 1-3 个候选。
3. 读取候选文档。
4. 检查候选文档 relations。
5. 只跟随与任务相关的 relations。
6. 不做无限图谱漫游。
```

禁止行为：

```text
- 只凭文件名猜测内容
- 读取整个 knowledge tree
- 只读第一个命中文档后直接修改代码
- 忽略 contract / architecture 约束
```

***

# 9. Relations 设计：强语义链接

OKF 中 Markdown link 表达 concept 之间关系，具体关系语义由周围文本表达；构建图视图时通常可视为有向但未类型化关系。 [\[github.com\]](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)

Paradigma 需要更强的 runtime 关系，因此建议在 `paradigma.relations` 中定义结构化关系。

推荐关系类型：

```yaml
paradigma:
  relations:
    depends_on:
      - /architecture.md
    constrains:
      - /domains/payment.md
    related_to:
      - /manuals/paradigma-deploy.md
      - /manuals/paradigma-baseline-test.md
    supersedes:
      - /decisions/adr-0001-old-auth.md
    affected_by:
      - /known-issues/payment-callback-race-condition.md
```

语义：

| 关系            | 含义                               |
| ------------- | -------------------------------- |
| `depends_on`  | 当前文档理解依赖目标文档                     |
| `constrains`  | 当前文档约束目标文档                       |
| `related_to`  | 一般相关                             |
| `supersedes`  | 当前文档取代旧文档                        |
| `affected_by` | 当前文档受某 known issue 或 decision 影响 |
| `implements`  | 当前模块实现某 contract 或 decision      |
| `cites`       | 当前文档引用某来源或参考                     |

***

# 10. Generated 文件规则

自动生成文件必须明确标记。

frontmatter：

```yaml
paradigma:
  update_policy: generated
  generated_by: pd-index.py
```

Markdown block：

```markdown
<!-- BEGIN PARADIGMA AUTO-INDEX -->
...
<!-- END PARADIGMA AUTO-INDEX -->
```

规则：

1. Agent 不得手动修改 generated block；
2. 人类补充内容应放在 block 外；
3. 工具只能覆盖 block 内内容；
4. lint 工具应检测 generated block 是否被破坏；
5. CI 中应重建 cache、检查 tracked 局部索引无 diff，再运行 verify。

***

# 11. Agent 行为规范

## 11.1 新任务启动

Agent 必须：

```text
1. 检查 active-task.md
2. 若存在未完成任务，先报告并询问是否继续、覆盖或归档
3. 读取 knowledge/index.md
4. 读取 HOT knowledge
5. 根据用户需求路由 WARM 文档
6. 创建或更新 active-task.md
```

***

## 11.2 修改接口、数据库、状态机

Agent 必须：

```text
1. 从 index 中寻找 type: paradigma-contract 的相关文档
2. 读取相关 contract
3. 读取 architecture
4. 读取相关 domain 文档
5. 修改前检查 update_policy
6. 若 update_policy = requires-human-confirmation，只能提出 patch
7. 修改后运行 lint、link check、index sync
```

***

## 11.3 修改架构

Agent 必须：

```text
1. 读取 project-brief
2. 读取 architecture
3. 读取 relevant decisions
4. 读取 affected domains/contracts
5. 新建或追加 decision record
6. 不得直接覆盖 accepted decision
7. 修改 architecture 前需用户确认
```

***

## 11.4 处理 bug

Agent 必须：

```text
1. 读取 active-task
2. 从 index 中查找 known-issues
3. 读取相关 domain / contract
4. 若发现新问题，创建 known issue
5. 若修复问题，更新 known issue status
6. 在 session log 中记录处理过程
```

***

## 11.5 任务结束

Agent 必须：

```text
1. 更新 active-task checklist
2. 归档 session log
3. 将长期事实迁移到 knowledge
4. 将决策迁移到 decisions
5. 将问题迁移到 known-issues
6. 运行工具链
7. 清空或重置 active-task
```

***

# 12. 校验级别

Paradigma 工具链应支持不同严格度。

```text
strict:
  用于 CI / release / main branch

normal:
  用于日常 Agent 修改后校验

warn:
  用于草稿期、迁移期、探索期
```

建议默认：

| 场景           | 模式       |
| ------------ | -------- |
| Agent 每次修改后  | `normal` |
| PR / merge 前 | `strict` |
| 初始迁移旧项目      | `warn`   |
| 用户探索性草稿      | `warn`   |

***

# 13. 并发与多人协作规则

## 13.1 避免单文件冲突

不建议所有 session 追加到一个 `progress.md`。

推荐：

```text
logs/progress/YYYY-MM-DD-session-N.md
```

这样更适合 Git 协作。

***

## 13.2 active-task 的作用域

`active-task.md` 默认是单 Agent / 单工作流状态。

如果需要多人或多 Agent 协作，应改为：

```text
memory-bank/runtime/tasks/
├── task-2026-07-03-001.md
├── task-2026-07-03-002.md
└── index.md
```

并由工具生成 task index。

***

## 13.3 冲突解决

冲突处理优先级：

```text
1. 不覆盖 accepted decisions
2. 不覆盖 contracts
3. 不覆盖 generated block 之外的人工内容
4. session logs 采用追加或新文件
5. index 由工具重新生成
```

***

# 14. 迁移策略

从现有 Paradigma 迁移到本方案，建议分阶段。

## Phase 1：结构调整

```text
- 创建 memory-bank/knowledge/
- 创建 memory-bank/runtime/
- 创建 memory-bank/logs/
- 移动 active-task.md 到 runtime
- 移动长期文档到 knowledge
- 移动 progress/changelog 到 logs
```

## Phase 2：添加 frontmatter

为 knowledge 文档添加：

```yaml
type:
title:
description:
tags:
timestamp:
paradigma:
  temperature:
  lifecycle:
  update_policy:
  epistemic_status:
```

## Phase 3：建立 L2 schema

先支持核心类型：

```text
paradigma-project-brief
paradigma-architecture
paradigma-contract
paradigma-domain
paradigma-manual
```

再逐步支持：

```text
paradigma-decision
paradigma-known-issue
paradigma-glossary
```

## Phase 4：启用工具链

先启用：

```text
pd-lint-okf.py
pd-index.py
```

再启用：

```text
pd-check-links.py
pd-check-hot-size.py
pd-archive-task.py
pd-compact-progress.py
```

## Phase 5：更新 Agent runtime protocol

更新：

```text
AGENT_RULES.md
INIT_PROMPT.md
.cursor/rules/memory-bank-protocol.mdc
```

让 Agent 遵守新的：

```text
runtime / logs / knowledge 三态分离
L1 / L2 / L3 / L4 四层规则
```

***

# 15. 最小可行版本

如果要快速落地，不必一次实现全部。

建议 MVP 范围：

```text
1. memory-bank/runtime/active-task.md
2. memory-bank/logs/progress/
3. memory-bank/knowledge/index.md
4. memory-bank/knowledge/project-brief.md
5. memory-bank/knowledge/architecture.md
6. memory-bank/knowledge/conventions.md
7. memory-bank/knowledge/domains/
8. memory-bank/knowledge/contracts/
9. pd-lint-okf.py
10. pd-index.py
```

MVP 的强制规则：

```text
- knowledge 文档必须有 frontmatter
- knowledge 文档必须有 type/title/description
- type 必须属于 Paradigma 允许集合
- root index 必须是人工高层导航，子目录 generated block 必须由工具生成
- active-task 不进入 OKF knowledge bundle
- session log 按文件拆分
```

***

# 16. 推荐规范摘要

最终规范可以压缩为以下几条硬规则。

## 16.1 Format Rules

```text
FR-1: 所有长期知识必须放在 memory-bank/knowledge/
FR-2: knowledge 文档必须是 Markdown + YAML frontmatter
FR-3: knowledge 文档必须包含 type/title/description
FR-4: Paradigma 扩展字段必须放在 paradigma namespace
FR-5: index.md 和 log.md 可以存在，但 generated 区域必须由工具维护
```

## 16.2 Semantic Rules

```text
SR-1: type 必须属于 Paradigma 类型集合
SR-2: 每种 type 必须有对应 schema
SR-3: 每种 type 必须定义必填 section
SR-4: 长期知识必须声明 epistemic_status
SR-5: 长期知识必须声明 update_policy
```

## 16.3 Runtime Rules

```text
RR-1: 新任务开始必须读取 active-task、knowledge/index、HOT knowledge
RR-2: Agent 必须通过 index 路由 WARM 文档
RR-3: One-shot retrieval 是第一跳，不是终点
RR-4: Agent 修改长期知识前必须检查 update_policy
RR-5: 任务结束必须归档 session log
RR-6: 长期事实不得停留在 active-task 或 session log 中
```

## 16.4 Tooling Rules

```text
TR-1: 修改 knowledge 后必须运行 lint
TR-2: 修改 links 或 relations 后必须运行 link check
TR-3: 新增、删除、修改 knowledge 文档后必须 sync index
TR-4: generated block 不得手动编辑
TR-5: HOT 文件超过阈值必须归档或压缩
```

***

# 17. 示例：完整 knowledge 文档

```markdown
---
type: paradigma-contract
title: Payment Callback Contract
description: Defines the payment callback API and order status transition rules.
tags: [payment, api, contract, order]
timestamp: 2026-07-03T00:00:00Z

paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: stable
  update_policy: requires-human-confirmation
  epistemic_status: confirmed
  contract_kind: api
  owner_module: payment
  retrieval_hints:
    zh:
      - 支付回调
      - 订单状态机
      - 支付 webhook
      - 订单生命周期
    en:
      - payment callback
      - payment webhook
      - order state machine
      - order lifecycle
  symbols:
    - PENDING
    - PAID
    - FAILED
    - REFUNDED
  apis:
    - POST /api/payment/callback
  relations:
    depends_on:
      - /architecture.md
    constrains:
      - /domains/payment.md
    related_to:
      - /manuals/paradigma-baseline-test.md
---

# Scope

This document defines the payment callback API and order status transition rules.

# Contract

## Endpoint

`POST /api/payment/callback`

# Request Schema

# Response Schema

# State Transitions

# Compatibility Notes

# Breaking Change Policy

# Citations
```

***

# 18. 示例：active-task.md

```markdown
---
type: paradigma-runtime-state
title: Active Task
description: Current active task state for the Agent session.

paradigma:
  layer: runtime
  temperature: hot
  lifecycle: ephemeral
  okf_export: false
  update_policy: agent-editable
  archive_to: /memory-bank/logs/progress/
---

# Active Task

## Task ID

2026-07-03-001

## User Request

Refactor payment callback handling and update relevant contracts.

## Current Status

active

## Checklist

- [x] Read knowledge index
- [x] Read payment contract
- [ ] Update implementation
- [ ] Propose contract update
- [ ] Run validation tools
- [ ] Archive session log

## Relevant Knowledge

- /memory-bank/knowledge/contracts/payment-api.md
- /memory-bank/knowledge/domains/payment.md
- /memory-bank/knowledge/architecture.md

## Blockers

None.

## Notes

Contract update requires human confirmation.
```

***

# 19. 主要风险与应对

## 风险 1：规范过重，用户不愿使用

应对：

```text
- 提供 MVP 模式
- 提供 strict / normal / warn 三种校验模式
- 初始模板不要过度复杂
- 工具自动生成 index，减少人工负担
```

***

## 风险 2：frontmatter 变得臃肿

应对：

```text
- OKF 字段保持简洁
- Paradigma 扩展统一放入 paradigma namespace
- retrieval hints 只写高价值关键词
- relations 只写 runtime 有用的关系
```

***

## 风险 3：index.md 过大

应对：

```text
- 分层 index
- root index 只保留高层路由
- 子目录 index 负责细节
- large project 可生成 compact index
```

***

## 风险 4：Agent 把假设写成事实

应对：

```text
- 强制 epistemic_status
- contracts / architecture 默认 requires-human-confirmation
- session log 中的假设不得直接进入 knowledge
- decisions 必须 append-only
```

***

## 风险 5：工具链成为维护负担

应对：

```text
- 工具保持本地、无外部依赖优先
- 每个工具职责单一
- 先做 lint + sync index
- 其他工具逐步加入
```

***

# 20. 最终定义

建议在 Paradigma README 中这样定义：

> **Paradigma is an OKF-compatible Agent Memory Runtime Framework.**  
> Its knowledge base uses Markdown + YAML frontmatter for interoperability; its semantic layer defines project-specific memory types; its runtime protocol tells agents how to read, update, and maintain memory; and its deterministic tooling prevents memory corruption.

中文版本：

> **Paradigma 是一个 OKF 兼容的 Agent 外部记忆运行框架。**  
> 它用 Markdown + YAML Frontmatter 保证长期知识的可读、可解析和可互操作；用 Paradigma 语义层定义项目记忆的类型和角色；用运行协议规定 Agent 如何高效读取、维护和归档这些记忆；用确定性工具链防止知识库腐化。

***
