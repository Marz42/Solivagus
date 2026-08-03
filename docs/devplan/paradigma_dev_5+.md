
# Paradigma Agent Memory Runtime 开发计划

**文档状态：** Approved Development Plan  
**规划版本：** v0.5.1–v1.0  
**开发原则：** 小步迭代、保持可用、每阶段独立验收  
**核心定位：** 文件优先、可解释、可审计的 LLM Agent 外部记忆内核  
**首个领域集成：** Coding  
**第二个领域集成：** Research / OSINT  
**MCP 引入版本：** v0.9  
**长期知识载体：** OKF-compatible Markdown  
**派生检索层：** SQLite + FTS5  
**运行状态事实源：** YAML 原子快照  
**审计方式：** Append-only JSONL Audit Log

---

## 1. 项目定位

Paradigma 的近期定位为：

> Paradigma 是一个面向长期运行 LLM Agent 的、文件优先、可解释、可审计的外部记忆内核。Coding Agent Runtime 是它的第一个领域集成，Research / OSINT 是第二个抽象验证领域。

Paradigma 不以构建完整 Agent Framework、工作流引擎或模型调用框架为近期目标。

核心要解决的问题是：

1. 哪些信息应当成为长期记忆；
2. 记忆属于什么作用域；
3. 记忆来源和证据是什么；
4. 记忆何时有效、何时过期；
5. 新旧信息冲突时如何处理；
6. 记忆如何修订、取代和遗忘；
7. Agent 如何检索相关记忆；
8. 系统如何解释召回原因；
9. 不同 Agent Session 如何共享长期状态而不共享全部上下文。

---

## 2. 已确认的架构决策

### ADR-D1：文档级记忆

v0.x 采用：

```text
一个受管理 Markdown 文档
        =
一个 MemoryRecord
```

暂不支持：

- 段落级记忆；
-句子级记忆；
-自动 Chunk；
-单个文档内部多个独立 revision；
-细粒度位置锚点同步。

该选择优先保证：

- 人工可读；
- Git diff 清晰；
- revision 容易理解；
-手工修改可检测；
-迁移成本可控。

后续只有在 Research / OSINT 使用中证明文档级粒度不足时，才评估块级记忆。

---

### ADR-D2：SQLite + FTS5 派生 Catalog

长期知识继续保存在 Markdown 中。

SQLite Catalog 负责：

- 全文检索；
-元数据查询；
-作用域过滤；
-有效期过滤；
-关系查询；
-状态过滤；
-路径映射；
-快速统计。

SQLite 不作为 canonical store。

```text
Markdown
  = 唯一长期知识事实源

SQLite
  = 可删除、可重建的派生索引
```

建议默认路径：

```text
.paradigma/cache/catalog.sqlite3
```

Catalog 损坏时，必须能够通过以下命令完整重建：

```bash
pd catalog rebuild
```

---

### ADR-D3：长期记忆分级确认

长期记忆写入采用三级政策。

#### Level 1：自动提交

适用于能够由确定性工具直接验证的低风险事实，例如：

- 文件路径；
-Git commit；
-测试结果；
-任务状态；
-明确的配置值；
-用户直接要求保存的普通项目事实。

#### Level 2：候选自动生成，提交前确认

适用于：

- Agent 提取的长期经验；
-项目规范摘要；
-架构结论；
-Research Claim；
-来源综合结论；
-对未来工作可能产生影响的推断。

#### Level 3：强制人工确认

适用于：

- 敏感信息；
-用户画像和偏好；
-高影响决策；
-有争议的研究结论；
-低置信度推断；
-删除或物理清除；
-改变已有 canonical knowledge 的操作。

默认流程：

```text
propose
   ↓
validate
   ↓
classify risk
   ↓
auto commit / request approval / reject
```

---

### ADR-D4：YAML 快照作为运行状态事实源

Coding Task、Session 和其他当前运行状态采用结构化 YAML。

```text
YAML snapshot
    = 当前事实源

Markdown
    = 人类可读投影

JSONL audit
    = 操作和变更审计
```

暂不采用完整 Event Sourcing。

例如：

```text
memory-bank/runtime/tasks/TASK-001.yaml
memory-bank/runtime/sessions/SESSION-001.yaml
memory-bank/runtime/active-task.yaml
```

人类可读投影：

```text
memory-bank/runtime/active-task.md
memory-bank/runtime/handoff.md
```

---

