---
type: paradigma-decision
title: ADR-008 Establish the Installable Package Core Boundary
description: Defines src/paradigma as the reusable value-returning core and legacy scripts as transitional outer adapters.
tags: [adr, package, application-core, cli, compatibility]
timestamp: 2026-07-23T22:31:40+08:00
paradigma:
  schema_version: "0.1"
  temperature: cold
  lifecycle: append-only
  update_policy: append-only
  epistemic_status: decision
  status: accepted
  retrieval_hints:
    zh:
      - Python Package 边界
      - 应用内核
      - 兼容包装器
    en:
      - Python package boundary
      - application core
      - compatibility wrapper
  symbols:
    - pyproject.toml
    - src/paradigma
    - OperationResult
    - Diagnostic
  relations:
    constrains:
      - /architecture.md
      - /conventions.md
      - /contracts/repository-contract.md
      - /domains/tooling.md
    follows:
      - /decisions/adr-007-separate-index-boundaries.md
---

# Context

Phase 0 的独立脚本已经可靠且有 characterization baseline，但解析、配置、Schema、原子写入、错误和输出逻辑仍以脚本目录为中心。继续直接扩展脚本会让统一 CLI、MCP 和后续 Memory Kernel 重复业务规则，也无法把 Paradigma 作为标准 Python distribution 安装和复用。

# Decision

建立 `pyproject.toml` 和 `src/paradigma/`：

1. 根 `VERSION` 继续是 distribution version 唯一真相源，setuptools 动态读取该文件。
2. `src/paradigma/` 保存不依赖 CLI 的可复用能力；核心方法返回值、`OperationResult` 或结构化 diagnostics/errors，不直接打印、不解析 argv、不执行 subprocess。
3. config、parser、schema validator、atomic writer、diagnostics、errors 和 results 先进入 package；业务 services 与统一 CLI 在后续 Batch 1.2 加入。
4. `.paradigma/tools/` 在迁移期继续保证现有命令可用，Batch 1.3 将其收缩为只调用 package/Application Service 的薄包装器。
5. unit、integration、architecture 和 characterization tests 分别保护模块行为、旧行为等价、依赖方向和 CLI 兼容性。

# Consequences

- Paradigma 可以构建 wheel 并安装，后续 CLI/MCP 共享同一应用内核。
- Phase 1 迁移期间会短暂存在 package 与 legacy helper 的重复实现；必须在 Batch 1.3 删除脚本侧独立业务逻辑。
- package core 保持纯值边界，输出格式和进程退出码由外层 adapter 决定。
- `requirements.txt` 暂时保留给 legacy workspace bootstrap；`pyproject.toml` 是 package dependency contract。

# Alternatives Considered

1. 继续扩展独立脚本：拒绝，因为无法形成稳定 Application API。
2. 一次性删除旧脚本：拒绝，因为会破坏 v0.5.x 使用方式和 characterization baseline。
3. 先实现 MCP 再抽内核：拒绝，因为 adapter 会被迫承载业务逻辑。
4. 提前建立完整未来目录树：拒绝，只创建 Phase 1 已有真实职责的模块。

# Status

Accepted for Phase 1 Batch 1.1.

# Related Documents

- `docs/devplan/paradigma_dev_5+.md`
- `pyproject.toml`
- `memory-bank/knowledge/architecture.md`
- `memory-bank/knowledge/contracts/repository-contract.md`
- `memory-bank/knowledge/domains/tooling.md`
