# 2026-08-04 — Brief gap remediation (ADR-002)

## Adopted priority

| Gap | Priority | Status |
|-----|----------|--------|
| footnote/aside default (split flags) | P0 | done |
| YAML / `--config` | P0 | done |
| real Tokenizer | P0/P1 | done (optional dep + env paths; approx fallback) |
| Unit bisect | P0/P1 | done (one-level bisect before fallback) |
| `manifest.json` stable | P1 | done |
| output-ratio calibration | P1 | done (rolling P90 after 5 samples) |
| `inspect-data` minimal | P1/P2 | done (`solivagus inspect-data`) |
| adaptive concurrency (cap + Retry-After) | P2 | done (max cap, 429/503, Retry-After sleep; p95 deferred) |
| `references_mode` expand | deferred | keep-only commitment |

## Next

- Optional: p95 latency gate for concurrency bump
- Production soak on real batch directory
