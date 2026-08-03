# 变更日志

> 🌡️ WARM 知识 — 记录 Project Paradigma 模板库自身的版本发布历史。
>
> 格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)。

---

## [Unreleased]

### Fixed
- Windows CI 路径断言改为比较规范化路径身份，兼容 GitHub runner 将 `RUNNER~1` 8.3 短路径展开为 `runneradmin` 长路径的行为。

## [0.7.0] - 2026-07-26

### Added
- 新增收缩后的 CLI-driven Agent Operation Protocol、source/Cursor adapter minimal-operation golden parity test、ADR-021 和 Agent protocol contract。
- 新增 dry-run-first `pd runtime init`，只补充缺失 null pointers、重建 projections，并覆盖幂等及部分初始化恢复测试。
- 新增 `ContextRequest`/`ContextManifest`、OKF knowledge + canonical Memory 双源 deterministic Context Builder，以及 `pd context build/verify`。

- 新增 mandatory/path/symbol/keyword/scope-validity/one-hop/dedup/budget pipeline、stable reasons、source digest/checksum、golden/drift/failure tests、ADR-020 和 context contract。
- 新增 `pd session start/status/checkpoint/end` 与 `pd handoff build`，覆盖 Session lifecycle、append-only Checkpoint、active/last-session recovery 和 handoff projection。
- 新增 CLI Git/test/build evidence collector、工具事实/Agent narrative 分离、checkpoint attach/end 中断恢复、ADR-019 和 Session/Checkpoint contract。
- 新增 tool-enforced CodingTask lifecycle：pure transition table、`pd task start/status/block/unblock/suspend/resume/complete/abort`、默认 dry-run 和稳定非法迁移 diagnostics。
- 新增 start/terminal 多文件中断恢复、active-session terminal guard、YAML runtime legacy archive refusal、failure injection、ADR-018 和 lifecycle contract。
- 新增 versioned Coding YAML runtime：strict Task/Session snapshot codec、active pointers、source-hash CAS、managed lock 与 atomic replace。
- 新增 `pd runtime rebuild/verify`、active-task/handoff deterministic Markdown projections、projection drift CI gate、failure injection、ADR-017 和 runtime contract。
- 新增 Phase 3 Coding Domain Model：immutable RepositoryScope、CodingTask、CodingSession、CodingCheckpoint 以及 Git/Test/Build Evidence。
- 新增 Coding→MemoryScope 显式投影、task/session/evidence 严格不变量、Coding Integration architecture gate、ADR-016 和 domain contract。

### Changed
- `AGENT_RULES.md` 移除 Persona、固定 HOT/progress 扫描和手工 runtime checklist；README/INIT_PROMPT 改用 Task/Session status、Context Manifest、Checkpoint 与 CLI bootstrap。
- 发行版本、安装版本和用户文档统一升级到 0.7.0；config/OKF/document/Memory/catalog schema 保持独立且不变。

### Deprecated
- `.paradigma/tools/` compatibility adapters 在 v0.7.0 继续保留；文档和 CI 已迁移到 `pd`，但尚无真实衍生项目停止依赖旧入口的充分证据。

### Fixed
- text CLI 在 Task/Session 等命令失败时先渲染稳定 diagnostics，不再因缺少 success payload 二次抛出 `KeyError`/`IndexError`。

## [0.6.0] - 2026-07-24

