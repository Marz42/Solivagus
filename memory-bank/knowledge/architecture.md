---
type: paradigma-architecture
title: System Architecture
description: Top-level architecture, technology stack, module boundaries, and key constraints for Solivagus.
tags: [architecture, system, solivagus]
timestamp: 2026-08-03T17:20:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: hot
  lifecycle: evolving
  update_policy: requires-human-confirmation
  epistemic_status: confirmed
  retrieval_hints:
    zh:
      - 系统架构
      - 双流水线
      - OCR
      - 翻译并发
      - SQLite
      - uv
    en:
      - system architecture
      - dual pipeline
      - OCR worker
      - translation concurrency
      - SQLite state
      - uv
  symbols:
    - Batch Supervisor
    - OCR Worker
    - Translation Manager
    - DeepSeek Provider
    - Token and Plan Engine
    - Style Capsule
    - solivagus
  relations:
    informed_by:
      - /project-brief.md
      - /decisions/adr-001-package-name-solivagus.md
    constrains:
      - /contracts/repository-contract.md
      - /contracts/cli-contract.md
      - /contracts/workspace-artifact-contract.md
    informs:
      - /plans/solivagus-v1-roadmap.md
      - /domains/document-pipeline.md
---

# Overview

Solivagus 是本地 CLI 文档处理系统，不是 Web 服务。运行时由 **Batch Supervisor** 协调两条可重叠流水线：

1. **OCR Queue**：本地 GPU 上的 PaddleOCR-VL（独立子进程，单文档加载/释放）
2. **Translation Queue**：OpenAI-compatible API 异步并发翻译（当前仅 DeepSeek `deepseek-v4-flash`）

状态以工作区级 SQLite 为权威事实源；每文档 artifact 目录保存 OCR/单元/分区/输出文件。Paradigma Memory-Bank 仅服务开发 Agent 记忆，不参与 PDF 处理运行时。

推荐目标目录：

```text
src/solivagus/       # 业务应用（Phase 1+）
src/paradigma/       # Memory harness（`pd` 入口保留）
project-brief/       # MVP 与设计源材料（可提交）
example/             # 本地样例 PDF/产物（整目录 gitignore）
legacy/              # 冻结单脚本归档
requirements-gpu.txt # 已跑通 GPU/OCR 依赖钉选
tests/
```

安装：

```powershell
uv pip install -e ".[dev]" --python python3.12
# Windows example:
# uv pip install -e ".[dev]" --python "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
solivagus version
pd version
```

# Technology Stack

| Layer | Choice | Notes |
|-------|--------|-------|
| Language | Python **3.11 基线**，推荐 **3.12** | 开发机与夜间机一致；当前开发环境 3.12.9 |
| Packaging | **uv** | 创建/同步环境与锁定；与 Paradigma 的 pip 安装可并存 |
| CLI | Typer | 入口命令 `solivagus` |
| OCR | `paddleocr[doc-parser]` + `paddlepaddle-gpu` | 钉选见 `requirements-gpu.txt`（paddleocr 3.6.0 / paddlepaddle-gpu 3.3.0 等） |
| PDF preflight | PyMuPDF 或等价 | 首版不替代 OCR；MVP 侧有 pypdfium2 等，正式选型 Phase 1 确认 |
| HTTP | httpx.AsyncClient（或 openai SDK 客户端） | 长 timeout；OAI-compatible |
| State | SQLite WAL（aiosqlite 或同步封装） | 工作区 `.solivagus/state.db` |
| Config | pydantic-settings + YAML profile | API Key 仅 `.env` |
| LLM | OpenAI-compatible Chat Completions | **当前唯一模型 `deepseek-v4-flash`**；`thinking: disabled`；Key 不分流 |
| HTML | beautifulsoup4 | 表格节点处理 |
| Dev | pytest、pytest-asyncio、respx、ruff、mypy | |

首版不引入：SQLAlchemy、Celery、Redis、FastAPI、Docker Compose、消息队列。

