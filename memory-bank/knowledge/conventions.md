---
type: paradigma-convention
title: Coding and Collaboration Conventions
description: Coding, naming, testing, documentation, versioning, and prohibited patterns for Project Paradigma.
tags: [conventions, semver, collaboration, tooling]
timestamp: 2026-07-24T00:25:40+08:00
paradigma:
  schema_version: "0.1"
  temperature: hot
  lifecycle: stable
  update_policy: requires-human-confirmation
  epistemic_status: confirmed
  retrieval_hints:
    zh:
      - 代码规范
      - 版本规则
      - 文档约定
      - 工具校验
    en:
      - coding conventions
      - versioning
      - documentation
      - tooling
  symbols:
    - SemVer
    - VERSION
    - Update Phase
  relations:
    constrains:
      - /contracts/repository-contract.md
      - /manuals/paradigma-baseline-test.md
---

# Naming

| Target | Rule | Example |
|--------|------|---------|
| Files and directories | kebab-case, except established tool names | `pd-lint-okf.py`, `memory-bank` |
| Python functions/variables | snake_case | `parse_frontmatter` |
| Python classes | PascalCase | `LintIssue` |
| Constants | UPPER_SNAKE_CASE | `RESERVED_FILENAMES` |
| Markdown concept type | stable kebab-like string | `paradigma-contract` |
| Memory ID | `MEM-` + 26 uppercase Crockford Base32 characters | `MEM-01J...` |

Avoid pinyin, ambiguous abbreviations, and generic names such as `data`, `info`, or `temp` unless scoped to a tiny local context.

# Code Style

- Prefer standard-library Python except for the approved PyYAML runtime dependency.
- Keep tools single-purpose: lint, link check, index sync, hot-size check, archive, compact.
- Route all YAML and Markdown frontmatter reads through `_paradigma_yaml.py`; keep parsing conservative and deterministic.
- Avoid premature abstractions until duplicated logic proves stable across at least three tools.
- Use comments only when they explain why a rule exists or why a parser is intentionally limited.
- Keep `src/paradigma/` value-returning and adapter-neutral: no argv parsing, subprocess execution, direct printing, or imports from `.paradigma/tools/`.
- Keep CLI formatting and process exit behavior outside package core services.
- Keep Memory Kernel values frozen and storage-neutral; reject ambiguous naive datetimes, mutable collections, duplicate identifiers/tags/relations, and silent string normalization.

# Error Handling

- Tool failures should use non-zero exit codes when they produce ERROR-level findings.
- WARNING-level findings should be visible but should not fail `warn` mode.
- CLI output should include repository-relative paths.
- Parser failures must preserve their structured diagnostic code; do not reinterpret syntax or encoding failures as Schema errors.
- Generated files should be updated only when the user passes an explicit write flag or archive/compact command.
- Single-file generated writes must use a same-directory temporary file, flush, `fsync`, and atomic replace; failures preserve the previous target and remove the temporary file.
- Multi-file mutations must publish a dry-run plan, bind the source content hash, use atomic single-file writes, and define a retry-safe recovery path.
- Canonical Memory Markdown uses semantic `content_hash` for record integrity and exact-byte `source_hash` for optimistic concurrency; never overwrite a document without the caller's observed source hash.
- Derived SQLite files must stay in `.paradigma/cache/`, be rebuildable solely from canonical source, and be published as a complete temporary database rather than mutated in place during rebuild.
- Catalog-backed query uses `CatalogQuery` around storage-neutral `MemoryQuery`; keyword is a casefold literal substring and FTS is an explicit FTS5 expression. Never depend on implicit SQLite row order or silently query a stale catalog.
- Canonical memory mutations use pure Kernel transitions and exact-byte source-hash CAS. Candidate is canonical but non-active; revise requires new provenance; supersede preserves the old record; forget writes a tombstone and never unlinks content.
- Memory explain remains structured and canonical-first: include reasons, fields, scope, validity, status, provenance, confidence, relation source and warnings. Query fails on stale catalog; explain reports the drift without hiding a valid canonical record.

## Active Task Status

- `Current Status` is exactly one of `pending`, `active`, `blocked`, `completed`, or `aborted`.
- Status values are lowercase and contain no punctuation or prose.
- Checklist completion never changes or infers task status.
- Archive only `completed` tasks by default; run `pd-archive-task.py --dry-run` before `--write`.

# Testing Conventions

- Run `python -m unittest discover -s tests -p "test_*.py" -v` before and after tool refactors.
- Keep pre-package tool behavior baselines under `tests/characterization/`; mutation tests must operate in temporary repositories.
- Characterization coverage must include each public tool's repository success path plus its material validation, exit-code, compatibility, or write-failure behavior.
- Put pure package behavior in `tests/unit/`, legacy/package equivalence in `tests/integration/`, and dependency direction checks in `tests/architecture/`.
- Inject timestamp and entropy in stable-ID tests; production ID generation must use the system UTC clock and a cryptographic entropy source.
- Storage mutation tests must inject create/replace failures and assert the prior canonical bytes survive with no temporary or managed-writer lock leak.
- Catalog tests must cover source drift, row/FTS drift, corrupt SQLite, atomic replace failure, empty source, and installed-package access to bundled `schema.sql`.
- Run `pd check --dry-run` after knowledge/RFC edits (aggregates version, lint, links, index, hot-size, and optional design checks).
- Run `pd index rebuild` after adding/removing concepts or changing retrieval metadata, then run `pd index verify`.
- Use `.paradigma/tools/` commands only for v0.5.x compatibility verification; new automation must use `pd`.
- Compile Python tools with `python -m py_compile` when tool code changes, then remove or ignore `__pycache__` outputs.

