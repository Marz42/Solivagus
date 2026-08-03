---
type: paradigma-session-log
title: Phase 2 Memory Query Explain and Exit Audit
description: Session summary for Batch 2.6 public query/explain adapters, exclusion warnings, canonical-first diagnostics, and Phase 2 exit evidence.
tags: [session, phase-2, memory, query, explain, acceptance]
timestamp: 2026-07-24T04:30:00+08:00
paradigma:
  layer: log
  lifecycle: append-only
  okf_export: optional
  update_policy: append-only
---

# Session Summary

## User Goal

按照正式主计划持续向前推进，每完成一个 Batch 更新 memory-bank 并 commit；当前完成 Batch 2.6 并审计 Phase 2 退出门限。

## Actions Taken

- 新增 `pd memory query`，映射 text mode、ID/path/tag/scope/status/validity/relation/limit flags 到既有 structured query。
- Query JSON/text 返回 match reasons/fields、scope、validity、status、provenance、confidence、relation source 和 warnings 等完整解释字段。
- 非 active 显式结果标记 ordinary-query exclusion；未传 valid_at 时只警告、不注入 wall clock，从而保持 stable query。
- 新增 canonical-first `explain_memory` 和 `pd memory explain`，返回 hashes/revision/canonical、当前 validity evaluation 与 catalog freshness。
- Explain 在 catalog missing/corrupt/stale 时仍返回目标 canonical record 并给出恢复警告；query 继续严格拒绝 stale catalog。
- 新增 rich response、filter validation、UTF-8 text、corrupt-catalog explain 和 Phase 2 golden lifecycle tests。

## Phase 2 Exit Audit

1. propose → commit → query → explain → revise → forget：`test_phase2_golden_propose_commit_query_explain_revise_forget_chain`，revision 1→4，forget 后普通 query 为 0。
2. 所有 canonical 修改具有 revision：Kernel transition tests + Markdown store strict +1 CAS + golden chain。
3. 每条正式记忆具有 provenance：MemoryRecord constructor invariant、proposal strict payload、revise requires provenance。
4. SQLite 可从 Markdown 完整重建：catalog projection/verify/corruption/replace tests，并由每次 mutation refresh。
5. 普通查询不返回 expired、superseded 或 tombstoned：MemoryQuery 默认严格 active-only；lifecycle tests 验证 supersede/forget 后不可见，status filter tests 覆盖显式非 active。
6. 相同结构化 Query 产生稳定结果：stable-order/reasons integration test，query 不注入当前时间。
7. Memory Kernel 不包含 Coding 语义：dependency architecture gate + domain-profile token architecture gate。

## Validation

- Explain/golden/failure/architecture 针对性测试：17/17 passed。
- 最终全量 unit/integration/architecture/characterization/failure-injection 回归：135/135 passed。
- repository quality gate：6/6 passed；39 个 concept、47 个 link-check 文件均无 error/warning。
- 从独立 wheel 安装目录验证 rich query/explain outcomes、provenance projection 和 catalog freshness。

## Follow-ups

- 准备 v0.6.0 release：版本元数据、migration/release notes、cross-platform CI 和安装产物 smoke test。
- Phase 3 Batch 3.1：Coding Memory Profile，应只使用 Kernel/Application API，不向 Kernel 注入 Coding 特例。