### ADR-D5：Research / OSINT 作为第二领域集成

第二个领域不选择 Personal Assistant，而选择 Research / OSINT。

该领域重点验证：

- Claim；
-Source；
-Evidence；
-Entity；
-Event Time；
-Publication Time；
-Confidence；
-Contradiction；
-Supersession；
-调查范围；
-分析假设；
-证据链。

Research / OSINT 不只是演示 Profile，而是用于验证 Memory Kernel 是否真正脱离 Coding 领域假设。

---

### ADR-D6：MCP 延至 v0.9

MCP 是 Paradigma 的访问适配器，不是 Memory Kernel 的组成部分。

```text
Agent Harness
      ↓
MCP Adapter
      ↓
Paradigma Application API
      ↓
Memory Kernel
```

在 v0.9 之前：

- 不实现 MCP Server；
-不依据 MCP Schema 设计 Kernel；
-不提前冻结 Tool Contract；
-不建设远程服务；
-不引入 MCP 认证和授权。

---

## 3. 总体架构

```text
┌──────────────────────────────────────────────┐
│ Agent Harness                                │
│ Cursor / Hermes / Claude Code / CLI / MCP    │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│ Adapter Layer                                │
│ Cursor Adapter / CLI / MCP Adapter           │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│ Domain Integrations                          │
│ Coding Integration / Research-OSINT          │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│ Application API                              │
│ propose / commit / query / explain           │
│ revise / supersede / forget / build_context  │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│ Memory Kernel                                │
│ Record / Scope / Provenance / Revision       │
│ Validity / Conflict / Retention / Retrieval  │
└───────────────┬──────────────────┬───────────┘
                │                  │
┌───────────────▼────────┐ ┌───────▼───────────┐
│ Canonical Store        │ │ Derived Catalog   │
│ OKF Markdown           │ │ SQLite + FTS5      │
└───────────────┬────────┘ └───────────────────┘
                │
┌───────────────▼──────────────────────────────┐
│ Runtime and Audit                            │
│ YAML Snapshots / JSONL Audit Logs            │
└──────────────────────────────────────────────┘
```

---

## 4. 责任边界

### 4.1 Memory Kernel

Memory Kernel 只处理领域中立的记忆语义：

- MemoryRecord；
-MemoryScope；
-Provenance；
-Revision；
-Validity；
-Status；
-Relation；
-Conflict；
-Retention；
-Query；
-Result Explanation。

Memory Kernel 不得理解：

```text
repository
branch
commit
symbol
test
build
claim
source credibility
user preference
calendar
contact
```

---

### 4.2 Coding Integration

Coding Integration 负责：

- RepositoryScope；
-CodingTask；
-CodingSession；
-Checkpoint；
-Git Evidence；
-Test Evidence；
-Build Evidence；
-Path Signal；
-Symbol Signal；
-Coding Context Builder；
-Coding Write Policy。

---

### 4.3 Research / OSINT Integration

Research / OSINT Integration 负责：

- Research Project；
-Investigation Question；
-Claim；
-Source；
-Evidence；
-Entity；
-Event；
-Timeline；
-Hypothesis；
-Confidence；
-Contradiction；
-Analytic Judgment；
-Collection Gap。

---

### 4.4 Adapter Layer

Adapter 只负责：

- 平台工具映射；
-调用 Application API；
-输入输出格式转换；
-平台指令渲染；
-上下文注入；
-错误呈现。

Adapter 不得：

- 自行修改 Markdown；
-自行维护状态机；
-复制 Schema；
-决定记忆是否允许提交；
-直接操作 SQLite；
-实现自己的检索逻辑。

---

## 5. 最小 Memory Domain Model

### 5.1 MemoryRecord

```python
@dataclass(frozen=True)
class MemoryRecord:
    memory_id: str
    memory_type: str
    title: str
    content: str

    scope: MemoryScope
    provenance: tuple[ProvenanceRef, ...]

    status: MemoryStatus
    revision: int

    valid_from: datetime | None
    valid_until: datetime | None

    confidence: float | None
    sensitivity: str

    tags: tuple[str, ...]
    relations: tuple[MemoryRelation, ...]

    created_at: datetime
    updated_at: datetime
```

---

### 5.2 MemoryType

首期只定义通用类型：

```text
semantic
episodic
procedural
decision
working
```

Coding 和 Research 的具体类型通过 integration metadata 表达，不立即扩大 Kernel 枚举。

