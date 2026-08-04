# 2026-08-04 — Phase 6 style capsule

## Done

- `src/solivagus/style/capsule.py`: freeze/render/hash, seed select, provisional, next-capsule builder
- Wire into partition warm-up prefix + local cache key + unit `style_capsule_version`
- Partition-1: seed → provisional → rebuild prefix → re-warmup → concurrent rest
- Persist `style_capsules` rows and `artifact/style_capsules/vN.json`
- Tests: `tests/unit/test_solivagus_style_capsule_phase6.py`

## Next

- Phase 7: mechanical QA + specialized structure handlers