# Documentation Conventions

- `AGENT_RULES.md` is the source of truth for Agent protocol.
- `.cursor/rules/memory-bank-protocol.mdc` is a synchronized Cursor adapter.
- `README.md` explains user-facing setup and maintenance workflows.
- `INIT_PROMPT.md` contains copyable conversation starters.
- `docs/rfc/*.md` stores proposal documents and must remain OKF-compatible.
- Long-lived knowledge belongs in `memory-bank/knowledge/`; runtime state belongs in `memory-bank/runtime/`; process logs belong in `memory-bank/logs/`.

## Versioning

Project Paradigma follows SemVer using the root `VERSION` file as the source of truth.

Version fields have distinct responsibilities:

| Field | Location | Meaning |
|-------|----------|---------|
| Distribution version | `VERSION` | Source repository release version and sole release truth |
| Installed distribution version | `.paradigma/config.yaml` | Paradigma distribution deployed in the current workspace |
| Config schema version | `.paradigma/config.yaml` | Shape and semantics of `config.yaml` |
| OKF version | `.paradigma/config.yaml` | External OKF format compatibility target |
| Document schema version | `.paradigma/schemas/paradigma-types.schema.yaml` | Paradigma concept-document registry version |

Run `pd version --format text` after changing any version field. The legacy `paradigma_harness_version` and ambiguous top-level config `schema_version` are migration inputs only and must not be written by current tooling.

| Change type | Version action |
|-------------|----------------|
| Typo or wording only | May skip version bump |
| Template path, protocol, or tooling behavior change | PATCH or MINOR depending on scope |
| New workflow/tooling capability | MINOR |
| Breaking protocol/path change for derived projects | MAJOR proposal, requires user confirmation |

When bumping versions, update:

1. `VERSION`
2. `memory-bank/logs/changelog.md`
3. A progress session in `memory-bank/logs/progress/`
4. ADR when the change is architectural

## Document Size Limits

HOT 文档（`project-brief.md`、`architecture.md`、`conventions.md`、`repository-contract.md`）每次会话都会被完整读入 Agent 上下文。为控制 token 消耗，应遵守以下阈值：

| 文档类型 | WARN | ERROR | 超出后操作 |
|----------|------|-------|-----------|
| HOT knowledge 文档 | 260 行 | 420 行 | 拆分 |
| `active-task.md` | 160 行 | 260 行 | 归档 |
| Progress index | 160 行 | 260 行 | 压缩 |

### architecture.md 拆分策略

当 `architecture.md` 超过 260 行时，按模块拆分为核心 + 细节：

```text
architecture.md                   ← HOT, 核心骨架 (~100–150 行)
  保留: Overview, Technology Stack, Module Boundaries, Key Constraints,
        Open Questions, Citations
  移出: 每模块的技术选型理由、数据流细节、trade-off 讨论

domains/architecture/             ← WARM, 模块级架构细节
├── payment-architecture.md
├── auth-architecture.md
└── frontend-architecture.md
```

拆分后，`architecture.md` 的 Module Boundaries 表应包含指向细节文档的路径：

```markdown
| Module | Responsibility | Architecture Detail |
|--------|----------------|---------------------|
| Payment | 支付回调与订单生命周期 | domains/architecture/payment-architecture.md |
```

### contracts/ 拆分策略

当单个 `paradigma-contract` 文档超过 200 行时，按 `contract_kind` 拆分为独立业务域文件：

```text
contracts/
├── index.md                     ← auto-generated
├── repository-contract.md       ← HOT, Paradigma 专用
├── api/                         ← contract_kind: api
│   ├── payment-api.md
│   └── auth-api.md
├── database/                    ← contract_kind: database
│   ├── user-schema.md
│   └── order-schema.md
└── events/                      ← contract_kind: event
    └── order-events.md
```

每个拆分文件保持独立的 OKF frontmatter（独立的 hints/symbols/relations），让 Agent 通过 index 精确路由到相关 contract，避免一次性加载所有 contract。

### 拆分原则

- **按业务域拆分**：同一业务域的 API + DB + Events 放在不同子目录。
- **保持独立可读性**：每个拆分文件应包含完整的 context（Scope / Contract / Schema / Compatibility），Agent 不需要读原文件即可理解。
- **temperature 差异化**：频繁变动的 contract 设为 `warm`，基础设施级 contract 保留 `hot`。
- **拆分后更新 relations**：拆分出的子文件应在 `depends_on` 中引用 `architecture.md`，原文件涉及的跨文档关系应在子文件中重新声明。

# Prohibited Patterns

- Do not write long-lived facts into `memory-bank/runtime/active-task.md`.
- Maintain root index navigation by hand, but do not place recursive generated blocks there.
- Do not manually edit subdirectory generated blocks or `.paradigma/cache/` machine indexes.
- Do not add new concept documents without OKF frontmatter.
- Do not change contracts, architecture, or accepted ADRs without checking update policy.
- Do not keep legacy flat Memory-Bank paths in active protocol docs.
- Do not introduce external dependencies into tooling without explicit justification.
