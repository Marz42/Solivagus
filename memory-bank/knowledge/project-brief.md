---
type: paradigma-project-brief
title: Project Brief
description: Project vision, target users, scope, non-goals, and success criteria for Project Paradigma.
tags: [project, brief, scope, okf]
timestamp: 2026-07-04T22:50:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: hot
  lifecycle: stable
  update_policy: requires-human-confirmation
  epistemic_status: confirmed
  retrieval_hints:
    zh:
      - 项目愿景
      - 适用范围
      - Agent 外部记忆
    en:
      - project vision
      - agent memory
      - scope
  symbols:
    - Project Paradigma
    - Memory-Bank
    - OKF
  relations:
    informs:
      - /architecture.md
      - /contracts/repository-contract.md
---

# Vision

Project Paradigma is an OKF-compatible Agent Memory Runtime Framework. It helps software projects preserve architecture decisions, working context, contracts, and operational knowledge across AI-assisted development sessions.

The project treats memory as a versioned repository asset: readable by humans, routable by agents, and checkable by deterministic tools.

# Target Users

| User | Need | Frequency |
|------|------|-----------|
| Solo developer using AI agents | Keep context, decisions, and constraints stable across sessions | Daily |
| Small engineering team | Share AI-readable project knowledge and reduce onboarding drift | Weekly/Daily |
| Template maintainer | Evolve the Paradigma protocol and templates without mixing runtime project memory with blank templates | Per release |

# Scope

Paradigma provides:

- OKF-compatible Markdown knowledge organization.
- Runtime/logs/knowledge separation for Agent memory.
- IDE-agnostic protocol source plus Cursor adapter.
- Bootstrap prompts and blank templates for derived projects.
- Local deterministic tools for linting, link checking, indexing, and runtime/log maintenance.

# Non-goals

- Paradigma is not an application framework.
- Paradigma does not prescribe a frontend/backend stack for derived projects.
- Paradigma does not replace domain-specific schemas such as OpenAPI, database migrations, or protobuf.
- Paradigma does not require a hosted service or external dependency for the MVP tooling.

# Success Criteria

| Criterion | Target |
|-----------|--------|
| Bootstrap clarity | A new project can activate Memory-Bank from templates with clear instructions |
| Agent continuity | New sessions can load active task, knowledge index, and HOT knowledge without guessing |
| OKF compliance | Knowledge and RFC concept documents pass strict local lint |
| Tooling closure | Index, links, runtime size, archive, and progress compaction can be checked locally |
| Version traceability | Protocol and template changes update VERSION, changelog, ADR, and session logs |

# Constraints

- `AGENT_RULES.md` remains the IDE-agnostic protocol source of truth.
- `.cursor/rules/memory-bank-protocol.mdc` must be synchronized after protocol changes.
- `memory-bank/knowledge/` and `docs/rfc/` concept documents must keep OKF-compatible frontmatter.
- `memory-bank/runtime/` must not accumulate long-lived knowledge.
- Generated index blocks must be updated by tools, not by hand.