---

### 5.3 MemoryStatus

```text
candidate
active
superseded
expired
rejected
tombstoned
```

含义：

| 状态 | 含义 |
|---|---|
| candidate | 尚未进入正式长期记忆 |
| active | 当前有效并允许普通查询 |
| superseded | 已被新 revision 取代 |
| expired | 超过有效期 |
| rejected | 候选未获批准 |
| tombstoned | 已逻辑删除 |

普通查询默认只返回 `active`。

---

### 5.4 MemoryScope

```python
@dataclass(frozen=True)
class MemoryScope:
    namespace: str
    workspace_id: str | None
    project_id: str | None
    task_id: str | None
    session_id: str | None
    entity_ids: tuple[str, ...]
```

首期不实现多租户，但不得将 scope 固定为 Git Repository。

---

### 5.5 Provenance

```python
@dataclass(frozen=True)
class ProvenanceRef:
    source_type: str
    source_uri: str | None
    source_id: str | None
    observed_at: datetime | None
    excerpt_hash: str | None
    actor: str | None
```

初始来源类型：

```text
user_statement
repository_file
git_commit
tool_result
research_source
web_source
agent_inference
manual_entry
```

`agent_inference` 必须具有置信度，且默认不能直接作为高置信度事实提交。

---

### 5.6 Revision

长期记忆不允许无痕覆盖。

```text
MEM-001 revision 1
        ↓
MEM-001 revision 2
```

Revision 必须记录：

- 修改原因；
-修改者；
-修改时间；
-来源变化；
-内容 hash；
-前一个 revision；
-冲突处理方式。

---

## 6. 目标代码结构

```text
paradigma/
├── pyproject.toml
├── VERSION
├── src/
│   └── paradigma/
│       ├── kernel/
│       │   ├── models/
│       │   │   ├── memory.py
│       │   │   ├── scope.py
│       │   │   ├── provenance.py
│       │   │   ├── relation.py
│       │   │   └── query.py
│       │   ├── services/
│       │   │   ├── memory_service.py
│       │   │   ├── mutation_service.py
│       │   │   ├── retrieval_service.py
│       │   │   └── conflict_service.py
│       │   ├── policies/
│       │   │   ├── write_policy.py
│       │   │   ├── retention.py
│       │   │   └── retrieval_policy.py
│       │   └── results.py
│       │
│       ├── storage/
│       │   ├── contract.py
│       │   ├── markdown/
│       │   │   ├── codec.py
│       │   │   ├── store.py
│       │   │   └── atomic_write.py
│       │   ├── catalog/
│       │   │   ├── sqlite.py
│       │   │   ├── schema.sql
│       │   │   └── rebuild.py
│       │   └── audit/
│       │       └── jsonl.py
│       │
│       ├── application/
│       │   ├── commands.py
│       │   ├── queries.py
│       │   └── errors.py
│       │
│       ├── integrations/
│       │   ├── coding/
│       │   └── research/
│       │
│       ├── adapters/
│       │   ├── cursor/
│       │   ├── generic_cli/
│       │   └── mcp/
│       │
│       ├── cli/
│       │   ├── main.py
│       │   ├── output.py
│       │   └── commands/
│       │
│       └── migrations/
│
├── tests/
│   ├── unit/
│   ├── characterization/
│   ├── integration/
│   ├── architecture/
│   ├── migration/
│   ├── failure_injection/
│   └── golden/
│
├── memory-bank-template/
└── .paradigma/
    └── tools/
        └── compatibility wrappers
```

不提前创建尚无实现的扩展框架、动态插件系统和通用 DSL。

---

# 7. 版本实施路线

## Phase 0：现有系统可靠化

**目标版本：v0.5.1**

### 目标

不新增重大能力，先解决现有工具的可靠性、自洽性和可测试性。

### Batch 0.1：版本与配置统一

工作项：

1. 明确根目录 `VERSION` 为发行版本真相源。
2. 配置增加：
   ```yaml
   config_schema_version: "0.2"
   okf_version: "0.1"
   ```
3. 移除或迁移含义模糊的：
   ```yaml
   paradigma_harness_version
   ```
4. 明确文档 Schema 版本与发行版本分离。
5. 新增：
   ```bash
   pd version --verbose
   ```
6. 输出：
   - distribution version；
   -config schema version；
   -OKF version；
   -document schema version。

#### 验收

