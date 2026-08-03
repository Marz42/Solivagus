---
type: paradigma-session-log
title: Phase 0 Index Boundaries
description: Session summary for separating human navigation, local indexes, and the machine index cache.
tags: [session, phase-0, index, navigation, cache]
timestamp: 2026-07-23T21:42:14+08:00
paradigma:
  layer: log
  lifecycle: append-only
  okf_export: optional
  update_policy: append-only
---

# Session Summary

## User Goal

继续正式开发计划 Phase 0 Batch 0.4：调整索引边界，分离人工导航与机器完整索引。

## Actions Taken

- 新增共享 `_index.py` 和 `pd-index.py rebuild/verify/inventory`，统一派生索引的收集、渲染、校验和原子写入。
- 根 `index.md` 改为人工维护的高层导航，不再递归展开全部 concept 文档。
- 子目录 `index.md` 只生成该目录的直接文档，嵌套目录各自维护局部索引。
- 完整递归机器索引迁移到 ignored `.paradigma/cache/knowledge-index.json`，使用确定性 JSON、source digest 和原子 replace，可随时从 canonical Markdown 重建。
- 保留 `pd-sync-index.py --write/--check` 作为 v0.5.x 兼容包装器，并将 `pd-check-all.py` 切换到新 verify 入口。
- CI 先执行 rebuild，再通过 tracked Markdown diff 检测过期局部索引；机器 cache 不进入版本控制。
- `.paradigma/config.yaml` 升级到 config schema 0.3，并声明受限于 `.paradigma/cache/` 的 `machine_index_path`。
- 增加根导航规模不随 concept 数线性增长、局部索引非递归、损坏 cache 不影响 canonical knowledge、cache 可重建和旧入口兼容测试。
- 同步 README、协议、RFC、架构、约定、契约、tooling、manual、ADR-007 和 changelog。

## Validation

- `python -m unittest discover -s tests -p "test_*.py" -v`: 36/36 passed。
- `python -m py_compile`: 全部工具和测试通过。
- `pd-index.py rebuild`: 26 concepts，重复执行 `updated_markdown=0`。
- `pd-index.py verify`: stale=0。
- `pd-check-all.py --keep-going`: 6/6 passed。
- `pd-diagnose.py --project . --upstream . --json`: 0 gaps。
- `git diff --check`: passed。

## Decisions

- 根索引属于人工导航，局部索引属于 tracked 派生路由，机器完整索引属于 ignored cache；三者不再混用。
- 机器 cache 的损坏或删除不会改变 canonical knowledge，只会使 verify 失败，rebuild 后恢复。
- 配置中的机器索引路径必须位于 `.paradigma/cache/`，避免把 rebuild 变成任意路径写入入口。
- 旧 `pd-sync-index.py` 在 v0.5.x 兼容窗口内保留，但新协议和质量门禁统一使用 `pd-index.py`。

## Follow-ups

- Batch 0.5：补齐 lint、links、index、hot-size、archive、compact、diagnose、version 和 check-all 的 Characterization Tests。
- 满足 Phase 0 退出门槛后准备 v0.5.1 发布。
