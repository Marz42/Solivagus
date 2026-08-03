---
type: paradigma-domain
title: Document Processing Pipeline
description: Dual OCR/translation pipeline responsibilities and risks for Solivagus.
tags: [domain, pipeline, ocr, translation, solivagus]
timestamp: 2026-08-03T21:20:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: evolving
  update_policy: agent-editable
  epistemic_status: confirmed
  retrieval_hints:
    zh:
      - 文档流水线
      - OCR 批次
      - 翻译分区
      - 失败隔离
    en:
      - document pipeline
      - OCR batches
      - translation partitions
      - failure isolation
  symbols:
    - OCR Queue
    - Translation Queue
    - warm-up
    - style capsule
  relations:
    informed_by:
      - /architecture.md
      - /project-brief.md
    related_to:
      - /contracts/workspace-artifact-contract.md
      - /plans/solivagus-v1-roadmap.md
---

# Responsibility

定义从 PDF 到中文/双语 Markdown 的端到端流水线：预检、OCR 批次、结构树、Token/分区规划、DeepSeek 缓存感知翻译、风格胶囊、QA 与组装，以及批处理级失败隔离。

# Public Interfaces

- Supervisor 队列接口：提交文档、查询状态、重试失败、取消
- OCR Worker 进程协议：输入 PDF + OCR 配置签名 → 批次产物 / 缺页警告
- Planner：`structural_nodes` → `translation_units` + `cache_partitions` + 费用估计
- Provider：稳定前缀 warm-up、Unit 翻译、usage 回传
- Assembler：按 `sequence_index` 组装，不依赖完成顺序

# Internal Flow

1. Preflight 估计工作量与异常页
2. OCR 默认 8 页一批；失败则拆分直至单页，再记录缺页继续
3. 构建文档树；HTML 表格首版整表保留
4. 规划 Unit（目标约 12K Token，最大 24K）与 Partition（首包约 96K，后续约 220K，最大 300K）
5. 分区：warm-up → probe（≥70% 放行，50–70% 低并发，<50% 降级）→ 并发 Unit（`target_mode=repeat`）
6. 分区结束更新 style capsule，再进入下一分区
7. QA（结构/数字/引用/术语）→ 必要时定向修复一次 → 组装输出

# Dependencies

- PaddleOCR-VL / PaddlePaddle（本地 GPU；F1 实跑已验证）
- DeepSeek Chat Completions（网络）
- SQLite 工作区状态（`.solivagus/state.db`）
- pypdfium2 预检

# Related Contracts

- `/contracts/cli-contract.md`
- `/contracts/workspace-artifact-contract.md`
- `/contracts/repository-contract.md`

# Known Risks

| Risk | Mitigation |
|------|------------|
| KV Cache best-effort | warm-up、probe、自动降级 |
| 并发击穿缓存 / 风格漂移 | barrier 后放量；capsule 分区冻结 |
| 长输出截断 | finish_reason 门禁 + 自动拆分 |
| OCR 长文档崩溃 | 页面批次 checkpoint + 进程隔离 |
| SQLite 写冲突 | WAL、短事务、单 writer |
| HTML 表格被模型破坏 | 独立节点；首版原样保留 |