- 不存在相互冲突的版本字段；
-所有工具使用统一版本解析逻辑；
-版本检查进入 CI。

---

### Batch 0.2：统一 Parser

工作项：

1. 使用标准 YAML 库。
2. 提取统一 frontmatter parser。
3. 删除现有工具中的重复解析逻辑。
4. Parser 返回结构化 diagnostics。
5. 严格区分：
   - YAML 语法错误；
   -缺失 frontmatter；
   -Schema 错误；
   -编码错误。

#### 验收

- 所有工具调用同一 Parser；
-中文、非 ASCII、Windows 换行和 UTF-8 BOM 有测试；
-非法 YAML 不被静默接受。

---

### Batch 0.3：严格状态与归档安全

工作项：

1. 删除自然语言子串状态判断。
2. 定义状态枚举：
   ```text
   pending
   active
   blocked
   completed
   aborted
   ```
3. 未知状态直接失败。
4. 修复已完成任务仍残留为 active 的问题。
5. 归档操作先生成 mutation plan。
6. 引入原子写入。
7. 支持：
   ```bash
   pd task archive --dry-run
   ```

#### 验收

- “未完成”不会被识别为“完成”；
-中途中断不会产生半归档状态；
-重复归档具有幂等行为；
-失败返回稳定错误码。

---

### Batch 0.4：索引边界调整

工作项：

1. 根 `index.md` 改为高层导航。
2. 停止递归展开全部知识文件。
3. 机器完整索引迁移到：
   ```text
   .paradigma/cache/
   ```
4. 保留子目录局部索引。
5. 提供：
   ```bash
   pd index rebuild
   pd index verify
   ```

#### 验收

- 根索引大小不随文档数量线性膨胀；
-人类导航与机器索引职责分离；
-索引损坏不影响 canonical knowledge。

---

### Batch 0.5：Characterization Tests

为现有工具建立行为基线。

覆盖：

- lint；
-link check；
-index sync；
-hot-size；
-archive；
-compact；
-diagnose；
-version；
-check-all。

#### Phase 0 退出门槛

- 仓库自身全部检查通过；
-工具具备基础回归测试；
-写入操作具备原子性；
-不存在版本漂移；
-不存在自然语言状态误判；
-当前使用方式未被破坏。

---

## Phase 1：Python Package 与统一 CLI

**目标版本：v0.5.2**

### 目标

将独立脚本收敛为可测试、可复用的应用内核。

### Batch 1.1：Package Skeleton

建立：

```text
pyproject.toml
src/paradigma/
tests/
```

提取：

- errors；
-results；
-config；
-parser；
-schema validator；
-atomic writer；
-diagnostics。

---

### Batch 1.2：统一 CLI

提供：

```bash
pd version
pd config validate
pd check
pd diagnose
pd index rebuild
pd index verify
pd task archive
```

所有命令支持：

```bash
--format text
--format json
--dry-run
```

---

### Batch 1.3：兼容包装器

现有命令继续工作：

```bash
python .paradigma/tools/pd-check-all.py
```

但内部只调用新 CLI/Application Service。

包装器不得保留独立业务逻辑。

#### Phase 1 退出门槛

- Paradigma 可作为 Python Package 安装；
-旧脚本与新 CLI 行为等价；
-业务逻辑不再散落于脚本；
-Core 方法返回对象，不直接打印；
-Windows 与 POSIX 集成测试通过。

---

## Phase 2：Memory Kernel 纵向闭环

**目标版本：v0.6.0**

### 目标

完成 Paradigma 作为 Memory Runtime 的第一个完整闭环。

### Batch 2.1：Memory Model

实现：

- MemoryRecord；
-MemoryScope；
-ProvenanceRef；
-MemoryRelation；
-MemoryStatus；
-MemoryQuery；
-MemoryResult。

确定稳定 ID 格式，例如：

```text
MEM-01J...
```

---

### Batch 2.2：Markdown Codec 与 Store

实现：

- MemoryRecord → Markdown；
-Markdown → MemoryRecord；
-Schema 校验；
-content hash；
-revision；
-原子写入；
-手工修改检测。

首期采用：

```text
一个 Markdown 文档
=
一个 MemoryRecord
```

现有 legacy 文档通过兼容适配读取，不要求一次性重写。

---

### Batch 2.3：SQLite Catalog

Catalog 保存：

