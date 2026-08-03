---
type: paradigma-project-brief
title: Project Brief
description: Project vision, target users, scope, non-goals, and success criteria for Solivagus.
tags: [project, brief, scope, solivagus]
timestamp: 2026-08-03T17:20:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: hot
  lifecycle: stable
  update_policy: requires-human-confirmation
  epistemic_status: confirmed
  retrieval_hints:
    zh:
      - 项目愿景
      - 技术文献翻译
      - PDF 翻译 CLI
      - 无人值守
      - 范围边界
    en:
      - project vision
      - technical literature translation
      - PDF translation CLI
      - unattended batch
      - scope
  symbols:
    - Solivagus
    - PaddleOCR-VL
    - DeepSeek
    - solivagus
  relations:
    informs:
      - /architecture.md
      - /contracts/repository-contract.md
      - /plans/solivagus-v1-roadmap.md
    related_to:
      - /decisions/adr-001-package-name-solivagus.md
---

# Vision

Solivagus 是面向个人研究、技术阅读和批量文档处理的本地 PDF 技术文献智能翻译 CLI。

系统使用 **PaddleOCR-VL** 完成 PDF 版面理解与结构化提取，使用 **DeepSeek** OpenAI-compatible API 完成英文到简体中文的技术翻译，并输出适合 Obsidian / Markdown 阅读器与后续知识整理的中文及双语文档。

正式工程在已验证 MVP 核心链路上重构，不更换技术路线：

```text
PDF → PaddleOCR-VL → Markdown → 结构感知分块 → DeepSeek 翻译 → 中文/双语 Markdown
```

# Target Users

| User | Need | Frequency |
|------|------|-----------|
| 个人研究者 / 技术读者 | 可靠翻译论文、技术报告、教材级长文档 | Daily / Weekly |
| 批量处理用户 | 目录批处理、断点续跑、夜间无人值守（惯例目录 `D:\PDFS`） | Per overnight batch |
| 成本敏感用户 | 利用 DeepSeek KV Cache 控制长文档费用 | Per long document |

# Scope

## In scope (v1)

**输入**

- 本地 PDF 文件；包含 PDF 的本地目录；可选递归扫描。
- 文档类型：英文技术论文、技术报告、教材/专著、双栏论文、含图/公式/代码/表格的 PDF、普通扫描件。

**输出（每文档）**

```text
source.md
translated.zh.md
translated.bilingual.md
qa-report.md
usage-report.json
manifest.json
```

附属产物：`assets/`、`ocr/`、`units/`、`partitions/`、`logs/`。

**能力优先级**

1. 可靠处理论文 / 报告 / 书籍级长文档
2. 断点续跑与夜间无人值守
3. 批量目录处理（夜间惯例：`D:\PDFS`）
4. DeepSeek KV Cache 降本
5. API 并发缩短总时长
6. 保留标题、段落、公式、代码、图片、页码与引用结构
7. 单页 / 单翻译单元 / 单文档失败不阻塞整批
8. 保持 CLI 产品形态

**工程基线（MVP 已验证）**

- PaddleOCR-VL 可在 RTX 4060 运行；已跑通依赖钉在 `requirements-gpu.txt`（源自本机 `example/requirements.txt`）
- 普通技术 PDF 可完成 OCR 与结构化提取
- 翻译 Token 成本可接受；中断后可从翻译块续跑
- HTML 表格可整体保留；单文件 CLI 可满足基本个人使用
- 参考实现：`project-brief/pdf_translate_cli_v0_2.py`、`project-brief/nightauto.ps1`
- 已跑通样本（**本地 only，不入库**）：`example/Qwen3_TTS.pdf` + `example/Qwen3_TTS.translation/`

## Naming

| 角色 | 名称 | 说明 |
|------|------|------|
| 产品 / 仓库 / 包 / CLI | `solivagus` | 已冻结，见 ADR-001 |
| 工作区状态根 | `.solivagus/` | 正式布局 |
| Memory harness | Paradigma (`pd`) | 模板保留，与业务代码共存 |
| 设计草案别名 | `pdf2zh` | 仅历史文稿；不再作为实现名 |

# Non-goals

以下不进入首个正式版本：

- 按原版式重新生成翻译 PDF
- GUI / SaaS / 多用户 / 账户权限 / 移动端
- 向量数据库、RAG 问答、Agent 工作流
- 自动发布到 Obsidian
- 图片内部文字的完整翻译重绘
- 完整参考文献本地化
- 多 GPU 分布式调度
- 自托管大语言模型
- 复杂自动术语生成、整书一次输出、多供应商统一框架（首版不做）

# Success Criteria

| Criterion | Target |
|-----------|--------|
| 批处理可靠性 | 正常 PDF 批处理完成率 ≥ 98%；单 Unit / 单文档失败不停止批次 |
| 可恢复 | 进程被终止后可从最近成功 checkpoint 继续；重复运行不重复翻译已成功 Unit |
| OCR | 页面批次可续跑；损坏页可隔离；OCR 配置变化可检测 |
| DeepSeek 缓存 | 可观测 hit/miss；稳定前缀不被动态字段污染；缓存失败可降级；预热后前缀 Token 命中率目标 ≥ 70%（优化目标，非硬失败条件） |
| 并发 | 默认并发 16 稳定；可配置到 32/64；429 后自动降速；无请求风暴 |
| 翻译完整性 | 每个 Unit 有译文或明确英文回退；页码可追溯；代码/公式/图片路径不被破坏；`finish_reason != stop` 不入正式译文 |
| 可观测性 | Unit 级 usage、文档级成本与 QA 报告、批次夜间汇总 |

# Constraints

- 保持 CLI；不建设 Web UI / 服务端 / 多用户系统。
- 正式项目在 MVP 已验证链路上重构，不更换 PaddleOCR-VL + DeepSeek 路线。
- Python：**3.11 为基线**；开发机与夜间机一致；**推荐 3.12**（已验证 GPU `.venv` 为 3.11.15，机上亦有 3.12）。包管理使用 **uv**。
- LLM：保留 OpenAI-compatible Provider 抽象；**当前唯一生产模型 `deepseek-v4-flash`**；Key 不做日常/夜间区分。翻译请求必须显式 `thinking: disabled`。
- 平台并发上限 ≠ 客户端默认并发。初始建议：`global=16`、`per_document=8`、`per_partition=8`、`max_global=64`。
- 文档结构优先于固定字符切分；表格/公式/代码/图片为独立节点。
- 每个处理阶段必须有独立 checkpoint；重要中间产物内容寻址且幂等。
- KV Cache 优化不得损害翻译边界：公共分区上下文 + 请求尾部重复目标原文。
- API Key 仅存 `.env`（gitignore）；不向 API 上传原 PDF，只发送 OCR 后文本。
- 本地样例与大文件在 `example/`（gitignore 整目录）；详细设计源：`project-brief/project-brief.md`。
