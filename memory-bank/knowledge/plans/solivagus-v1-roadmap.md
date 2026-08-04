---
type: paradigma-plan
title: Solivagus v1 Roadmap
description: Phased roadmap from MVP freeze through unattended batch production for Solivagus.
tags: [plan, roadmap, solivagus, v1]
timestamp: 2026-08-04T09:45:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: evolving
  update_policy: agent-editable
  epistemic_status: decision
  retrieval_hints:
    zh:
      - 路线图
      - Phase
      - MVP 冻结
      - 实施顺序
    en:
      - roadmap
      - phases
      - MVP freeze
      - implementation order
  symbols:
    - Phase 0
    - Phase 1
    - Phase 8
    - solivagus
  relations:
    informed_by:
      - /project-brief.md
      - /architecture.md
      - /decisions/adr-001-package-name-solivagus.md
    related_to:
      - /domains/document-pipeline.md
---

# Goal

将已验证的单脚本 MVP 重构为可恢复、可观测、缓存与并发感知的 Solivagus v1 CLI（命令 `solivagus`），达到夜间无人值守批处理生产可用。

# Scope

**包含：** Phase 0–8。

**不包含（首版）：** Web UI、SaaS、RAG/Agent、多 GPU、自托管 LLM、多供应商默认路径、原版式翻译 PDF。

# Approach

```text
冻结 MVP 与测试样本
 → 项目骨架 + SQLite（uv + Python 3.11/3.12）
 → 无人值守 OCR checkpoint
 → 结构树 + Token Planner
 → OAI-compatible Provider（DeepSeek flash）+ usage
 → 分区缓存 warm-up/probe
 → 8→16→32 并发（评估 64）
 → 风格胶囊
 → 机械 QA
 → HTML 表格翻译 / 批量生产化（D:\PDFS）
```

业务代码：`src/solivagus/`。依赖钉选：`requirements-gpu.txt`。样例仅本机 `example/`。

默认生产锚点：

```yaml
model: deepseek-v4-flash
thinking: disabled
ocr_batch_pages: 8
unit_target_tokens: 12000
unit_max_tokens: 24000
first_partition_tokens: 96000
partition_target_tokens: 220000
partition_max_tokens: 300000
global_concurrency: 16
per_document_concurrency: 8
max_global_concurrency: 64
target_mode: repeat
cache_probe_min_ratio: 0.70
fallback_to_source: true
batch_default_dir: "D:\\PDFS"
```

# Tasks

## Phase 0 — 冻结 MVP 基线

- [x] 归档 `project-brief/pdf_translate_cli_v0_2.py` → `legacy/pdf_translate_cli_v0_2.py`
- [x] 以本机 `example/` 建立 characterization 清单（不入库）：
  - `Attention Is All You Need.pdf`（+ 可选 html/md 对照；有段落/公式/表格，无双栏）
  - `Aerial Attack Study Boyd.pdf`（较差扫描）
  - `Vox Latina ...pdf`（尚可扫描）
  - `Qwen3_TTS.pdf` + `Qwen3_TTS.translation/`（已跑通基线）
- [x] 记录复现命令与期望产物路径（`manuals/solivagus-mvp-baseline.md`）
- [x] 建立基线测试骨架：`tests/characterization/test_mvp_baseline.py`（表格 passthrough、占位符、分块、回退、组装；本机 F4 产物断言）
- [x] 验收：无 GPU 测试通过；F4 SHA-256 与 `state.json` 对齐
- [ ] （可选）本机对 F1 `--ocr-only` / F2·F3 OCR 质量抽查笔记

## Phase 1 — 项目骨架和 SQLite

- [x] 确认包名/CLI 名 = `solivagus`（ADR-001）
- [x] 用 uv/pip 创建业务包 `src/solivagus/` + Typer CLI + 配置加载 + `.env.example` / `config.example.yaml`
- [x] SQLite schema（`.solivagus/state.db`）+ artifact 约定
- [x] 迁入 MVP 通用函数（protect/split/assemble/provider）；`solivagus import-mvp` 导入旧 `*.translation/`
- [x] 验收：`solivagus status` / `inspect` / `run --stage translate` 基于 SQLite（OCR 阶段留 Phase 2）

## Phase 2 — 无人值守 OCR

- [x] OCR 独立子进程、预检、页面批次 checkpoint、失败拆分、锁、防睡眠、夜间报告
- [x] 验收：单元测试覆盖强杀后续跑（done.json skip）、坏批次拆分、单页失败带警告继续
- [x] 本机 GPU：`solivagus run "example\Attention Is All You Need.pdf" --stage ocr --device gpu:0 --prevent-sleep` → `ocr_complete`（见 `manuals/solivagus-phase2-ocr-gpu.md`）
- [ ] （可选）F2/F3 OCR 质量抽查笔记

## Phase 3 — 结构树和 Token Planner

- [x] 结构解析、Unit/Partition、`plan` 与成本预估
- [x] 验收：幂等规划；不拆开公式/代码/表（单测）
- [x] 用正式规划替换 Phase 2 OCR 后的字符分块种子 units
- [x] CLI：`solivagus plan` / `run --stage plan|all` + `--force-plan`

## Phase 4 — Provider 与 KV Cache

- [x] OAI-compatible Provider；默认仅 `deepseek-v4-flash`；thinking disabled；warm-up/probe/本地缓存
- [x] 验收：cache hit 可观测（`translation_attempts` + `usage-report.json`）；低命中降级；缓存损坏不致失败
- [x] 分区路径：`pipeline/partition_runner.py` + `pipeline/warmup.py`；无 partition 时回退 legacy flat

## Phase 5 — 异步并发

- [x] Semaphore（global / per-document / per-partition）、warm-up barrier、自适应 429 降速、单 writer
- [x] 验收：并发吞吐量高于串行（单测 wall-time）；无 SQLite 写冲突（DbWriter 锁）；组装顺序按 sequence_index
- [x] Probe 决策驱动区内并发：full→`per_partition`、low→`low_probe`、degraded→1

## Phase 6 — 风格胶囊

- [x] 分区边界冻结 capsule；跨区术语/样例/边界上下文传递
- [x] 第一分区 seed → provisional → 重建前缀并 re-warmup
- [x] 本地缓存键包含 `style_capsule_hash`；单元记录 `style_capsule_version`
- [x] 产物：`style_capsules/vN.json` + SQLite `style_capsules`

## Phase 7 — QA 与专用结构处理

- [ ] 机械 QA、定向修复、表格翻译器、参考文献模式

## Phase 8 — 批量生产化

- [ ] 双队列、`D:\PDFS` 批处理、manifest、配置档案、Task Scheduler 说明
- [ ] 验收：整夜无人值守；早上一份报告

# Status

**in-progress**

Phase 0–6 完成。下一会话：**Phase 7**（机械 QA 与专用结构处理）。