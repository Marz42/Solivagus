---
type: paradigma-session-log
title: Phase 0 Unified YAML and Frontmatter Parser
description: Session summary for consolidating all YAML consumers on PyYAML with structured parser diagnostics.
tags: [session, phase-0, yaml, frontmatter, diagnostics]
timestamp: 2026-07-23T00:06:54+08:00
paradigma:
  layer: log
  lifecycle: append-only
  okf_export: optional
  update_policy: append-only
---

# Session Summary

## User Goal

提交已有 Phase 0 工作并继续 Batch 0.2：统一 YAML/frontmatter parser。

## Actions Taken

- 新增 `_paradigma_yaml.py`，集中安全 YAML 加载、Markdown frontmatter 分割、UTF-8 读取和 dotted-key compatibility view。
- 使用 PyYAML `SafeLoader`，拒绝重复键，并保持 timestamp 为协议字符串。
- 新增稳定的 `ParseDiagnostic` / `ParseFailure` 模型，区分编码、文件读取、frontmatter 边界、YAML 语法、重复键和根类型错误。
- 将 lint、links、index、HOT size、diagnose、version 和 progress compact 迁移到共享 parser，删除各工具的手写 YAML subset 实现。
- 保留 Schema 校验在 lint 层，parser failure 不再降级成缺失字段。
- 新增根 `requirements.txt`，CI 在质量门禁前安装 PyYAML。
- 增加 BOM、CRLF、中文、timestamp、非法 YAML、重复键、非 mapping 根节点、frontmatter 边界和非法 UTF-8 回归测试。
- 新增 ADR-005，并同步 README、architecture、conventions、repository contract、tooling domain、baseline manual 和 changelog。

## Validation

- `python -m unittest discover -s tests -p "test_*.py" -v`: 28/28 passed。
- `python -m py_compile`: 全部工具和测试通过。
- `pd-check-all.py --keep-going`: 6/6 passed。
- `pd-diagnose.py --project . --upstream . --json`: 0 gaps。
- `git diff --check`: passed。

## Decisions

- PyYAML 6.x 是当前唯一运行时第三方依赖，其余工具逻辑继续优先使用 Python 标准库。
- 所有 YAML/frontmatter 消费者必须通过 `_paradigma_yaml.py`；partial tool copy 也必须携带共享模块。
- 版本保持 0.5.0 并写入 Unreleased，Phase 0 发布准备阶段统一 bump 0.5.1。

## Follow-ups

- Batch 0.3：修复 task 状态枚举和 completed 判断。
- 为 archive 引入显式 mutation plan、原子写入、幂等性和故障恢复测试。
- 后续调整索引职责，避免 index 成为隐式主存储。
