---
type: paradigma-manual
title: Paradigma Harness Update
description: Guide for checking and updating Paradigma Harness (tools, protocol, schema, templates) in derived projects.
tags: [manual, harness, update, migration, paradigma]
timestamp: 2026-07-26T15:38:51+08:00
paradigma:
  schema_version: "0.1"
  temperature: cold
  lifecycle: evolving
  update_policy: agent-editable
  epistemic_status: confirmed
  retrieval_hints:
    zh:
      - 套件更新
      - 结构迁移
      - 诊断
      - 模式 H
      - pd-diagnose
    en:
      - harness update
      - structure migration
      - diagnose
      - mode H
      - pd-diagnose
  symbols:
    - pd-diagnose.py
    - installed_distribution_version
    - INIT_PROMPT mode H
  relations:
    related_to:
      - /domains/design-system.md
      - /manuals/paradigma-design-wizard.md
      - /manuals/paradigma-baseline-test.md
---

# Purpose

This manual guides users through checking and updating the Paradigma Harness (tool chain, protocol files, schema, templates) in derived projects. The Harness is the set of infrastructure that makes Paradigma work — tools, rules, and knowledge structure — and it evolves across Paradigma releases.

There are two upgrade paths depending on the project's current state:

| Path | Current State | Paradigma Version | Process |
|------|--------------|-------------------|---------|
| A: Structure Migration | `memory_bank/` (underscore) or `memory-bank/` flat (no runtime/logs/knowledge) | pre-0.3.0 | Agent-guided migration via INIT_PROMPT mode H |
| B: Version Upgrade | `memory-bank/runtime|logs|knowledge` three-state | 0.3.0+ | Manual protocol review + automatic tool/schema copy |

# Preconditions

- Python 3.11+ available.
- Local copy of Paradigma latest source (e.g., `D:\Repos\paradigma`).
- The project was initialized from a Paradigma template.

# Steps

## 1. Run Diagnosis

```bash
python .paradigma/tools/pd-diagnose.py --upstream <paradigma源路径>
```

This produces a gap report across five dimensions: structure, tools, schema, config, and protocol.

If `pd-diagnose.py` is not yet available in the project, copy it together with both shared dependencies and install the runtime requirements:
```bash
cp <paradigma源>/.paradigma/tools/pd-diagnose.py .paradigma/tools/
cp <paradigma源>/.paradigma/tools/_version.py .paradigma/tools/
cp <paradigma源>/.paradigma/tools/_paradigma_yaml.py .paradigma/tools/
cp <paradigma源>/requirements.txt ./requirements.txt
python -m pip install -r requirements.txt
```

For CI/automation, use `--check-version` for a quick pass/fail check:
```bash
python .paradigma/tools/pd-diagnose.py --upstream <paradigma源> --check-version
# Exit 0 = version matches, 1 = update needed
```

## 2. Choose Upgrade Path

### Path A: Structure Migration (pre-OKF → OKF)

**Trigger**: Diagnose shows "pre-0.2.0" or "0.2.x (flat memory-bank/)" with many structure errors.

1. Use INIT_PROMPT mode H to guide the Agent through migration.
2. The Agent handles:
   - Directory creation (`memory-bank/runtime|logs|knowledge`)
   - File movement and OKF frontmatter addition
   - Breaking down flat `progress.md` into individual session logs
   - Splitting `decisions.md` into individual ADR files
3. Infrastructure files (tools, schema, templates) are copied from upstream.
4. The Agent does NOT automatically overwrite customized protocol files — it backs them up first.
5. After migration, run `pd-check-all.py` to verify.

### Path B: Version Upgrade (OKF → newer OKF)

**Trigger**: Diagnose shows "0.3.0+" or a specific version number, with only tool/schema/config gaps.

1. **Package and adapters**: Copy `pyproject.toml`, `src/paradigma/`, and all `.py` files from `<upstream>/.paradigma/tools/`, then install the project package. The adapters are only a v0.5.x compatibility surface and must match the package version.

2. **Schema**: Copy all `.yaml` files from `<upstream>/.paradigma/schemas/`. New types are backward-compatible.

3. **Config**: Merge new keys from upstream `config.yaml`. Never blindly overwrite custom project keys. Migrate `paradigma_harness_version` to `installed_distribution_version`, then remove the legacy field.

4. **Protocol**: Review differences manually.
   ```bash
   diff AGENT_RULES.md <upstream>/AGENT_RULES.md
   diff INIT_PROMPT.md <upstream>/INIT_PROMPT.md
   ```
   Protocol files are commonly customized for project-specific needs. NEVER auto-overwrite them. Apply upstream changes selectively.

## 3. Update Version Tracking

Edit `.paradigma/config.yaml`:
```yaml
installed_distribution_version: "<new_version>"
```

Then install the package and run `pd version --format json`.

### v0.5.0 → v0.5.1 Metadata Migration

The 0.5.0 source used ambiguous legacy version fields. For a derived 0.5.0 workspace:

1. Copy the complete upstream `.paradigma/tools/` and `.paradigma/schemas/` directories, plus `requirements.txt`.
2. Install `requirements.txt`; v0.5.1 tooling requires PyYAML.
3. Replace config `schema_version` and `paradigma_harness_version` with the explicit fields below, preserving project-specific roots and paths:

   ```yaml
   config_schema_version: "0.3"
   okf_version: "0.1"
   installed_distribution_version: "0.5.1"
   machine_index_path: .paradigma/cache/knowledge-index.json
   ```

