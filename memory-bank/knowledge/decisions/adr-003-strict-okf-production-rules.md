---
type: paradigma-decision
title: ADR-003 Adopt Strict OKF Production Rules
description: Decision to harden Paradigma from OKF MVP into strict production-ready validation and maintenance workflows.
tags: [adr, okf, tooling, validation]
timestamp: 2026-07-04T22:57:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: cold
  lifecycle: append-only
  update_policy: append-only
  epistemic_status: decision
  status: accepted
  retrieval_hints:
    zh:
      - strict lint
      - link check
      - index checksum
      - runtime log tools
    en:
      - strict lint
      - link check
      - index checksum
      - runtime log tools
  relations:
    constrains:
      - /architecture.md
      - /contracts/repository-contract.md
    follows:
      - /decisions/adr-002-okf-compatible-memory-runtime.md
---

# Context

ADR-002 established the OKF-compatible runtime/logs/knowledge structure and minimal tools. The RFC still called for stricter schema validation, relationship and link checking, richer retrieval indexes, and runtime/log maintenance tools.

# Decision

Adopt strict OKF production rules for Paradigma 0.4.0:

- `pd-lint-okf.py --strict` validates schema registry types, required frontmatter, Paradigma namespace fields, timestamps, required sections, enum policies, and generated block checksums.
- `pd-check-links.py` validates local Markdown links, frontmatter relations, and generated index entries.
- `pd-sync-index.py` generates root and subdirectory indexes with retrieval hints, symbols, relations, and checksums.
- Runtime/log tools report HOT size, archive completed active tasks, and compact progress logs without deleting originals.
- Protocol documents require lint, link check, index check, and hot-size check during Update Phase.

# Consequences

- Paradigma knowledge becomes more reliable for both humans and agents.
- Generated blocks have a detectable fingerprint, reducing accidental manual drift.
- Derived projects receive clearer maintenance commands and stricter validation expectations.
- The tooling remains standard-library Python for portability.

# Alternatives Considered

- Keep MVP-only lint and index generation: simpler, but it leaves the RFC's production closure unimplemented.
- Introduce third-party YAML/schema libraries immediately: more complete parsing, but adds dependency management before the protocol stabilizes.
- Add CI now: useful later, but the current iteration focuses on stable local commands first.

# Status

Accepted.

# Related Documents

- `docs/rfc/paradigma-okf-compatible-runtime.md`
- `memory-bank/knowledge/architecture.md`
- `memory-bank/knowledge/contracts/repository-contract.md`
- `memory-bank/knowledge/manuals/paradigma-baseline-test.md`
