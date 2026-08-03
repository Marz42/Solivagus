---
type: paradigma-session-log
title: Phase 2 Deterministic Memory Query
description: Session summary for Batch 2.4 structured filters, keyword and FTS retrieval, stable ordering, and one-hop relation expansion.
tags: [session, phase-2, memory, query, retrieval, fts5]
timestamp: 2026-07-24T02:25:00+08:00
paradigma:
  layer: log
  lifecycle: append-only
  okf_export: optional
  update_policy: append-only
---

# Session Summary

## User Goal

按照正式主计划持续向前推进，每完成一个 Batch 更新 memory-bank 并 commit；当前完成 Batch 2.4。

## Actions Taken

- 新增 storage-aware `CatalogQuery` 和 `CatalogTextMode`，保持 Kernel `MemoryQuery` 不包含 path/SQLite 细节。
- 实现 memory ID、canonical path、literal casefold keyword、FTS5 expression、tag、scope、status 与 inclusive validity 组合查询。
- query 前完整 verify canonical/catalog freshness；缺失、漂移、损坏或非法 FTS 明确返回 `PD_CATALOG_QUERY_ERROR`，不修改 Markdown。
- 实现 score 降序 + memory ID 升序的 direct 稳定排序，以及 direct-first、outgoing-only、filtered one-hop relation expansion。
- 每条结果返回 matched fields、match reasons、适用 score 和 relation source；相同结构化请求产生稳定 projection。
- 新增 object-returning `query_memories` Application API；按计划不提前加入 Batch 2.6 的 CLI/explain adapter。
- 新增 integration、failure-injection 和 architecture regression coverage，并固化 ADR-013 与 memory query contract。

## Validation

- Query/architecture/failure 针对性测试：15/15 passed。
- 最终全量 unit/integration/architecture/characterization/failure-injection 回归：119/119 passed。
- repository quality gate：6/6 passed；35 个 concept、43 个 link-check 文件均无 error/warning。
- 从独立 wheel 安装目录导入 public query API，并完成零记录 catalog rebuild/query。

## Follow-ups

- Batch 2.5：实现 propose/validate/commit/revise/supersede/forget mutation lifecycle，并让 canonical write 后的 catalog 一致性策略明确可恢复。
- Batch 2.6：在同一 Application API 上增加 `pd memory query/explain`，补齐 exclusions、provenance 与 confidence 的面向用户解释。
