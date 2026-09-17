# 2026-09-16/17 — Soak pre-run（4 本）规模与问题记录

> **判定（2026-09-17 评审）：预跑有价值，但不能算 SOAK 通过。** 1,425 页 / ≈9.7h 已暴露真实并发问题；下一步集中 SQLite 写入冲突，**暂时不要扩大文档规模**。  
> Workspace：`soak-workspace/prerun` · Inbox：`soak-inbox/prerun` · Profile：`conservative` · 开跑 HEAD≈`dd3469a`。  
> 供应商账单字段于 2026-09-17T09:27:37+08:00 由用户从 DeepSeek 控制台补入；口径问题见下。

## 墙钟用时

| 项 | 值 |
|----|-----|
| 开始（UTC+8） | 2026-09-16 17:44 |
| 结束（UTC+8） | 2026-09-17 03:26 |
| **墙钟总时长** | **≈ 9h 43m** |
| Provider JSONL 跨度 | ≈ 4.1h（预跑阶段；不含后续 PsychofIntel 续跑） |
| 预跑脚本退出码 | 1（未全绿） |

## 规模汇总

| 指标 | 合计 |
|------|------|
| 文档数 | 4 |
| **PDF 页数** | **1 425** |
| OCR 英文词（约） | ≈ 574k |
| 中文汉字（预跑完成的 3 本） | ≈ 547k |

## 请求计数三套口径（尚未闭合）

| 来源 | 数值 | 备注 |
|------|------|------|
| 本机 `global-usage` / 文档 usage-report 汇总 | **340** api_calls | 文档级 totals；PsychofIntel 预跑无 usage |
| DeepSeek 控制台（用户抄录） | **550** 请求 | 同窗口/类型是否对齐未核 |
| `provider-requests.jsonl`（预跑结束时） | **596** 行 | 含 warm-up/probe/repair 等入口；与上两者窗口可能不同 |

**账单字段算术不一致（需再核抄录或字段定义）：**

```text
命中缓存 56,689,600 + 输出 1,124,429 = 57,814,029
> 标注总 Tokens 57,589,399
```

¥7.91 保留为控制台观察值，**暂不宜**推算完整四本单位成本。对齐要求：同一时间窗、同一供应商、同一请求类型（含/不含 warm-up·probe·repair）。

## 分文档（预跑结束时）

| 文档 | 页数 | 预跑终态（脚本结束） | 备注 |
|------|------|----------------------|------|
| OSTEP | 708 | `qa_complete` | 再跑续完 |
| Packet Analysis | 372 | `qa_complete` | 再跑续完 |
| PsychofIntelNew | 214 | 曾 `translation_running` | 后单文档+Opencode GO 续至 `qa_complete`（非原配置自动恢复证明） |
| Cookbook Vol.1 | 131 | `qa_complete` | 首轮即完成 |

## 本机环境

| 项 | 值 |
|----|-----|
| CPU / RAM / GPU | i5-14400F · 32GB · **RTX 4060 8GB** |
| OCR | `gpu:0` · Paddle 3.3.0 / PaddleOCR 3.6.0 |
| 预跑模型 | DeepSeek `deepseek-flash` |
| PsychofIntel 续跑 | Opencode GO `deepseek-v4.1-flash`（配置/供应商已变） |

## 问题清单（评审修订）

### P0 — `database is locked`（正式 SOAK 阻断）

| 已确认 | 并发 batch 中出现锁错误；留下不准确运行态（如 `translation_running` + pending） |
| 未确认 | 谁持锁、哪段事务过长、OCR 子进程是否直接写库 |
| 假设（待验证） | Windows 默认 busy 等待不足——**不可**仅加 timeout 后关单 |
| 下一轮 | 小规模多文档并发复现 → 定位报错 SQL / 事务起止 / 进程线程 / 持锁时长 → 再选写入串行化；并修失败态落库（勿把未完成标成成功） |
| 记录 | `/known-issues/batch-sqlite-database-locked.md` |

### 恢复能力

| 已有证据 | PsychofIntel 进度可复用，单文档续跑能完成 |
| 不能证明 | 原 batch 命令、原供应商、原配置下「失败 → 重跑 → 完成」 |
| 下一轮 | **固定提交 / 供应商 / 配置 / workspace**：失败 → 原命令重跑 → 完成；再单独做完成态零请求幂等 |

### P1 — 表格 QA HIGH

| 契约 | `html_table_mode=keep` ⇒ 表格应原样保留 |
| 不宜 | 用放宽门禁「消掉」HIGH |
| 应查 | 表格为何仍进入可改写路径；protect/占位符恢复是否完整 |
| 若产品要译单元格 | 显式 `translate_cells`，并验证结构/数字/公式/链接 |
| 说明 | `qa_complete` ≠ 质量通过；现有 HIGH 先抽样确认真实改写 vs 误报 |

### P1 — Opencode GO 403（已缓解）

自定义 `User-Agent` + `x-opencode-session`；非 DeepSeek 官方域名不发 `thinking`。与 DB 锁分列。

### 验收口径修正（2026-09-17）

- **明确失败 / 等待恢复**的文档：允许残留 `pending` Units。
- **禁止**无执行者的 `running`；**禁止**把未完成文档标成成功。
- 「成功终态文档不得有 pending」；「所有终态都不得有 pending」过严，已改 `scripts/soak_verify.py`。

## 建议下一轮（仅三步；暂不扩规模）

1. 小规模多文档并发：稳定复现并修复 DB 锁 + 失败状态落库。
2. 同一批四本、固定配置：验证中断恢复 + 完成态零请求重跑。
3. 表格 HIGH 全部解释清楚后，再进入夜间正式 SOAK。

## 产物指针

- Reports：`soak-workspace/prerun/.solivagus/reports/`
- Verify / provider log：`…/soak/`、`…/provider-requests.jsonl`
- Known-issue：`memory-bank/knowledge/known-issues/batch-sqlite-database-locked.md`
