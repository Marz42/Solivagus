---
type: paradigma-domain
title: Paradigma Migration Flows
description: Migration flow taxonomy (F-STRUCT, F-UPGRADE, F-SYNC) with phase breakdowns, file mapping tables, decision points, and a real-world case study.
tags: [domain, migration, harness, upgrade, paradigma]
timestamp: 2026-07-23T21:35:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: evolving
  update_policy: agent-editable
  epistemic_status: confirmed
  retrieval_hints:
    zh:
      - 迁移流程
      - 升级路径
      - 结构迁移
      - 版本升级
      - 最小同步
      - 分类法
    en:
      - migration flow
      - upgrade path
      - structure migration
      - version upgrade
      - minimal sync
      - taxonomy
  symbols:
    - pd-diagnose.py
    - installed_distribution_version
    - INIT_PROMPT mode H
    - F-STRUCT
    - F-UPGRADE
    - F-SYNC
  relations:
    related_to:
      - /manuals/paradigma-harness-update.md
      - /manuals/paradigma-baseline-test.md
      - /contracts/repository-contract.md
---

# Responsibility

Define the migration flow taxonomy for Paradigma derived projects. Three flow types (F-STRUCT, F-UPGRADE, F-SYNC) are identified based on the version gap detected by `pd-diagnose.py`. Each flow has a defined phase structure, file mapping, and decision points. This domain is the design reference; for operational steps see `paradigma-harness-update.md`.

# Public Interfaces

## Flow Taxonomy

| Flow ID | Name | Detected Version | Gap Type |
|---------|------|-----------------|----------|
| **F-STRUCT** | Structure Migration | `pre-0.2.0` or `0.2.x` | Flat `memory_bank/` or `memory-bank/` (no `runtime|logs|knowledge`) |
| **F-UPGRADE** | Version Upgrade | `0.3.0+` (known version < upstream) | Three-state structure exists but tools/schema/protocol lag |
| **F-SYNC** | Minimal Sync | Matches upstream, drift only | Version matches but files locally modified |

## Decision Tree

```text
Run pd-diagnose.py --upstream <upstream>
│
├─ detected == "unknown"
│  └─ No Paradigma traces. Verify directory structure.
│
├─ detected == "pre-0.2.0" or "0.2.x"
│  └─ → F-STRUCT
│
├─ detected == "0.3.0+" (matches upstream major)
│  ├─ version_match == True & gaps == [] → Up to date
│  ├─ version_match == True & gaps != [] → F-SYNC
│  └─ version_match == False           → F-UPGRADE
│
└─ detected >= "0.3.0" but far behind (>= 2 minor)
   └─ → F-UPGRADE (beware cumulative changes)
```

### F-STRUCT Phase Structure

```
Phase 1: Diagnose    (user)   — Review gap report, confirm scope
Phase 2: Foundation  (agent)  — Create dirs, copy tools/schema/templates
Phase 3: Knowledge   (agent)  — Migrate content, add OKF frontmatter
Phase 4: Validate    (agent)  — pd-check-all, pd-diagnose confirmation
Phase 5: Cleanup     (user)   — Review protocol .bak, delete old flat dir
```

### F-UPGRADE Phase Structure

```
Phase 1: Diagnose     — Gap report
Phase 2: Auto-copy    — Tools + schema from upstream (safe)
Phase 3: Config merge — Add missing keys to config.yaml
Phase 4: Protocol     — Manual diff review (NEVER auto-overwrite)
Phase 5: Validate     — pd-check-all
```

### F-SYNC Phase Structure

```
Phase 1: Diagnose — Identify specific gaps
Phase 2: Review   — User checks each gap
Phase 3: Fix      — Selectively apply or acknowledge
```

# Internal Flow

## Phase 2: Foundation — File Copy Rules