### Added
- 新增 `pd memory query/explain` public adapter、完整 structured explanation projection、非 active/validity warnings 和 canonical-first catalog failure diagnostics。
- 新增 Phase 2 golden propose→commit→query→explain→revise→forget gate、Kernel domain-profile architecture gate、ADR-015 和 explain contract。
- 新增 canonical candidate 到 tombstone 的 Memory Mutation Lifecycle：pure Kernel transitions、source-hash CAS、严格 revision/provenance policy 与 catalog 自动刷新。
- 新增 `pd memory propose/validate/commit/revise/supersede/forget`、默认 dry-run、完整 lifecycle/query 集成测试、refresh failure recovery、ADR-014 和 mutation contract。
- 新增 deterministic catalog-backed Memory Query Application API，覆盖 ID/path/keyword/FTS/tag/scope/status/inclusive-validity 组合过滤和 outgoing relation 一跳扩展。
- 新增稳定 score/ID 排序、matched fields/reasons、stale/corrupt catalog refusal、query failure-injection tests、ADR-013 和 memory query contract。
- 新增 SQLite/FTS5 derived memory catalog schema 0.1 与 `pd catalog rebuild/verify/stats`；完整保存查询 projection、normalized tags/relations、source digest 和统计。
- 新增 atomic full-catalog publication、source/row/FTS drift verification、corruption/replace failure tests、ADR-012 和 catalog contract；CI 在 Windows/POSIX rebuild 后 verify。
- 新增 canonical Memory Markdown v0.1 codec/store：一个文档对应一个 MemoryRecord，支持 deterministic round trip、strict Schema、semantic content hash 和 exact-byte source hash。
- 新增 revision 1 原子创建、严格 `+1` compare-and-swap 更新、managed-writer lock，以及 create/replace failure-injection tests；ADR-011 和 memory document contract 固化行为。
- 新增存储无关且不可变的 Memory Kernel 值模型：MemoryRecord、MemoryScope、ProvenanceRef、MemoryRelation、MemoryStatus、MemoryQuery 和 MemoryResult。
- 新增 `MEM-` + ULID-compatible Crockford Base32 稳定 ID、领域不变量测试和 Kernel 外层依赖架构门禁，并以 ADR-010 固化契约。
- 新增 `pyproject.toml` 和 `src/paradigma/` package skeleton，提取 structured diagnostics/errors/results、config、safe parser、Schema validator 和 atomic writer。
- 新增 package unit、legacy parser equivalence、repository schema integration 和 architecture boundary tests；CI 安装本地 package 后再运行门禁。
- 新增可安装的 `pd` 统一 CLI，覆盖 version、config validate、check、diagnose、index rebuild/verify 和 task archive。
- 新增 adapter-neutral Application Service 与 `CommandOutcome`，统一 text/JSON、dry-run、diagnostics 和退出码契约。
- 新增旧/new CLI 等价测试、Unicode/space 路径集成测试和 Windows/POSIX CI matrix。

### Changed
- config schema 升级到 0.4，新增 `memory_root` 与 `catalog_path`；旧配置缺字段时回退到安全默认值。
- `.paradigma/tools/` 全部收敛为 package-backed 兼容适配器；parser、task state、index、validation、diagnosis、archive 和 progress compaction 不再保留脚本侧独立实现。

### Deprecated
- v0.5.x 继续接受 `.paradigma/tools/pd-*.py` 调用，但新文档和 CI 以安装后的 `pd` 为主入口。

### Fixed
- CLI adapter 显式将 stdout/stderr 配置为 UTF-8，避免 Windows CI 重定向输出使用 `cp1252` 时无法打印中文 progress metadata。

## [0.5.1] - 2026-07-23

### Added
- 新增 `pd-version.py` 和共享 `_version.py`，报告并校验 distribution、installed distribution、config schema、OKF 和 document schema 五个版本维度。
- 新增 ADR-004，记录分离版本模型及旧字段迁移政策。
- 新增 PyYAML 驱动的共享 `_paradigma_yaml.py`、结构化 parser diagnostics 和 ADR-005。
- 新增共享 `_task_state.py` 严格状态枚举、归档 mutation plan、稳定 `PD_TASK_*` / `PD_ARCHIVE_*` 错误码和 ADR-006。
- 新增 `pd-index.py rebuild/verify`、共享 `_index.py`、可重建机器 JSON cache 和 ADR-007。
- 新增覆盖九类公开工具成功、失败、兼容、原子写入和外部临时 Workspace 的 Characterization Tests。
- 新增可重复的 0.5.0 → 0.5.1 版本元数据迁移说明与临时 Workspace 验证。

