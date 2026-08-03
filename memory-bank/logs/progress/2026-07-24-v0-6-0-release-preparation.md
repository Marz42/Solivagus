---
type: paradigma-session-log
title: v0.6.0 Release Preparation
description: Session summary for the Phase 2 release candidate, migration compatibility, and artifact validation.
tags: [session, release, v0.6.0, phase2, migration, validation]
timestamp: 2026-07-24T01:19:00+08:00
paradigma:
  layer: log
  lifecycle: append-only
  okf_export: optional
  update_policy: append-only
---

# Session Summary

## User Goal

完成 Phase 2 后稳健准备 Paradigma v0.6.0 发布候选，并在发布收口后继续 Phase 3。

## Actions Taken

- 将根 `VERSION`、config `installed_distribution_version`、README 和仓库行为基线统一 bump 到 0.6.0。
- 将 Phase 2 的 Unreleased 内容冻结为 `[0.6.0] - 2026-07-24`，保留新的空 Unreleased 区域。
- 明确七个版本维度：distribution 0.6.0、installed distribution 0.6.0、config 0.4、OKF 0.1、document 0.2、memory document 0.1、catalog 0.1。
- 更新发布手册，纳入 catalog rebuild/verify 和隔离 wheel smoke test。
- 新增 0.5.1 → 0.6.0 迁移说明：既有 knowledge/runtime/logs 不批量转换，旧 config 缺少 Memory 路径时使用安全默认值，catalog 始终可删除重建。
- 新增旧 config 兼容回归，验证 config schema 0.3 可无损读取 v0.6 Memory 路径默认值。
- 构建并隔离安装 `paradigma-0.6.0-py3-none-any.whl`，通过 propose → commit → query → explain → forget 生命周期 smoke test。

## Validation

- `python -m unittest discover -s tests -p "test_*.py" -v`: 136/136 passed。
- wheel build: `paradigma-0.6.0-py3-none-any.whl`，isolated import version 0.6.0。
- installed-wheel lifecycle smoke: candidate 创建、active commit、query 命中 1 条、explain 成功、最终 `tombstoned`。
- repository catalog: zero canonical records，rebuild/verify current。

## Release Assessment

- Phase 2 代码、迁移策略和安装产物已形成完整、可复现的 v0.6.0 候选。
- 兼容风险集中在衍生项目配置升级；安全默认值和空 catalog 合法性已由测试覆盖，不要求一次性改写旧知识。
- 本提交只准备发布候选，不创建 tag、不 push，也不替代远端 Windows/POSIX CI 审核。

## Follow-ups

- 推送发布候选并等待远端 CI；通过后由人工确认创建 annotated `v0.6.0` tag。
- 开始 Phase 3 Batch 3.1 Coding Domain Model，保持 Coding 语义位于 Kernel 外层。
