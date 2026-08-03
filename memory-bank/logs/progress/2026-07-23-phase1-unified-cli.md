---
type: paradigma-session-log
title: Phase 1 Unified CLI
description: Session summary for the package-backed pd command tree and adapter-neutral application services.
tags: [session, phase-1, cli, application-service, python]
timestamp: 2026-07-23T22:47:10+08:00
paradigma:
  layer: log
  lifecycle: append-only
  okf_export: optional
  update_policy: append-only
---

# Session Summary

## User Goal

继续 Phase 1 Batch 1.2，建立一个可安装、可脚本化且默认安全的统一 CLI。

## Actions Taken

- 在 package metadata 中注册 `pd` console script。
- 新增 adapter-neutral `CommandOutcome`，统一 data、messages、diagnostics、changed、dry-run 和 exit code。
- 新增 package application services，承载版本、配置、六项质量门禁、Harness 诊断、index rebuild/verify 和 active-task archive 业务逻辑。
- 新增 `pd version`、`pd config validate`、`pd check`、`pd diagnose`、`pd index rebuild/verify` 和 `pd task archive`。
- 所有叶子命令支持 text/JSON、dry-run 和显式 project root；task archive 默认只预览，只有 `--write` 才执行。
- 新增 CLI unit tests，覆盖结构化聚合结果、无副作用 dry-run、self-diagnose 和显式归档写入。

## Validation

- 全量 unit/integration/architecture/legacy characterization：65/65 passed。
- wheel 构建并安装到隔离 Windows venv 后，真实 `pd.exe version --format json --dry-run` 返回一致的五维版本数据。
- Repository self-diagnose 无 gap；index verify 无 stale output。
- Archive 默认调用保持源文件不变，显式 `--write` 创建一个 archive 并重置 active task。

## Follow-ups

- Batch 1.3：把 `.paradigma/tools/` 中的旧入口改为 package-backed thin wrappers。
- 增加新旧 CLI 等价、安装后 console script 和 Windows/POSIX 路径集成验证。
