---
type: paradigma-manual
title: Solivagus Phase 2 GPU OCR Verification
description: Local GPU acceptance notes for solivagus run --stage ocr on fixture F1.
tags: [manual, ocr, gpu, phase-2, solivagus]
timestamp: 2026-09-15T17:51:25+08:00
paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: evolving
  update_policy: agent-editable
  epistemic_status: confirmed
  retrieval_hints:
    zh:
      - GPU OCR
      - Phase 2 验收
      - Attention Is All You Need
      - prevent-sleep
    en:
      - GPU OCR
      - Phase 2 acceptance
      - Attention Is All You Need
      - prevent-sleep
  symbols:
    - solivagus run --stage ocr
    - Attention_Is_All_You_Need.solivagus
    - gpu:0
    - normalize_for_pandoc
  relations:
    informed_by:
      - /plans/solivagus-v1-roadmap.md
      - /manuals/solivagus-mvp-baseline.md
    related_to:
      - /contracts/workspace-artifact-contract.md
      - /architecture.md
---

# Purpose

记录 Phase 2 本机 GPU OCR 实跑验收（fixture F1），供后续续跑与质量抽查对照。产物在本机 `example/`，不入库。

# Preconditions

- 已激活含 PaddleOCR-VL 的 `.venv`（见 README 环境安装）
- 本机存在 `example/Attention Is All You Need.pdf`（SHA-256 见 MVP baseline manual）
- 工作区可写：仓库根 `.solivagus/state.db` 与 PDF 旁 `*.solivagus/` artifact

# Steps

## 1. 已验证命令（2026-08-03）

```powershell
.\.venv\Scripts\Activate.ps1
solivagus run "example\Attention Is All You Need.pdf" `
  --stage ocr `
  --device gpu:0 `
  --prevent-sleep
```

## 2. 期望产物

| Path | Expectation |
|------|-------------|
| `example/Attention_Is_All_You_Need.solivagus/` | 文档 artifact（stem 经 sanitize） |
| `…/preflight.json` | 页数与预检摘要 |
| `…/ocr/batch-0001/`、`batch-0002/` | 各含 `done.json`、`source.md`、`result.json` |
| `…/source.md` | 合并后的全文 OCR Markdown（经 `normalize_for_pandoc`：Pandoc Image + 紧凑 `$math$`） |
| `…/units/uNNNNN.source.md` | Phase 2 临时字符分块种子（Phase 3 将由结构规划替换） |
| `.solivagus/state.db` | `documents.status = ocr_complete` |

## 3. 本机观测摘要（F1）

| Field | Value |
|-------|-------|
| `source_sha256` | `bdfaa68d8984f0dc02beaca527b76f207d99b666d31d1da728ee0728182df697` |
| status | `ocr_complete` |
| OCR batches | 2（均 `done.json` 存在） |
| `source.md` | ~62 KB / ~435 lines |
| provisional units | 6（`translation_status` 仍为空；待 Phase 3/4） |

抽查：`solivagus status "example\Attention Is All You Need.pdf"` 应显示 `status: ocr_complete` 与上述 artifact 路径。

# Verification

- [x] F1 GPU OCR 完成且 `ocr_complete`
- [x] 批次 checkpoint（`done.json`）齐全
- [x] 合并 `source.md` 生成
- [x] `tests/unit/test_pandoc_compat.py`：HTML img → Pandoc Image、inline math 去空格、Pandoc AST、XeLaTeX 一步 PDF
- [ ] F2/F3 质量抽查（差扫描 / 尚可扫描）仍可选
- [ ] 人工对照 F1 的 HTML/MD 参考做结构质量笔记（Phase 3 前可选）

# Rollback

本机 GPU 验收记录；无需回滚代码。若误删 artifact，用同一命令重跑 OCR（已完成批次凭 `done.json` 跳过）；配置签名变化时加 `--force-ocr`。

# Troubleshooting

| Symptom | Likely Cause | Action |
|---------|--------------|--------|
| `No module named paddle` / OCR import 失败 | 仅装了 `.[dev]`，未带 GPU 栈 | 按 README 从 Paddle 官方索引安装 `paddlepaddle-gpu`，再装 `paddleocr` |
| `paddlepaddle-gpu` 在 PyPI 找不到 | 公共 PyPI 无 3.3.0 GPU 包 | 使用 `https://www.paddlepaddle.org.cn/packages/stable/cu129/`（或本机 CUDA 对应索引） |
| 强杀后续跑重做已完成批 | `done.json` 丢失或 config hash 变化 | 保留 `ocr/batch-*/done.json`；配置变更需 `--force-ocr` |
| Windows 睡眠打断长 OCR | 未开防睡眠 | 加 `--prevent-sleep` |

# Citations

- `/plans/solivagus-v1-roadmap.md`
- `/manuals/solivagus-mvp-baseline.md`
- `/contracts/cli-contract.md`
- `src/solivagus/ocr/`
