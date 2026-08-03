---
type: paradigma-decision
title: ADR-009 Adopt One Unified CLI with a Time-Bounded Compatibility Layer
description: Makes pd the primary command surface and limits legacy scripts to package-backed adapters during v0.5.x.
tags: [adr, cli, compatibility, deprecation, application-service]
timestamp: 2026-07-23T23:04:58+08:00
paradigma:
  schema_version: "0.1"
  temperature: cold
  lifecycle: append-only
  update_policy: append-only
  epistemic_status: decision
  status: accepted
  retrieval_hints:
    zh:
      - 统一 CLI
      - 兼容窗口
      - 旧脚本弃用
    en:
      - unified CLI
      - compatibility window
      - legacy wrapper deprecation
  symbols:
    - pd
    - CommandOutcome
    - .paradigma/tools
  relations:
    constrains:
      - /architecture.md
      - /conventions.md
      - /contracts/repository-contract.md
      - /domains/tooling.md
    follows:
      - /decisions/adr-008-package-core-boundary.md
---

# Context

Phase 1 需要在不立即破坏衍生项目旧命令的前提下，结束多个脚本各自实现业务规则的状态。统一入口还必须同时服务人类终端、自动化 JSON 消费者和后续 MCP adapter。

# Decision

1. 安装后的 `pd` 是唯一首选命令入口，Application Service 返回 `CommandOutcome`，CLI adapter 负责参数、text/JSON 和退出码。
2. 所有叶子命令接受 `--format text|json`、`--dry-run` 和 `--project`；mutation 默认或显式支持无副作用预览。
3. `.paradigma/tools/` 在 v0.5.x 只保留 bootstrap、旧参数与旧输出适配，不得实现 parser、validation、index、diagnosis 或 mutation 规则。
4. 兼容入口与新 CLI 的数据和退出语义由 integration tests 对比；architecture tests 禁止业务实现回流脚本目录。
5. CI 在 Windows 与 POSIX runner 上安装 package，以 `pd` 跑主门禁，再运行一次 legacy aggregate adapter。

# Consequences

- CLI、未来 MCP 和 Python 调用共享同一业务语义。
- 旧项目可以在 v0.5.x 继续调用原脚本，但必须安装 matching package 或携带 matching `src/paradigma/`。
- 旧脚本参数形状暂时增加维护成本；计划在 v0.7.0 前基于真实使用情况评估删除。

# Alternatives Considered

1. 立即删除旧脚本：拒绝，会破坏衍生项目自动化。
2. 让旧脚本 subprocess 调用新 CLI：拒绝，会丢失结构化对象边界并增加平台差异。
3. 永久维护两套实现：拒绝，会重新产生规则漂移。

# Status

Accepted for Phase 1 Batch 1.3.

# Related Documents

- `docs/devplan/paradigma_dev_5+.md`
- `memory-bank/knowledge/architecture.md`
- `memory-bank/knowledge/contracts/repository-contract.md`
- `memory-bank/knowledge/domains/tooling.md`
