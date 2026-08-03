# INIT_PROMPT.md — 会话启动模板

> **使用方式**：根据你的场景复制对应模板，将 `{{PLACEHOLDER}}` 替换为实际内容后粘贴到 IDE 对话框中。
>
> **前置条件**：确保已按照 README.md 完成步骤 1（获取基座、断开上游 git remote）。

---

## 模式 F：Project Setup & Bootstrap（一次性机械设置）

> **适用场景**：刚 clone 了 Paradigma，还没有做任何初始化设置。让 Agent 帮你完成机械操作。

```
你好，我刚从这个项目模板创建了我的新项目。

【我的项目名】：{{项目名，例如 TodoTracker}}

请先阅读 README.md 的"如何使用"部分，理解完整设置流程。然后帮我按以下步骤操作：

1. 激活 OKF-compatible Memory-Bank 模板：
   - 从 memory-bank-template/logs/ 复制到 memory-bank/logs/
   - 从 memory-bank-template/knowledge/ 复制到 memory-bank/knowledge/
   - 安装本地 `paradigma` 包后，先运行 `pd runtime init` 审查计划，再运行 `pd runtime init --write`

2. 确认 runtime/logs/knowledge 三态结构存在：
   - memory-bank/runtime/active-task.yaml
   - memory-bank/runtime/active-session.yaml
   - memory-bank/runtime/active-task.md
   - memory-bank/runtime/handoff.md
   - memory-bank/logs/progress/
   - memory-bank/knowledge/index.md
   - memory-bank/knowledge/project-brief.md
   - memory-bank/knowledge/architecture.md
   - memory-bank/knowledge/conventions.md
   - memory-bank/knowledge/contracts/

3. 修改项目标识：
   - 将 README.md 的标题从 "Project Paradigma" 改为 "{{项目名}}"
   - 将 README.md 的副标题改为适合我项目的简介
   - 更新 memory-bank/knowledge/project-brief.md 中的项目身份信息

4. 处理 git remote：
   - 执行 `git remote -v` 检查当前 remote
   - 如果 remote 仍指向 Marz42/paradigma，执行 `git remote remove origin`
   - 然后告诉我你的 GitHub 仓库 URL，我帮你关联 `git remote add origin <你的仓库URL>`

5. 运行 `pd runtime verify`、`pd index rebuild` 和 `pd check` 验证 Memory-Bank 状态。

6. 将所有更改做首次 commit：
   - 提交信息：chore: init from paradigma template
   - 如果 remote 已配置且与你的仓库关联，同时 push

7. 完成后告诉我一切就绪，我们可以进入模式 A 填充项目知识，或者直接开始写代码。
```

---

## 模式 A：全新项目初始化（Agent 填充所有文档）

```
你好，我们将开始一个新项目。

【项目目标】
{{用1-2句话描述项目要解决什么问题，面向什么用户}}

【技术栈偏好】
{{例如：Vue3 + FastAPI + PostgreSQL，或其他}}

【核心卖点 / 差异化特性】
{{例如：支持自然语言输入记账}}

请按以下步骤操作：

1. 运行 `pd task status`；若没有 Task，为知识初始化任务先 dry-run `pd task start ...`，确认后加 `--write`，再启动 Session。
2. 以项目目标、knowledge 路径和关键词运行 `pd context build ... --write` 与 `pd context verify`。
3. 基于 Manifest 命中的 project-brief 填充项目愿景、受众、边界和成功指标。
4. 基于 Manifest 命中的 architecture 填充技术栈、目录结构和关键约束。
5. 基于 repository contract 设计第一版契约边界；如涉及 API/数据库，新增 contracts 文档。
6. 对暂时无法确定的字段标记为 `TODO`，不要编造。
7. 运行 `pd index rebuild`、重新构建 Context，然后运行 `pd check`。
8. 用 `pd session checkpoint` 记录成果并结束 Session；完成知识初始化 Task 后再用 `pd task complete --write`。
```

---

## 模式 B：已有项目续接（Agent 读取已有文档并审查）

```
你好，这是一个已有项目。请按以下步骤操作：

1. 运行 `pd task status` 和 `pd session status`，通过 handoff + latest Checkpoint 恢复状态；需要时启动新 Session。
2. 为 `{{具体的下一步任务}}` 规划 path/symbol/keyword 信号，运行 `pd context build ... --write` 与 `pd context verify`。
3. 根据 Manifest 选择的文档及 reasons 审查：
   - 哪些文档信息不足或过时
   - architecture 与实际代码结构是否一致
   - contracts 的约束是否仍然有效
4. 仅当 handoff/Checkpoint 信息不足或需要历史审计时，再读取 progress logs。
5. 给出审查意见，然后继续推进 {{具体的下一步任务}}。
```

---

## 模式 C：单任务突击（跳过审查，直接执行）

