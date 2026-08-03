---
type: paradigma-glossary
title: Project Glossary
description: Glossary of project-specific terms and abbreviations.
tags: [glossary, terminology]
timestamp: 2026-07-23T21:35:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: cold
  lifecycle: evolving
  update_policy: agent-editable
  epistemic_status: confirmed
  retrieval_hints:
    zh:
      - 术语
      - 缩写
      - OKF
    en:
      - glossary
      - abbreviations
      - OKF
  symbols:
    - OKF
    - Memory-Bank
  relations:
    related_to:
      - /project-brief.md
---

# Terms

| Term | Meaning | Notes |
|------|---------|-------|
| OKF | Open Knowledge Format | Markdown + YAML frontmatter knowledge bundle format. |
| Memory-Bank | External memory system used by Paradigma | Split into runtime, logs, and knowledge in the OKF iteration. |
| Runtime | Ephemeral Agent state (`memory-bank/runtime/`) | Holds active-task; not exported as OKF knowledge. |
| Logs | Operational logs (`memory-bank/logs/`) | Progress sessions, changelog, tool-generated summaries; append-first. |
| Knowledge | Long-lived OKF-compatible concepts (`memory-bank/knowledge/`) | architecture, contracts, decisions, domains, manuals, known issues, glossary. |
| HOT | Files read at every session start | active-task (runtime) + HOT knowledge (project-brief, architecture, conventions, repository-contract). |
| WARM | Files read on-demand by task routing | domains, contracts, manuals, RFC docs. |
| COLD | Files read for audits, archaeology, or disputes | decisions, known issues, glossary. |
| Concept Document | OKF-compatible Markdown file under `knowledge/` or `docs/rfc/` | Must have YAML frontmatter with non-empty `type`. |
| Paradigma Namespace | `paradigma:` block in frontmatter | Holds Paradigma-specific metadata (temperature, lifecycle, update_policy, epistemic_status, retrieval_hints, symbols, relations). |
| Retrieval Hints | `paradigma.retrieval_hints` in frontmatter | zh/en keyword arrays that `pd-index.py` uses for local and machine route indexes. |
| Symbols | `paradigma.symbols` in frontmatter | Domain-specific identifiers (class names, endpoints, constants) for index routing. |
| Epistemic Status | `paradigma.epistemic_status` field | One of: confirmed, decision, proposal, assumption, deprecated, unknown. |
| Update Policy | `paradigma.update_policy` field | One of: agent-editable, requires-human-confirmation, append-only, generated, read-only. |
| Generated Block | Section between `<!-- BEGIN PARADIGMA AUTO-INDEX -->` and `<!-- END PARADIGMA AUTO-INDEX -->` | Used only in local subdirectory indexes and maintained by `pd-index.py`; root navigation is manual. |
| Session Log | Progress log under `logs/progress/` | Records one Agent session: goal, actions, files, decisions, follow-ups. |
| ADR | Architecture Decision Record | Stored under `knowledge/decisions/`; append-only, accepted decisions constrain future work. |
| Active Task | Current task state in `memory-bank/runtime/active-task.md` | Single focus; archived to session log on completion. |
| DESIGN.md | 项目根目录的视觉设计规范文件 | 遵循 google-labs-code/design.md 格式，包含 colors/typography/spacing/components 等结构化设计 tokens。可选——无前端需求的项目无需创建。Agent 在涉及前端/UI 任务时将其作为 WARM 参考。 |
| 设计器模式 | DESIGN.md 的 Agent 辅助创建流程 | 即 INIT_PROMPT 模式 G。通过问答形式引导用户定义视觉风格，Agent 逐段构建符合 design.md 规范的 DESIGN.md 文件。详见 `manuals/paradigma-design-wizard.md`。 |
| Harness 诊断器 | Paradigma 版本差距检测工具 | 即 `pd-diagnose.py`。对比项目与上游 Paradigma 在结构、工具、Schema、配置、协议五个维度的差异，生成可操作的迁移建议。 |
| 结构迁移 | pre-OKF flat 结构到 OKF 三态结构的升级过程 | 即 INIT_PROMPT 模式 H。由 Agent 主导：创建 runtime/logs/knowledge 目录，为知识文档添加 OKF frontmatter，拆分组合文件为独立 concept 文档。 |
| 中期计划 (Plan) | 介于项目愿景和当前任务之间的多会话实施路径 | `paradigma-plan` 类型文档，存放于 `knowledge/plans/`。含 Goal、Scope、Approach、Tasks、Status。执行中为 WARM，完成后自动降为 COLD。 |
| Distribution Version | Paradigma 源码发行版本 | 根 `VERSION` 是唯一发行真相源。 |
| Installed Distribution Version | 当前 workspace 已部署的 Paradigma 版本 | 记录在 `.paradigma/config.yaml` 的 `installed_distribution_version`；源码仓库中必须与根 `VERSION` 一致。 |
| Config Schema Version | `.paradigma/config.yaml` 的格式版本 | 使用 `config_schema_version`，不等于发行版本。 |
| Document Schema Version | Paradigma concept-document 类型注册表版本 | 使用 `.paradigma/schemas/paradigma-types.schema.yaml` 的 `document_schema_version`。 |

# Abbreviations

| Abbreviation | Meaning |
|--------------|---------|
| RFC | Request for Comments |
| OKF | Open Knowledge Format |
| ADR | Architecture Decision Record |
| SemVer | Semantic Versioning |

# Domain-specific Meanings

| Term | Domain | Meaning |
|------|--------|---------|
| pd-* | Tooling | Paradigma deterministic tool prefix (e.g., `pd-lint-okf.py`). |
| HOT/WARM/COLD | Memory-Bank | Temperature tiers for retrieval frequency, not directory location. |
