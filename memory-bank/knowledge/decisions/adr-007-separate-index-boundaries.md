---
type: paradigma-decision
title: ADR-007 Separate Human Navigation from Derived Machine Indexes
description: Defines root index files as bounded human navigation, local generated indexes as non-recursive views, and the full machine inventory as rebuildable cache.
tags: [adr, index, navigation, cache, retrieval]
timestamp: 2026-07-23T21:35:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: cold
  lifecycle: append-only
  update_policy: append-only
  epistemic_status: decision
  status: accepted
  retrieval_hints:
    zh:
      - 索引边界
      - 根导航
      - 机器索引缓存
      - 非递归局部索引
    en:
      - index boundaries
      - root navigation
      - machine index cache
      - non-recursive local index
  symbols:
    - pd-index.py
    - _index.py
    - knowledge-index.json
    - pd-sync-index.py
  relations:
    constrains:
      - /architecture.md
      - /conventions.md
      - /contracts/repository-contract.md
      - /domains/tooling.md
    supersedes:
      - /decisions/adr-003-strict-okf-production-rules.md
    follows:
      - /decisions/adr-006-transactional-task-archive.md
---

# Context

原 `pd-sync-index.py` 把每个 knowledge root 的全部 concept 文档递归展开到根 `index.md`。根索引因此随文档数量线性增长，同时承担人工导航、Agent 首跳上下文和机器全量元数据三种职责。子目录索引也递归包含后代目录内容，无法保持局部边界。

根索引是每次会话的 HOT 入口，不能成为全库清单。机器完整索引又必须可校验、可删除、可重建，并且损坏时不能改变 canonical Markdown。

# Decision

采用三层索引边界：

1. knowledge root 的 `index.md` 是人工维护的高层导航，只列 HOT 文档、主要目录和关键入口；生成器会移除旧 auto-index block，但之后不再向根索引追加完整清单。
2. 子目录 `index.md` 保留 generated block，但只列该目录的直接 concept 文档，不递归展开后代目录。
3. 全部 knowledge root 的递归元数据生成到 `.paradigma/cache/knowledge-index.json`。缓存内容确定、无时间戳，包含 source digest，可随时删除并从 canonical Markdown 重建。

`pd-index.py rebuild` 重建局部 Markdown 索引和机器缓存；`pd-index.py verify` 验证根导航无生成块、局部索引与直接文档一致、机器缓存与 canonical source 一致。旧 `pd-sync-index.py --write/--check` 保留为 v0.5.x 兼容包装器。

`.paradigma/cache/` 不进入版本控制。CI 先重建缓存，再用 Git diff 确认 tracked Markdown 索引本来就是 current，最后运行 verify 门禁。配置新增 `machine_index_path`，因此 config schema 从 0.2 升级到 0.3。

# Consequences

- 根索引大小由人工导航结构决定，不随 concept 数量线性膨胀。
- Agent 首跳读取保持稳定，详细清单按目录 progressive disclosure。
- 机器消费者获得统一、完整、确定性的 JSON inventory。
- 删除或破坏 cache 不会修改 knowledge；rebuild 可恢复，verify 会报告 stale。
- 新增根级 concept 时，需要人工决定是否值得加入高层导航；机器缓存仍会自动收录。
- CI 和新 workspace 在 verify 前必须先执行一次 rebuild 以生成被忽略的缓存。

# Alternatives Considered

1. 继续在根 Markdown 保存全量清单：拒绝，因为 HOT 上下文随知识规模线性增长。
2. 删除所有子目录 Markdown 索引：拒绝，因为人类和 Agent 仍需要可读的局部导航。
3. 将机器 JSON 提交到 Git：拒绝，因为它是纯派生产物，提交会制造大规模无语义 diff。
4. 立即使用 SQLite/FTS5：推迟到 Phase 2；Phase 0 JSON inventory 足以验证 canonical/derived 边界。

# Status

Accepted for Phase 0 Batch 0.4.

# Related Documents

- `docs/devplan/paradigma_dev_5+.md`
- `docs/rfc/paradigma-okf-compatible-runtime.md`
- `memory-bank/knowledge/architecture.md`
- `memory-bank/knowledge/contracts/repository-contract.md`
- `memory-bank/knowledge/domains/tooling.md`