```
你好，请按以下步骤操作：

1. 运行 `pd task status`、`pd session status`；需要时先 dry-run，再显式启动 Task/Session。
2. 根据任务信号运行 `pd context build ... --write` 与 `pd context verify`，只读取 Manifest 选择的必要文档。
3. 理解当前项目状态后，直接开始执行任务：
   {{具体任务描述}}
4. 执行完成后按 AGENT_RULES.md 更新 knowledge，运行测试、`pd check`，记录 Checkpoint，结束 Session；任务完成时再执行 `pd task complete --write`。
```

---

## 模式 D：架构决策讨论（聚焦决策层面）

```
你好，我们需要做一个架构决策。

【背景】
{{简要描述当前遇到的架构问题或需要决策的事项}}

请按以下步骤操作：

1. 运行 Task/Session 状态命令，并以 architecture、contract、ADR 的 path/keyword 信号构建和校验 Context Manifest。
2. 给出 2-3 个可行方案，并分析各自优缺点。
3. 给出你的推荐方案及理由。
4. 待我确认后，将最终决策追加到 memory-bank/knowledge/decisions/。
```

---

## 模式 G：DESIGN.md 设计器（视觉设计规范创建）

> **适用场景**：项目需要前端 UI，需要建立统一的视觉设计规范来指导 Agent 生成一致的界面。
> **前置条件**：项目已按模式 F 完成初始化。建议安装 Node.js（可选，用于 `@google/design.md` CLI 深度校验）。

```
你好，我需要为我的项目创建一份视觉设计规范（DESIGN.md）。

【项目类型】：{{SaaS Dashboard / 内容博客 / 工具产品 / 电商 / 其他}}
【视觉风格偏好】：{{专业严肃 / 活泼友好 / 极简克制 / 前卫实验 / 不确定，请你推荐}}
【参考品牌/产品】：{{如有，列 1-3 个你喜欢的产品的视觉风格}}
【品牌色（如有）】：{{已有品牌色的 hex 值，没有就留空}}

请按以下步骤操作：

———— Phase 1：发现阶段 ————

1. 运行 Task/Session 状态命令，并把 `DESIGN.md` 与 `memory-bank/knowledge/domains/design-system.md` 作为显式 path signal 构建和校验 Context。
2. 读取 Manifest 选择的 design-system 文档，理解 DESIGN.md 在 Paradigma 中的角色和格式要求。
3. 根据我的项目类型和风格偏好，用 2-3 句话归纳你的设计理念理解，让我确认方向后再继续。
4. 如果我有参考品牌，简要分析它们的视觉特征（配色倾向、字体风格、空间感）。

———— Phase 2：逐段构建 ————

每段完成后让我确认，确认后再继续下一段。

5. **Overview**：基于 Phase 1 确认的方向，写一段设计理念描述（2-5 句）。风格可以参考 design.md 社区的惯例，如 "Architectural Minimalism meets Journalistic Gravitas"。

6. **Colors**：提出一套配色方案。至少包含：
   - primary（主色，标题/核心元素）
   - secondary（辅色，边框/字幕/元数据）
   - tertiary（强调色/交互色，CTA 按钮）
   - neutral（底色，背景）
   可额外添加 semantic 色（success/error/warning）。每种颜色给出 hex 值和用途说明。
   ⚠️ 硬约束：组件 textColor 与 backgroundColor 的 WCAG AA 对比度至少 4.5:1。

7. **Typography**：建议一个字体层级（h1/h2/body/caption）。优先使用系统字体栈（如 system-ui, -apple-system, BlinkMacSystemFont）或 Google Fonts。每个层级给出 fontFamily、fontSize、fontWeight、lineHeight。

8. **Layout & Spacing**：建议间距尺度（sm/md/lg/xl，推荐 8px 栅格）和圆角（sm/md/lg）。说明各尺度的典型使用场景。

9. **Components**：建议 3-5 个核心组件的 token。使用 `{colors.xxx}` 和 `{spacing.xxx}` 引用上文定义的 tokens。至少包含一个 button variant、一个 card/surface、一个 input 字段。

10. **Do's and Don'ts**：基于以上选择，生成 3-5 条使用原则（每条含 ✅ DO 和 ❌ DON'T）。

———— Phase 3：生成与校验 ————

11. 将所有确认结果写入项目根目录 `DESIGN.md`。
12. 运行 `pd check` 验证 DESIGN.md 基本格式。
13. （可选）若有 Node.js，运行 `npx @google/design.md lint DESIGN.md` 做深度校验（token 引用、对比度、section 顺序）。
14. 告知校验结果和需要人工审视的部分。

———— Phase 4：集成 ————

15. 提醒我：后续前端开发任务中，应把 DESIGN.md 作为显式 Context path signal。
16. 如果要修改设计规范，可以直接编辑 DESIGN.md 或再次使用本模式 G 重新生成。
```



---

## 模式 H：Paradigma 结构迁移（pre-OKF → 三态结构）

