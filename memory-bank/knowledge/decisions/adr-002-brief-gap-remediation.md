---
type: paradigma-decision
title: ADR-002 Post-Phase-8 brief gap remediation priority
description: Prioritized remediation of gaps between project-brief and implementation after Phase 8.
tags: [decision, gap, remediation, solivagus]
timestamp: 2026-08-04T10:25:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: warm
  lifecycle: evolving
  update_policy: agent-editable
  epistemic_status: decision
  retrieval_hints:
    zh:
      - 差距修复
      - 优先级
      - footnote
      - tokenizer
    en:
      - gap remediation
      - priority
      - footnote
      - tokenizer
  symbols:
    - ADR-002
    - P0
    - P1
    - P2
  relations:
    informed_by:
      - /project-brief.md
      - /plans/solivagus-v1-roadmap.md
    related_to:
      - /architecture.md
      - /decisions/adr-001-package-name-solivagus.md
---

# Context

Phase 0–8 主链路落地后，对照 `project-brief/project-brief.md` 自检发现若干差距。需要冻结修复优先级，避免平均用力或误扩 `references_mode` 等暂缓项。

# Decision

按用户确认的优先级消化差距：

| 差距 | 动作 | 优先级 |
|------|------|--------|
| footnote/aside 默认策略 | 修复；脚注与 aside **拆开**处理 | P0 |
| YAML / `--config` | 必须补齐为唯一可复现配置入口 | P0 |
| 真实 Tokenizer | 应补齐 | P0/P1 |
| Unit 二分重试 | 必须补齐（坏 Unit 不直接退英文） | P0/P1 |
| `manifest.json` 稳定输出 | 立即修复（低成本） | P1 |
| 输出比例滚动校准 | 建议补齐 | P1 |
| `inspect-data` | 最小版本 | P1/P2 |
| 自适应并发精细策略 | 部分：硬上限 + Retry-After；p95 延期 | P2 |
| `references_mode` 扩展 | **暂缓**；保持 `keep`，收缩承诺 | 暂缓 |

生产默认：OCR 保留 footnote/aside（丢弃需显式开关）；配置以 YAML/`--config` + `.env` 密钥为准。

# Consequences

- OCR 默认 ignore 列表不再含 footnote/aside；提供独立 `--drop-footnotes` / `--drop-aside-text`。
- CLI 增加 `--config`；`config.example.yaml` 成为可加载档案。
- TokenCounter 优先 exact tokenizer，近似为回退。
- 翻译失败路径：重试 → Unit 二分 → 英文回退。
- `references_mode` 不再承诺 translate_titles/all。

# Alternatives Considered

1. **一次性修齐全部差距**：拒绝；范围过大，打乱无人值守稳定性。
2. **先扩 references_mode**：拒绝；`keep` 最稳，用户明确暂缓。
3. **脚注与 aside 共用一个 drop 开关**：拒绝；用户要求拆开处理。

# Status

Accepted — 2026-08-04（表内功能已落地）

**生产就绪门禁（2026-09-14）**：对照 soak 前审查，`main` 上曾存在跨 Partition 事件循环锁复用、CI `--no-deps` 依赖缺失、校准竞态、二分绕过闸门、`inspect-data` 清单不准等问题。修复进行中；**在门禁测试与 CI 转绿之前，不建议关闭本 ADR 或进入生产浸泡。** p95 延迟门禁仍延期。

# Related Documents

- `/project-brief.md`
- `/architecture.md`
- `/plans/solivagus-v1-roadmap.md`
- `/decisions/adr-001-package-name-solivagus.md`
- `/known-issues/production-gate-concurrency-ci.md`
- `project-brief/project-brief.md` §9.5 / §11 / §19.2 / §25 / §28
