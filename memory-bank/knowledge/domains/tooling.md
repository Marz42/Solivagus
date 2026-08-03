---
type: paradigma-domain
title: Tooling Domain
description: Deterministic tooling layer for OKF lint, link checking, index sync, and runtime maintenance.
tags: [domain, tooling]
timestamp: 2026-07-23T22:31:40+08:00
paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: evolving
  update_policy: agent-editable
  epistemic_status: confirmed
  retrieval_hints:
    zh:
      - 工具
      - lint
      - link check
      - index sync
      - 归档
    en:
      - tooling
      - lint
      - link check
      - index sync
      - archive
  symbols:
    - pd-lint-okf.py
    - pd-check-links.py
    - pd-index.py
    - pd-check-hot-size.py
    - pd-check-all.py
    - pd-version.py
    - pd-archive-task.py
    - pd-compact-progress.py
  relations:
    depends_on:
      - /architecture.md
    constrains:
      - /contracts/repository-contract.md
    related_to:
      - /manuals/paradigma-baseline-test.md
---

# Responsibility

The tooling domain covers the L4 Deterministic Tooling Layer of Paradigma. Reusable core and application services live under `src/paradigma/`; `.paradigma/tools/` is a deprecated v0.5.x compatibility surface with no independent business logic.

# Public Interfaces

安装 package 后，首选统一入口：

| Command | Purpose |
|---------|---------|
| `pd version` | Report separated version dimensions |
| `pd config validate` | Validate repository configuration and path boundaries |
| `pd check` | Run all six deterministic quality gates and return one result |
| `pd diagnose --upstream <path>` | Compare a project harness with an upstream repository |
| `pd index rebuild/verify` | Rebuild or verify derived indexes |
| `pd task archive` | Preview an archive plan by default; mutate only with `--write` |

每个叶子命令支持 `--format text|json`、`--dry-run` 和
`--project <path>`。Application Service 返回 `CommandOutcome`，仅 CLI adapter
负责格式化和进程退出码。

| Tool | Command | Purpose |
|------|---------|---------|
| `pd-check-all.py` | `python .paradigma/tools/pd-check-all.py` | Aggregates version, lint, link, index, hot-size, and DESIGN.md validation into a single quality gate |
| `pd-version.py` | `python .paradigma/tools/pd-version.py --verbose` | Reports and validates the separated Paradigma version dimensions |
| `pd-lint-okf.py` | `python .paradigma/tools/pd-lint-okf.py --strict` | Validates concept documents against schema, sections, timestamps, policies, and generated blocks |
| `pd-check-links.py` | `python .paradigma/tools/pd-check-links.py` | Checks Markdown links, frontmatter relations, and generated index entries |
| `pd-index.py` | `python .paradigma/tools/pd-index.py rebuild` | Rebuilds non-recursive local Markdown indexes and the complete ignored machine cache |
| `pd-sync-index.py` | `python .paradigma/tools/pd-sync-index.py --write` | Deprecated v0.5.x compatibility wrapper for index rebuild/verify |
| `pd-check-hot-size.py` | `python .paradigma/tools/pd-check-hot-size.py` | Reports active-task, HOT knowledge, and progress index size status |
| `pd-archive-task.py` | `python .paradigma/tools/pd-archive-task.py --dry-run` | Plans or atomically applies a strict, idempotent active-task archive transaction |
| `pd-compact-progress.py` | `python .paradigma/tools/pd-compact-progress.py --write` | Atomically replaces a compact progress summary without deleting source logs |
| `pd-diagnose.py` | `python .paradigma/tools/pd-diagnose.py --upstream <path>` | Compares project harness against upstream; reports gaps in structure/tools/schema/config/protocol |

# Internal Flow

Package modules expose structured config, parsing, Schema validation, atomic write, validation, diagnosis, index, progress and task-archive services without CLI side effects. The `pd` adapter performs argument parsing, text/JSON rendering and exit-code mapping. Legacy tools and private helpers import these package services and contain only bootstrap, argument and presentation adapters. Configuration comes from `.paradigma/config.yaml`, type rules come from `.paradigma/schemas/paradigma-types.schema.yaml`, and dry-run (no `--write`) remains the default for mutation tools.

Current behavior is preserved by `tests/characterization/`, while `tests/integration/test_cli_equivalence.py` compares old and new entrypoints. A relocated Unicode/space-containing workspace is exercised on Windows locally and on both Windows/POSIX CI runners.

# Dependencies

- Python 3.11+.
- PyYAML 6.x, declared in both `pyproject.toml` and legacy bootstrap `requirements.txt`.
- `.paradigma/config.yaml` for knowledge roots, reserved filenames, and generated block markers.
- `.paradigma/cache/knowledge-index.json` as a disposable, ignored machine inventory generated from canonical Markdown.
- `.paradigma/schemas/paradigma-types.schema.yaml` for type registry, required sections, and field validation.
- `memory-bank-template/` for active-task reset template.
- Python standard-library `unittest` for the characterization suite.

# Related Contracts

- `memory-bank/knowledge/contracts/repository-contract.md` — defines tool command contracts and exit codes.

# Known Risks

- Legacy scripts require either an installed `paradigma` distribution or the matching `src/paradigma/` source tree; copying one script by itself is unsupported.
- Adding a new tool requires manually updating this document, the repository contract, and the testing guide.
- Cross-file archive/reset is recoverable rather than globally atomic: after archive creation but before reset, the archive remains and the next invocation completes the reset using the same `archive_id`.
