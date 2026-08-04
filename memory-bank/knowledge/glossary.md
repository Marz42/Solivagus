---
type: paradigma-glossary
title: Project Glossary
description: Glossary of Solivagus project-specific terms and abbreviations.
tags: [glossary, terminology, solivagus]
timestamp: 2026-08-03T17:20:00+08:00
paradigma:
  schema_version: "0.1"
  temperature: cold
  lifecycle: evolving
  update_policy: agent-editable
  epistemic_status: confirmed
  retrieval_hints:
    zh:
      - 术语表
      - Translation Unit
      - Cache Partition
      - 风格胶囊
    en:
      - glossary
      - translation unit
      - cache partition
      - style capsule
  symbols:
    - Translation Unit
    - Cache Partition
    - Style Capsule
    - Batch Supervisor
    - solivagus
  relations:
    related_to:
      - /architecture.md
      - /project-brief.md
      - /decisions/adr-001-package-name-solivagus.md
---

# Terms

| Term | Meaning | Notes |
|------|---------|-------|
| Solivagus / solivagus | 产品名、Python 包名与 CLI 入口 | ADR-001 已冻结 |
| Translation Unit | 一次翻译请求的最小成功/失败单元 | 结构感知切分，非固定字符块 |
| Cache Partition | 多个连续 Unit 共享的稳定 KV Cache 前缀范围 | 分区间串行，区内并发 |
| Style Capsule | 分区边界冻结的术语、文风样例与边界上下文 | 分区内不可变 |
| Batch Supervisor | 批处理总控：队列、锁、恢复、夜间报告 | 批目录可配置，无固定机器路径 |
| OCR Worker | 单文档 OCR 子进程 | 退出以回收 CUDA/Paddle 资源 |
| Characterization fixture | 冻结 MVP 行为的输入/输出样本 | 本机 `example/`，不入库 |
| Memory-Bank | Paradigma 三态外部记忆 | 开发用，非 PDF 运行时状态 |
| Paradigma / `pd` | Agent Memory harness 与 CLI | 模板保留 |
| pdf2zh | 设计草案历史别名 | 不再作为实现目标名 |

# Abbreviations

| Abbreviation | Meaning |
|--------------|---------|
| OCR | Optical Character Recognition / 版面理解提取 |
| KV Cache | DeepSeek 提示缓存；以 hit/miss Token 计量 |
| QA | 翻译后机械检查与定向修复 |
| CLI | Command-Line Interface |
| OAI | OpenAI-compatible API 形状 |
| WAL | SQLite Write-Ahead Logging |
| OKF | Open Knowledge Format |
| ADR | Architecture Decision Record |
| MVP | Minimum Viable Product（单脚本基线） |
| uv | Python 包/环境管理工具 |

# Domain-specific Meanings

| Term | Solivagus meaning |
|------|-------------------|
| checkpoint | 某处理阶段可恢复的完成标记，不是 Git commit |
| warm-up | 发送分区稳定前缀以构建远端 KV Cache，再放行并发 Unit |
| probe | 用实测 `prompt_cache_hit_tokens` 判断是否达到并发门槛 |
| fallback | Unit 失败时保留英文原文并继续文档 |
| bilingual | 中文正文 + 可折叠英文原文的 Markdown 输出 |
| target_mode=repeat | 生产默认：公共分区上下文后再附目标 Unit 原文副本 |
| `.solivagus/` | 正式工作区状态与缓存根目录 |
