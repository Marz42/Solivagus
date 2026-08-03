---
type: paradigma-known-issue
title: paddlepaddle-gpu 3.3.0 is not installable from public PyPI
description: requirements-gpu.txt is a freeze snapshot; GPU Paddle must be installed from the Paddle package index.
tags: [known-issue, gpu, paddle, install, solivagus]
timestamp: 2026-08-03T21:20:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: evolving
  update_policy: agent-editable
  epistemic_status: confirmed
  retrieval_hints:
    zh:
      - paddlepaddle-gpu
      - PyPI
      - 安装失败
      - requirements-gpu
    en:
      - paddlepaddle-gpu
      - PyPI
      - install failure
      - requirements-gpu
  symbols:
    - paddlepaddle-gpu==3.3.0
    - requirements-gpu.txt
  relations:
    related_to:
      - /architecture.md
      - /manuals/solivagus-phase2-ocr-gpu.md
    informed_by:
      - /conventions.md
---

# Symptom

`uv pip install -r requirements-gpu.txt`（或对公共 PyPI 直接装 `paddlepaddle-gpu==3.3.0`）失败：包在公共索引不可用或仅有过时 CPU/旧 GPU 构建。

# Impact

无法用「单条 freeze 文件」一键复现 GPU OCR 环境；新机器或空 venv 需要分步安装。

# Root Cause

`paddlepaddle-gpu==3.3.0` 由飞桨官方索引分发，不在公共 PyPI 提供同版本 GPU 轮子。`requirements-gpu.txt` 是本机 `pip freeze` 式钉选，混有需官方索引的包。

# Workaround

1. 创建/复用 venv（已验证可复制既有 `.venv`，Python 3.11+）
2. 从 Paddle 官方索引安装 GPU 轮子，例如 cu129：

```powershell
uv pip install paddlepaddle-gpu==3.3.0 `
  --python .\.venv\Scripts\python.exe `
  -i https://www.paddlepaddle.org.cn/packages/stable/cu129/
```

3. 再安装 OCR 与业务包（勿覆盖已装好的 paddle）：

```powershell
uv pip install "paddleocr[doc-parser]>=3.6.0,<3.7" --python .\.venv\Scripts\python.exe
uv pip install -e ".[dev]" --python .\.venv\Scripts\python.exe
```

`requirements-gpu.txt` 仍作为**已跑通钉选清单**保留，不是一键安装器。

# Permanent Fix

保持分步安装文档；可选后续增加 `scripts/bootstrap-gpu.ps1` 封装索引 URL，但不把私有索引写入默认 `pyproject` 依赖。

# Related Documents

- `/architecture.md`
- `/manuals/solivagus-phase2-ocr-gpu.md`
- `README.md`（快速开始）
- `requirements-gpu.txt`

# Status

open — 文档与 README 已标明；未计划把私有索引写入默认 `pyproject` 依赖。
