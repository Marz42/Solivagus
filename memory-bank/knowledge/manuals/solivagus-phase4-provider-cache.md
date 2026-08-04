---
type: paradigma-manual
title: Solivagus Phase 4 Provider and KV Cache
description: Warm-up, probe thresholds, local cache, and usage reporting for partition translation.
tags: [manual, provider, cache, phase-4, solivagus]
timestamp: 2026-08-04T09:15:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: evolving
  update_policy: agent-editable
  epistemic_status: confirmed
  retrieval_hints:
    zh:
      - Phase 4
      - warm-up
      - probe
      - 本地缓存
      - usage-report
    en:
      - Phase 4
      - warm-up
      - probe
      - local cache
      - usage report
  symbols:
    - partition_runner
    - usage-report.json
    - target_mode
    - prompt_cache_hit_tokens
  relations:
    informed_by:
      - /plans/solivagus-v1-roadmap.md
      - /architecture.md
    related_to:
      - /manuals/solivagus-phase2-ocr-gpu.md
      - /contracts/workspace-artifact-contract.md
---

# Purpose

记录 Phase 4 分区翻译的 warm-up / probe / 本地缓存行为，供 Phase 5 并发改造对照。

# Preconditions

- 文档已 `ocr_complete` 且已 `solivagus plan`（存在 `cache_partitions` + `units`）
- `.env` 含 `LLM_API_KEY`（真实 API）；单测使用注入的 `chat_fn`

# Steps

## 1. 行为摘要

| Step | Behavior |
|------|----------|
| Warm-up | 发送稳定 system+user 前缀；保存**实际** assistant 文本 |
| Probe | 首个真实 Unit 的 `prompt_cache_hit_tokens / expected_cache_tokens` |
| ≥ 0.70 | `full`（Phase 4 串行；Phase 5 开满区内并发） |
| 0.50–0.70 | `low`（警告；Phase 5 低并发） |
| < 0.50 | 再探测一次；仍低则 `degraded` 普通单轮，不失败文档 |
| Local cache | `.solivagus/cache/translations/{ab}/{hash}.json`；损坏忽略 |
| Usage | `translation_attempts` + artifact `usage-report.json` |

生产默认 `target_mode=repeat`；`user_id = pdf_` + `source_sha256[:20]`。

## 2. 命令

```powershell
solivagus plan "example\Attention Is All You Need.pdf"
solivagus run "example\Attention Is All You Need.pdf" --stage translate
```

# Verification

- [x] 单测覆盖 probe 阈值、warm-up 使用真实 assistant、本地缓存命中、损坏缓存回退、degraded 仍完成
- [x] 模块：`pipeline/partition_runner.py`、`pipeline/warmup.py`、`cache/local.py`、`providers/prompts.py`

# Rollback

关闭本地缓存：配置 `enable_local_translation_cache=false`。无 partition 的文档仍走 legacy flat 路径。

# Troubleshooting

| Symptom | Likely Cause | Action |
|---------|--------------|--------|
| 无 `usage-report.json` | 走了 legacy flat（无 partitions） | 先 `solivagus plan` |
| 全部 degraded | API 未返回 cache hit 字段 | 检查 provider usage；可继续翻译 |

# Citations

- `/plans/solivagus-v1-roadmap.md`
- `src/solivagus/pipeline/partition_runner.py`
- `tests/unit/test_solivagus_provider_phase4.py`