- memory ID；
-path；
-title；
-description；
-content；
-tags；
-status；
-scope；
-validity；
-confidence；
-provenance summary；
-relations；
-content hash。

实现：

```bash
pd catalog rebuild
pd catalog verify
pd catalog stats
```

SQLite 文件默认不提交 Git。

---

### Batch 2.4：Memory Query

实现以下查询方式：

1. memory ID；
2. path；
3. keyword；
4. FTS；
5. tag；
6. scope；
7. status；
8. validity；
9. relation 一跳扩展。

不实现：

- embedding；
-向量数据库；
-LLM reranking；
-自动 Chunk；
-多跳图推理。

---

### Batch 2.5：Mutation Lifecycle

实现：

```bash
pd memory propose
pd memory validate
pd memory commit
pd memory revise
pd memory supersede
pd memory forget
```

`forget` 首期表示 tombstone，不立即保证物理清除。

未来另行定义：

```bash
pd memory purge
```

---

### Batch 2.6：Explain

实现：

```bash
pd memory query "..."
pd memory explain <memory-id>
```

查询结果必须包含：

- 匹配原因；
-匹配字段；
-作用域；
-有效期；
-状态；
-来源；
-置信度；
-关系扩展来源；
-排除警告。

#### Phase 2 退出门槛

- propose → commit → query → explain → revise → forget 全链路可运行；
-所有 canonical 修改具有 revision；
-每条正式记忆具有 provenance；
-SQLite 可从 Markdown 完整重建；
-普通查询不返回 expired、superseded 或 tombstoned；
-相同结构化 Query 产生稳定结果；
-Memory Kernel 不包含 Coding 语义。

---

## Phase 3：Coding Integration

**目标版本：v0.7.0**

### 目标

将现有 Paradigma 编程工作流建立在 Memory Kernel 之上。

### Batch 3.1：Coding Domain Model

实现：

- RepositoryScope；
-CodingTask；
-CodingSession；
-CodingCheckpoint；
-GitEvidence；
-TestEvidence；
-BuildEvidence。

---

### Batch 3.2：YAML Runtime State

建议结构：

```text
memory-bank/runtime/
├── tasks/
│   └── TASK-001.yaml
├── sessions/
│   └── SESSION-001.yaml
├── active-task.yaml
├── active-session.yaml
├── active-task.md
└── handoff.md
```

YAML 为事实源，Markdown 为可重建投影。

---

### Batch 3.3：Task Lifecycle

状态：

```text
pending
active
blocked
suspended
completed
aborted
```

支持：

```bash
pd task start
pd task status
pd task block
pd task unblock
pd task suspend
pd task resume
pd task complete
pd task abort
```

非法状态迁移由工具拒绝。

---

### Batch 3.4：Session 与 Checkpoint

支持：

```bash
pd session start
pd session status
pd session checkpoint
pd session end
pd handoff build
```

Checkpoint 中：

工具确定：

- task/session ID；
-时间；
-Git commit；
-touched files；
-test result；
-current status。

Agent 候选：

-摘要；
-已完成工作；
-剩余工作；
-阻塞项；
-建议下一步。

---

### Batch 3.5：Coding Context Builder

结构化 ContextRequest：

```python
ContextRequest(
    intent=...,
    task_id=...,
    explicit_paths=...,
    explicit_symbols=...,
    keywords=...,
    budget=...,
)
```

确定性执行：

```text
Mandatory Memory
      ↓
Path Match
      ↓
Symbol Match
      ↓
Keyword / FTS Match
      ↓
Scope and Validity Filter
      ↓
One-hop Relation Expansion
      ↓
Deduplicate
      ↓
Budget Trim
      ↓
Context Manifest
```

Query Planning 可以使用 LLM，但 Retrieval Execution 不依赖模型。

---

### Batch 3.6：Agent Rules 收缩

调整 `AGENT_RULES.md`：

- 移除 Persona；
-删除要求模型手工维护的状态；
-将确定性操作替换为 CLI；
-保留最小操作纪律；
-不立即完全自动生成。

#### Phase 3 退出门槛

- Task 生命周期由工具强制执行；
-active task 可由 YAML 状态恢复；
-新 Session 不必扫描全部日志；
-Checkpoint 可稳定恢复工作；
-Context Manifest 具有选择理由；
-Coding Integration 不向 Kernel 注入领域特例。

---

## Phase 4：Research / OSINT Integration

**目标版本：v0.8.0**

### 目标

