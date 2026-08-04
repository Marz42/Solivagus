---
type: paradigma-contract
title: Workspace and Artifact Contract
description: Workspace SQLite state and per-document artifact layout for Solivagus.
tags: [contract, workspace, artifacts, sqlite, solivagus]
timestamp: 2026-08-03T21:20:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: evolving
  update_policy: requires-human-confirmation
  epistemic_status: proposal
  contract_kind: data
  retrieval_hints:
    zh:
      - 工作区
      - artifact
      - SQLite
      - checkpoint
    en:
      - workspace
      - artifacts
      - SQLite
      - checkpoint
  symbols:
    - state.db
    - source.md
    - translated.zh.md
    - translation_units
    - cache_partitions
    - .solivagus
  relations:
    depends_on:
      - /architecture.md
      - /decisions/adr-001-package-name-solivagus.md
    related_to:
      - /contracts/cli-contract.md
    informed_by:
      - /project-brief.md
---

# Scope

约定用户工作区状态库与每文档产物布局。不覆盖 Memory-Bank 开发记忆文件。

# Contract

## Workspace root

```text
<workspace>/.solivagus/state.db
<workspace>/.solivagus/cache/translations/
<workspace>/.solivagus/supervisor.lock
```

正式 artifact 目录：PDF 同级 `{sanitized_stem}.solivagus/`（空格等字符会 sanitize，例如 `Attention_Is_All_You_Need.solivagus`）。

MVP 兼容：PDF 旁 `*.translation/` 可由 `solivagus import-mvp` 映射到正式布局。

本地样例（不入库）：`example/Qwen3_TTS.translation/`、`example/Attention_Is_All_You_Need.solivagus/` 等。

## Per-document artifacts

```text
preflight.json
source.md
translated.zh.md
translated.bilingual.md
qa-report.md
usage-report.json
manifest.json
assets/
ocr/batch-NNNN/{result.json,source.md,done.json,worker-config.json}
units/                 # Phase 3：结构规划写入；OCR 阶段可能有临时字符种子
partitions/pNN.json
style_capsules/vN.json
usage-report.json
plan-report.json
logs/
```

翻译阶段会更新 `cache_partitions.actual_probe_hit_tokens` / `warmup_status`，并向 `translation_attempts` 写入 usage。风格胶囊仅在分区边界升级版本；同分区内所有 Unit 共享同一 capsule 文本。
## SQLite tables（首版概念）

`documents`、`ocr_batches`、`structural_nodes`、`translation_units`、`cache_partitions`、`translation_attempts`、`style_capsules`、`artifacts`。

文档身份：`source_sha256` + 配置哈希；路径变化不丢失身份。

# Request Schema

写入规则：

- 完成批次必须出现 `done.json`（或等价 DB 状态）才可跳过
- 翻译 Unit 成功条件：HTTP 2xx + `finish_reason=stop` + Unit 标记完整 + 非空 + 结构校验通过
- 本地翻译缓存键包含：原文、provider、model、prompt_version、target_language、glossary_hash、style_capsule_hash、参数

# Response Schema

| File | Meaning |
|------|---------|
| `translated.zh.md` | 日常阅读主输出 |
| `translated.bilingual.md` | 校对用（折叠英文） |
| `qa-report.md` | 机械检查与修复摘要 |
| `usage-report.json` | Token / 费用 / 重试 / 回退统计 |

# State Transitions

OCR 批次：缺失 `done.json` → 重跑该批；存在则跳过。  
配置签名变化 → 不得静默复用旧 OCR。  
Style capsule 仅在分区边界升级版本。

# Compatibility Notes

- MVP `state.json` + `chunks/` 为遗留布局；正式版以 SQLite + `units/` 为准。
- 工作区与 artifact、整个 `example/` **永不**提交到 git。

# Breaking Change Policy

改变 artifact 文件名、DB schema 或缓存键字段，需要迁移脚本与契约版本说明。

# Citations

- `project-brief/project-brief.md` §7–§9、§23
- `/architecture.md`
- `/contracts/cli-contract.md`
