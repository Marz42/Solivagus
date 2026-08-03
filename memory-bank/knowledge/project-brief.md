---
type: paradigma-project-brief
title: Project Brief
description: Project vision, target users, scope, non-goals, and success criteria for Solivagus.
tags: [project, brief, scope]
timestamp: 2026-08-03T16:32:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: hot
  lifecycle: stable
  update_policy: requires-human-confirmation
  epistemic_status: confirmed
  retrieval_hints:
    zh:
      - 项目愿景
      - 技术文献翻译
      - PDF 翻译 CLI
    en:
      - project vision
      - technical literature translation
      - PDF translation CLI
  symbols:
    - Solivagus
    - PaddleOCR-VL
    - DeepSeek
  relations:
    informs:
      - /architecture.md
      - /contracts/repository-contract.md
---

# Vision

Solivagus 是面向个人研究与技术阅读的本地 PDF 技术文献智能翻译 CLI。系统使用 PaddleOCR-VL 完成版面理解与结构化提取，使用 DeepSeek API 完成英文到简体中文的技术翻译，并输出适合 Obsidian / Markdown 阅读器的中文与双语文档。

# Target Users

| User | Need | Frequency |
|------|------|-----------|
| 个人研究者 / 技术读者 | 可靠翻译论文、技术报告与长篇教材 | Daily/Weekly |
| 批量文档处理用户 | 断点续跑、夜间无人值守、目录批处理 | Per batch |

# Scope

TODO（模式 A 填充）：输入范围、输出产物、OCR/翻译流水线边界、CLI 能力。当前基线见 `project-brief/project-brief.md`。

# Non-goals

TODO（模式 A 填充）。首版明确不做：Web UI、SaaS、多用户、原版式 PDF 重排、RAG/Agent 工作流等。

# Success Criteria

TODO（模式 A 填充）。方向性目标：批处理可靠、可恢复、可观测、成本可控、结构完整。

# Constraints

- 保持 CLI 产品形态；不建设 Web UI / 服务端 / 多用户系统。
- 正式项目在已验证 MVP 核心链路上重构，不更换 PaddleOCR-VL + DeepSeek 技术路线。
- Memory-Bank 与 Paradigma harness 随仓库维护；业务知识与框架知识分离。
- 详细设计草案位于 `project-brief/project-brief.md`，待模式 A 同步进 knowledge。