### Changed
- `pd-check-all.py` 增加版本一致性门禁。
- `pd-diagnose.py` 以上游根 `VERSION` 作为发行版本真相源，并使用共享版本读取逻辑。
- `.paradigma/config.yaml` 升级到 `config_schema_version: "0.3"`，使用 `installed_distribution_version` 并声明 `machine_index_path`。
- 文档类型注册表使用明确的 `document_schema_version` 字段。
- lint、links、index、HOT size、diagnose、version 和 progress compact 统一使用共享 YAML/frontmatter parser；CI 显式安装 `requirements.txt`。
- `pd-archive-task.py` 默认 dry-run，使用 source hash、content-addressed archive ID、原子单文件写入和幂等恢复协议。
- 根 index 改为人工高层导航；子目录 generated block 改为非递归局部视图；全量递归元数据迁移到 ignored `.paradigma/cache/knowledge-index.json`。
- `pd-compact-progress.py --write` 改为原子替换；写入失败保留旧 summary 和全部 source logs，并返回 `PD_COMPACT_IO_ERROR`。

### Deprecated
- `pd-sync-index.py --write/--check` 保留为 v0.5.x 兼容入口，分别映射到 `pd-index.py rebuild/verify`。
- `paradigma_harness_version` 和 config 顶层含义模糊的 `schema_version` 仅保留为迁移输入。

### Fixed
- 非法 YAML、重复键、缺失/未闭合 frontmatter 与编码错误不再被静默忽略或误报为 Schema 缺字段。
- “未完成”等自然语言状态和已勾选 checklist 不再被误判为完成；成功归档后 active-task 明确重置为 `pending`。

## [0.5.0] - 2026-07-08

### Added
- **Phase checkpoints**：在 Plan Phase 和 Execution Phase 中新增 checkpoint 提醒，Agent 在每个阶段关键边界被提示检查是否需要更新 Memory-Bank 文档（ADRs、contracts、conventions、known-issues）。
- **DESIGN.md 集成**：新增 `paradigma-design-system` 类型，支持项目根目录 `DESIGN.md` 作为可选的前端视觉设计规范。Agent 在涉及前端/UI 任务时将其作为 WARM 参考。`pd-check-all.py` 新增第 5 步（DESIGN.md 基本格式校验，文件不存在时静默跳过）。
- **INIT_PROMPT 模式 G（设计器模式）**：通过问答形式引导用户创建符合 `google-labs-code/design.md` 规范的 DESIGN.md 文件。4 阶段流程：发现 → 逐段构建 → 校验 → 集成。
- **`pd-diagnose.py`**：Paradigma Harness 诊断工具。对比衍生项目与上游在结构、工具、Schema、配置、协议五个维度的差异，生成人类可读或 JSON 格式的诊断报告。支持 `--check-version` 快速版本检查。
- **INIT_PROMPT 模式 H（结构迁移）**：Agent 引导的 pre-OKF flat 结构到 OKF 三态结构的迁移向导。5 阶段流程：诊断 → 基础设施 → 知识迁移（含 OKF frontmatter 映射表）→ 校验 → 清理。
- **`paradigma_harness_version`**：在 `.paradigma/config.yaml` 中新增版本追踪字段，衍生项目记录当前使用的 Paradigma 版本。
- **Mid-term plans 层**：新增 `paradigma-plan` 类型（`knowledge/plans/`）。三层 planning 架构（vision → plans → active-task），填补了项目愿景和当前任务之间的中期规划空白。temperature 随 status 切换：`in-progress` → WARM，`completed` → COLD。
- 新增 domain 文档：`design-system.md`、`migration-flows.md`、`plans.md`。
- 新增 manual 文档：`paradigma-design-wizard.md`、`paradigma-harness-update.md`。
- 新增已知问题：`session-context-fragmentation.md`（active-task 完成后上下文断裂的根因分析与三层次修复方案）。

### Changed
- `pd-check-all.py` 现在运行 5 项检查（lint / links / index / hot-size / design）；links check 使用 `--allow-warnings` 以容忍 planned relations 目标。
- `AGENT_RULES.md` Read Phase 新增步骤 5（DESIGN.md 前端任务引导）和步骤 6（relations 补读依赖）。
- `AGENT_RULES.md` WARM 列表新增 `DESIGN.md`、`knowledge/plans/*.md`。
- `AGENT_RULES.md` Update Phase 新增可选步骤 9（DESIGN.md 一致性检查）。
- `AGENT_RULES.md` 防幻觉节新增 `pd-diagnose.py --check-version` 指引。
- `architecture.md` Open Questions 从 3 条扩展为 22 条，按四类组织（协议/运行时、工具链、语义模型、用户体验）。
- `architecture.md` Data Flow 加入 plan context 节点，Key Constraints 加入 plan 温度切换规则。
- `glossary.md` 新增 DESIGN.md、设计器模式、Harness 诊断器、结构迁移、中期计划 5 个词条。

