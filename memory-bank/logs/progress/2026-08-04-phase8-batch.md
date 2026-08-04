# 2026-08-04 — Phase 8 batch production

## Done

- Memory-bank: batch_dir default `null` (no `D:\PDFS`); Phase 8 docs/manual/index
- `src/solivagus/batch/`: discover, profiles, dual-queue supervisor, manifest, usage rollup
- CLI: `solivagus batch` / `retry`; `report` writes global usage
- OCR `acquire_supervisor_lock=` for batch-held lock
- Profiles: conservative / balanced / throughput
- Manual + `scripts/night-batch.ps1` for Task Scheduler
- Tests: `tests/unit/test_solivagus_batch_phase8.py`

## Acceptance mapped

- Overnight unattended: prevent-sleep + continue-on-error + scheduler script
- Single-file failure isolated
- Morning report: nightly + batch-manifest + global-usage
