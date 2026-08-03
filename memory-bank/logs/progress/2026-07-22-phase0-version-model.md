---
type: paradigma-session-log
title: Phase 0 Version and Configuration Model
description: Session summary for separating Paradigma distribution, installation, config, OKF, and document schema versions.
tags: [session, phase-0, versioning, config, diagnostics]
timestamp: 2026-07-22T23:49:54+08:00
paradigma:
  layer: log
  lifecycle: append-only
  okf_export: optional
  update_policy: append-only
---

# Session Summary

## User Goal

执行正式开发计划 Phase 0 Batch 0.1：版本与配置统一。

## Actions Taken

- 新增共享 `_version.py`，集中读取和验证版本元数据。
- 新增 `pd-version.py`，支持默认、`--verbose`、`--check` 和 `--json` 输出。
- 明确根 `VERSION` 为 distribution release 唯一真相源。
- `.paradigma/config.yaml` 升级为 `config_schema_version: "0.2"`，增加 `installed_distribution_version`，保留独立 `okf_version`。
- 类型注册表将含义模糊的 `schema_version` 改名为 `document_schema_version`。
- `pd-diagnose.py` 使用共享版本读取逻辑，并优先读取上游根 `VERSION`。
- 旧 `paradigma_harness_version` 继续作为迁移输入，但会产生 deprecated gap。
- `pd-check-all.py` 增加版本门禁，CI 通过聚合检查自动执行。
- 新增 ADR-004，记录五维版本模型及兼容政策。
- 修正正式开发计划中的工具数量和 characterization coverage 清单。
- 同步 README、INIT_PROMPT、architecture、conventions、contract、tooling、migration flow 和 manuals。

## Version Model

| Dimension | Source | Current |
|-----------|--------|---------|
| Distribution | `VERSION` | 0.5.0 |
| Installed distribution | `.paradigma/config.yaml` | 0.5.0 |
| Config schema | `.paradigma/config.yaml` | 0.2 |
| OKF | `.paradigma/config.yaml` | 0.1 |
| Document schema registry | `.paradigma/schemas/paradigma-types.schema.yaml` | 0.2 |

## Validation

- `pd-version.py --verbose --check`: passed。
- `python -m unittest discover -s tests -p "test_*.py" -v`: 20/20 passed。
- `python -m py_compile`: all tools and tests passed。
- `pd-check-all.py --keep-going`: 6/6 passed。
- `pd-diagnose.py --project . --upstream .`: 0 gaps, detected/upstream 0.5.0。
- `git diff --check`: passed。

## Decisions

- 版本保持 0.5.0 并记录到 Unreleased；Phase 0 完成发布准备时再 bump 0.5.1。
- 当前 workspace 的安装版本暂存于 config；是否迁移到 lock file 推迟到 package/migration 语义稳定后评估。
- `pd-version.py` 是 Phase 1 统一 `pd version` CLI 之前的兼容入口。

## Follow-ups

- Batch 0.2：引入标准 YAML 库和统一 frontmatter parser。
- 为 YAML 语法、BOM、CRLF、中文、编码错误建立结构化 diagnostics 测试。
- 后续 Batch 0.3 修复严格状态枚举、归档 mutation plan、原子写入和幂等性。
