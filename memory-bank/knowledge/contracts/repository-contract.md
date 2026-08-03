---
type: paradigma-contract
title: Repository Contract
description: Current repository-level contract boundaries for APIs, databases, tools, and versioning.
tags: [contract, repository, tooling]
timestamp: 2026-07-24T02:44:33+08:00
paradigma:
  schema_version: "0.1"
  temperature: hot
  lifecycle: evolving
  update_policy: requires-human-confirmation
  epistemic_status: confirmed
  contract_kind: repository
  retrieval_hints:
    zh:
      - 仓库契约
      - 工具命令
      - 兼容策略
    en:
      - repository contract
      - tool commands
      - compatibility policy
  symbols:
    - pd-version.py
    - pd-lint-okf.py
    - pd-index.py
    - VERSION
  relations:
    depends_on:
      - /architecture.md
---

# Scope

This contract defines the externally meaningful repository boundaries for Project Paradigma. Phase 1 introduced an installable application core while preserving the documentation/template and legacy script surfaces; Phase 2 adds a storage-neutral Memory Kernel behind those outer interfaces.

# Contract

## Repository Layout

| Area | Contract |
|------|----------|
| `memory-bank/runtime/` | Ephemeral Agent state; not exported as OKF knowledge |
| `memory-bank/logs/` | Operational logs and changelog; append-first history |
| `memory-bank/knowledge/` | OKF-compatible long-lived knowledge bundle |
| `docs/rfc/` | OKF-compatible proposal/RFC documents |
| `memory-bank-template/` | Blank templates for derived projects |
| `.paradigma/tools/` | Deprecated v0.5.x command adapters backed by the installed/source-tree package |
| `pyproject.toml` + `src/paradigma/` | Installable Python distribution and value-returning application core |
| `src/paradigma/parser.py` | Sole YAML/frontmatter parser implementation |
| `src/paradigma/task_state.py` | Sole active-task status enum/parser implementation |
| `src/paradigma/kernel/` | Immutable Memory domain values and stable IDs; no Markdown, SQLite, Coding, Research, CLI, or adapter rules |
| `src/paradigma/storage/markdown/` | Canonical one-record Markdown codec/store; strict Schema, dual hashes, revision checks and atomic publication |
| `memory-bank/memories/` | Default canonical Memory Markdown root; outside the legacy OKF concept index |
| `src/paradigma/storage/catalog/` | Complete rebuild/verify/stats for the ignored SQLite + FTS5 memory projection |
| `.paradigma/cache/` | Ignored, disposable machine index artifacts; never canonical knowledge |
| `tests/characterization/` | Executable baseline for current tool CLI and mutation behavior |
| `tests/unit/`, `tests/integration/`, `tests/architecture/` | Package behavior, legacy equivalence, and dependency-boundary enforcement |

## Tool Commands

