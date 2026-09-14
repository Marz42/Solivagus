---
type: paradigma-known-issue
title: Production soak blocked until concurrency and CI gates are green
description: Cross-partition asyncio gate reuse, CI dependency install, calibration races, ungated bisect, and inspect-data manifests blocked production soak on 2026-09-14.
tags: [known-issue, concurrency, ci, calibration, inspect-data, solivagus]
timestamp: 2026-09-14T16:45:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: evolving
  update_policy: agent-editable
  epistemic_status: confirmed
  retrieval_hints:
    zh:
      - 生产浸泡
      - 事件循环
      - 校准竞态
      - CI pydantic
      - inspect-data
    en:
      - production soak
      - event loop
      - calibration race
      - CI pydantic
      - inspect-data
  symbols:
    - ConcurrencyGate
    - ThreadSafeGate
    - run_translate_stage
    - record_calibration_sample
    - inspect-data
  relations:
    related_to:
      - /decisions/adr-002-brief-gap-remediation.md
      - /architecture.md
      - /domains/document-pipeline.md
    informed_by:
      - /conventions.md
---

# Symptom

`main`（审查基线 `7fbf46d`）不适合进入生产浸泡：跨 Partition 复用 `asyncio.Condition` 闸门会在第二分区抛出 `RuntimeError`（不同 event loop），并可能被吞成英文 fallback；CI 用 `pip install --no-deps .` 缺少 pydantic 等依赖；校准文件并发写丢失样本；二分重试绕过 NestedGates；`inspect-data` 不是按 Partition 的真实请求清单且 `--sample 0` 崩溃。

# Impact

文档可能静默回退英文；CI 不能覆盖主链路；费用/规划幂等与真实校准状态脱节；限流时重试放大。

# Root Cause

1. 每个 Partition 单独 `asyncio.run()`，但 document/global gate 在循环外创建。
2. CI 只装 `requirements.txt`（PyYAML）再 `--no-deps` 安装包。
3. 校准 read-merge-write 无锁，临时文件名固定。
4. 失败路径直接调用 `_kv_translate_unit_async` 且不重新 acquire gates。
5. `inspect-data` 用整文档前 20 Unit 构造 prefix，且在空 samples 上索引。

# Workaround

在修复合入前：不要关闭 ADR-002；不要跑真实批目录 soak；本地检查改用 `pip install ".[dev]"`。

# Permanent Fix

- 单文档单事件循环调度全部 Partition；Batch Supervisor 持有 `ThreadSafeGate` 作为批级 global gate。
- CI / README 安装 `.[dev]`；`pyproject` 从 `VERSION` 动态读版本。
- `record_calibration_sample` 文件锁 + 按 model/language/tokenizer 分桶；plan **结构**幂等键为 config+source.md（校准指纹仅写入报告，不触发 replace_units）。
- 强制重规划时按 `source_hash` 保留 DONE/FALLBACK 译文。
- 全量已完成文档/分区跳过 warm-up；warm-up/probe 进入 `NestedGates`。
- 二分左右半重新进入 `NestedGates`。
- `inspect-data` 按 Partition 推进胶囊并输出请求 manifest，支持 `--include-content`，`--sample 0` 合法。

# Related Documents

- `/decisions/adr-002-brief-gap-remediation.md`
- `/architecture.md`
- `README.md`

# Status

open — 幂等/跳过 warm-up/闸门/inspect 胶囊推演已补强；真实批目录 soak 前仍保持 open。
