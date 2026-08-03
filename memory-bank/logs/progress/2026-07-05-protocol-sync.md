---
type: paradigma-session-log
title: Protocol Sync Regression Fix
description: Session summary for full regression review against AGENT_RULES and INIT_PROMPT, fixing drift in README, INIT_PROMPT, cursor rule, paradigma-deploy, and glossary template.
tags: [session, regression, protocol, sync]
timestamp: 2026-07-05T12:43:00+08:00
paradigma:
  layer: log
  lifecycle: append-only
  okf_export: optional
  update_policy: append-only
---

# Session Summary

## User Goal

Run a full regression review against AGENT_RULES.md and INIT_PROMPT.md specifications. Fix all drift and non-compliance issues found.

## Actions Taken

- **C1**: Fixed `README.md` version badge from `0.4.0` to `0.4.2`.
- **C2**: Fixed `memory-bank-template/knowledge/glossary.template.md` timestamp from real data (`2026-07-04T22:33:00+08:00`) to placeholder (`YYYY-MM-DDTHH:mm:ssZ`). This was a bug: derived projects activating the template would fail strict lint due to the stale real timestamp.
- **P1-P2**: Replaced 4 individual tool commands in `README.md` ("如何使用" section and "推荐检查顺序") with `pd-check-all.py` + `pd-sync-index.py --write`.
- **R1**: Added `pd-check-all.py` and `.github/workflows/check.yml` to `README.md` directory tree.
- **P3**: `INIT_PROMPT.md` mode F step 5: 4 individual commands → `pd-check-all.py` + `pd-sync-index.py --write`.
- **P4**: `INIT_PROMPT.md` mode A step 7: 4 individual commands → `pd-check-all.py` + `pd-sync-index.py --write`.
- **P5**: `INIT_PROMPT.md` mode C step 4: "lint, link check, index check and hot-size check" → `pd-check-all.py`.
- **P6**: `INIT_PROMPT.md` custom tips: "strict lint, link check, index sync/check, hot-size check" → `pd-check-all.py`.
- **P7**: `paradigma-deploy.md` Verification section: 4 bullet commands → single `pd-check-all.py` bash block.
- **D1**: Removed redundant standalone `pd-sync-index.py --check` line from cursor rule Update Phase (AGENT_RULES.md source of truth lists only `pd-check-all.py`).

## Files Read

- `AGENT_RULES.md`
- `INIT_PROMPT.md`
- `README.md`
- `.cursor/rules/memory-bank-protocol.mdc`
- `memory-bank/knowledge/manuals/paradigma-deploy.md`
- `memory-bank-template/knowledge/glossary.template.md`
- `VERSION`

## Files Modified

- `README.md`
- `INIT_PROMPT.md`
- `.cursor/rules/memory-bank-protocol.mdc`
- `memory-bank/knowledge/manuals/paradigma-deploy.md`
- `memory-bank-template/knowledge/glossary.template.md`
- `memory-bank/runtime/active-task.md`

## Decisions Accepted

- Version stays at 0.4.2: this is a pure documentation sync, no functional or protocol change.
- `INIT_PROMPT.md` modes F and A keep `pd-sync-index.py --write` as a separate step because template activation requires index generation, not just checking.

## Validation

- `pd-check-all.py`: All 4 checks passed (0 errors, 0 warnings).

## Follow-ups

- Template `glossary.template.md` was intentionally kept with minimal content (3 base terms), matching its role as a starting point for derived projects. Paradigma's own comprehensive glossary lives in `memory-bank/knowledge/glossary.md`.