| Command | Status | Contract |
|---------|--------|----------|
| `python -m unittest discover -s tests -p "test_*.py" -v` | Stable | Runs the pre-refactor characterization suite using Python standard-library unittest |
| `python -m pip install --no-deps .` | Stable | Installs the `paradigma` distribution using root `VERSION` as package version |
| `pd version/config/check/diagnose/index/task` | Stable | Phase 1 unified CLI surface; every leaf supports text/JSON, dry-run, and explicit project root |
| `pd catalog rebuild/verify/stats` | Experimental | Phase 2 derived SQLite/FTS5 catalog surface backed only by canonical Memory Markdown |
| `pd memory propose/validate/commit/revise/supersede/forget` | Experimental | Phase 2 canonical mutation lifecycle; mutating leaves default to preview and require explicit `--write` plus source-hash CAS for updates |
| `pd memory query/explain` | Experimental | Phase 2 public retrieval adapter; query requires current catalog and explain remains canonical-first under catalog failure |
| `pd task start/status/block/unblock/suspend/resume/complete/abort` | Experimental | Phase 3 YAML CodingTask lifecycle; mutations default to dry-run and illegal transitions fail before writes |
| `pd session start/status/checkpoint/end` + `pd handoff build` | Experimental | Phase 3 recoverable Session/append-only Checkpoint lifecycle and active/last-session handoff projection |
| `pd context build/verify` | Experimental | Phase 3 deterministic Coding context manifest; build is non-writing unless `--write`, verify detects request/source/checksum drift |
| `pd runtime init/rebuild/verify` | Experimental | Initializes only missing null runtime pointers, or rebuilds/verifies Markdown projections; init defaults to dry-run and never overwrites existing facts |
| `python .paradigma/tools/pd-version.py --verbose` | Deprecated compatibility | Reports distribution, installed distribution, config schema, OKF, and document schema versions |
| `python .paradigma/tools/pd-version.py --check` | Stable | Fails when required version fields are missing, legacy fields remain, or the installed distribution drifts from root `VERSION` |
| `python .paradigma/tools/pd-check-all.py` | Deprecated compatibility | Aggregates version, lint, link, index, hot-size, and DESIGN.md validation into a single quality gate |
| `python .paradigma/tools/pd-lint-okf.py --strict` | Stable | Checks concept documents against schema, sections, timestamps, policies, and generated blocks |
| `python .paradigma/tools/pd-check-links.py` | Stable | Checks Markdown links, frontmatter relations, and generated index entries |
| `python .paradigma/tools/pd-index.py rebuild` | Stable | Strips legacy root generated blocks, rebuilds non-recursive local indexes, and writes the complete machine cache |
| `python .paradigma/tools/pd-index.py verify` | Stable | Fails when root navigation, local indexes, or machine cache drift from canonical Markdown |
| `python .paradigma/tools/pd-sync-index.py --write/--check` | Deprecated compatibility | Maps legacy write/check behavior to rebuild/verify during the v0.5.x compatibility window |
| `python .paradigma/tools/pd-check-hot-size.py` | Stable | Reports active-task, HOT knowledge, and progress index size status |
| `python .paradigma/tools/pd-archive-task.py --dry-run` | Stable | Validates exact task state and prints the immutable archive mutation plan without writes |
| `python .paradigma/tools/pd-archive-task.py --write` | Stable | Atomically creates the content-addressed archive, then atomically resets active task to `pending`; retries recover without duplication |
| `python .paradigma/tools/pd-compact-progress.py --write` | Stable | Atomically replaces the compact progress summary without deleting or rewriting source logs |
| `python .paradigma/tools/pd-diagnose.py --upstream <path>` | Experimental | Compares project harness against upstream Paradigma; reports gaps across structure, tools, schema, config, and protocol |

# Request Schema

The installed package publishes one `pd` command with the following stable Phase 1
command tree: `version`, `config validate`, `check`, `diagnose`, `index
rebuild/verify`, `runtime init/rebuild/verify`, `catalog rebuild/verify/stats`, `memory
propose/validate/commit/revise/supersede/forget/query/explain`, `task
start/status/block/unblock/suspend/resume/complete/abort/archive`, `session
start/status/checkpoint/end`, `handoff build`, and `context build/verify`. Every leaf accepts `--format
text|json`, `--dry-run`, and `--project <path>`. Mutation commands remain
non-mutating unless their explicit write option is present; `pd task archive`
therefore requires `--write` to apply its plan.

Package core methods return values, `OperationResult`, or structured exceptions/diagnostics. They do not parse CLI arguments, invoke subprocesses, or print output directly.

The Phase 2 Memory Kernel accepts `MemoryRecord`, `MemoryScope`, `ProvenanceRef`, `MemoryRelation`, and `MemoryQuery` values and returns explainable `MemoryResult` values. Canonical memory IDs match `MEM-[0-7][0-9A-HJKMNP-TV-Z]{25}`. Query status defaults to exactly `active`; relation expansion is opt-in. All datetimes are timezone-aware and every record carries at least one provenance reference. Markdown paths and catalog columns are not part of this domain contract; `CatalogQuery` adds path and keyword/FTS mode only at the storage boundary.

Canonical memory documents use the separate `memory_schema_version: "0.1"` contract defined in `memory-document-contract.md`. `content_hash` protects the decoded record; `source_hash` binds exact bytes for compare-and-swap update. Create requires revision 1, update requires exactly the stored revision plus one, and neither operation silently overwrites an existing or externally changed document.

Config schema 0.4 adds `memory_root` and `catalog_path`; old configurations use `memory-bank/memories` and `.paradigma/cache/catalog.sqlite3`. Catalog rebuild validates all canonical documents before atomic publication. Verify compares source, primary rows, normalized tags/relations and FTS; stats never modifies either store.

`query_memories` is the Batch 2.4 object-returning Application API. It refuses missing, damaged, or stale catalogs; composes direct selectors deterministically; supports keyword/FTS, tag, scope, status and inclusive validity filters; and performs only explicit outgoing one-hop relation expansion. The `pd memory query/explain` adapter remains reserved for Batch 2.6.