# Module Boundaries

| Module | Responsibility | Must not |
|--------|----------------|----------|
| CLI (`cli.py`) | `run` / `batch` / `plan` / `status` / `retry` / `inspect` / `report` | 内嵌 OCR 模型生命周期 |
| Batch Supervisor | 队列、锁、恢复、夜间报告、防睡眠；默认批目录 `D:\PDFS` | 直接调用模型 HTTP |
| OCR Worker | 独立子进程；页面批次 checkpoint；失败降级 | 调用翻译 API |
| Structure Processor | Markdown 树、节点分类、HTML 表格独立节点 | Token 计费或 HTTP |
| Token & Plan Engine | Unit / Partition 规划、成本预估 | 发起翻译请求 |
| Provider (OAI-compatible) | 请求、usage、finish_reason、thinking 关闭、user_id | 业务调度策略 |
| Translation Manager | 分区串行、区内并发、warm-up barrier、自适应限流 | OCR |
| Style Capsule | 分区边界冻结术语/样例 | 分区内可变 |
| QA & Assembly | 机械检查、定向修复、中文/双语组装 | 重新 OCR |
| SQLite State Store | documents / batches / units / partitions / attempts | 存 API Key 或原 PDF 二进制 |

# Data Flow

```text
PDF
 → Preflight
 → OCR Worker (page batches → ocr/batch-NNNN/)
 → Structure Processor (structural_nodes)
 → Token & Plan Engine (translation_units + cache_partitions)
 → [optional] plan / cost estimate
 → per partition:
      stable prefix warm-up → probe
      → concurrent units (repeat target tail)
      → style capsule update for next partition
 → Assembly (zh + bilingual) + QA report + usage
```

双流水线重叠：GPU OCR 文档 B 的同时，API 可翻译文档 A。

内容寻址：相同原文 + 模型 + 提示词版本 + 术语表 + 翻译配置 → 相同本地缓存键；重复运行不得重复成功请求。

# Key Constraints

1. **结构优先**：切分顺序为 文档→章→节→小节→段→句；不得拆开代码围栏、块公式、HTML 表格、图片链接。
2. **阶段可恢复**：预检、OCR 批次、结构分析、规划、分区、翻译单元、组装、QA 均有 checkpoint。
3. **失败隔离**：批处理 > 文档 > OCR 批次 > 分区 > Unit > 节点；Unit 失败尽量英文回退并继续。
4. **缓存边界**：生产 `target_mode: repeat`；禁止为了命中率省略尾部目标原文。
5. **并发默认克制**：平台上限不是客户端默认值。
6. **安全**：PDF/图片留本地；只上传 OCR 文本；`user_id` 用文档哈希；`.env` 与 `example/` 不入库。
7. **Harness 边界**：`src/paradigma` 与 `memory-bank/` 服务开发记忆；业务运行时状态在 `.solivagus/` / artifact 中。

# Open Questions

- Characterization 夹具以本机 `example/` 为准（见 `manuals/solivagus-mvp-baseline.md`）；不入库。
- 正式 preflight 库最终选 PyMuPDF 还是沿用 MVP 的 pypdfium2？
- DeepSeek 价格 profile 的更新频率与告警阈值？
- 是否在 CLI 增加兼容短别名？（首版不做）

已关闭：包/CLI 名 → `solivagus`（ADR-001）；Python → 3.11 基线 / 推荐 3.12 + uv；模型 → OAI-compatible 抽象 + 仅 `deepseek-v4-flash`；批目录惯例 → `D:\PDFS`；样例不入库 → `example/`；MVP 归档 → `legacy/`。

# Citations

- `project-brief/project-brief.md`
- `project-brief/pdf_translate_cli_v0_2.py`
- `requirements-gpu.txt`
- `/project-brief.md`
- `/decisions/adr-001-package-name-solivagus.md`
- `/plans/solivagus-v1-roadmap.md`
