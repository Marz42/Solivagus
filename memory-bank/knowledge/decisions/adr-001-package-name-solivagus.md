---
type: paradigma-decision
title: ADR-001 Adopt solivagus as package and CLI name
description: Decide product, Python package, CLI entry, and workspace directory naming for Solivagus.
tags: [decision, adr, naming, solivagus]
timestamp: 2026-08-03T17:20:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: cold
  lifecycle: stable
  update_policy: requires-human-confirmation
  epistemic_status: decision
  retrieval_hints:
    zh:
      - 包名
      - CLI 名称
      - solivagus
      - 命名决策
    en:
      - package name
      - CLI name
      - solivagus
      - naming decision
  symbols:
    - solivagus
    - src/solivagus
    - .solivagus
  relations:
    informs:
      - /architecture.md
      - /contracts/repository-contract.md
      - /contracts/cli-contract.md
    related_to:
      - /project-brief.md
---

# Context

设计草案 `project-brief/project-brief.md` 使用 `pdf2zh` 作为业务包与 CLI 名，而产品与仓库名为 Solivagus。开发前需要冻结命名，避免脚手架与契约漂移。

# Decision

1. 产品名、Python 包名、CLI 入口统一为 **`solivagus`**。
2. 业务代码目录为 **`src/solivagus/`**。
3. 用户工作区状态根为 **`.solivagus/`**（例如 `.solivagus/state.db`）。
4. 历史文稿中的 `pdf2zh` 仅作设计来源别名，不再作为实现目标名。
5. MVP 旁路目录 `*.translation/` 仍可作为导入兼容输入，正式布局以 `.solivagus/` + artifact 契约为准。

# Consequences

- Phase 1 脚手架、Typer entry point、文档与 Memory-Bank 契约全部使用 `solivagus`。
- 迁移工具需识别旧 `*.translation/` / 草案 `.pdf2zh/` 路径并映射到 `.solivagus/`。
- 对外 README / 用法速查在实现后替换 `pdf2zh` 命令示例。

# Alternatives Considered

1. **保留 `pdf2zh` 包名、Solivagus 仅作产品名**：拒绝，双名增加认知与发布成本。
2. **CLI 用短命令、包名用 solivagus**：可后续再加 alias；首版先单一名称。

# Status

Accepted — 2026-08-03

# Related Documents

- `/project-brief.md`
- `/architecture.md`
- `/contracts/cli-contract.md`
- `/contracts/repository-contract.md`
- `/plans/solivagus-v1-roadmap.md`
