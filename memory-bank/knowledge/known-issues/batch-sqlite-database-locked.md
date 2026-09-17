---
type: paradigma-known-issue
title: Batch soak hits SQLite database is locked under concurrent document work
description: Multi-document batch on one workspace state.db observed database is locked mid-translate/OCR, leaving inaccurate run state (e.g. translation_running + pending units).
tags: [known-issue, soak, sqlite, batch, concurrency, solivagus]
timestamp: 2026-09-17T11:01:33+08:00
paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: evolving
  update_policy: agent-editable
  epistemic_status: confirmed
  retrieval_hints:
    zh:
      - database is locked
      - 批处理
      - 浸泡
      - SQLite
    en:
      - database is locked
      - batch soak
      - SQLite lock
  symbols:
    - run_batch
    - state.db
    - supervisor.lock
    - run_ocr_stage
    - run_translate_stage
    - _record_batch
    - _persist_document_failed
  relations:
    related_to:
      - /known-issues/production-gate-concurrency-ci.md
      - /manuals/solivagus-phase8-batch.md
      - /decisions/adr-002-brief-gap-remediation.md
    informed_by:
      - /architecture.md
---

# Symptom

`solivagus batch`（conservative，4 本大书，共享 `soak-workspace/prerun/.solivagus/state.db`）出现：

- 首轮：`translate: database is locked`（3/4 文档）
- 再跑：`ocr: database is locked`（含已 OCR 完成的 PsychofIntel）
- 文档停在 `translation_running`（未落成明确 `failed`），大量 unit `pending`

证据：`batch-manifest-20260917-030114.json` / `…-032649.json`；进度记录 `logs/progress/2026-09-16-soak-prerun-4books.md`。

小并发复现（2026-09-17）：未提交的 `ocr_batches` INSERT 跨等待窗口会阻塞对端 `UPDATE documents`（`tests/unit/test_sqlite_batch_lock.py`）。OCR worker 本身不写库。

# Impact

无人值守 batch 不能保证文档进入明确终态；「失败 → 原命令重跑」与完成态零请求重跑尚未在固定配置下验证；正式 SOAK 阻断。

# Root Cause

确认放大器（非唯一可能的锁源）：OCR 父进程 `_record_batch` 未立即 commit，并在 `worker()` 长等待期间持有写事务，与 translate 线程写同一 `state.db` 交叉，触发 `database is locked`。失败路径上 `except: pass` 吞掉 status 更新，留下孤儿 `translation_running`。

busy_timeout 过短是辅助因素，不是根因。

# Workaround

- 单文档续跑：`solivagus run <pdf> --stage translate` 再 `--stage qa`（勿 `--force-ocr`）——证明进度可复用，**不等于**原 batch 自动恢复已验证。
- 暂时不要扩大文档规模；不要迁移文档级 DB，除非调查结论要求。

# Permanent Fix

已落地（代码侧 mitigation，待同配置四本回归）：

1. `ocr/runner.py`：`_record_batch` 立即 `commit`；调用 `worker()` 前再 `commit`。
2. `batch/supervisor.py`：`_persist_document_failed` 短退避重试；OCR/translate 失败记录落库错误而非静默吞掉。
3. `pipeline/translate.py`：`TRANSLATION_RUNNING` 之后非 FatalProvider 异常也尽量落 `failed`。
4. `database.py`：`busy_timeout=30000` + `connect(timeout=30.0)`（辅助，不得单独关单）。

验证：`python -m unittest tests.unit.test_sqlite_batch_lock`（4/4 OK）。

仍需：同四本固定配置中断恢复 + 完成态零请求重跑；正式 ≥12h SOAK。

# Related Documents

- `/known-issues/production-gate-concurrency-ci.md`
- `/manuals/solivagus-phase8-batch.md`
- `/decisions/adr-002-brief-gap-remediation.md`
- `logs/progress/2026-09-17-sqlite-lock-repro.md`

# Status

mitigated-in-code — 小并发复现与短事务/失败落库已落地；待同配置四本回归后再考虑关 issue / 进 SOAK。
