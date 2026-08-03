---
type: paradigma-session-log
title: Session 2026-06-02 conventions.md 补充版本号规范
description: 评估并决定 SemVer 规范在 conventions.md 中的呈现方式。
tags: [session-log, conventions, semver]
timestamp: 2026-06-02T23:50:00+08:00
paradigma:
  schema_version: "0.1"
  layer: log
  lifecycle: append-only
  update_policy: append-only
  okf_export: optional
---

# Session Summary

> 📜 从 pre-OKF 时代的 `memory_bank/progress.md` 归档恢复。

## User Goal

评估是否应将完整 SemVer 2.0.0 规范纳入 conventions.md，并做出决策。

## Actions Taken

- [x] 评估是否应将完整 SemVer 2.0.0 规范纳入 conventions.md
- [x] 决策：只放操作摘要（递增规则、0.y.z、先行版本号约定），不放完整规范（BNF、优先级比较、正则、FAQ）
- [x] 在 conventions.md 中新增"版本号规范"板块（~35 行），含 Agent 行为约定
- [x] 保留 semver.org/lang/zh-CN/ 链接供 Agent 按需查阅

## Decisions Proposed

- 版本号规范采取"操作摘要"而非"完整规范"的策略 — 为 Agent 提供可执行的递增规则，将完整 SemVer 作为外部参考链接。

## Knowledge Updates

- conventions.md 新增版本号规范板块

## Follow-ups

- 无
