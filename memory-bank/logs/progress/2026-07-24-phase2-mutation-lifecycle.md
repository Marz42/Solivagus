---
type: paradigma-session-log
title: Phase 2 Memory Mutation Lifecycle
description: Session summary for Batch 2.5 canonical candidates, revision CAS, lifecycle CLI, tombstones, and recoverable catalog refresh.
tags: [session, phase-2, memory, mutation, lifecycle, revision]
timestamp: 2026-07-24T03:35:00+08:00
paradigma:
  layer: log
  lifecycle: append-only
  okf_export: optional
  update_policy: append-only
---

# Session Summary

## User Goal

按照正式主计划持续向前推进，每完成一个 Batch 更新 memory-bank 并 commit；当前完成 Batch 2.5。

## Actions Taken

- 新增 Kernel pure transition services，固定 commit/revise/supersede/forget 的状态、revision 和时间不变量。
- 新增严格 proposal/revision YAML payload parser；所有层级拒绝 unknown fields，revise 要求新的 provenance。
- 实现 propose/validate/commit/revise/supersede/forget object-returning Application API 和六个 `pd memory` CLI 命令。
- 所有既有记录 mutation 使用 caller-observed source hash + store lock CAS；CLI mutation 默认 dry-run，显式 `--write` 才发布。
- Candidate canonical 保存但普通 query 不可见；supersede 保留旧文档并追加 `superseded_by`；forget 只 tombstone、不物理删除。
- Canonical write 后完整 rebuild catalog。刷新失败返回专用 partial-success 错误，保留已提交 Markdown 并可手动 rebuild 恢复。
- 新增完整 propose→commit→query→revise→supersede→forget 集成测试、六命令 CLI 测试、并发/策略测试和 catalog refresh failure injection。

## Validation

- Mutation/CLI/failure/architecture 针对性测试：13/13 passed；Kernel + lifecycle 组合测试：17/17 passed。
- 最终全量 unit/integration/architecture/characterization/failure-injection 回归：127/127 passed。
- repository quality gate：6/6 passed；37 个 concept、45 个 link-check 文件均无 error/warning。
- 从独立 wheel 安装目录完成 propose → commit → query，验证 public API、catalog schema 和 package discovery。

## Follow-ups

- Batch 2.6：实现 `pd memory query` 和 `pd memory explain`，把来源、置信度、有效期、relation source 和 exclusion warnings 完整呈现。
- Phase 2 收口时补 golden end-to-end gate，并评估 v0.6.0 release preparation。
