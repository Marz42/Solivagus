---
type: paradigma-session-log
title: Rename Manuals and Config-Driven Index Sync
description: Session summary for renaming manuals to avoid ambiguity and upgrading pd-sync-index to use config.yaml knowledge_roots.
tags: [session, rename, tooling, config]
timestamp: 2026-07-05T12:02:00+08:00
paradigma:
  layer: log
  lifecycle: append-only
  okf_export: optional
  update_policy: append-only
---

# Session Summary

## User Goal

1. Rename deploy.md → paradigma-deploy.md (cold) and testing-guide.md → paradigma-baseline-test.md (warm) to avoid ambiguity with derived-project deploy/test docs.
2. Upgrade pd-sync-index.py to read knowledge_roots from .paradigma/config.yaml and generate indexes for both memory-bank/knowledge and docs/rfc.
3. Commit and evaluate version bump.

## Actions Taken

- Renamed `manuals/deploy.md` → `manuals/paradigma-deploy.md` with updated title, description, hints, and clarified that this is Paradigma-specific (not a general deploy guide).
- Renamed `manuals/testing-guide.md` → `manuals/paradigma-baseline-test.md` with temperature raised from cold to warm, same Paradigma-specific clarification.
- Updated all references across conventions.md, domains/tooling.md, known-issues/stale-section-structure-in-adr001.md, decisions/adr-003-*.md, manuals/index.md, and docs/rfc/paradigma-okf-compatible-runtime.md.
- Rewrote pd-sync-index.py to:
  - Read `.paradigma/config.yaml` for `knowledge_roots` (same config source as pd-lint-okf.py).
  - Auto-detect subdirectory indexes per knowledge root instead of hardcoding.
  - Generate index for `docs/rfc` for the first time.
- Bumped VERSION from 0.4.0 to 0.4.1 (PATCH: manual rename + tool config-driven behavior change).

## Files Read

- `.paradigma/tools/pd-sync-index.py`
- `.paradigma/tools/pd-lint-okf.py`
- `.paradigma/config.yaml`
- `memory-bank/knowledge/manuals/deploy.md` (deleted)
- `memory-bank/knowledge/manuals/testing-guide.md` (deleted)
- `memory-bank/knowledge/conventions.md`
- `memory-bank/knowledge/domains/tooling.md`
- `memory-bank/knowledge/known-issues/stale-section-structure-in-adr001.md`
- `memory-bank/knowledge/decisions/adr-003-strict-okf-production-rules.md`
- `docs/rfc/paradigma-okf-compatible-runtime.md`

## Files Modified

- `.paradigma/tools/pd-sync-index.py`
- `VERSION`
- `memory-bank/logs/changelog.md`
- `memory-bank/knowledge/conventions.md`
- `memory-bank/knowledge/domains/tooling.md`
- `memory-bank/knowledge/known-issues/stale-section-structure-in-adr001.md`
- `memory-bank/knowledge/decisions/adr-003-strict-okf-production-rules.md`
- `docs/rfc/paradigma-okf-compatible-runtime.md`
- `memory-bank/knowledge/manuals/index.md`
- `memory-bank/knowledge/index.md` (auto-generated)
- `memory-bank/knowledge/contracts/index.md` (auto-generated)
- `memory-bank/knowledge/decisions/index.md` (auto-generated)
- `memory-bank/knowledge/domains/index.md` (auto-generated)
- `memory-bank/knowledge/known-issues/index.md` (auto-generated)
- `docs/rfc/index.md` (auto-generated block added)
- `memory-bank/runtime/active-task.md`

## Files Created

- `memory-bank/knowledge/manuals/paradigma-deploy.md`
- `memory-bank/knowledge/manuals/paradigma-baseline-test.md`

## Files Deleted

- `memory-bank/knowledge/manuals/deploy.md`
- `memory-bank/knowledge/manuals/testing-guide.md`

## Decisions Accepted

- Version 0.4.0 → 0.4.1: manual rename is backward-compatible (derived projects name their own manuals), and pd-sync-index config-driven behavior is a tool PATCH.
- `paradigma-baseline-test.md` temperature: warm (used in every Update Phase).

## Validation

- `pd-lint-okf.py --strict`: errors=0, warnings=0
- `pd-check-links.py`: errors=0, warnings=0
- `pd-sync-index.py --check`: stale=0 (now 7 indexes including docs/rfc)
- `pd-check-hot-size.py`: all OK
- `python -m py_compile pd-sync-index.py`: OK

## Follow-ups

- Explain remaining P2/P3 issues for user decision.
- Add CI wiring for the strict local command sequence.
