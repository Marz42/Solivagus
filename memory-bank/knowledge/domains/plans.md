---
type: paradigma-domain
title: Plans Domain
description: Mid-term planning layer bridging project vision and active task execution within Paradigma Memory-Bank.
tags: [domain, plans, planning, roadmap]
timestamp: 2026-07-23T21:35:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: evolving
  update_policy: agent-editable
  epistemic_status: confirmed
  retrieval_hints:
    zh:
      - 计划
      - 中期规划
      - 实施路径
      - 任务拆解
    en:
      - plans
      - mid-term planning
      - roadmap
      - task breakdown
  symbols:
    - paradigma-plan
    - knowledge/plans
  relations:
    depends_on:
      - /architecture.md
      - /domains/protocol.md
    related_to:
      - /contracts/repository-contract.md
---

# Responsibility

The Plans domain adds a mid-term planning layer to Paradigma Memory-Bank, bridging the gap between high-level vision (`project-brief.md`) and session-level execution (`runtime/active-task.md`).

## Problem

`active-task.md` is designed for single-focus, short-lived work (one session). It cannot represent:

- Multi-session, multi-task initiatives ("Add payment module: 5 tasks across 2 weeks")
- Parallel active plans ("Auth refactor + payment module, both in progress")
- Abstract/high-level decisions ("We need to decide on JWT vs session before coding")

These gaps cause plans to exist only in conversation context, lost when a session ends.

## The Plans Layer

```
project-brief.md          ← "We are building a SaaS platform" (vision, years)
    ↓
knowledge/plans/*.md      ← "Q3: add payment module" (mid-term, days-to-weeks)  NEW
    ↓
runtime/active-task.md    ← "Implement WeChat Pay callback" (now, hours)
```

| Plan document | Has | Active-task references it |
|---|---|---|
| `plans/add-payment.md` | Goal, Scope, Approach, Tasks (5 items) | `active-task.md` Relevant Knowledge links to it |
| `plans/auth-refactor.md` | Goal, Scope, Approach, Tasks (3 items) | Same |

## Lifecycle & Temperature

Plans have a temperature switch based on status:

| Status | `temperature` | `epistemic_status` | Agent behavior |
|--------|--------------|-------------------|----------------|
| `proposed` | warm | proposal | Index routes to it |
| `in-progress` | warm | decision | Agent reads on related tasks |
| `completed` | cold | confirmed | Retained as historical record, not routed |
| `archived` | cold | deprecated | Ignored |

Agent responsibility: when marking a plan `completed`, update frontmatter `temperature: cold`. This is NOT automatic — the Agent must do it explicitly.

# Public Interfaces

## File Structure

```
memory-bank/knowledge/plans/
├── index.md                    ← local generated block by pd-index.py
└── <slug>.md                   ← one file per plan (type: paradigma-plan)
```

## paradigma-plan Type

| Section | Purpose |
|---------|---------|
| `# Goal` | What this plan aims to achieve (1-2 sentences) |
| `# Scope` | Boundaries: what's in, what's out |
| `# Approach` | High-level strategy (no code). Tech choices, key steps, dependencies |
| `# Tasks` | Checklist of executable tasks. Each should be concrete enough to become an active-task |
| `# Status` | `proposed` / `in-progress` / `completed` / `archived` |

## Relationship with active-task

```markdown
## Relevant Knowledge
- /memory-bank/knowledge/plans/add-payment.md  ← parent plan
- /memory-bank/knowledge/contracts/payment-api.md
```

## Relationship with ADRs

If a plan involves architectural decisions, create a separate ADR under `decisions/` and cross-reference:

```markdown
# Approach
...
See /decisions/adr-0004-jwt-vs-session.md for auth strategy decision.
```

# Internal Flow

```text
User proposes a plan
  → Agent creates knowledge/plans/<slug>.md (status: proposed)
  → User approves (status → in-progress, epistemic_status → decision)
  → Tasks become active-task inputs in subsequent sessions
  → All tasks complete
  → Agent updates status → completed, temperature → cold
  → Plan remains in knowledge/ as historical reference
```

# Dependencies

- `pd-index.py` — rebuilds the local plans index and complete machine inventory
- `pd-lint-okf.py` — validates required sections (Goal, Scope, Approach, Tasks, Status)
- `AGENT_RULES.md` — lists `knowledge/plans/*.md` in WARM tier

# Related Contracts

- `memory-bank/knowledge/contracts/repository-contract.md` — schema type registry
- `memory-bank/knowledge/domains/protocol.md` — WARM list references

# Known Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Plans accumulate and never get completed | WARM layer bloats with stale plans | Agent should periodically review plan status during sessions; `pd-check-hot-size` warns on large WARM directories |
| Plan granularity too coarse | Not useful for driving active tasks | Template enforces concrete Tasks section |
| Plan granularity too fine | Essentially duplicates active-task | If a plan has only 1 task, it probably should just be an active-task |
| Agent forgets to flip temperature on completion | Completed plans stay WARM, cluttering index routes | Plan Phase checkpoint (WS-1) reminds agent to update plan status |
