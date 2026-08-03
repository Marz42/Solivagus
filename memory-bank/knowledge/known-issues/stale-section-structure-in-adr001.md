---
type: paradigma-known-issue
title: Stale section structure in ADR-001 and manuals after OKF hardening
description: The first strict lint run exposed stale section structures in ADR-001 and manuals that did not match the updated schema registry.
tags: [known-issue, okf, lint]
timestamp: 2026-07-05T11:45:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: cold
  lifecycle: evolving
  update_policy: agent-editable
  epistemic_status: confirmed
  retrieval_hints:
    zh:
      - schema registry
      - section
      - 结构
      - strict lint
    en:
      - schema registry
      - section
      - structure
      - strict lint
  relations:
    related_to:
      - /decisions/adr-003-strict-okf-production-rules.md
      - /domains/tooling.md
---

# Symptom

Running `pd-lint-okf.py --strict` after upgrading the schema registry to require specific sections for each type produced errors on ADR-001 and manual documents whose sections did not match the new required section lists.

# Impact

Blocked the strict lint pass during the hardening session until the section structures were normalized. Did not affect normal/warn lint modes.

# Root Cause

The schema registry in `paradigma-types.schema.yaml` was expanded with `required_sections` for each type (e.g., `paradigma-decision` requires Context, Decision, Consequences, Alternatives Considered, Status, Related Documents). ADR-001 and the manuals predated this expansion and used slightly different heading structures.

# Workaround

Normalize section headings in each concept document to match the required sections declared in the schema registry for its type.

# Permanent Fix

Section structures were normalized in the hardening session. For future schema expansions, run `pd-lint-okf.py --strict` before declaring the hardening complete, and use the lint output to identify all affected documents before making targeted fixes.

# Related Documents

- `memory-bank/knowledge/decisions/adr-001-template-runtime-split.md`
- `/memory-bank/knowledge/manuals/paradigma-deploy.md`
- `/memory-bank/knowledge/manuals/paradigma-baseline-test.md`
- `.paradigma/schemas/paradigma-types.schema.yaml`
- `memory-bank/knowledge/decisions/adr-003-strict-okf-production-rules.md`

# Status

Resolved (0.4.0).