```
From upstream → To project:

.paradigma/tools/*.py        → .paradigma/tools/       (safe: derived projects rarely modify)
.paradigma/schemas/*.yaml    → .paradigma/schemas/     (safe: new types are backward-compatible)
.paradigma/config.yaml       → .paradigma/config.yaml  (safe: blank upstream config)
memory-bank-template/*       → memory-bank-template/    (safe: doesn't affect activated projects)
AGENT_RULES.md               → AGENT_RULES.md          (⚠ BACKUP FIRST → AGENT_RULES.md.bak)
INIT_PROMPT.md               → INIT_PROMPT.md          (⚠ BACKUP FIRST)
.cursor/rules/*.mdc          → .cursor/rules/          (⚠ BACKUP FIRST)
```

## Phase 3: Knowledge Migration — File Mapping (F-STRUCT only)

| Source (flat) | Target (three-state) | Paradigma Type | Notes |
|---|---|---|---|
| `active-task.md` | `runtime/active-task.md` | `paradigma-runtime-state` | Add frontmatter |
| `progress.md` | `logs/progress/YYYY-MM-DD-session-*.md` | `paradigma-session-log` | **Split** into per-session files |
| `changelog.md` | `logs/changelog.md` | _(keep existing)_ | Move verbatim |
| `project-brief.md` | `knowledge/project-brief.md` | `paradigma-project-brief` | Add frontmatter |
| `architecture.md` | `knowledge/architecture.md` | `paradigma-architecture` | Add frontmatter |
| `conventions.md` | `knowledge/conventions.md` | `paradigma-convention` | Add frontmatter |
| `decisions.md` | `knowledge/decisions/adr-NNNN-*.md` | `paradigma-decision` | **Split** each ADR |
| `glossary.md` | `knowledge/glossary.md` | `paradigma-glossary` | Add frontmatter |
| `known-issues.md` | `knowledge/known-issues/issue-*.md` | `paradigma-known-issue` | **Split** if multiple |
| `data-contracts.md` | `knowledge/contracts/data-contracts.md` | `paradigma-contract` | Add frontmatter |
| `domains/*.md` | `knowledge/domains/*.md` | `paradigma-domain` | Add frontmatter |
| `manuals/*.md` / `handbooks/*.md` | `knowledge/manuals/*.md` | `paradigma-manual` | Add frontmatter |
| `plans/*.md` | `knowledge/domains/plans/*.md` | `paradigma-domain` | Add frontmatter |
| `history/reports/*.md` | `logs/progress/history-*.md` | `paradigma-session-log` | Reclassify |
| `history/proposals/*.md` | `knowledge/domains/proposals/*.md` | `paradigma-domain` | Reclassify |
| Non-markdown assets | `memory-bank/reference/` | _(none)_ | Move without frontmatter |

## Phase 3: OKF Frontmatter Template

```yaml
---
type: <paradigma-type>
title: <document title>
description: <1-2 sentence description>
tags: [<relevant tags>]
timestamp: <ISO 8601>
paradigma:
  schema_version: "0.1"
  temperature: <warm|cold|hot>
  lifecycle: evolving
  update_policy: agent-editable
  epistemic_status: confirmed
  retrieval_hints:
    zh: [<keywords>]
    en: [<keywords>]
---
```

Agent frontmatter rules:
- `type`: Always from mapping table. Never guess.
- `title` / `description`: Infer from content.
- `timestamp`: File mod time or embedded date. ISO 8601.
- `retrieval_hints`: 3-7 zh/en keywords from subject matter.
- **Uncertain fields → write `TODO`. Never fabricate.**

## Phase 3: Subdirectory Classification (F-STRUCT)

| Old Subdirectory | Recommended Target | Rationale |
|---|---|---|
| `domains/` | `knowledge/domains/` | Direct mapping |
| `handbooks/` | `knowledge/manuals/` | Handbooks are operational guides |
| `plans/` | `knowledge/domains/plans/` | Plans are design documents |
| `history/reports/` | `logs/progress/history-*.md` | Periodic reports = session logs |
| `history/proposals/` | `knowledge/domains/proposals/` | Proposals are domain docs |
| `archive/` | `memory-bank/archive/` (no type) | Keep outside knowledge bundle |
| `demos/` | `memory-bank/demos/` (no type) | Non-knowledge assets |
| `reference/` | `memory-bank/reference/` (no type) | Media/screenshots |
| `templates/` | `memory-bank/templates/` (no type) | Workflow JSON files |