> **适用场景**：旧项目使用 pre-OKF 的 flat `memory_bank/` 或 `memory-bank/` flat 结构，需要迁移到 OKF-compatible 的 `memory-bank/runtime|logs|knowledge/` 三态结构。
> **前置条件**：项目根目录存在旧版 `memory_bank/`（下划线）或 `memory-bank/` flat 结构（无 runtime/logs/knowledge 子目录）。本地有 Paradigma 最新版本的源目录。

```
你好，我的项目需要从旧版 Paradigma 迁移到 OKF-compatible 三态 Memory-Bank 结构。

【Paradigma 源路径】：{{最新 Paradigma 的本地路径，如 D:\Repos\paradigma}}

请按以下步骤操作：

———— Phase 1：诊断 ————

1. 运行 python .paradigma/tools/pd-diagnose.py --upstream {{Paradigma 源路径}} --json
   查看当前项目与最新 Paradigma 的差距。打印报告让我确认。

———— Phase 2：基础设施 ————

2. 创建新目录结构（保留旧目录不动，迁移完成后我会手动清理）：
   - memory-bank/runtime/
   - memory-bank/logs/progress/
   - memory-bank/knowledge/domains/
   - memory-bank/knowledge/contracts/
   - memory-bank/knowledge/manuals/
   - memory-bank/knowledge/decisions/
   - memory-bank/knowledge/known-issues/
   - memory-bank-template/

3. 从 {{Paradigma 源路径}} 安全复制基础设施文件：
   - .paradigma/tools/*.py          → .paradigma/tools/
   - .paradigma/schemas/*.yaml      → .paradigma/schemas/
   - .paradigma/config.yaml         → .paradigma/config.yaml
   - memory-bank-template/*         → memory-bank-template/
   - AGENT_RULES.md                 → AGENT_RULES.md（⚠ 先备份旧版为 AGENT_RULES.md.bak）
   - INIT_PROMPT.md                 → INIT_PROMPT.md（⚠ 同上备份）
   - .cursor/rules/*.mdc            → .cursor/rules/

———— Phase 3：知识迁移（逐文件，每文件确认后再继续）————

4. 迁移旧 active-task 信息：
   - 将旧 active-task.md 保留为迁移审计材料，不复制到 generated runtime 路径
   - 安装本地 `paradigma` 包，先运行 `pd runtime init`，确认后执行 `pd runtime init --write`
   - 从旧文件提取 title/goal/scope，先 dry-run `pd task start ...`，确认映射后加 `--write`；不要手工创建 Task YAML 或 active-task.md

5. 迁移 progress.md：
   - 读取旧 progress.md，拆分为独立 session log（每个会话一个文件）
   - 写入 memory-bank/logs/progress/YYYY-MM-DD-*.md
   - 每个文件添加 OKF frontmatter（type: paradigma-session-log）

6. 迁移 changelog.md → memory-bank/logs/changelog.md

7. 迁移长期知识文档（project-brief, architecture, conventions, glossary 等）：
   - 每个文件复制到 memory-bank/knowledge/ 对应子目录
   - 为每个文件添加完整 OKF frontmatter：
     * type/title/description/tags/timestamp
     * paradigma: schema_version, temperature, lifecycle, update_policy, epistemic_status
     * retrieval_hints (zh/en)
   - 文件类型映射：
     * project-brief.md → paradigma-project-brief
     * architecture.md → paradigma-architecture
     * conventions.md → paradigma-convention
     * glossary.md → paradigma-glossary
     * decisions.md → 拆分为独立 paradigma-decision 文件（adr-0001-xxx.md）
     * known-issues.md → 拆分为独立 paradigma-known-issue 文件
     * manuals/*.md → paradigma-manual
     * domains/*.md → paradigma-domain
   - 对无法确定的内容标记为 TODO，不要编造。

———— Phase 4：校验与清理 ————

8. 运行 `pd runtime verify` 和 `pd index rebuild`
9. 运行 `pd check`
10. 如有 lint 错误，逐一修复。
11. 更新 `.paradigma/config.yaml` 的 `installed_distribution_version` 为最新版本；旧 `paradigma_harness_version` 应迁移并移除。
12. 全部通过后告诉我，我会手动删除旧 memory_bank/ 或 memory-bank/ flat 结构。
13. 提醒我 git add + commit：chore: migrate to Paradigma OKF three-state structure
```

---

## 自定义提示

核心原则：

- 始终让 Agent 先用 `pd task/session status` 恢复事实，再用显式信号构建和校验 Context Manifest。
- 明确告诉 Agent 你期望的输出，是填充知识、写代码还是做决策。
- 约定好会话结束时的交付物，并要求执行测试、`pd check`、Checkpoint 和 Session end；运行状态不手工编辑。
- 大任务拆分为阶段（Plan → Execution），每个阶段结束时提醒 Agent 检查是否需要更新相关 Memory-Bank 文档（ADRs、contracts、domains、conventions、known-issues）。
