# Progress — SQLite lock small-concurrency repro + FAILED落库

timestamp: 2026-09-17T11:01:33+08:00  
session: SESSION-20260917-SQLITE-LOCK  
task: TASK-20260804-P5

## Done

- Mapped write paths: OCR parent holds DB; workers are file-only; `_record_batch` was uncommitted across `worker()` waits.
- Small concurrent repro in `tests/unit/test_sqlite_batch_lock.py`:
  - uncommitted INSERT blocks peer UPDATE (`database is locked`)
  - commit-before-wait allows peer FAILED update
  - `_persist_document_failed` retries under short lock
  - batch translate boom leaves `failed`, not `translation_running`
- Code: OCR immediate commit + pre-worker commit; supervisor retry FAILED落库; translate outer catch marks failed; busy_timeout 30s auxiliary.

## Gates

`python -m unittest tests.unit.test_sqlite_batch_lock tests.unit.test_solivagus_batch_phase8` → OK (10).

## Not done

- Same 4-book fixed-config recovery + zero-provider re-run
- Overnight SOAK
- Metering / HTML-table QA policy unchanged
