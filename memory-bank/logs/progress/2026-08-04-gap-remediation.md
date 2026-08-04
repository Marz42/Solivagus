# 2026-08-04 — Brief gap remediation (ADR-002)

## Adopted priority

| Gap | Priority | Status this session |
|-----|----------|---------------------|
| footnote/aside default (split flags) | P0 | done |
| YAML / `--config` | P0 | done |
| real Tokenizer | P0/P1 | done (optional dep + env paths; approx fallback) |
| Unit bisect | P0/P1 | done (one-level bisect before fallback) |
| manifest.json stable | P1 | done |
| output-ratio calibration | P1 | pending |
| inspect-data minimal | P1/P2 | pending |
| adaptive concurrency (cap + Retry-After) | P2 | pending |
| references_mode expand | deferred | keep-only commitment |

## Next

- P1: rolling output-ratio calibration
- P1/P2: `inspect-data`
- P2: concurrency hard-cap + Retry-After
