---
type: paradigma-plan
title: Paradigma v0.5.0 Roadmap & Known Gaps
description: Prioritized milestones for the next Paradigma iteration, covering session continuity, tooling gaps, and protocol hardening.
tags: [plan, roadmap, paradigma, v0.5.0]
timestamp: 2026-07-08T16:40:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: cold
  lifecycle: evolving
  update_policy: agent-editable
  epistemic_status: confirmed
  retrieval_hints:
    zh:
      - 路线图
      - 里程碑
      - 下一个迭代
      - 能力缺口
      - v0.5.0
    en:
      - roadmap
      - milestones
      - next iteration
      - capability gaps
      - v0.5.0
  relations:
    related_to:
      - /known-issues/session-context-fragmentation.md
      - /architecture.md
      - /domains/protocol.md
---

# Goal

完成 Paradigma v0.4.2 → v0.5.0 的收尾，并将已识别的结构性盲点纳入路线图。本 plan 本身也是 `knowledge/plans/` 层的第一份正式文档。

# Scope

**包含**：
- Session 间上下文断裂问题的深度分析与修复方案
- architecture.md Open Questions 补充（12 条新能力缺口）
- 已交付的 WS-0 ~ WS-4 收尾（version bump、清理）
- 识别下一迭代（v0.5.0 → v0.6.0）的优先级任务

**不包含**：
- WS-4 的 pd-update.py --apply（推迟到 v0.6.0）
- 知识新鲜度自动检测（需要 doc-gardening agent，探索性工作）
- 多 Agent 协议（RFC 中标记为 future work）

# Approach

1. **PD-01**: 深入分析 session 间上下文断裂的根因，编写 known-issue 文档
2. **PD-02**: 将系统性盲点分析中的 15 条能力缺口写入 architecture.md Open Questions
3. **PD-03**: 标记下一个 major 迭代中的高优先级项目
4. **PD-04**: 版本 bump 到 0.5.0 + 更新 changelog

# Tasks

- [x] G-1: 创建本 plan 文档（paradigma-plan 类型，temperature: warm）
- [x] G-2: 编写 `known-issues/session-context-fragmentation.md`（PD-01）
- [x] G-3: 更新 `architecture.md` Open Questions（PD-02）
- [x] G-4: 版本 bump 到 0.5.0 + 更新 changelog（PD-04）
- [x] G-5: 更新本 plan 状态为 completed，temperature 切换为 cold

# Status

**completed**
