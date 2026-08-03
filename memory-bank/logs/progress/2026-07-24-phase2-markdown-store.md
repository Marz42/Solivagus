---
type: paradigma-session-log
title: Phase 2 Canonical Markdown Codec and Store
description: Session summary for Batch 2.2 deterministic memory documents, dual hashes, revision checks, and atomic storage.
tags: [session, phase-2, markdown, storage, integrity, revision]
timestamp: 2026-07-24T00:07:33+08:00
paradigma:
  layer: log
  lifecycle: append-only
  okf_export: optional
  update_policy: append-only
---

# Session Summary

## User Goal

继续正式计划 Phase 2，稳健完成 Batch 2.2 Markdown Codec & Store。

## Actions Taken

- 定义 `memory_schema_version: "0.1"` exact-key frontmatter 和一个文档对应一个 MemoryRecord 的 canonical 表达。
- 实现 MemoryMarkdownCodec 的确定性 Unicode round trip、timezone-aware datetime、strict nested Schema 和 semantic content hash。
- 扩展共享 UTF-8 reader，在保留既有 parser diagnostics 的同时提供原始字节用于 source hash。
- 实现 MarkdownMemoryStore 的 read/create/update/paths、revision 1 创建、严格 `+1` 更新、created_at 保持和 updated_at 单调校验。
- 用 exact-byte source hash、managed-writer lock 和 atomic create/replace 防止静默覆盖人工或并发修改。
- 新增 unit、integration、architecture 和 failure-injection tests，覆盖 BOM/排版编辑、未更新 hash 的正文编辑、stale writer、锁冲突、create/replace 故障与清理。
- 新增 v0.1 golden Markdown 文档，锁定字段顺序、UTC 时间、Unicode、hash 和正文边界。
- 新增 ADR-011 和独立 memory document contract，并同步架构、约定、repository contract、changelog 与索引。

## Validation

- Markdown codec/store 针对性测试：23/23 passed。
- 最终全量 unit/integration/architecture/characterization/failure-injection 回归：102/102 passed。
- 源码隔离安装后成功从安装目录执行 MarkdownMemoryStore create/read，并验证 record 与 content hash。
- relocation 回归曾发现契约文档硬链接上游 devplan；改为非强制路径说明后，精简衍生 workspace 和 Unicode 路径测试均通过。

## Follow-ups

- Batch 2.3：从 canonical Markdown 完整重建 SQLite + FTS5 catalog，并实现 rebuild/verify/stats。
- Batch 2.5 mutation service 需要在提交前使用本批的 expected source hash，并为残留 writer lock 提供显式诊断/恢复操作。
