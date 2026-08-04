---
type: paradigma-manual
title: Solivagus MVP Baseline Characterization
description: Phase 0 fixture inventory, reproduce commands, and acceptance checks for the frozen MVP translator.
tags: [manual, mvp, characterization, phase-0, solivagus]
timestamp: 2026-08-03T17:30:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: cold
  lifecycle: evolving
  update_policy: agent-editable
  epistemic_status: confirmed
  retrieval_hints:
    zh:
      - MVP 基线
      - characterization
      - example 样例
      - 复现命令
    en:
      - MVP baseline
      - characterization
      - example fixtures
      - reproduce commands
  symbols:
    - legacy/pdf_translate_cli_v0_2.py
    - example/Qwen3_TTS.pdf
    - Qwen3_TTS.translation
  relations:
    informed_by:
      - /plans/solivagus-v1-roadmap.md
      - /project-brief.md
    related_to:
      - /architecture.md
      - /contracts/workspace-artifact-contract.md
---

# Purpose

冻结单脚本 MVP 行为，供后续重构对照。样例 PDF 与译文产物仅存在于本机 `example/`（gitignore），不进入 git。

# Preconditions

- 仓库根目录存在 `legacy/pdf_translate_cli_v0_2.py`
- 本机存在 `example/` 样例（见下表）
- GPU/OCR 环境可按 `requirements-gpu.txt` 复现（完整 OCR 重跑非 CI 默认）
- `.env` 已配置 `LLM_API_KEY`（仅翻译阶段需要）

# Steps

## 1. Fixture inventory（本机路径）

| ID | Local path | Role | SHA-256 (at Phase 0 freeze) | Notes |
|----|------------|------|-----------------------------|-------|
| F1 | `example/Attention Is All You Need.pdf` | 结构样例 | `bdfaa68d8984f0dc02beaca527b76f207d99b666d31d1da728ee0728182df697` | 段落/公式/表格；无双栏；另有 `.html` / `.md` 对照 |
| F2 | `example/Aerial Attack Study Boyd.pdf` | 差扫描 | `293e04114f4a721e11c911c14f68033b0584700e52f5c6966741c20ebb696136` | OCR 压力 |
| F3 | `example/Vox Latina  A Guide to the Pronunciation of Classical Latin (William Sidney Allen) (Z-Library).pdf` | 尚可扫描 | `b7c858b8d70727c633bb5466d8a315e1827b43fb7e276627ded77c11c12adf3b` | OCR 对照 |
| F4 | `example/Qwen3_TTS.pdf` | 已跑通基线 | `b818867cf8f190185eae83238bde3adfc0c47c1864e587efdc59ee8ab5c7d0cb` | 配套 `example/Qwen3_TTS.translation/` |

## 2. 已跑通产物期望（F4）

目录：`example/Qwen3_TTS.translation/`

```text
source.md
translated.zh.md
translated.bilingual.md
state.json          # completed=true；chunks[*].status=done
assets/
chunks/
parsed/
```

`state.json` 中 `source_pdf_sha256` 必须等于上表 F4。

## 3. 复现命令（Windows / PowerShell）

OCR only（任意样例）：

```powershell
python legacy/pdf_translate_cli_v0_2.py "example\Attention Is All You Need.pdf" `
  --env-file ".env" `
  --ocr-only
```

续跑 / 翻译（复用工作目录）：

```powershell
python legacy/pdf_translate_cli_v0_2.py "example\Qwen3_TTS.pdf" `
  --env-file ".env" `
  --work-dir "example\Qwen3_TTS.translation"
```

夜间批处理目录由 `SOLIVAGUS_BATCH_DIR` / 配置 / CLI 指定（无硬编码默认；`project-brief/nightauto.ps1` 仅为历史本机示例）。Phase 0 不要求改脚本路径。

## 4. 自动化骨架

运行不依赖 GPU 的 characterization：

```powershell
python -m unittest tests.characterization.test_mvp_baseline -v
```

覆盖：HTML 表格整表 passthrough（不产生海量占位符）、占位符保护/恢复、分块不拆表、英文回退组装、以及（若本机存在）F4 产物结构断言。

# Verification

- [x] MVP 脚本已归档到 `legacy/pdf_translate_cli_v0_2.py`
- [x] Fixture 清单与 SHA-256 已记录
- [x] F4 复现命令与产物路径已记录
- [x] `tests/characterization/test_mvp_baseline.py` 可在无 GPU 下通过
- [x] 正式 CLI 对 F1 执行 GPU OCR（`solivagus run --stage ocr`，见 `manuals/solivagus-phase2-ocr-gpu.md`）
- [ ] （可选本地）对照 F1 HTML/MD 做 OCR 质量人工抽查笔记
- [ ] （可选本地）对 F2/F3 记录 OCR 质量笔记

# Rollback

若误改 `legacy/pdf_translate_cli_v0_2.py`，从 git 恢复该文件；不要用未冻结的热修覆盖归档副本。

# Troubleshooting

| Symptom | Likely Cause | Action |
|---------|--------------|--------|
| unittest 跳过 F4 断言 | `example/` 不存在或被清空 | 恢复本机样例；测试仍应通过纯函数用例 |
| 续跑报 PDF hash 不匹配 | PDF 被替换或路径指向不同文件 | 核对 SHA-256；或换 `--work-dir` / `--force-ocr` |
| OCR import 失败 | GPU 栈未装或 `paddlepaddle-gpu` 装错索引 | 按 README / `known-issues/paddlepaddle-gpu-not-on-pypi.md` 分步安装；CI 不跑真实 OCR |

# Citations

- `legacy/pdf_translate_cli_v0_2.py`
- `legacy/README.md`
- `project-brief/PDF翻译使用速查.md`
- `/plans/solivagus-v1-roadmap.md`
- `tests/characterization/test_mvp_baseline.py`
