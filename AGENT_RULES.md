# Paradigma Agent Operation Protocol (IDE-Agnostic Source of Truth)

> 本文件是 IDE 无关的规范原文。IDE 适配器只能压缩或映射本协议，不得复制状态机或改变命令语义。

---

# 1. Memory 与事实源边界

- `memory-bank/runtime/`：短生命周期 Coding runtime。Task、Session、Checkpoint YAML 是事实；Markdown handoff/active-task 和 Context Manifest 是可重建投影。
- `memory-bank/logs/`：append-first 人类审计日志，不是运行状态恢复的必读来源。
- `memory-bank/knowledge/`：OKF-compatible 长期知识。
- `docs/rfc/`：OKF-compatible 提案与 RFC。
- `memory-bank-template/`：衍生项目的空白模板源。

Knowledge/RFC 中除 `index.md` / `log.md` 外的 concept 文档必须有 YAML frontmatter、非空 `type`、title/description/tags/timestamp，并将 Paradigma 扩展放入 `paradigma:`。生产规则以 schema 和 `pd check` 为准。

HOT/WARM/COLD 是 retrieval metadata，不是要求 Agent固定扫描目录。HOT 是 mandatory Context 候选；WARM/COLD 由 Context Builder 按显式信号和 relations 选择。前端/UI 任务应把项目根 `DESIGN.md` 作为显式 path signal（若存在）。

---

# 2. CLI 权威与禁止事项

确定性运行操作必须通过 `pd`：

```text
pd task start/status/block/unblock/suspend/resume/complete/abort
pd session start/status/checkpoint/end
pd handoff build
pd context build/verify
pd runtime rebuild/verify
pd catalog rebuild/verify
pd index rebuild/verify
pd check
```

纪律：

1. mutation 先运行默认 dry-run；检查结构化结果后才加 `--write`。
2. 不直接编辑 Task/Session/Checkpoint/pointer YAML。
3. 不直接编辑 generated `active-task.md`、`handoff.md`、`context-manifest.yaml`、子目录 index block 或 `.paradigma/cache/`。
4. Checkpoint append-only；不要覆盖或删除既有 Checkpoint 来“修正”历史。
5. YAML runtime 仓库不使用 legacy `pd-archive-task.py` 维护 Task 生命周期。
6. 工具拒绝状态迁移、scope、source hash、catalog 或 projection 时，先处理诊断，不绕过工具写文件。

长期知识、ADR、contract、known issue 和必要的人类 progress/changelog 仍是 Markdown authoring；它们不是可由 CLI 推导的运行状态。

---

# 3. 最小四阶段工作流

## 3.1 Bootstrap / Read

1. 运行 `pd task status`，从 YAML 恢复当前 Task。
2. 没有 active Task 且需要开发时，先 dry-run `pd task start ...`；确认 identity/scope/goal 后用 `--write`。
3. 运行 `pd session status`；需要新工作会话时 dry-run 后执行 `pd session start --session-id ... --write`。
4. 将用户意图规划为显式 `path`、`symbol`、`keyword` 和 budget，运行：

   ```bash
   pd context build --intent "..." --task-id TASK-... \
     --path ... --symbol ... --keyword ... --budget 12000 --write
   pd context verify
   ```

5. 按 `memory-bank/runtime/context-manifest.yaml` 读取 selected documents 及 reasons；不要用递归扫描全部 knowledge/progress logs 代替 Context Builder。
6. 仅在历史审计、故障调查或用户明确要求时读取 progress logs；从 `handoff.md` + latest Checkpoint 恢复最近会话。

Query planning 可以使用 Agent 推理；retrieval execution 和选择理由以 `pd context` 为准。

## 3.2 Plan

- 写代码前用简短语言说明目标、边界、验证方法和风险。
- 修改 API、数据库、CLI、目录协议、schema 或跨模块边界前，检查 Manifest 中相关 contract/ADR；信号不足时重建 Context，而不是猜测。
- `update_policy: requires-human-confirmation` 的长期知识变更必须先取得用户授权。
- 新架构决策写 ADR；稳定外部语义写 contract。不要把计划 checklist 写进 generated runtime projection。

## 3.3 Execution

- 只改任务范围内文件，保留用户未授权的既有改动。
- 长期事实写 knowledge，运行事实交给 Task/Session/Checkpoint CLI，过程叙述可写 logs。
- 被外部条件阻塞时用 `pd task block --reason ... --write`；主动暂停用 `pd task suspend --reason ... --write`，恢复使用对应 CLI。
- 在可恢复边界运行 `pd session checkpoint --checkpoint-id ... --input narrative.yaml --write`。需要 test/build evidence 时显式提供 command；dry-run 不执行这些命令。
- API/schema/contract/known issue 发生变化时及时更新相应 knowledge，而不是等到会话结束凭记忆补写。

## 3.4 Update / Handoff

结束一次实质工作前：

1. 更新受影响的 knowledge/ADR/contract/known issue/changelog；写 timestamp 前从系统获取当前时间。
2. concept metadata 变化后运行 `pd index rebuild`，随后 `pd index verify`。
3. 运行与变更范围匹配的测试，再运行 `pd check`；Coding runtime 另运行 `pd runtime verify`，Memory 变更另运行 `pd catalog verify`。
4. knowledge/runtime source 变化后重新 `pd context build ... --write` 并运行 `pd context verify`。
5. 用 `pd session checkpoint` 保存最终 Git/test/build facts 和 summary/completed/remaining/blockers/next steps。
6. 运行 `pd session end --write`。如果仅需修复投影，运行 `pd handoff build` 或重复相同 lifecycle command。
7. 工作完成后运行 `pd task complete --write`；未完成则保持 active，或明确 block/suspend。Terminal Task 必须在 Session end 后执行。
8. progress session log 是版本/Batch/人工审计交付物，不是每次对话的强制状态文件；创建时 append-first，不覆盖历史。
9. 告知用户：完成内容、验证结果、Task/Session 状态、Memory-Bank/知识变更和仍存在的风险。

---

# 4. 质量与安全

- 不确定时读取 Manifest 命中的 canonical 文档；signals 不足时扩充 Request 并重建。
- 不凭文件名、旧 progress 或模型记忆推断 contract。
- 不将 Coding Task/Session/Checkpoint/Context 语义放进 Memory Kernel。
- 不使用 wall clock 影响相同 ContextRequest 的 retrieval；有效期由工具绑定 Task snapshot。
- generated drift 通过 verify/rebuild 修复，不反向导入事实源。
- 版本或 Harness 可疑时运行 `pd diagnose --upstream <path>`。
- 修改前检查工作树；不得把无关用户改动混入提交。

---

# 5. IDE 适配器同步

- Cursor：`.cursor/rules/memory-bank-protocol.mdc`，`alwaysApply: true`。
- Codex / Antigravity / 其他：映射本协议的事实源边界、CLI 操作和最小四阶段纪律。

维护顺序：先改本文件，再同步 IDE adapter、README、INIT_PROMPT 和 template-facing 文档。首期协议仍人工维护，不自动生成。
