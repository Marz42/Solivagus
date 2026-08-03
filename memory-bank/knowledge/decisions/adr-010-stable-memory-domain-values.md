---
type: paradigma-decision
title: ADR-010 Use Immutable Memory Values and Time-Sortable Stable IDs
description: Fixes the Phase 2 Memory Kernel value boundaries, invariants, and stable identifier format before storage is introduced.
tags: [adr, memory-kernel, domain-model, identifiers, provenance]
timestamp: 2026-07-23T23:48:40+08:00
paradigma:
  schema_version: "0.1"
  temperature: cold
  lifecycle: append-only
  update_policy: append-only
  epistemic_status: decision
  status: accepted
  retrieval_hints:
    zh:
      - Memory Kernel 模型
      - 稳定记忆 ID
      - 记忆模型不变量
    en:
      - memory kernel model
      - stable memory ID
      - immutable domain values
  symbols:
    - MemoryRecord
    - MemoryQuery
    - MemoryResult
    - generate_memory_id
  relations:
    constrains:
      - /architecture.md
      - /conventions.md
      - /contracts/repository-contract.md
    follows:
      - /decisions/adr-009-unified-cli-compatibility-window.md
---

# Context

Phase 2 后续的 Markdown codec、SQLite catalog、query、mutation 和 explain 都会依赖同一组领域值。若先让存储格式决定字段和默认行为，memory ID、时间、来源与查询状态会在多个 adapter 中形成不同解释。

# Decision

1. `src/paradigma/kernel/` 保存领域中立且不可变的 `MemoryRecord`、`MemoryScope`、`ProvenanceRef`、`MemoryRelation`、`MemoryQuery` 和 `MemoryResult`；Kernel 不依赖 application、storage、integration 或 adapter 层。
2. memory ID 固定为 `MEM-` 加 26 位大写 Crockford Base32，编码 48-bit UTC 毫秒时间和 80-bit 加密随机数。它与 ULID 字符布局兼容、按生成时间可排序；revision 延续原 memory ID。
3. 所有时间必须是 timezone-aware `datetime`；revision 从 1 开始；confidence 若存在则在 0 到 1 之间；有效期为闭区间；对象不静默修剪或去重输入。
4. 每条 `MemoryRecord` 至少有一个可定位 provenance。`agent_inference` 必须提供 confidence；能否作为高置信度事实提交由后续 write policy 决定。
5. 普通 `MemoryQuery` 默认只检索 `active`，relation expansion 必须显式开启。`MemoryResult` 通过 matched fields、reasons、relation source 和 warnings 提供 explain 所需边界，不复制 record 已有字段。
6. Batch 2.1 不定义 Markdown/SQLite 表达，不创建空 service/policy 层，也不加入 Coding 或 Research 专用类型。

# Consequences

- Batch 2.2 和 2.3 可以围绕一个已验证的 canonical value model 实现双向 codec 与可重建 catalog。
- 严格的 tuple、时间和 provenance 校验会要求 codec 在构造对象前显式规范化外部数据，避免 Kernel 内部存在半可变或含糊状态。
- `MEM-` ID 不保证同一毫秒内的调用顺序；它保证唯一性概率、规范格式和跨毫秒排序。需要单调生成器时必须另立契约。
- 未来扩展字段需要经过兼容性评估，因为这些对象是 v1.0 计划稳定的核心契约。

# Alternatives Considered

1. 自增整数：拒绝，因为离线 Markdown 写入、合并和重建 catalog 时需要中心协调。
2. 随机 UUID：拒绝作为默认格式，因为不能提供自然的时间排序且不符合正式计划的 `MEM-01J...` 方向。
3. 先实现 Markdown dataclass：拒绝，因为会把路径、frontmatter 和序列化细节泄漏到 Kernel。
4. 自动修剪字符串、把 list 转 tuple：拒绝，因为 canonical 输入错误应在边界显式暴露，而不是被静默改写。

# Status

Accepted for Phase 2 Batch 2.1.

# Related Documents

- `docs/devplan/paradigma_dev_5+.md`
- `memory-bank/knowledge/architecture.md`
- `memory-bank/knowledge/contracts/repository-contract.md`
- `src/paradigma/kernel/`