用真实 OSINT 调查验证 Paradigma 的通用性和证据管理能力。

### 推荐试点

建议选择一个范围有限但信息碎片化明显的调查项目，例如：

```text
2022 年以来乌克兰与日本、台湾、韩国之间的技术合作
```

也可以使用一个更小的子课题进行首轮实验。

---

### Batch 4.1：Research Domain Model

实现：

```text
ResearchProject
ResearchQuestion
Claim
Source
Evidence
Entity
Event
Hypothesis
AnalyticJudgment
CollectionGap
```

---

### Batch 4.2：Source 与 Evidence

Source 保存：

- source ID；
-标题；
-URL 或文件位置；
-发布者；
-作者；
-发布时间；
-获取时间；
-来源类型；
-可靠性备注；
-内容 hash；
-存档位置。

Evidence 保存：

- evidence ID；
-source ID；
-excerpt 或定位信息；
-支持或反驳的 Claim；
-证据强度；
-提取方式；
-观察时间。

---

### Batch 4.3：Claim 与 Contradiction

Claim 保存：

- statement；
-涉及实体；
-时间范围；
-支持证据；
-反驳证据；
-confidence；
-status；
-分析备注。

状态建议：

```text
hypothesis
supported
contested
superseded
rejected
unresolved
```

Paradigma 不自动把多个来源合成为唯一真相。

存在冲突时，应保留：

- 各方主张；
-证据差异；
-来源差异；
-时间差异；
-当前分析判断；
-不确定性。

---

### Batch 4.4：时间模型

明确区分：

```text
event_time
publication_time
observed_time
valid_from
valid_until
```

这对于新闻、企业合作、政府政策和武器采购调查是必要条件。

---

### Batch 4.5：OSINT Query 与 Context

支持：

```bash
pd research source add
pd research evidence add
pd research claim propose
pd research claim review
pd research claim explain
pd research timeline build
pd research gaps
```

Context Builder 应支持：

-实体；
-国家和机构；
-时间范围；
-Claim；
-Source；
-证据关系；
-冲突；
-调查问题；
-Collection Gap。

---

### Batch 4.6：Retrieval Golden Set

建立测试集：

```yaml
query: ...
required_records: [...]
acceptable_records: [...]
forbidden_records: [...]
expected_relations: [...]
```

测量：

- Required Recall；
-Precision；
-过期信息误召回率；
-冲突遗漏率；
-证据链完整率；
-平均 Context 大小；
-结果解释准确率。

#### Phase 4 退出门槛

- Research Integration 不要求修改 Kernel 核心模型；
-Claim 能追溯到 Evidence 和 Source；
-冲突不会被静默覆盖；
-事件时间和发布时间可分别查询；
-调查缺口可以明确记录；
-真实 OSINT 项目能够持续使用；
-能够基于测量结果判断是否需要 embedding。

---

## Phase 5：MCP Adapter

**目标版本：v0.9.0**

### 目标

在 Application API 稳定后，为不同 Agent Harness 提供标准访问接口。

### Batch 5.1：本地 MCP Server

首期只支持：

```text
Transport: stdio
Deployment: local
Workspace: single
```

不提供：

- Streamable HTTP；
-远程访问；
-OAuth；
-多租户；
-服务器托管；
-MCP Registry 发布。

---

### Batch 5.2：只读 Tools

优先实现：

```text
paradigma_memory_search
paradigma_memory_get
paradigma_memory_explain
paradigma_context_build
paradigma_task_status
paradigma_research_claim_get
```

---

### Batch 5.3：受控写入 Tools

实现：

```text
paradigma_memory_propose
paradigma_task_checkpoint
paradigma_research_claim_propose
```

不直接暴露：

```text
memory_write_arbitrary
edit_markdown
update_frontmatter
delete_file
run_sql
```

正式 commit、forget 和高影响 revise 必须经过分级确认政策。

---

### Batch 5.4：CLI / MCP Parity

同一 Application API 同时服务：

```text
CLI
MCP
Cursor Adapter
```

建立 parity tests：

-相同输入；
-相同 policy；
-相同错误码；
-相同结果语义；
-允许表现形式不同。

#### Phase 5 退出门槛

- MCP Server 不包含业务逻辑；
-MCP 被移除后 CLI 和 Kernel 不受影响；
-至少两个 Harness 可以使用；
-写操作遵守同一确认政策；
-MCP 与 CLI 对相同请求语义一致；
-没有远程安全负担。

