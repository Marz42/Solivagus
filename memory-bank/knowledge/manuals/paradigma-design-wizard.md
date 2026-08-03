---
type: paradigma-manual
title: Paradigma Design Wizard
description: Guide for creating visual design specifications (DESIGN.md) via agent-assisted Q&A using INIT_PROMPT mode G.
tags: [manual, design, design.md, frontend, paradigma]
timestamp: 2026-07-08T15:30:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: evolving
  update_policy: agent-editable
  epistemic_status: confirmed
  retrieval_hints:
    zh:
      - 设计器
      - 设计向导
      - 视觉设计
      - DESIGN.md
      - 模式 G
    en:
      - design wizard
      - visual design
      - DESIGN.md
      - mode G
  symbols:
    - INIT_PROMPT
    - mode G
    - DESIGN.md
  relations:
    related_to:
      - /domains/design-system.md
      - /manuals/paradigma-baseline-test.md
---

# Purpose

This manual guides users through creating a visual design specification (DESIGN.md) using Paradigma's design wizard mode (INIT_PROMPT mode G). The wizard is an agent-assisted Q&A flow that produces a [google-labs-code/design.md](https://github.com/google-labs-code/design.md)-compliant file at the project root.

This manual is for **users who want to create or regenerate a DESIGN.md**. It is not a reference for the DESIGN.md format itself — see `domains/design-system.md` for that.

# Preconditions

- Project is initialized with Paradigma Memory-Bank (mode F completed).
- `memory-bank/knowledge/domains/design-system.md` exists (part of Paradigma template).
- Optional: Node.js 18+ for `@google/design.md` CLI deep validation.

# Steps

## 1. Activate the Wizard

Copy the Mode G prompt from `INIT_PROMPT.md` and paste it into your IDE chat. Replace the `{{PLACEHOLDER}}` values:

- **项目类型**: Be specific — "SaaS Dashboard" helps the agent choose data-dense layouts; "内容博客" leads to reading-optimized typography.
- **视觉风格偏好**: If unsure, leave as "不确定，请你推荐" — the agent will propose based on project type.
- **参考品牌/产品**: This is the strongest signal. "Linear.app" pushes toward minimal dark mode with system fonts; "Stripe" leans into colorful gradients and clean spacing.
- **品牌色**: Paste hex values if you already have brand colors. Otherwise leave blank.

## 2. Guide the Agent Through Four Phases

The wizard runs in four sequential phases:

| Phase | What happens | Your role |
|-------|-------------|-----------|
| 1. Discovery | Agent reads project context and proposes a design direction | Confirm or correct the direction |
| 2. Building | Agent builds each section (Overview → Colors → Typography → Layout → Components → Do's/Don'ts) | Confirm each section before the agent moves to the next |
| 3. Validation | Agent writes DESIGN.md and runs pd-check-all + optional deep lint | Review validation output |
| 4. Integration | Agent explains how DESIGN.md will be used in future sessions | Acknowledge |

**Important**: During Phase 2, the agent should pause after each section and wait for your confirmation. If the agent skips ahead, remind it: "请每段完成后等我确认再继续下一段。"

## 3. After Creation

Once DESIGN.md is created:

- `pd-check-all.py` will include it in quality checks (warn-only).
- The agent will read DESIGN.md as a WARM reference when working on frontend/UI tasks.
- To update the design system later, either edit DESIGN.md directly or re-run mode G.

# Verification

```bash
# Basic check (always available)
python .paradigma/tools/pd-check-all.py

# Deep validation (requires Node.js)
npx @google/design.md lint DESIGN.md

# Export tokens for Tailwind (optional)
npx @google/design.md export --format json-tailwind DESIGN.md > tailwind.theme.json
```

# Rollback

If mode G produces an unsatisfactory DESIGN.md:

1. Edit `DESIGN.md` directly to fix specific tokens or sections.
2. Or delete `DESIGN.md` and re-run mode G with refined preferences.
3. DESIGN.md is a plain text file — no other cleanup needed.

# Troubleshooting

| Symptom | Likely Cause | Action |
|---------|--------------|--------|
| Agent produces generic/poor color scheme | Preferences too vague | Rerun with specific reference brands (e.g. "Linear.app" or "Vercel") |
| Agent skips sections without confirmation | Phase 2 discipline not enforced | Remind: "请每段完成后等我确认再继续下一段" |
| `pd-check-all` warns about missing token sections | Agent omitted a required section | Ask agent: "请补充缺失的 Colors/Typography token section" |
| `npx @google/design.md lint` fails with contrast errors | Color pair fails WCAG AA | Ask agent to lighten/darken problematic color pair and re-run |
| DESIGN.md tokens not being used by agent in later sessions | Agent didn't read design-system domain | Remind: "请读取 memory-bank/knowledge/domains/design-system.md 和 DESIGN.md" |

# Citations

- [design.md spec](https://github.com/google-labs-code/design.md/blob/main/docs/spec.md)
- [design.md README](https://github.com/google-labs-code/design.md)
- `memory-bank/knowledge/domains/design-system.md`
- `INIT_PROMPT.md` — Mode G
