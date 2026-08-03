---
type: paradigma-session-log
title: v0.7.0 Release Preparation
description: Release-candidate summary for Phase 3 Coding integration, migration compatibility, artifact smoke, and release gates.
tags: [session, release, v0.7.0, phase3, coding, migration, validation]
timestamp: 2026-07-26T15:38:51+08:00
paradigma:
  layer: log
  lifecycle: append-only
  okf_export: optional
  update_policy: append-only
---

# Session Summary

## User Goal

在 Phase 3 全部门槛通过后准备 v0.7.0 发布候选，修正误执行 `git add .` 带来的暂存问题，并最终提交到干净工作区。

## Actions Taken

- 将根 `VERSION`、config `installed_distribution_version`、README 和仓库行为基线统一升级到 0.7.0。
- 将 Phase 3 Unreleased 内容冻结为 `[0.7.0] - 2026-07-26`，保留新的空 Unreleased 区域。
- 保持 config 0.4、OKF 0.1、document 0.2、Memory document 0.1、catalog 0.1 与 Coding runtime/context 0.1 独立不变。
- 新增 v0.6.0 → v0.7.0 Coding runtime 迁移说明：保留 canonical Memory/knowledge/logs，以 `pd runtime init` 建立 YAML pointers/projections，并通过 CLI 映射旧 active-task。
- 评估 v0.7.0 compatibility wrapper 删除条件：文档和 CI 已以 `pd` 为主，但真实衍生项目不再依赖旧入口的证据缺失，因此继续保留 deprecated adapters。
- wheel smoke 首轮发现 text CLI 在 failure outcome 上读取 success payload，导致稳定状态冲突被 `KeyError`/`IndexError` 掩盖；修复为失败优先渲染 diagnostics，并增加回归测试。
- `.gitignore` 新增 `.tmp/`，防止本地 wheel、target 和 smoke workspace 再被 `git add .` 误暂存；已从 Git 索引移除 2183 个临时文件。

## Artifact Verification

- wheel：`paradigma-0.7.0-py3-none-any.whl`，SHA-256 `94cbaaa7bdd8787a51d8e21a0de00192821acc26cc9c04754c4531ade77930f5`。
- isolated target import：distribution 0.7.0，模块来自隔离 target，PyYAML 6.0.3 来自独立临时 dependency target。
- Memory smoke：candidate → active revision 2 → query/explain → tombstoned revision 3；普通 query 最终返回 0，catalog verify current。
- Coding smoke：runtime init、Task start、Session start、Context build/verify、Checkpoint、Session end、Task complete、final Context/runtime verify 全部通过。
- Conflict smoke：第二个 Task start 使用 text 输出返回 exit 3 与 `PD_TASK_ALREADY_ACTIVE`，无 traceback。

## Repository Verification

- 完整测试：191 项通过。
- `pd check` 与 legacy `pd-check-all.py --keep-going`：六项门限全部通过。
- index、catalog、Coding runtime：verify 全部 current；self-diagnose gaps=0。
- Windows 隔离运行时补充修正 UTF-8 子进程测试：测试仍令源码路径优先，但不再覆盖调用方已有 dependency path。

## Runtime Closure

- Checkpoint：`CHECKPOINT-20260726-V070`。
- Session：`SESSION-20260724-V070` 已结束。
- Task：`TASK-20260724-V070` 已完成。
- 最终 Context checksum：`sha256:2f3860315f6ab8ea4fc68b120a4788b1c62709b65c177e8a7b153c9eb7d6ee70`，verify current。

## Release Assessment

- Phase 3 的 Task、Session、Checkpoint、Context Builder 与 Agent protocol 已形成可安装、可迁移、可恢复的 v0.7.0 候选。
- 本批只准备发布候选并提交，不创建 tag、不 push；远端 Windows/POSIX CI 仍是发布前外部门限。
- 下一步在发布提交后进入 Phase 4 Batch 4.1 Research Domain Model。
