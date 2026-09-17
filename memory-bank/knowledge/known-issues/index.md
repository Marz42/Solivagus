# Known Issues Index

No known issues recorded yet.

<!-- BEGIN PARADIGMA AUTO-INDEX -->
<!-- checksum: b3c047c9e655c99a -->
<!-- generated_by: pd-index.py -->

| Path | Type | Title | Hints | Symbols | Relations |
|------|------|-------|-------|---------|-----------|
| [batch-sqlite-database-locked.md](batch-sqlite-database-locked.md) | `paradigma-known-issue` | Batch soak hits SQLite database is locked under concurrent document work | database is locked<br>批处理<br>浸泡 ... | run_batch<br>state.db<br>supervisor.lock ... | related_to:/known-issues/production-gate-concurrency-ci.md<br>related_to:/manuals/solivagus-phase8-batch.md<br>related_to:/decisions/adr-002-brief-gap-remediation.md<br>informed_by:/architecture.md |
| [paddlepaddle-gpu-not-on-pypi.md](paddlepaddle-gpu-not-on-pypi.md) | `paradigma-known-issue` | paddlepaddle-gpu 3.3.0 is not installable from public PyPI | paddlepaddle-gpu<br>PyPI<br>安装失败 ... | paddlepaddle-gpu==3.3.0<br>requirements-gpu.txt | related_to:/architecture.md<br>related_to:/manuals/solivagus-phase2-ocr-gpu.md<br>informed_by:/conventions.md |
| [production-gate-concurrency-ci.md](production-gate-concurrency-ci.md) | `paradigma-known-issue` | Production soak blocked until concurrency and CI gates are green | 生产浸泡<br>事件循环<br>校准竞态 ... | ConcurrencyGate<br>ThreadSafeGate<br>run_translate_stage ... | related_to:/decisions/adr-002-brief-gap-remediation.md<br>related_to:/architecture.md<br>related_to:/domains/document-pipeline.md<br>informed_by:/conventions.md |

<!-- END PARADIGMA AUTO-INDEX -->
