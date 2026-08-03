---
type: paradigma-domain
title: Design System Domain
description: Visual design specification integration via DESIGN.md format, bridging Paradigma Memory-Bank with frontend design knowledge.
tags: [domain, design-system, design.md, frontend]
timestamp: 2026-07-08T15:23:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: evolving
  update_policy: agent-editable
  epistemic_status: confirmed
  retrieval_hints:
    zh:
      - 设计系统
      - 视觉规范
      - 前端设计
      - DESIGN.md
      - design.md
    en:
      - design system
      - visual specification
      - frontend design
      - DESIGN.md
      - design.md
  symbols:
    - DESIGN.md
    - design.md
    - design-system
  relations:
    depends_on:
      - /architecture.md
    related_to:
      - /contracts/repository-contract.md
      - /manuals/paradigma-design-wizard.md
---

# Responsibility

The Design System domain manages the visual specification layer for Paradigma-managed projects. It bridges the [google-labs-code/design.md](https://github.com/google-labs-code/design.md) format with Paradigma's Memory-Bank, enabling coding agents to produce visually consistent frontend output by referencing structured design tokens.

This domain is **optional** — projects without a frontend (CLI tools, pure backend services, text-only research) do not need to activate it.

## Activation

A project activates this domain when a `DESIGN.md` file exists at the project root. No configuration flag is required; the presence of the file is the activation signal.

# Public Interfaces

## DESIGN.md File

Location: `{project_root}/DESIGN.md`

Format: [design.md specification](https://github.com/google-labs-code/design.md/blob/main/docs/spec.md) — YAML frontmatter (design tokens) + Markdown body (design rationale).

### Token Schema (summary)

```yaml
version: "alpha"        # optional
name: <string>
description: <string>   # optional
colors:
  <token-name>: <Color>
typography:
  <token-name>: <Typography>
rounded:
  <scale-level>: <Dimension>
spacing:
  <scale-level>: <Dimension | number>
components:
  <component-name>:
    <token-name>: <string | token reference>
```

### Token Types

| Type | Format | Example |
|------|--------|---------|
| Color | Any CSS color | `#1A1C1E`, `oklch(62% 0.18 250)` |
| Dimension | number + unit | `48px`, `-0.02em` |
| Token Reference | `{path.to.token}` | `{colors.primary}` |
| Typography | object with `fontFamily`, `fontSize`, etc. | See spec |

### Section Order

When present, sections must follow the canonical order: Overview, Colors, Typography, Layout & Spacing, Elevation & Depth, Shapes, Components, Do's and Don'ts.

## Tool Bridge

| Tool | Role |
|------|------|
| `pd-check-all.py` | Checks DESIGN.md existence and basic format validity (YAML frontmatter, required token fields). Warnings only — does not block non-frontend projects. |
| `npx @google/design.md lint` | Deep validation: broken token references, WCAG contrast ratios, section ordering. Optional external tool. |

# Internal Flow

```text
Project with frontend needs
  → CREATE DESIGN.md (manually or via INIT_PROMPT mode G)
  → pd-check-all.py picks up DESIGN.md
  → Agent reads DESIGN.md alongside knowledge docs for frontend tasks
  → Agent references design tokens when generating UI code
  → Update Phase checks DESIGN.md consistency (WS-1 step 9)
```

# Dependencies

- `DESIGN.md` at project root — the single source of truth for visual tokens.
- `@google/design.md` CLI (optional) — for deep lint, diff, and export.
- `pd-check-all.py` — validates DESIGN.md existence and basic format.
- `memory-bank-template/DESIGN.md` — blank template for new projects.

# Related Contracts

- `memory-bank/knowledge/contracts/repository-contract.md` — `pd-check-all.py` tool contract.
- `memory-bank/knowledge/domains/protocol.md` — AGENT_RULES.md references DESIGN.md in WARM list.
- `memory-bank/knowledge/glossary.md` — DESIGN.md entry.

# Known Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| design.md spec is `alpha` — token schema may change | DESIGN.md files created now may need migration later | Keep DESIGN.md version in frontmatter; `@google/design.md diff` can detect format changes |
| Agent visual reasoning is limited — generated UI may not fully reflect intent | UI output quality varies by model capability | DESIGN.md provides exact token values (hex, px) rather than relying on Agent interpretation |
| `@google/design.md` CLI requires Node.js | Deep lint not available in Node-free environments | Basic check in pd-check-all.py is always available; deep lint is optional |
| Token references in components require valid `{path}` syntax | Broken references cause silent fallbacks in agent output | pd-check-all.py basic check warns on obvious issues; `@google/design.md lint` catches broken refs |