---

## Phase 6：Operation Contract 收敛

**目标版本：v0.9.x**

### 目标

根据 CLI、Cursor 和 MCP 的真实重复需求，提炼统一操作契约。

可能形成：

```python
OperationSpec(
    operation_id=...,
    input_schema=...,
    output_schema=...,
    mutability=...,
    confirmation_policy=...,
    idempotency=...,
)
```

OperationSpec 可以用于：

- CLI 参数校验；
-MCP Tool Schema；
-Agent 操作说明；
-参考文档。

不自动生成：

-全部 Adapter 代码；
-平台 Hook；
-平台错误界面；
-用户 Prompt。

#### Phase 6 退出门槛

- 至少两个消费者证明 OperationSpec 能减少重复；
-CLI 和 MCP Schema 不再漂移；
-Adapter 不复制业务规则；
-AGENT_RULES 固定内容明显缩短；
-旧脚本包装器有移除计划。

---

## Phase 7：v1.0 稳定化

### v1.0 稳定对象

只承诺以下核心契约：

```text
MemoryRecord
MemoryScope
MemoryQuery
MemoryResult
MemoryMutation
MemoryStore
Provenance
Revision
Validity
Relation
Forget semantics
Application error model
Migration model
```

### v1.0 不承诺

- 公共第三方 Profile SDK；
-动态插件；
-多 Profile 组合；
-完整 Event Sourcing；
-向量数据库；
-远程 MCP；
-多租户；
-完整 Personal Assistant；
-通用 Workflow Engine；
-多 Agent 调度；
-Web 管理后台。

### v1.0 验收标准

1. Coding 和 Research / OSINT 使用同一个 Kernel。
2. Kernel 不包含领域特例。
3. Markdown canonical store 可人工阅读和编辑。
4. SQLite Catalog 可完整重建。
5. 所有正式记忆具有来源和 revision。
6. 查询结果可解释。
7. 过期、取代、冲突和遗忘语义明确。
8. YAML Runtime 状态可以恢复。
9. CLI 和 MCP 使用同一 Application API。
10. 从 v0.5.x 有可重复迁移路径。
11. Windows、Linux 和 macOS 有基础兼容测试。
12. 真实项目持续使用后核心模型保持稳定。

---

# 8. 迁移策略

## 8.1 Legacy 文档兼容

现有文档不一次性重写。

采用：

```text
Legacy Markdown
      ↓
Legacy Document Adapter
      ↓
MemoryRecord View
```

文档在下次正式修改时，逐步补齐：

- memory ID；
-revision；
-status；
-scope；
-provenance；
-content hash。

---

## 8.2 迁移命令

```bash
pd migrate inspect
pd migrate plan
pd migrate apply
pd migrate verify
pd migrate rollback
```

要求：

- 默认 dry-run；
-显示文件 diff；
-不删除未知文件；
-每一步具有 migration ID；
-重复执行安全；
-失败后可回滚；
-输出迁移报告。

---

## 8.3 兼容周期

旧工具包装器至少保留两个次版本。

例如：

```text
v0.5.2：开始 deprecation
v0.6.x：继续兼容
v0.7.0：评估删除
```

删除前必须确认：

- 文档已迁移；
-CI 已使用新命令；
-真实项目不再依赖旧入口。

---

# 9. 测试体系

## 9.1 Unit Tests

覆盖：

- MemoryRecord；
-Scope；
-Provenance；
-Revision；
-Validity；
-Conflict；
-Write Policy；
-Retrieval；
-Markdown Codec；
-Atomic Writer；
-SQLite Catalog；
-Task State Machine；
-Research Claim。

---

## 9.2 Integration Tests

覆盖：

```text
Markdown → Catalog
propose → commit → query
revise → supersede
forget
catalog rebuild
task start → checkpoint → complete
claim → evidence → explain
CLI → Application API
MCP → Application API
```

---

## 9.3 Failure Injection

必须覆盖：

- 临时文件写入后崩溃；
-原子替换前崩溃；
-Markdown 成功但 Catalog 更新失败；
-SQLite 损坏；
-JSONL 最后一行不完整；
-两个进程同时修改同一 Memory；
-用户手工修改 Markdown；
-重复 idempotency key；
-YAML Runtime 状态损坏。

恢复原则：

```text
Canonical Markdown 优先
YAML Runtime 明确报错
Catalog 可重建
Audit 用于诊断
不得静默覆盖
```