4. In `paradigma-types.schema.yaml`, replace top-level `schema_version` with `document_schema_version: "0.2"`.
5. Update the workspace root `VERSION` to `0.5.1`, rebuild indexes, and run the version and aggregate checks.
6. Keep any customized `AGENT_RULES.md`, `INIT_PROMPT.md`, and IDE rules under manual diff review; do not overwrite them blindly.

The migration is retry-safe because configuration edits are declarative and generated indexes are rebuildable. Roll back with `git revert` or restore the pre-migration commit; `.paradigma/cache/` may be deleted at any time.

### v0.5.1 → v0.6.0 Memory Runtime Migration

v0.6.0 adds the document-level Memory Kernel without rewriting existing knowledge or runtime documents. For a derived v0.5.1 workspace:

1. Install the v0.6.0 package and update root `VERSION` plus config `installed_distribution_version` to `0.6.0`.
2. Upgrade `config_schema_version` to `0.4` and add the explicit paths below. A v0.5.1 config that omits them remains readable through the same safe defaults, so this edit is declarative and retry-safe:

   ```yaml
   memory_root: memory-bank/memories
   catalog_path: .paradigma/cache/catalog.sqlite3
   ```

3. Preserve existing `memory-bank/knowledge`, `runtime`, and `logs` content. Do not bulk-convert it into Memory Records.
4. Copy the current compatibility wrappers when the workspace still invokes `.paradigma/tools/pd-*.py`; use installed `pd` commands for new automation.
5. Run `pd index rebuild`, then `pd catalog rebuild`. The catalog is derived state and may be deleted and rebuilt at any time; canonical Memory Markdown under `memory-bank/memories/` is the source of truth.
6. Run `pd version --format json`, `pd check --dry-run`, and `pd catalog verify`. An empty memory root and zero-record catalog are valid immediately after migration.

Rollback by reverting the declarative config/version update and removing `.paradigma/cache/catalog.sqlite3`. Do not delete canonical files under `memory-bank/memories/` if records were created after upgrading.

### v0.6.0 → v0.7.0 Coding Runtime Migration

v0.7.0 adds the Coding integration without changing config, OKF, document, Memory document, or catalog schema versions. For a derived v0.6.0 workspace:

1. Install the v0.7.0 package and update root `VERSION` plus config `installed_distribution_version` to `0.7.0`; preserve all project-specific roots.
2. Keep canonical `memory-bank/knowledge`, `memory-bank/memories`, and logs. Do not copy `memory-bank-template/runtime/*` into a live workspace.
3. Back up any hand-authored legacy `runtime/active-task.md`, then run `pd runtime init` and review the plan. Apply `pd runtime init --write`; it only creates missing null pointers and rebuilds projections, and never overwrites existing YAML facts.
4. If legacy active-task work must continue, map its title/goal/repository scope into `pd task start ...` using dry-run first. Start a Session explicitly and create a Checkpoint before ending it.
5. Update customized `AGENT_RULES.md`, IDE adapters, README, and INIT_PROMPT by semantic diff. The v0.7 protocol uses Task/Session status plus `pd context build/verify`; do not restore manual runtime checklist instructions.
6. Run `pd index rebuild`, `pd catalog rebuild`, `pd runtime verify`, `pd check`, and a representative Context build/verify. Existing v0.6 Memory records and catalog schema remain compatible.
7. Retain `.paradigma/tools/` when local automation still calls it. v0.7.0 keeps these adapters because real-project non-use has not been proven; migrate new automation to installed `pd`.

Rollback by reverting the package/version/protocol update. YAML Task/Session/Checkpoint facts created after upgrading are ordinary repository files and should be preserved or migrated deliberately, not deleted as cache.

## 4. Validate

```bash
python .paradigma/tools/pd-index.py rebuild
python .paradigma/tools/pd-check-all.py
```

# Verification

- `pd-diagnose.py --upstream <upstream>` shows no gaps (exit 0).
- `pd-check-all.py` all checks pass.
- Agent reads new protocol files correctly in the next session.

# Rollback

| Scenario | Action |
|----------|--------|
| Migration broke something | `git revert` the migration commit |
| Protocol files lost customizations | Restore from `.bak` backup created by Agent |
| Tools don't work after copy | Check Python version (3.11+ required). Verify file permissions. |

# Troubleshooting

| Symptom | Likely Cause | Action |
|---------|--------------|--------|
| `pd-diagnose.py` not found | Tool not in project | Copy from upstream first |
| Diagnose shows "unknown" | Project has no Paradigma traces | Verify `memory-bank/` or `memory_bank/` directory exists |
| Protocol has many diffs but no obvious changes needed | Project heavily customized AGENT_RULES | Cherry-pick only the new sections (checkpoints, DESIGN.md, diagnostics reference) |
| `pd-check-all` fails after migration | Missing OKF frontmatter on migrated files | Re-run mode H Step 7 to add frontmatter |
| Agent can't find files after migration | Index not rebuilt | Run `pd-index.py rebuild` |

# Citations

- `memory-bank/knowledge/domains/design-system.md`
- `memory-bank/knowledge/contracts/repository-contract.md`
- `INIT_PROMPT.md` — Mode H