## Phase 4: Protocol Review Patterns (F-UPGRADE)

| Upstream Change | Typical Action |
|---|---|
| New checkpoint section | Apply |
| New DESIGN.md WARM reference | Apply if frontend; skip if backend |
| New pd-diagnose hint | Apply |
| New INIT_PROMPT mode (G, H) | Apply |
| Wording / phrasing changes | Optional |
| Section reordering | Review carefully |

## Decision Points Reference

| # | Decision | When | Options | Default |
|---|----------|------|---------|---------|
| D1 | Confirm migration scope | Phase 1 | Proceed / Adjust / Cancel | — |
| D2 | `progress.md` split strategy | Phase 3 | Split all / Archive old + split recent | Split all |
| D3 | `history/reports/` classification | Phase 3 | Session logs / Reference docs | Session logs |
| D4 | `plans/` classification | Phase 3 | domains/plans/ / Keep top-level / Archive | domains/plans/ |
| D5 | Protocol merge strategy | Phase 4/5 | Full replace / Cherry-pick / Keep custom | Cherry-pick |
| D6 | Non-markdown assets | Phase 3 | Move to reference/ / Keep original / Delete | Move to reference/ |
| D7 | Old directory cleanup | Phase 5 | Delete now / Later / Keep as archive | Delete after confirm |

## Case Study: FilumReforge (v0.2.x → v0.4.2)

- **Detected**: `0.2.x (flat memory-bank/)` | **Upstream**: `0.4.2`
- **Diagnose**: 9 errors (5 structure + 1 tools + 1 schema + 2 config), 3 infos (protocol)
- **Scope**: 14 flat `.md` files + 8 subdirectories; `progress.md` with 52 sessions; `decisions.md` with 1 ADR placeholder
- **AGENT_RULES.md**: 132 lines, heavily customized (project identity, Phase 0-4, default plan refs)
- **Path**: F-STRUCT. Phase 2 all infrastructure created. Phase 3: all progress split, all knowledge files frontmatter-added. `handbooks/` → `manuals/`, `plans/` → `domains/plans/`. Phase 4: pd-check-all passed after iterative fixes. Phase 5: user cherry-picks project identity from `.bak`, deletes old flat dir.

# Dependencies

- `pd-diagnose.py` — detects version and gaps (must be in project or copied from upstream first)
- `_version.py` — shared version reader required by `pd-diagnose.py` and `pd-version.py`
- `pd-version.py` — validates local version metadata after migration
- `pd-check-all.py` — validates migration completeness
- `pd-index.py` — rebuilds local and machine indexes after knowledge file changes
- `pd-lint-okf.py` — validates OKF frontmatter on migrated files
- Upstream Paradigma source — local path or git repo

# Related Contracts

- `memory-bank/knowledge/manuals/paradigma-harness-update.md` — Operational update commands and troubleshooting
- `memory-bank/knowledge/contracts/repository-contract.md` — Tool command contracts and status (pd-diagnose is Experimental)
- `INIT_PROMPT.md` — Mode H (Agent-guided structure migration wizard)

# Known Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Agent deletes old directory before Phase 5 | Content loss if migration incomplete | Always keep old files until user confirms Phase 5 |
| Agent overwrites AGENT_RULES.md without backup | Permanent loss of custom project rules | Always create `.bak` (Phase 2 copies with backup) |
| Agent fabricates frontmatter for unknown content | False metadata in knowledge base | Rule: write `TODO`, never fabricate |
| User skips Phase 1 diagnosis | Unknown scope → incomplete migration | pd-diagnose.py is the mandatory first step |
| Agent classifies subdirectories without asking | Misclassification (e.g. `plans/` ≠ `domains/`) | Phase 3 asks user before classifying ambiguous dirs |
| Large `progress.md` (50+ sessions) overwhelms agent | Timeout or incomplete migration | Offer batch-create option; ask split vs archive |
| Pre-0.2.0 `memory_bank/` (underscore) vs `memory-bank/` (hyphen) confused | Files moved to wrong location | Agent must check both directories exist and warn if both present |