Batch 2.5 adds object-returning propose/validate/commit/revise/supersede/forget services and matching `pd memory` leaves. Candidate is canonical revision 1 but excluded by default queries; updates bind the source hash returned by validate, increment revision exactly once, and rebuild the derived catalog. Forget is a tombstone, not physical deletion.

Batch 2.6 exposes `pd memory query/explain`. Query results include reasons, matched fields, scope, validity, status, provenance, confidence, relation source and warnings. Query refuses stale catalog; explain reads canonical first and reports catalog issues without hiding a valid record.

Phase 3 adds versioned Coding Task/Session/Checkpoint runtime and `pd context build/verify`. Context build consumes a structured request, current catalog/canonical Memory, configured knowledge roots and task/session facts; it returns a checksummed Manifest with stable selection/exclusion reasons and only writes the derived runtime projection under `--write`.

JSON responses expose `command`, `ok`, `changed`, `dry_run`, `data`, `messages`,
and `diagnostics`. Diagnostics provide stable codes and severities. Text rendering
is an adapter concern and does not change the underlying outcome. Unified and
legacy CLI adapters configure stdout/stderr as UTF-8 so redirected Windows output
has the same encoding contract as POSIX output.

# Response Schema

Tooling uses process exit codes:

| Exit code | Meaning |
|-----------|---------|
| `0` | Success |
| `1` | Validation failed |
| `2` | Input/path/parser/storage/evidence/catalog availability failure |
| `3` | State transition, source-hash, pointer, task/session, or identity conflict |

Parser failures include a stable code, source, message, and optional line/column. YAML syntax and encoding failures must not be reported as document Schema failures. Supported parser codes are `ENCODING_ERROR`, `FILE_READ_ERROR`, `FRONTMATTER_MISSING`, `FRONTMATTER_UNCLOSED`, `YAML_SYNTAX_ERROR`, `YAML_DUPLICATE_KEY`, and `YAML_ROOT_TYPE_ERROR`.

Generated single-file writes use a same-directory temporary file, flush, `fsync`, and atomic replace. A compact-summary write failure returns `PD_COMPACT_IO_ERROR`, preserves the prior summary and all source logs, and removes its temporary file.

Active-task status is an exact enum: `pending`, `active`, `blocked`, `completed`, `aborted`. Invalid runtime state fails HOT/runtime and aggregate checks with `PD_TASK_INVALID_STATUS`; archive failures expose stable `PD_ARCHIVE_*` diagnostics. The archive mutation plan binds the active-task SHA-256; archive creation precedes reset, and `archive_id` makes recovery and repeated invocation idempotent.

Index boundaries are normative: root `index.md` is bounded human navigation, subdirectory generated blocks are non-recursive local views, and `.paradigma/cache/knowledge-index.json` is the disposable complete machine inventory. Cache loss or corruption must not mutate canonical Markdown and must be recoverable with rebuild.

Catalog drift returns `PD_CATALOG_DRIFT`; catalog read/schema failure returns `PD_CATALOG_ERROR`; binary publication failure returns `PD_CATALOG_WRITE_ERROR` and preserves the prior database. `.paradigma/cache/catalog.sqlite3` is ignored and fully rebuildable from `memory_root`.

# State Transitions

```text
User request -> runtime active task -> knowledge routing -> edits -> lint -> logs/knowledge update
```

# Compatibility Notes

- Adding new optional frontmatter fields is backward compatible.
- Tooling requires Python 3.11+ and dependencies declared in root `requirements.txt`.
- `.paradigma/config.yaml` schema 0.3 adds `machine_index_path`; older 0.2 configurations fall back to the default cache path during migration.
- Config schema 0.4 adds optional `memory_root` and `catalog_path`; 0.3 workspaces receive safe defaults until explicitly migrated.
- Adding new Paradigma concept types is backward compatible if existing types remain valid.
- Adding optional Memory query/result fields may be backward compatible; changing the memory ID grammar, default query status, revision origin, validity interval, or provenance requirement is compatibility-impacting.
- Changing canonical Memory Markdown fields, hash payload, filename mapping or source-hash update semantics requires memory schema and migration evaluation.
- Moving core paths such as `memory-bank/knowledge/` or changing required tooling commands is a compatibility-impacting protocol change and requires version evaluation.

# Breaking Change Policy

Breaking repository protocol changes require explicit user confirmation and SemVer evaluation under `memory-bank/knowledge/conventions.md`.

# Citations

- [OKF v0.1 Draft](https://raw.githubusercontent.com/GoogleCloudPlatform/knowledge-catalog/main/okf/SPEC.md)
