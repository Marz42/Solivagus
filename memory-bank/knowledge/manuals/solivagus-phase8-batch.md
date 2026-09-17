---
type: paradigma-manual
title: Solivagus Phase 8 Batch and Task Scheduler
description: Configurable batch directory, dual queues, profiles, and Windows Task Scheduler setup for overnight runs.
tags: [manual, batch, phase8, task-scheduler, solivagus]
timestamp: 2026-09-17T10:39:03+08:00
paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: evolving
  update_policy: agent-editable
  epistemic_status: confirmed
  retrieval_hints:
    zh:
      - 批处理
      - 夜间无人值守
      - Task Scheduler
      - 配置档案
    en:
      - batch
      - overnight
      - Task Scheduler
      - profiles
  symbols:
    - solivagus batch
    - solivagus retry
    - SOLIVAGUS_BATCH_DIR
    - conservative
    - balanced
    - throughput
  relations:
    informed_by:
      - /plans/solivagus-v1-roadmap.md
      - /architecture.md
    related_to:
      - /contracts/cli-contract.md
      - /contracts/workspace-artifact-contract.md
---

# Purpose

说明 Phase 8 批量生产：可配置 PDF 目录（无硬编码默认）、OCR/翻译双队列、配置档案，以及 Windows 任务计划程序夜间运行。

# Preconditions

- 已安装 Solivagus 与可用 `.env`（`LLM_API_KEY`）
- 显式指定批目录：CLI 参数、`SOLIVAGUS_BATCH_DIR` 或配置 `batch_dir`（**不要依赖 `D:\PDFS`**）
- OCR 设备按需设置（如 `SOLIVAGUS_OCR_DEVICE=gpu:0`）

# Steps

1. 配置批目录与档案：

```powershell
$env:SOLIVAGUS_BATCH_DIR = "E:\papers\inbox"
solivagus batch --profile balanced --prevent-sleep --continue-on-error
# 或：solivagus batch "E:\papers\inbox" --profile throughput --recursive
```

2. 次日查看报告：

```powershell
solivagus report
# 产物：.solivagus/reports/nightly-*.md、batch-manifest-latest.json、global-usage-latest.json
```

3. 重试失败文档：

```powershell
solivagus retry --all-failed --profile conservative
```

4. （可选）Windows Task Scheduler：程序 `powershell.exe`，参数指向 `scripts/night-batch.ps1`（先编辑其中的 `$BatchDir`）。

# Profiles

| Profile | 含义 |
|---------|------|
| `conservative` | 低并发；OCR/翻译各 1 worker |
| `balanced` | 默认；OCR 1 + 翻译 2 |
| `throughput` | 更高全局并发；OCR 1 + 翻译 4 |

OCR 保持单 worker；翻译队列 FIFO，与 OCR 并行（先完成 OCR 的文档先翻译）。

# Soak (two phases)

> 2026-09-16/17 四本预跑：**有价值，未通过 SOAK**。阻断项为 SQLite 写入冲突（调查中，勿仅加 timeout）。暂不扩大文档规模。详见 `logs/progress/2026-09-16-soak-prerun-4books.md`。

## Phase 1 — controlled pre-run

1. 独立 inbox + `soak-workspace/prerun`；固定提交 / 供应商 / 配置。
2. `scripts/soak-prerun.ps1` 或等价 batch；失败后用**同一命令**重跑验证自动恢复。
3. `scripts/soak_verify.py` 门禁（修订口径）：
   - 成功终态（`qa_complete` / translation complete*）：无 `pending`、无 `running`；
   - 明确 `failed`（可恢复）：允许 `pending`；**禁止**无执行者的 `running`；
   - 不得把未完成文档标成成功（如残留 `translation_running`）；
   - 完成 Partition：capsule DB↔JSON payload 一致；
   - 成功文档具备译文 / 双语 /（qa 时）qa-report；
   - 完成态再跑：`provider-requests.jsonl` 增量必须为 0（不以 attempts 单独定论）。
4. 表格 QA HIGH：抽样解释真实改写 vs 误报；`keep` 下不靠放宽门禁过关。

## Phase 2 — ≥12h unattended

仅当：DB 锁复现并修复、四本固定配置恢复+零请求重跑通过、表格 HIGH 解释完毕。然后 `night-batch.ps1` / Task Scheduler；次日 report + verify + `pd check` / 测试 / catalog·runtime verify。

# Verification

- `solivagus batch <dir>` 在未设置目录时失败并提示配置方式
- 单文档失败时其他文档继续（`--continue-on-error`）
- `.solivagus/reports/` 出现 nightly / manifest / global-usage
- 单元测试：`tests/unit/test_solivagus_batch_phase8.py`
- Soak：`scripts/soak-prerun.ps1` + `scripts/soak_verify.py`

# Rollback

- 停止任务计划中的夜间任务
- 删除或忽略失败文档的 artifact；成功 checkpoint 默认保留
- `solivagus retry` 仅重跑失败项，不强制 `--force-ocr` 除非另指定单文档 force 流程

# Troubleshooting

| Symptom | Check |
|---------|--------|
| `batch directory not set` | 传目录参数或设置 `SOLIVAGUS_BATCH_DIR` |
| `lock held by live pid` | 另一 `solivagus` 仍在跑；结束后或清理陈旧 `.solivagus/supervisor.lock` |
| 全部 OCR 失败 | GPU / Paddle 安装与 `SOLIVAGUS_OCR_DEVICE` |
| usage 汇总为空 | 翻译未完成或缺少 `usage-report.json` |

# Citations

- `project-brief/project-brief.md` §24 / §26 / Phase 8
- `/plans/solivagus-v1-roadmap.md`
- `/contracts/cli-contract.md`
