---
type: paradigma-session-log
title: Session 2026-06-02 Memory-Bank 体系搭建
description: Paradigma 最早期的 Memory-Bank 体系设计会话。
tags: [session-log, bootstrap, memory-bank]
timestamp: 2026-06-02T23:00:00+08:00
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

搭建 Paradigma 项目的 Memory-Bank 体系。

## Actions Taken

- [x] 设计 memory-bank 目录结构和文件模板
- [x] 创建 AGENT_RULES.md（IDE 无关的协议原文）
- [x] 设计知识温度体系（HOT / WARM / COLD）
- [x] 创建 INIT_PROMPT.md（多模式会话启动模板）
- [x] 创建 decisions.md（含 ADR-001 知识温度分离决策记录）
- [x] 创建 known-issues.md、glossary.md 冷知识模板
- [x] 创建 progress.md 会话日志
- [x] 创建 .cursor/rules/memory-bank-protocol.mdc（Cursor Rule 适配器）
- [x] 更新 README.md
- [x] 创建 manuals/ 目录和文件
- [x] 重写 project-brief.md（9 板块完整模板）
- [x] 填充 conventions.md（8 板块编码规范）
- [x] 输出 Memory-Bank 体系 8 维度演进路线及优先级排序

## Decisions Proposed

- **ADR-001 (旧): Memory-Bank 知识温度分离** — 将 memory-bank 内容按使用频率分为 HOT/WARM/COLD 三级。HOT 每次必读，WARM 按需读，COLD 排查时读。此决策现已融入 `AGENT_RULES.md` 核心协议和 `architecture.md` 的温度体系定义中。

## Decisions Accepted

- ADR-001 (旧): Memory-Bank 知识温度分离 — 已采纳

## Knowledge Updates

- 创建了 project-brief.md、conventions.md、glossary.md 等核心知识文档
- 建立了 HOT/WARM/COLD 三层知识温度体系

## Follow-ups

- architecture.md、data-contracts.md、roadmap.md、active-task.md 仍为空模板，待正式项目启动时填充
- domains/ 下的 module_1.md 为空，待按需创建具体模块文档
