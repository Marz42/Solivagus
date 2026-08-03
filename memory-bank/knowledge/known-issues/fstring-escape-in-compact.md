---
type: paradigma-known-issue
title: f-string backslash escape in pd-compact-progress.py
description: pd-compact-progress.py initially used a backslash inside an f-string expression, causing a syntax error.
tags: [known-issue, tooling, python]
timestamp: 2026-07-05T11:45:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: cold
  lifecycle: evolving
  update_policy: agent-editable
  epistemic_status: confirmed
  retrieval_hints:
    zh:
      - f-string
      - 转义
      - 语法错误
      - 反斜杠
    en:
      - f-string
      - escape
      - syntax error
      - backslash
  relations:
    related_to:
      - /domains/tooling.md
---

# Symptom

`pd-compact-progress.py` raised a Python `SyntaxError` when the f-string contained a backslash before the closing brace.

# Impact

The compact progress tool could not run in write mode until the escaping was fixed. The dry-run output path was unaffected because the bug was in the `--write` code path where a backslash-escaped pipe character appeared inside the f-string expression.

# Root Cause

Python f-strings do not allow bare backslashes inside `{...}` expressions. The code attempted `signal.replace("|", "\\|")` directly inside the f-string.

# Workaround

Precompute the escaped value before the f-string:

```python
escaped_signal = signal.replace("|", "\\|")
lines.append(f"| [{rel}]({rel}) | {title} | {escaped_signal} |")
```

# Permanent Fix

Applied in the hardening session (2026-07-04). The precomputed variable pattern should be used for any f-string expression that requires backslash escaping.

# Related Documents

- `.paradigma/tools/pd-compact-progress.py`
- `memory-bank/logs/progress/2026-07-04-okf-hardening.md`

# Status

Resolved (0.4.0).
