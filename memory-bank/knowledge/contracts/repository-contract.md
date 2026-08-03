---
type: paradigma-contract
title: Repository Contract
description: Repository-level layout and ownership boundaries for Solivagus.
tags: [contract, repository, solivagus]
timestamp: 2026-08-03T17:20:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: hot
  lifecycle: evolving
  update_policy: requires-human-confirmation
  epistemic_status: confirmed
  contract_kind: repository
  retrieval_hints:
    zh:
      - 仓库契约
      - 目录边界
      - 所有权
    en:
      - repository contract
      - directory boundaries
      - ownership
  symbols:
    - memory-bank
    - src/solivagus
    - src/paradigma
    - project-brief
    - example
    - requirements-gpu.txt
  relations:
    informed_by:
      - /architecture.md
      - /decisions/adr-001-package-name-solivagus.md
    related_to:
      - /contracts/cli-contract.md
      - /contracts/workspace-artifact-contract.md
---

# Scope

约束 Solivagus 仓库内目录职责、可提交内容与 harness/业务边界。

# Contract

| Path | Owner | Rules |
|------|-------|-------|
| `src/paradigma/` | Paradigma harness | 不实现 PDF 业务 |
| `src/solivagus/` | Solivagus 业务 | CLI、OCR、翻译、QA、组装 |
| `memory-bank/` | 开发记忆 | runtime/logs/knowledge 三态；不存 API Key 或用户 PDF |
| `memory-bank-template/` | 空白模板 | 仅模板源 |
| `project-brief/` | 设计与 MVP 源材料 | 可提交脚本/方案；不含密钥 |
| `example/` | 本机样例 | **整目录禁止提交**（PDF/HTML/MD/译文/私有依赖副本） |
| `requirements-gpu.txt` | 已跑通 GPU/OCR 钉选 | 可提交；来源于本机验证环境 |
| `legacy/` | 冻结 MVP 脚本 | `pdf_translate_cli_v0_2.py` 为 characterization 权威入口 |
| `tests/` | 测试 | 默认不调用真实付费 API |
| `.paradigma/` | harness 配置与可重建 cache | `cache/` 不入库 |
| `.env` / `.env.*` | 本地密钥 | **禁止提交**；提供 `.env.example` |
| `.solivagus/`、`*.translation/` | 运行时 | **禁止提交** |

# Request Schema

不适用。变更目录职责时：更新本契约、`architecture.md`、`.gitignore`，必要时新增 ADR。

# Response Schema

不适用。

# State Transitions

| Change | Required updates |
|--------|------------------|
| 重命名业务包/CLI | ADR + project-brief + architecture + 本契约 + README |
| 引入新运行时状态根 | workspace-artifact-contract、gitignore |
| 提升/替换 MVP 脚本 | legacy 路径、Phase 0 plan、characterization 说明 |

# Compatibility Notes

- 仓库以 `solivagus` 为发行包名（`pyproject.toml`），同时安装 `src/paradigma` 与 `pd` 入口。
- MVP `*.translation/` 与草案 `.pdf2zh/` 仅作迁移输入；正式根为 `.solivagus/`。
- `docs/rfc/` 保留 Paradigma OKF RFC，不充当产品规格。

# Breaking Change Policy

- 重命名业务包、移动 Memory-Bank 根、改变密钥或 `example/` 提交策略，视为破坏性变更。
- 删除 `project-brief/` 中 MVP 基线前，必须已有 `legacy/` 归档与可复现 characterization 说明。

# Citations

- `/architecture.md`
- `/decisions/adr-001-package-name-solivagus.md`
- `/project-brief.md`
- `/plans/solivagus-v1-roadmap.md`
