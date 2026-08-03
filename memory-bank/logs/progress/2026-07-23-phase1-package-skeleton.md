---
type: paradigma-session-log
title: Phase 1 Package Skeleton
description: Session summary for the installable src-layout package and reusable application-core foundations.
tags: [session, phase-1, package, python, architecture]
timestamp: 2026-07-23T22:31:40+08:00
paradigma:
  layer: log
  lifecycle: append-only
  okf_export: optional
  update_policy: append-only
---

# Session Summary

## User Goal

开始正式计划 Phase 1，先完成 Batch 1.1 Python Package Skeleton。

## Actions Taken

- 新增 setuptools `pyproject.toml` 和 `src/paradigma/` src-layout package，动态读取根 `VERSION`。
- 提取 structured diagnostics/errors/results、repository config、safe YAML/frontmatter parser、Schema registry/validator 和 atomic single-file writer。
- 核心模块不解析 CLI、不执行 subprocess、不直接打印，也不依赖 legacy tool 目录。
- 新增 unit、integration 和 architecture test 分层；逐个比较 package parser 与 legacy parser 对 canonical documents 和错误码的行为。
- 构建 `paradigma-0.5.1` wheel，并安装到 ignored 隔离目录验证 package metadata 和 import。
- CI 增加本地 package 安装步骤，同时继续保留全部 legacy characterization gates。
- 新增 ADR-008，并同步 README、架构、契约、tooling、测试手册与 changelog。

## Validation

- package core unit/integration/architecture + legacy characterization：59/59 passed。
- `pip wheel . --no-deps --no-build-isolation`: 生成 `paradigma-0.5.1-py3-none-any.whl`。
- 隔离 target install 后 `paradigma.__version__ == 0.5.1`，repository config installed version 为 0.5.1。

## Follow-ups

- Batch 1.2：建立 Application Service 和统一 `pd` CLI，支持 text/JSON/dry-run。
- Batch 1.3：将 legacy scripts 改为 package-backed thin wrappers，并删除重复业务逻辑。