---

## 9.4 Architecture Tests

禁止：

```text
kernel → integrations
kernel → adapters
storage → coding
storage → research
mcp → markdown implementation
```

允许：

```text
integrations → kernel
adapters → application
application → kernel
storage implements kernel contract
```

---

## 9.5 Golden Tests

对以下输出使用 Golden Files：

- Query Explanation；
-Context Manifest；
-Migration Plan；
-Catalog Schema；
-MCP Tool Schema；
-Research Claim Explanation；
-Agent Minimal Instructions。

---

# 10. CI 门禁

建议执行顺序：

```text
1. format
2. lint
3. type check
4. unit tests
5. architecture tests
6. integration tests
7. migration tests
8. failure injection tests
9. golden drift check
10. repository self-check
```

v0.6 后增加：

```text
11. catalog rebuild verification
12. canonical hash verification
```

v0.9 后增加：

```text
13. CLI / MCP parity
14. MCP schema validation
```

---

# 11. 开发节奏

## 11.1 单批次原则

每个 Batch 应满足：

- 目标单一；
-能够独立测试；
-能够独立回滚；
-不同时跨越多个架构层；
-完成后仓库仍可使用；
-不留下长期双实现。

---

## 11.2 合并规模

建议每个 Batch 拆分为 1–3 个 PR。

单个 PR 原则上只完成一种变化：

-纯测试；
-纯重构；
-纯模型；
-纯存储；
-纯 CLI；
-纯迁移。

避免在同一个 PR 中同时：

-重写 Parser；
-改变 Schema；
-修改目录；
-新增 CLI；
-迁移全部数据。

---

## 11.3 阶段停止点

每个 Phase 完成后暂停扩展，至少进行：

1. 自身仓库使用；
2. 一个外部测试 Workspace；
3. 故障注入；
4. 文档审查；
5. 数据迁移验证；
6. 技术债务清单更新。

只有退出门槛满足后才进入下一 Phase。

---

## 11.4 不提前实现

任何后续阶段能力不得仅为“将来可能需要”而提前建设。

特别禁止提前实现：

-通用 Profile SDK；
-通用 Policy DSL；
-通用 Lifecycle DSL；
-Event Projection Engine；
-Embedding Pipeline；
-远程 MCP；
-多租户；
-自动 Agent 长期写入。

---

# 12. 近期执行顺序

第一轮只启动 Phase 0。

建议顺序：

```text
Step 1
建立 characterization tests

Step 2
统一 YAML/frontmatter parser

Step 3
修复版本模型

Step 4
修复状态判断和归档事务

Step 5
调整索引职责

Step 6
运行完整回归和故障测试

Step 7
发布 v0.5.1
```

不建议在 v0.5.1 同时创建 MemoryRecord、SQLite Catalog 或 MCP。

v0.5.1 的成功标准不是增加新功能，而是：

> 现有 Paradigma 文档治理能力变得可靠、可测试、可迁移，并能够安全地承载后续 Memory Kernel 重构。

---

# 13. 近期里程碑

| 版本 | 核心成果 |
|---|---|
| v0.5.1 | 可靠化、统一 Parser、严格状态、原子写入 |
| v0.5.2 | Python Package、统一 CLI、兼容包装器 |
| v0.6.0 | 文档级 Memory Kernel、SQLite Catalog、完整记忆闭环 |
| v0.7.0 | Coding Task、Session、Checkpoint、Context Builder |
| v0.8.0 | Research / OSINT、Claim–Evidence–Source、检索评估 |
| v0.9.0 | 本地 stdio MCP Adapter |
| v0.9.x | Operation Contract 收敛 |
| v1.0 | 稳定 Memory Kernel 契约 |

---

# 14. 最终验收演示

Paradigma v1.0 应能够完成以下闭环：

```text
Agent 发现有长期价值的信息
        ↓
生成 Memory Candidate
        ↓
Paradigma 校验来源、作用域和风险
        ↓
根据分级政策自动提交或请求确认
        ↓
原子写入 OKF-compatible Markdown
        ↓
SQLite Catalog 更新
        ↓
新的 Agent Session 发起查询
        ↓
Paradigma 返回相关记忆和召回理由
        ↓
新证据出现
        ↓
创建新 Revision 或 Contradiction
        ↓
旧结论被 Supersede，但历史和证据仍可审计
