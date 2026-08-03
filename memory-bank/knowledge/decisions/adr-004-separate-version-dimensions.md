---
type: paradigma-decision
title: ADR-004 Separate Distribution and Schema Version Dimensions
description: Defines independent version fields for the Paradigma distribution, workspace installation, config schema, OKF format, and document schema.
tags: [adr, versioning, config, schema]
timestamp: 2026-07-22T23:44:32+08:00
paradigma:
  schema_version: "0.1"
  temperature: cold
  lifecycle: append-only
  update_policy: append-only
  epistemic_status: decision
  status: accepted
  retrieval_hints:
    zh:
      - 版本模型
      - 配置版本
      - 发行版本
      - Schema 版本
    en:
      - version model
      - distribution version
      - config schema
      - document schema
  symbols:
    - VERSION
    - installed_distribution_version
    - config_schema_version
    - okf_version
    - document_schema_version
  relations:
    constrains:
      - /architecture.md
      - /contracts/repository-contract.md
      - /domains/tooling.md
    follows:
      - /decisions/adr-003-strict-okf-production-rules.md
---

# Context

Paradigma v0.5.0 used the root `VERSION`, config-level `schema_version`, schema-registry `schema_version`, OKF version, and `paradigma_harness_version` without a fully explicit boundary. The source repository consequently reported distribution `0.5.0` while `pd-diagnose.py` treated `0.4.2` as the upstream version.

The ambiguity made it impossible to distinguish a release bump, a config migration, an OKF compatibility change, a concept-document schema change, and the version installed in a derived workspace.

# Decision

Adopt five independent version dimensions:

| Dimension | Field | Source |
|-----------|-------|--------|
| Distribution release | `distribution_version` | Root `VERSION`; the only release truth |
| Workspace installation | `installed_distribution_version` | `.paradigma/config.yaml` |
| Config format | `config_schema_version` | `.paradigma/config.yaml` |
| OKF compatibility | `okf_version` | `.paradigma/config.yaml` |
| Concept-document registry | `document_schema_version` | `.paradigma/schemas/paradigma-types.schema.yaml` |

The source repository's installed distribution must equal root `VERSION`. `pd-version.py --check` enforces the invariant and runs inside `pd-check-all.py`.

`paradigma_harness_version` and the ambiguous top-level config `schema_version` are deprecated migration inputs. `pd-diagnose.py` may read the legacy harness field to identify old workspaces, but current configuration and tooling must not write it.

Until the unified Phase 1 CLI exists, `python .paradigma/tools/pd-version.py --verbose` is the compatibility entry point for the planned `pd version --verbose` operation.

# Consequences

- Upstream version detection always reads root `VERSION` before compatibility fallbacks.
- Release and schema changes can evolve independently.
- Derived workspaces have an explicit installed distribution marker.
- Version drift becomes a deterministic CI failure.
- Updating an old workspace requires renaming the legacy harness field and adding config/document schema fields.
- The source repository temporarily carries an installed version equal to its distribution version; the invariant is checked rather than assumed.

# Alternatives Considered

1. Keep `paradigma_harness_version`: rejected because “harness” ambiguously referred to release, templates, protocol, and workspace state.
2. Infer versions from file hashes only: rejected because it cannot provide a stable human-readable installed version and is expensive to maintain.
3. Add a lock file immediately: deferred until package/migration semantics are implemented; the explicit config field is sufficient for the v0.5.x compatibility period.
4. Use one schema version for config and documents: rejected because those formats have independent compatibility lifecycles.

# Status

Accepted for Phase 0 Batch 0.1.

# Related Documents

- `docs/devplan/paradigma_dev_5+.md`
- `memory-bank/knowledge/architecture.md`
- `memory-bank/knowledge/conventions.md`
- `memory-bank/knowledge/contracts/repository-contract.md`
- `memory-bank/knowledge/domains/tooling.md`
