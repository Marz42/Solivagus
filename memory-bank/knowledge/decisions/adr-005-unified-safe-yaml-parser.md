---
type: paradigma-decision
title: ADR-005 Adopt a Unified Safe YAML Parser
description: Standardizes YAML and Markdown frontmatter parsing on PyYAML with duplicate-key rejection and structured diagnostics.
tags: [adr, yaml, frontmatter, diagnostics, tooling]
timestamp: 2026-07-23T00:04:40+08:00
paradigma:
  schema_version: "0.1"
  temperature: cold
  lifecycle: append-only
  update_policy: append-only
  epistemic_status: decision
  status: accepted
  retrieval_hints:
    zh:
      - 统一 YAML Parser
      - frontmatter 诊断
      - 重复键
      - PyYAML
    en:
      - unified YAML parser
      - frontmatter diagnostics
      - duplicate keys
      - PyYAML
  symbols:
    - _paradigma_yaml.py
    - ParseDiagnostic
    - ParseFailure
    - PyYAML
  relations:
    constrains:
      - /architecture.md
      - /contracts/repository-contract.md
      - /domains/tooling.md
    follows:
      - /decisions/adr-004-separate-version-dimensions.md
---

# Context

Paradigma 的 lint、link、index、HOT size、diagnose、version 和 progress compact 工具分别维护了简化 YAML/frontmatter 解析逻辑。这些实现会忽略无法识别的行、接受重复键，并把 YAML 语法、frontmatter 边界、Schema 和编码问题混为缺字段或空配置。

Phase 0 Batch 0.2 要求使用标准 YAML 库、删除重复解析逻辑，并提供可自动处理的错误分类。

# Decision

采用 PyYAML 6.x 作为唯一运行时第三方依赖，并由 `.paradigma/tools/_paradigma_yaml.py` 提供统一入口。

共享 parser 使用 `SafeLoader`，拒绝重复 mapping key，并将 YAML timestamp 保留为协议字符串。文件统一按 UTF-8（兼容 BOM）读取。解析失败通过 `ParseFailure` 携带 `ParseDiagnostic`，稳定区分 `ENCODING_ERROR`、`FILE_READ_ERROR`、`FRONTMATTER_MISSING`、`FRONTMATTER_UNCLOSED`、`YAML_SYNTAX_ERROR`、`YAML_DUPLICATE_KEY` 和 `YAML_ROOT_TYPE_ERROR`。

Schema 校验继续属于 `pd-lint-okf.py`，不得把 parser diagnostic 转换成缺失字段错误。`requirements.txt` 是依赖声明，CI 在运行测试和仓库检查前安装它。

# Consequences

- 所有 YAML/frontmatter 消费者共享相同的安全加载、编码和诊断语义。
- BOM、CRLF、中文和完整 YAML 语法由成熟库处理。
- 重复键和非法 YAML 变为确定性失败，不再静默覆盖或跳过。
- 衍生 workspace 在运行 Paradigma 工具前必须安装 `requirements.txt`。
- `_paradigma_yaml.py` 与依赖声明必须随工具链一起分发和升级。

# Alternatives Considered

1. 继续增强手写 subset parser：拒绝，因为 YAML 边界复杂，多个实现已经产生行为漂移。
2. 使用 `yaml.safe_load` 原样调用：拒绝，因为默认 mapping 构造会接受重复键，无法满足确定性治理要求。
3. 使用 ruamel.yaml：当前不采用；其 round-trip 能力适合编辑器，但 Phase 0 只需要安全读取，PyYAML 更小且足够。
4. 将 Schema 校验合并进 parser：拒绝，因为语法层和 Paradigma 文档规则应保持独立诊断。

# Status

Accepted for Phase 0 Batch 0.2.

# Related Documents

- `docs/devplan/paradigma_dev_5+.md`
- `memory-bank/knowledge/architecture.md`
- `memory-bank/knowledge/conventions.md`
- `memory-bank/knowledge/contracts/repository-contract.md`
- `memory-bank/knowledge/domains/tooling.md`
