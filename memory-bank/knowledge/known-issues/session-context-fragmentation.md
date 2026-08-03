---
type: paradigma-known-issue
title: Session Context Fragmentation Between Active Tasks
description: When an active-task is completed and archived, the next session suffers context loss due to missing handoff, fragile implicit context, and protocol ambiguity.
tags: [known-issue, protocol, session-continuity, active-task]
timestamp: 2026-07-24T02:44:33+08:00
paradigma:
  schema_version: "0.1"
  temperature: cold
  lifecycle: evolving
  update_policy: agent-editable
  epistemic_status: confirmed
  retrieval_hints:
    zh:
      - 会话上下文断裂
      - 任务切换
      - handoff
      - 活跃任务
    en:
      - session context
      - fragmentation
      - handoff
      - active task
  relations:
    related_to:
      - /domains/protocol.md
      - /domains/plans.md
      - /decisions/adr-002-okf-compatible-memory-runtime.md
      - /decisions/adr-020-deterministic-explainable-context-manifest.md
      - /contracts/coding-context-contract.md
---

# Symptom

当 Agent 完成一个 active-task 并归档后，下一个会话的 Agent 面临以下困难：

1. **无法判断"接下来做什么"**。归档后的 `logs/progress/` 是过程日志，不是任务队列。Agent 必须从头扫描最近的 session log、已有 plans 和未解决 ADRs 来推断下一步——这不是检索，是考古。
2. **中断后无法恢复**。如果用户说"先停下来，换个方向"，active-task 只能标记 completed（不诚实）或保持原样（污染下次会话）。
3. **多线任务丢失**。用户可以在口头讨论中提出"A 做完后做 B，B 涉及 C 的重构"，但这些依赖关系在 active-task 完成后全部消失。

具体表现：
- 用户："上次我们说到哪了？" → Agent 回答不准确，因为只能靠 progress logs 推测
- 用户切换任务时，Agent 问"要不要归档？" → 归档意味着丢弃未完成的工作
- 一个跨 5 个会话的 plan 执行到第 3 个会话时，Agent 无法从 active-task 直接得知 "这是 plan X 的一部分"

# Impact

| 场景 | 当前行为 | 理想行为 |
|------|---------|---------|
| 任务 A 完成，紧接着做任务 B | Agent 归档 A，用户必须明确说"开始做 B" | Agent 归档 A 后自动读出下一个待办任务 |
| 任务中断（"先不做这个了"） | 要么归档（丢了未完成工作），要么留着（污染） | 显式 suspend，保留状态供后续恢复 |
| 长 plan 中间会话 | Agent 靠读 progress logs 推测上下文，可能遗漏关键约束 | Agent 直接从 parent plan + handoff 摘要获得上下文 |
| 多个 Agent 并行 | active-task 是单文件，无法表示两个独立线程 | 每个 Agent 有独立 task slot |

# Root Cause

问题不是 `active-task.md` 功能不足——它设计正确（单焦点、短生命周期）。问题在于 **active-task 的上下游缺少连接协议**：

```
上游缺失:
  active-task 完成时，没有"下一个任务是什么"的指针。
  虽然 plans 层可以定义任务列表，但 active-task 没有
  自动消费 plans 中的下一个 task 的机制。

下游缺失:
  active-task 归档后，只留下了 logs/progress/ 的过程记录，
  缺少一个轻量的 "handoff summary"：在本次会话中，
  我完成了什么、改了什么文件、下一个会话应该从哪里继续。
```

具体根因：

| 根因 | 说明 |
|------|------|
| **缺少 Handoff 协议** | Update Phase 第 2 步创建了 progress session log，但那是过程记录（"我做了什么"），不是交接文档（"下一个 Agent 应该做什么"） |
| **缺少 Task Queue** | plans 层有 Tasks 列表，但没有 tracking 状态（哪些已完成、哪些在进行中）。Agent 无法一眼看到"还有哪些任务待做" |
| **缺少 Suspend 状态** | active-task 只有"进行中"和"完成"两个状态。没有 "暂停/挂起" 状态。 |
| **隐式上下文依赖** | 当前协议假设 Agent 能通过 reading progress logs 重建上下文。这在短会话中可行，在 50+ 个 session 的项目中不可行 |

# Workaround

**短期缓解**（可在当前协议下使用）：
1. 用户主动在 active-task 的 Notes 节中写下 "Next: 实现支付回调接口"。
2. 大任务挂靠到 `plans/` 文档，在 plan 的 Tasks 节中追踪进度。
3. 中断时手动在 active-task 中标注 "SUSPENDED" 并保留，下一次会话 Agent 读取后判断。

**这些办法的问题**：完全依赖用户自律和 Agent 的主动行为。缺少协议级约束。

# Permanent Fix

## 方案 A：Handoff Summary（最轻量，推荐 v0.5.x）

在 Update Phase 中额外生成一个 `memory-bank/runtime/handoff.md`：

```markdown
# Session Handoff (2026-07-08)
## Completed
- [x] 实现微信支付回调接口
- [x] 更新 contracts/payment-api.md

## Modified Files
- backend/payment/wechat_callback.py
- memory-bank/knowledge/contracts/payment-api.md

## Next Session
- 实现支付宝回调（plans/add-payment.md Task 3/5）
- 需要先确认支付宝商户号配置

## Open Decisions
- 是否需要支持部分退款？→ 待用户确认
```

`handoff.md` 是**过程日志的超集**——它包含已完成的工作，还包含"接下来"和"待决策"。

Agent 在新会话的 Read Phase 中除了读 active-task，也读 handoff.md（如果存在）。

## 方案 B：Task Queue in Plans（中等改动）

`plans/` 中的 Tasks 节增加自动追踪状态：

```markdown
# Tasks
- [x] Task 1: 设计 PaymentService 接口         (completed, 2026-07-06)
- [x] Task 2: 实现微信支付回调                   (completed, 2026-07-08)
- [ ] Task 3: 实现支付宝回调                     (next)
- [ ] Task 4: 集成测试                            (pending)
- [ ] Task 5: 文档与部署                          (pending)
```

Agent 在完成一个 task 后更新 plan 的 task 状态。下一个会话时，Agent 读取 plan 就能看到"下一步是 Task 3"。

方案 A 和 B 互补：A 解决"刚刚发生了什么"（单次会话视角），B 解决"整体进度如何"（plan 视角）。

## 方案 C：多 Task Slot（大改动，推迟到 v1.0+）

支持多个并行 active-task（`memory-bank/runtime/tasks/` 目录），每个 task slot 对应一个 Agent 焦点。

# Related Documents

- `memory-bank/knowledge/domains/protocol.md` — L3 Runtime Protocol 层
- `memory-bank/knowledge/domains/plans.md` — 中期 plans 层设计（含 task 列表）
- `memory-bank/knowledge/decisions/adr-002-okf-compatible-memory-runtime.md` — runtime/logs/knowledge 三态结构
- `memory-bank/knowledge/plans/pd-next-milestones.md` — 本问题纳入当前路线图

# Status

**Partially resolved** — Phase 3 Batch 3.2–3.6 已实现 versioned Task/Session facts、suspend/resume、append-only Checkpoint、last-session handoff、checksummed Context Manifest 和 CLI-driven Agent protocol。新 Session 明确从 YAML + 最近 Checkpoint + bounded Manifest 恢复，协议不再要求扫描全部 progress logs 或手工维护 active-task。

仍未解决：plans task queue 的自动消费/推进，以及多 Agent task slots 与冲突协议。方案 B/C 保持后续工作。
