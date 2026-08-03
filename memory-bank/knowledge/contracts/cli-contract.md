---
type: paradigma-contract
title: CLI Contract
description: First-cut CLI command surface and exit semantics for Solivagus.
tags: [contract, cli, solivagus]
timestamp: 2026-08-03T17:20:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: evolving
  update_policy: requires-human-confirmation
  epistemic_status: proposal
  contract_kind: api
  retrieval_hints:
    zh:
      - CLI 命令
      - run batch plan
      - 退出码
      - solivagus
    en:
      - CLI commands
      - run batch plan
      - exit codes
      - solivagus
  symbols:
    - solivagus run
    - solivagus batch
    - solivagus plan
    - solivagus status
    - solivagus retry
  relations:
    depends_on:
      - /architecture.md
      - /contracts/workspace-artifact-contract.md
      - /decisions/adr-001-package-name-solivagus.md
    informed_by:
      - /project-brief.md
---

# Scope

定义 v1 计划中的 CLI 命令、主要标志与成功/失败语义。命令前缀为 **`solivagus`**。

# Contract

| Command | Purpose |
|---------|---------|
| `solivagus run <pdf>` | 处理单文档；支持 `--stage ocr|translate`、强制重跑标志 |
| `solivagus batch <dir>` | 目录批处理；默认夜间惯例可指向 `D:\PDFS`；`--recursive`、`--continue-on-error`、`--prevent-sleep` |
| `solivagus plan <pdf>` | 只规划 Unit/Partition 与费用估计，不翻译 |
| `solivagus status [pdf]` | 工作区或单文档状态 |
| `solivagus retry <pdf>\|--all-failed` | 重试失败项 |
| `solivagus inspect <pdf>` | 诊断；可 `--unit` |
| `solivagus report <pdf>` | QA / usage 报告视图 |
| `solivagus inspect-data <pdf>` | 显示将发送给 API 的数据范围（隐私审计） |

公共配置：`--env-file`、`--model`、`--device`、profile 选择。默认模型 `deepseek-v4-flash`。API Key 经 `.env` / 环境变量，不在命令行默认传递。

# Request Schema

```yaml
run:
  input: path
  stage: optional enum [all, ocr, translate]
  force_ocr: bool
  force_translate: bool
  force_plan: bool
batch:
  input_dir: path  # convention: D:\PDFS
  recursive: bool
  continue_on_error: bool
  prevent_sleep: bool
plan:
  input: path
  model: optional string  # default deepseek-v4-flash
```

# Response Schema

- 人类可读进度写入 stdout/stderr；机器汇总写入 `usage-report.json` / 夜间报告。
- `plan` 输出：页数、预估 Token、Unit/Partition 数、预估费用、估计模式（exact/approximate）。

# State Transitions

```text
queued → preflight → ocr_running → ocr_complete(|_with_warnings)
 → planning → translation_running → translation_complete(|_with_warnings)
 → qa_complete
```

旁路：`failed`、`cancelled`。`retry` 从失败节点恢复，不默认清除成功 checkpoint（除非 force）。

# Compatibility Notes

- MVP 单脚本标志在迁移期可提供兼容别名；正式文档以本契约为准。
- Windows 是首要无人值守环境；`--prevent-sleep` 映射 `SetThreadExecutionState`。
- Provider 保持 OAI-compatible；当前只配置 DeepSeek flash。

# Breaking Change Policy

重命名子命令、改变默认 stage、或改变 force 标志破坏性含义时，需大版本或明确迁移说明。

# Citations

- `project-brief/project-brief.md` §24
- `/architecture.md`
- `/decisions/adr-001-package-name-solivagus.md`
