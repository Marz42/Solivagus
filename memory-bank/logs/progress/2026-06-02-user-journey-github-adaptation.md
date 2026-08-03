---
type: paradigma-session-log
title: Session 2026-06-02 用户旅程优化与 GitHub 适配
description: 模拟用户从 clone 到首次启动的全流程，修复卡点并适配 GitHub Template 使用模式。
tags: [session-log, user-journey, github, license]
timestamp: 2026-06-02T23:59:00+08:00
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

确保新用户从 clone Paradigma 到首次启动的全流程顺畅无卡点，并适配 GitHub Template 使用模式。

## Actions Taken

- [x] 完整模拟用户从 clone 到首次启动的全流程，识别 6 个卡点
- [x] 决策：INIT_PROMPT.md 集成 Setup prompt（模式 F），不另建 SETUP.md
- [x] 重写 README.md "如何使用" 部分 — 加入 GitHub Template 推荐、detach remote、首次 commit、两种路径总结
- [x] 新增 INIT_PROMPT.md 模式 F：一次性完成所有机械设置（cp 模板、改 README、改 .gitignore、检查 remote、首次 commit）
- [x] 微调 INIT_PROMPT.md 模式 A：增加"不确定字段标记 TODO"指引
- [x] 清理 .gitignore 注释中的 "paradigma" 引用
- [x] 创建 LICENSE 文件（MPL-2.0 — 文件级 copyleft：改 paradigma 本身须开源，用 paradigma 做的项目不受限）

## Decisions Proposed

- 许可证选择需权衡两个约束：paradigma 自身保持开源 vs 下游项目开闭源自由。MPL-2.0 的文件级 copyleft 恰好匹配模板项目的使用模式。

## Knowledge Updates

- README.md 重写用户旅程
- INIT_PROMPT.md 新增模式 F
- LICENSE 文件创建

## Follow-ups

- 无
