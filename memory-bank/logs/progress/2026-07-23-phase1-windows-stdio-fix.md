---
type: paradigma-session-log
title: Phase 1 Windows UTF-8 Stdio Fix
description: CI follow-up for deterministic Unicode output from unified and legacy CLI adapters.
tags: [session, phase-1, windows, ci, encoding]
timestamp: 2026-07-23T23:35:41+08:00
paradigma:
  layer: log
  lifecycle: append-only
  okf_export: optional
  update_policy: append-only
---

# Session Summary

## Failure

Windows CI redirected Python stdout through `cp1252`; legacy progress compaction
then failed while printing Chinese titles and bullets with `UnicodeEncodeError`.

## Fix

- Added one CLI stdio adapter that reconfigures stdout and stderr as UTF-8.
- Called it from unified `pd` startup and the shared legacy source-tree bootstrap.
- Added subprocess regression tests that force `PYTHONIOENCODING=cp1252` and emit
  deterministic Chinese content through both legacy and unified entrypoints.

## Validation

- Targeted Windows encoding regressions: 3/3 passed locally.
- Full suite: 72/72 passed; unified and legacy aggregate gates both passed 6/6.
