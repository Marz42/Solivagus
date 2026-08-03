---
type: paradigma-manual
title: Paradigma Baseline Validation
description: Baseline validation sequence for Paradigma knowledge quality, deterministic tooling, and release readiness.
tags: [manual, testing, quality, paradigma]
timestamp: 2026-07-24T00:25:40+08:00
paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: evolving
  update_policy: agent-editable
  epistemic_status: confirmed
  retrieval_hints:
    zh:
      - Paradigma 基线校验
      - 校验命令
      - 质量门禁
    en:
      - paradigma baseline
      - validation commands
      - quality gate
  relations:
    related_to:
      - /conventions.md
      - /contracts/repository-contract.md
---

# Purpose

This guide defines the local validation sequence for Paradigma changes. It is **not** a general-purpose testing guide for derived projects — it documents the baseline quality gates that the Paradigma repository itself must pass. Derived projects should write their own testing guide under `manuals/`.

# Preconditions

- Run commands from the repository root.
- Use Python 3.11+; install `requirements.txt`, then install the local package with `python -m pip install --no-deps .`.
- Set `PYTHONDONTWRITEBYTECODE=1` when running validation if you want to avoid local `__pycache__` files.

# Steps

1. Run the standard-library unittest suite before and after tool refactors.
2. Run version consistency checks after release, config, OKF, or document schema changes.
3. Run strict OKF lint after concept or schema edits.
4. Run link checks after Markdown links, relations, or index entries change.
5. Run `pd-index.py rebuild` after concept metadata changes, then run `pd-index.py verify`.
6. Run hot-size checks before ending substantial sessions.
7. Compile Python tools when their implementation changes.
8. Run archive tests after changing task state, templates, mutation planning, atomic writes, or retry behavior.
9. Build a wheel and import it from an isolated target after package metadata or `src/paradigma/` changes.
10. Rebuild and verify the SQLite catalog after canonical memory, catalog schema, config path, or retrieval projection changes.

# Characterization Matrix

| Surface | Preserved baseline |
|---------|--------------------|
| lint | Repository success; YAML diagnostics; strict timestamp, required-field, required-section, and generated-checksum failures |
| link check | Repository success; visible missing targets fail; planned relations warn; code-region links are ignored |
| index | Root/local/cache boundary; deterministic rebuild; corruption detection; atomic replace failure; legacy wrapper compatibility |
| hot-size | Repository success; exact task state validation; warning/error thresholds; `--fail-on-warn` exit behavior |
| archive | Default dry-run; strict status; source conflict; atomic create/replace; interruption recovery; idempotent retry |
| compact | Dry-run does not write; source logs are preserved; invalid YAML and atomic replace failure preserve the old summary |
| diagnose | Self-diagnosis success; legacy version migration; unknown workspace JSON and exit code 2 |
| version | Five version dimensions; legacy-field rejection; distribution drift; invalid SemVer |
| check-all | Repository success; default first-failure stop; `--keep-going` failure aggregation |
| memory catalog | Dry-run; atomic full rebuild; source/row/tag/relation/FTS drift; stats; corruption and replace-failure recovery |
| memory query | ID/path/keyword/FTS/tag/scope/status/validity composition; active-only default; stable order/reasons; filtered one-hop expansion; stale/corrupt refusal |
| memory mutation | Strict payloads; default dry-run; source-hash CAS; transition graph; revision/time invariants; full lifecycle query visibility; recoverable catalog-refresh failure |
| memory explain | Rich required fields; structured CLI filters; non-active/validity warnings; canonical-first stale/corrupt behavior; golden Phase 2 lifecycle |

The suite also relocates the harness into a temporary derived workspace, rebuilds its cache, and runs the aggregate quality gate there. Mutation and failure-injection tests never write into the working repository.

# Verification

Recommended command sequence:

```powershell
python -m pip install -r requirements.txt
python -m pip install --no-deps .
pd index rebuild
pd catalog rebuild
python -m unittest discover -s tests -p "test_*.py" -v
pd check --dry-run
pd catalog verify
```

Individual tools can also be run separately:

```powershell
python -m unittest tests.characterization.test_tools -v
python -m unittest tests.characterization.test_failure_baselines -v
pd version --format json
pd index verify --format json
pd catalog stats --format json
pd diagnose --project . --upstream . --format json
python .paradigma/tools/pd-check-all.py --keep-going  # compatibility only
```

# Rollback

Validation tools should not delete source content. If a local or machine index is wrong, fix canonical frontmatter/relations and rerun `pd-index.py rebuild`; deleting `.paradigma/cache/` is always safe.

# Troubleshooting

| Symptom | Likely Cause | Action |
|---------|--------------|--------|
| Version check fails | Distribution, installed, config, OKF, or document schema metadata drifted | Run `pd-version.py --verbose --check` and update only the field whose semantic version changed |
| `unknown type` | Schema registry missing the concept type | Add the type to `.paradigma/schemas/paradigma-types.schema.yaml` |
| Timestamp error | Non-ISO frontmatter timestamp | Use `YYYY-MM-DDTHH:mm:ss+08:00` |
| `YAML_SYNTAX_ERROR` / `YAML_DUPLICATE_KEY` | Invalid YAML or an ambiguous repeated key | Fix the reported source line; do not suppress the parser diagnostic |
| `ENCODING_ERROR` | File is not valid UTF-8 | Re-save as UTF-8 (UTF-8 BOM is accepted) |
| `PD_ARCHIVE_INVALID_STATUS` | `Current Status` is prose, punctuated, empty, or unknown | Use exactly one of `pending`, `active`, `blocked`, `completed`, `aborted` |
| `PD_ARCHIVE_SOURCE_CHANGED` | active-task changed after dry-run plan generation | Generate and review a fresh plan; do not force the stale plan |
| Archive exists but active-task was not reset | Process stopped between the two atomic writes | Re-run `pd-archive-task.py --write`; it reuses the same `archive_id` |
| Machine cache missing or stale | Cache was deleted/corrupted or source metadata changed | Run `pd-index.py rebuild`, then `pd-index.py verify` |
| Catalog missing, corrupt, or stale | Derived SQLite was deleted/damaged or canonical Markdown changed | Run `pd catalog rebuild`, then `pd catalog verify`; never repair canonical Markdown from SQLite |
| `PD_CATALOG_QUERY_ERROR` | Query used stale catalog or invalid FTS syntax | Rebuild/verify the catalog, or use valid FTS5 syntax / literal keyword mode |
| `PD_MEMORY_CONFLICT` / `PD_MEMORY_MUTATION_ERROR` | Caller hash is stale or lifecycle state disallows the operation | Run `pd memory validate`, review the current record/status, then build a fresh mutation |
| `PD_MEMORY_CATALOG_REFRESH` | Canonical mutation succeeded but derived catalog rebuild failed | Do not repeat the mutation with the old hash; run validate, then `pd catalog rebuild` |
| Root index starts growing with every concept | Recursive generated block was reintroduced | Remove it with rebuild and keep only high-level human navigation |
| `PD_COMPACT_IO_ERROR` | Summary temp write, flush, or atomic replace failed | Fix the filesystem issue and retry; the prior summary and all source logs remain unchanged |
| Link check reports a planned relation | The target is intentionally future work | Keep it under `paradigma.relations.planned` |

# Citations

- `.paradigma/tools/pd-version.py`
- `.paradigma/tools/pd-lint-okf.py`
- `.paradigma/tools/pd-check-links.py`
- `.paradigma/tools/pd-index.py`
- `.paradigma/tools/pd-sync-index.py` (compatibility wrapper)
- `tests/characterization/test_tools.py`
- `tests/characterization/test_failure_baselines.py`