### Fixed
- 归档 `memory_bank/` 旧 flat 目录中的历史内容：changelog (v0.1.0-pre, v0.2.0-pre) 追加到当前 changelog；旧 ADR-002 作为附录追加到 adr-001；progress.md 拆分为 5 个独立 session log 文件。

### Removed
- 删除遗留的 `memory_bank/` 目录（12 个 flat/模板文件，已被三态结构取代）。

## [0.4.2] - 2026-07-05

### Added
- 新增 `pd-check-all.py`，聚合 lint、link check、index check、hot-size 为单一质量门禁。
- 新增 `.github/workflows/check.yml`，在 push main 和 PR 上自动运行 `pd-check-all.py`。

### Fixed
- `pd-check-links.py` 现在排除 fenced/inline/indented code blocks 中的链接模式，避免 `[{rel}]({rel})` 等代码示例产生假阳性 ERROR。

### Changed
- 更新 `AGENT_RULES.md`、Cursor rule、`conventions.md`、`paradigma-baseline-test.md` 和 `repository-contract.md`，Update Phase 统一使用 `pd-check-all.py`。

## [0.4.1] - 2026-07-05

### Changed
- `deploy.md` 和 `testing-guide.md` 重命名为 `paradigma-deploy.md` (cold) 和 `paradigma-baseline-test.md` (warm)，避免与衍生项目自身 deploy/test 文档歧义。
- `pd-sync-index.py` 从 `.paradigma/config.yaml` 读取 `knowledge_roots` 配置，对每个 root 及其子目录自动生成索引（包括 `docs/rfc/`）。
- `pd-archive-task.py` 和 `pd-compact-progress.py` 状态从 Experimental 升级为 Stable。

### Added
- 新增 `domains/tooling.md` 和 `domains/protocol.md` 域文档。
- 新增 `known-issues/fstring-escape-in-compact.md` 和 `known-issues/stale-section-structure-in-adr001.md`。
- 扩充 `glossary.md` 至 20+ 核心术语。
- `docs/rfc/index.md` 补全 OKF frontmatter 并加入自动索引。

### Fixed
- 更新 `architecture.md` Open Questions 以反映 0.4.0 已实现工具。

## [0.4.0] - 2026-07-04

### Added
- 新增 strict OKF lint，校验 schema、type、section、timestamp、policy 和 generated block checksum。
- 新增 `pd-check-links.py`，校验 Markdown links、frontmatter relations 和 generated index entries。
- 新增 hot-size、active-task archive、progress compact 工具。
- 新增 ADR-003，记录从 OKF MVP 进入严格生产规则。

### Changed
- 升级 `pd-sync-index.py`，生成含 retrieval hints、symbols、relations 和 checksum 的根/子目录索引。
- 更新 README、INIT_PROMPT、AGENT_RULES 和 Cursor rule，采用 lint + link check + index check + hot-size check 的 Update Phase。
- 收敛核心 knowledge/templates section 结构，修正旧路径引用与 RFC 关系目标。

## [0.3.0] - 2026-07-04

### Added
- 新增 OKF-compatible runtime/logs/knowledge 三态 Memory-Bank 结构。
- 新增 `docs/rfc/`，并将 OKF runtime 草案迁入 RFC concept 文档。
- 新增 `.paradigma/config.yaml`、轻量 type registry 和最小 Python 工具链。
- 新增 `pd-lint-okf.py` 与 `pd-sync-index.py`。

### Changed
- 更新 `AGENT_RULES.md`、Cursor rule、`INIT_PROMPT.md` 和 README，切换到 OKF-compatible Agent runtime protocol。
- 将长期知识迁移到 `memory-bank/knowledge/` 并补充 OKF frontmatter。
- 将运行状态迁移到 `memory-bank/runtime/`，将日志迁移到 `memory-bank/logs/`。

