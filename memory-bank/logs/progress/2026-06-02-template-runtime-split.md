---
type: paradigma-session-log
title: Session 2026-06-02 模板与运行时分离
description: 设计模板污染问题的解决方案，建立 .template.md + .gitignore 模式。
tags: [session-log, template, runtime]
timestamp: 2026-06-02T23:30:00+08:00
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

解决 Memory-Bank 模板污染问题：下游用户 clone 后会拿到包含上游项目历史的文件。

## Actions Taken

- [x] 识别模板污染问题：包含本项目历史的 `progress.md`、`decisions.md` 等会在 clone 后暴露给下游
- [x] 设计解决方案：`.template.md`（跟踪）+ `.md`（gitignored）复制模式
- [x] 创建 `progress.template.md`、`decisions.template.md`、`known-issues.template.md`、`glossary.template.md`
- [x] 创建 `.gitignore` 排除 4 个运行时数据文件
- [x] 更新 `README.md`（新增步骤 2：激活 runtime 模板 + 目录树更新 + 维护原则第 4 条）
- [x] 更新 `INIT_PROMPT.md`（新增前置条件说明 + 模式 E：Memory-Bank 模板激活）
- [x] 验证 `git check-ignore` 确认 4 个文件全部被正确排除

## Decisions Proposed

- **ADR-002 (旧): 模板与运行时分离** — 采用 `.template.md` + `.gitignore` 模式。此决策已被 OKF 迁移后的 `memory-bank-template/` 独立目录方案取代，但其核心思想（模板与运行记忆分离）延续至今。详见 `adr-001-template-runtime-split.md` 附录。

## Decisions Accepted

- ADR-002 (旧): 模板与运行时分离 — 已采纳

## Knowledge Updates

- 建立了模板与运行时分离的标准
- 更新了 README.md 和 INIT_PROMPT.md 的初始化流程

## Follow-ups

- 后续可以考虑在 CI 中加入检查，防止 runtime 文件被意外提交
- 如果未来出现新的"模板 + 运行时"混合文件，需要及时拆分为两个文件
