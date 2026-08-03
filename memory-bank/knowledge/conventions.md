---
type: paradigma-convention
title: Coding and Collaboration Conventions
description: Coding, naming, testing, documentation, versioning, and prohibited patterns for Solivagus.
tags: [conventions, solivagus]
timestamp: 2026-08-03T17:20:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: hot
  lifecycle: stable
  update_policy: requires-human-confirmation
  epistemic_status: confirmed
  retrieval_hints:
    zh:
      - 编码约定
      - 命名
      - 测试
      - uv
      - 禁止模式
    en:
      - coding conventions
      - naming
      - testing
      - uv
      - prohibited patterns
  symbols:
    - ruff
    - pytest
    - uv
    - characterization
  relations:
    informed_by:
      - /project-brief.md
      - /architecture.md
      - /decisions/adr-001-package-name-solivagus.md
    constrains:
      - /contracts/repository-contract.md
---

# Naming

- 产品名、包名、CLI 入口统一为 `solivagus`（ADR-001）。
- 业务代码位于 `src/solivagus/`；工作区状态根为 `.solivagus/`。
- 模块使用清晰领域名：`ocr`、`structure`、`planning`、`providers`、`translation`、`qa`、`assembly`。
- 文档身份优先 `source_sha256`，不要仅用可变文件路径。
- Artifact / checkpoint 文件使用稳定、可排序 ID（如 `batch-0001`、`p001-u007`）。
- Memory-Bank 文档保持 OKF frontmatter；业务运行日志不要写入 `memory-bank/knowledge/`。
- 设计草案中的 `pdf2zh` 仅作历史别名，新代码与文档不得再将其作为目标名。

# Code Style

- Python 3.11+（推荐 3.12）；用 **uv** 管理虚拟环境与依赖同步。
- GPU/OCR 运行依赖以 `requirements-gpu.txt` 为已验证钉选清单（非一键安装）；`paddlepaddle-gpu` 须从 Paddle 官方索引安装。业务包元数据在 `pyproject.toml`。
- ruff 格式化 + lint；类型提示覆盖公共 API；mypy 逐步收紧。
- 异步 IO 用于翻译调度；OCR 保持子进程边界。
- 配置用 YAML profile + `.env` 密钥；价格与模型名可配置，不写死进逻辑。
- 状态文件原子写入；SQLite 使用 WAL + 短事务 + 单 writer 或明确串行化。
- 翻译请求必须 `thinking: disabled`；稳定缓存前缀不得包含时间戳、随机 ID、动态重试文案。

# Error Handling

- 区分不可重试（4xx 配置/权限/余额）与可重试（429/5xx/网络/`insufficient_system_resource`）。
- 内容级失败（截断、缺 Unit 标记、空译文、结构破坏）不得标为成功。
- Unit 持续失败：二分 → 可选升级模型修复（若启用）→ 英文回退并继续。当前生产仅 `deepseek-v4-flash`。
- 批次/文档级失败记录告警，默认 `continue_on_error` 不阻断整批。
- CLI 错误应可定位到 document / batch / unit。

# Testing Conventions

- Characterization 优先：以本机 `example/` 样例为输入（不入库）；`Qwen3_TTS` 为已跑通基线。
- 单测覆盖规划幂等、节点保护、usage 解析、`finish_reason` 门禁。
- 集成/e2e：OCR-only 后续跑、中断续跑、单页失败带警告完成、并发无写冲突。
- HTTP 使用 respx（或同等）模拟；不在 CI 默认调用真实付费 API。
- 真实 GPU/OCR 测试标记为可选/本地 job。

# Documentation Conventions

- 长期决策进 `knowledge/decisions/` ADR；中期路线进 `knowledge/plans/`；当前执行进 Coding Task。
- `project-brief/` 保留设计与 MVP 源材料；权威摘要以 `memory-bank/knowledge/` 为准。
- `example/` 仅本机样例与产物，不提交、不作为仓库权威文档。

# Prohibited Patterns

- 提交 `.env`、API Key、`example/` 下 PDF/HTML/译文、原始付费 API 响应当作默认夹具。
- 为提高 KV Cache 命中率而省略尾部目标原文（生产禁止默认 `id_only`）。
- 固定字符数粗暴切分导致拆开表格/公式/代码。
- 在 `src/paradigma` 中实现 PDF 业务逻辑，或把业务状态写入 Paradigma runtime 代替 `.solivagus/`。
- 首版引入 Web UI、任务队列中间件、多 GPU 调度，或把非 DeepSeek 后端设为默认生产路径。
- 静默把截断输出当作成功译文。