## [0.2.2] - 2026-07-04

### Changed
- 将空白 `.template.md` 文件从 `memory-bank/` 迁移到 `memory-bank-template/`，与项目运行记忆分离。
- 更新 `AGENT_RULES.md`、Cursor rule、`INIT_PROMPT.md` 和 README 中的模板回退与项目初始化路径。
- 移除 `.gitignore` 中对 `memory-bank/*.md` 运行时文件的排除规则，使 Paradigma 自身开发记忆可直接被版本控制追踪。

### Added
- 新增 Paradigma 自身的 `architecture.md`、`data-contracts.md`、`decisions.md` 和 `changelog.md` 运行时记忆文件。

## [0.2.1] - 2026-06-17

### Changed
- HOT/WARM 层占位文件统一改为 `.template.md` 格式范例（architecture、active-task、data-contracts、roadmap、domains）。
- `progress.md` 纳入统一模板机制，补充跨平台时间戳获取说明。
- `AGENT_RULES.md` 与 `memory-bank-protocol.mdc` 同步，新增模板回退读取规则。
- 统一时间格式为 `YYYY-MM-DD HH:mm`（changelog 发布日期为 `YYYY-MM-DD`）。
- `conventions.md` 新增「Paradigma 模板库自身维护」SemVer 规则。

### Fixed
- 消除 HOT 层空占位文件导致 Agent 读取无有效信息的问题。

## [0.2.0] - 2026-06-17

### Changed
- 统一 `memory-bank` 目录命名（原 `memory_bank`）。
- 日志时间戳须通过工具获取，精确到分钟。

---

> 📜 **Pre-history（从 pre-OKF 时代的 `memory_bank/changelog.md` 归档恢复）**
> 
> 以下条目记载了 Paradigma 项目最早期的发布历史。版本号在早期尚未严格遵循 SemVer，可能与本 changelog 中同版本号条目不完全一致。此处保留原始措辞以供历史参考。

## [0.2.0-pre] - 2026-06-03

### Added
- 版本管理体系：`VERSION` 文件作为版本号唯一真实来源，`changelog.md` 记录发布历史
- `conventions.md` 新增"主动版本管理"规则块，含修改类型 vs 版本动作决策表
- `AGENT_RULES.md` Update Phase 新增步骤 7：版本号评估
- `project-brief.md` 身份卡片新增"当前版本"字段

### Fixed
- README 步骤 1 缺少手动路径的"断开上游 git remote"说明
- README 步骤 4 模式列表缺少模式 F，导致新用户跳过 setup
- INIT_PROMPT 模式 F 步骤 4 不够主动（原为被动检查，改为主动执行 `git remote remove`）
- `.cursor/rules/memory-bank-protocol.mdc` 与 `AGENT_RULES.md` 不同步（缺少 version step、changelog、glossary）

## [0.1.0-pre] - 2026-06-02

### Added
- 设计 memory-bank 目录结构和知识温度体系（HOT / WARM / COLD）
- 创建 `AGENT_RULES.md` — IDE 无关的四阶段工作流协议
- 创建 `INIT_PROMPT.md` — 六种会话启动模式（F / A / B / C / D / 自定义）
- 创建 `conventions.md` — 编码规范（通用原则、命名约定、文件组织、前后端规范、类型安全、Git 提交、SemVer 摘要、测试规范、审查清单）
- 创建 `project-brief.md` — 九板块可填写模板
- 创建 `.cursor/rules/memory-bank-protocol.mdc` — Cursor 自动加载规则
- 创建 `.gitignore` — 模板与运行时分离机制
- 创建 `manuals/` 目录 — 部署运维和测试指南模板
- 创建 `changelog.md` — Keep a Changelog 格式发布日志
- 创建 `VERSION` — 版本号唯一真实源头
- 创建 `LICENSE` — MPL-2.0 文件级 copyleft 许可证
- 补充 conventions.md 中的 SemVer 操作摘要和 Agent 行为约定
- 补充 INIT_PROMPT.md 中的模式 F（Project Setup & Bootstrap）
