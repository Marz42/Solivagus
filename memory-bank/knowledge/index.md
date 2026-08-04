# Solivagus Knowledge Index

Agent 路由指南：先恢复 Task/Session 与 Context Manifest，再按任务选择最相关的 1-3 个文档继续阅读。

## HOT Knowledge

* [Project Brief](project-brief.md) - Vision, users, scope, non-goals, success criteria.
* [System Architecture](architecture.md) - Dual pipeline, stack, module boundaries.
* [Conventions](conventions.md) - Naming, testing, safety, prohibited patterns.
* [Repository Contract](contracts/repository-contract.md) - Repo layout and ownership.

## WARM Knowledge

* [Contracts](contracts/) - CLI, workspace/artifact, repository contracts.
* [Domains](domains/) - Document processing pipeline.
* [Manuals](manuals/) - MVP baseline, Phase 2 GPU OCR, Phase 4 provider/cache.
* [Plans](plans/) - Solivagus v1 phased roadmap (Phase 0–6 done; next Phase 7).
* [Known Issues](known-issues/) - e.g. paddlepaddle-gpu not on public PyPI.

## Source materials (not OKF knowledge)

* `project-brief/project-brief.md` — full design draft
* `project-brief/pdf_translate_cli_v0_2.py` — MVP single-script baseline
* `project-brief/PDF翻译使用速查.md` — MVP usage cheat sheet
* `project-brief/nightauto.ps1` — unattended batch driver
* `requirements-gpu.txt` — pinned GPU/OCR stack that already runs
* `example/` — local-only fixtures (gitignored; includes Qwen3_TTS baseline)
