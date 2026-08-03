---
type: paradigma-plan
title: [YOUR PLAN TITLE]
description: [1-2 sentence description of what this plan aims to achieve]
tags: [plan, YOUR-DOMAIN]
timestamp: YYYY-MM-DDTHH:mm:ss+08:00
paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: evolving
  update_policy: agent-editable
  epistemic_status: decision
  retrieval_hints:
    zh:
      - [3-7 Chinese keywords]
    en:
      - [3-7 English keywords]
---

# Goal

[TODO: 用 1-2 句话描述这个计划要达成什么目标。例如："Q3 加入支付模块，支持微信支付和支付宝。"]
# Scope

[TODO: 明确边界。做什么、不做什么。例如："包含微信扫码支付和支付宝 H5 支付。不包含退款流程和分账功能。"]

# Approach

[TODO: 高层次实现策略，不需要代码细节。描述技术选型、关键步骤、依赖关系。例如："1. 对接微信支付 API v3；2. 实现统一的 PaymentService 抽象层；3. 与订单模块集成回调通知。"]

# Tasks

[TODO: 将计划拆解为可执行的任务列表。每个任务应足够具体，能作为一次 active-task 的输入。]

- [ ] Task 1: [简短描述]
- [ ] Task 2: [简短描述]
- [ ] ...

# Status

**proposed** | in-progress | completed | archived

<!-- 
  生命周期说明：
  - proposed: 已提议，待批准
  - in-progress: 正在执行（temperature: warm）
  - completed: 已完成，放入 COLD 层作为历史参考
  - archived: 不再需要

  状态变更时更新 frontmatter:
  - in-progress → completed: temperature 改为 cold
  - epistemic_status 从 decision 变为 confirmed
-->
