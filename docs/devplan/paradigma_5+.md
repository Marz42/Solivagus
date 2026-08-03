# Paradigma Agent Profile 架构与实施方案

**文档状态：** Proposal  
**建议目标版本：** v0.5.1–v1.0  
**首个 Profile：** `coding`  
**后续实验 Profile：** `personal_assistant`  
**知识存储：** OKF-compatible Markdown  
**运行方式：** Shared Core + Agent Profile + CLI + Harness Adapter

---

## 1. 背景与问题定义

Paradigma 当前被定位为一个 IDE 无关的 Agent 外部记忆运行框架，使用 `runtime/`、`logs/` 和 `knowledge/` 分离当前状态、过程记录与长期知识，并依靠 OKF-compatible Markdown、Agent Runtime Protocol 和确定性工具链维持一致性。当前仓库版本为 `0.5.0`，已包含 Cursor Rule、配置文件、Schema、RFC、Memory-Bank 模板以及七个独立 Python 工具。citeturn967349view0turn754196view0

当前架构实际上主要面向编程 Agent，其默认假设包括：

- Agent 工作发生在代码仓库内；
- 长期知识可以随 Git 提交；
- Context Routing 主要依赖文件、模块、符号和架构关系；
- 运行生命周期以任务、计划、会话和归档为中心；
- 工具主要是 lint、link check、index sync、archive 和 diagnose；
- Adapter 的主要目标是 Cursor 或其他编程工具。

与此同时，Paradigma 又具备向其他 Agent 领域扩展的潜力，例如日常助理、研究助理和 OSINT Agent。但这些 Agent 在生命周期、知识对象、权限、时间有效性、隐私和删除语义方面与编程 Agent 存在根本差异。

因此需要引入 Agent Profile，但不能立即建设一个过度通用、允许任意插件加载的复杂框架。

本方案采用以下总体策略：

> 现在建立 Agent Profile 的明确架构边界，只实现内部 `coding` Profile；待 Shared Core、Lifecycle、Context Builder 和 Adapter Contract 稳定后，再使用实验性的 `personal_assistant` Profile 验证抽象。

---

## 2. 实施目标

### 2.1 核心目标

本次实施需要实现以下目标：

1. 将编程 Agent 特有的领域语义从 Shared Core 中隔离出来。
2. 将当前零散脚本逐步收敛为可测试、可复用的 Core。
3. 建立一个内部、静态注册的 Agent Profile Contract。
4. 使用 `coding` Profile 承载代码仓库、Git、文件、符号、测试、Task Run 等语义。
5. 保持 OKF-compatible Markdown 为长期知识的 canonical representation。
6. 让 CLI 成为人类、Agent 和 Adapter 调用 Paradigma 的统一入口。
7. 让 Adapter 只负责平台映射，不复制状态机、Schema 和策略。
8. 将注入 LLM 的内容压缩为最小操作协议、工具定义和相关状态。
9. 为未来 Personal Assistant Profile 预留必要边界，但不提前实现其完整能力。
10. 保持现有 `0.5.0` 使用方式在迁移期内基本兼容。

### 2.2 非目标

当前阶段明确不实现：

- 第三方动态 Profile 插件；
- 同一工作区同时启用多个 Profile；
- Profile 之间的继承与组合；
- 向量数据库；
- Embedding 检索；
- 通用 RAG 服务；
- 模型调用循环；
- Shell、浏览器或代码执行沙箱；
- 多 Agent 调度；
- Web 管理后台；
- Personal Assistant 的隐私、加密和跨设备同步；
- 自动将所有 Agent 推断写入长期记忆。

---

## 3. 核心设计决策

### 3.1 一个工作区只启用一个 Agent Profile

首个版本规定：

```yaml
profile:
  active: coding
```

一个 Paradigma Workspace 只能启用一个 Profile。

不支持：

```yaml
profiles:
  - coding
  - personal_assistant
```

原因是不同 Profile 可能存在：

- 生命周期命令冲突；
- 数据作用域冲突；
- 默认写入政策冲突；
- 存储后端冲突；
- 权限模型冲突；
- Context Routing 冲突。

多 Profile 组合应当在至少两个真实 Profile 稳定后再设计。

### 3.2 Profile 是领域能力包，不是 Prompt 人设

Agent Profile 不表示模型的语气、人格或 System Prompt 风格。

Profile 表示：

- 该类 Agent 管理什么对象；
- 支持哪些生命周期；
- 使用哪些领域 Schema；
- 依赖哪些上下文信号；
- 执行哪些确定性政策；
- 向 Agent 暴露哪些操作；
- 使用哪些默认存储和保留规则。

因此：

```text
Coding Profile
≠ “你是一名资深程序员”
```

而是：

```text
Coding Profile
= Repository Scope
+ Task Lifecycle
+ Git Evidence
+ File/Symbol Routing
+ Coding Policies
+ Coding Operations
```

### 3.3 Profile 不直接依赖具体 Harness

`coding` Profile 不得直接生成 Cursor MDC、Claude Code Hook 或 Codex 指令。

正确关系为：

```text
Profile
   ↓
Agent Contract Manifest
   ↓
Adapter Compiler
   ↓
Cursor / Claude Code / Codex / MCP
```

Profile 负责定义语义；Adapter 负责将语义翻译成特定平台能够识别的形式。

### 3.4 Adapter 不是真相源

当前项目规定协议修改先更新 `AGENT_RULES.md`，再同步 IDE Adapter。citeturn967349view0turn700278view3

实施 Profile 后，应逐步改为：

```text
Core/Profile 中的机器可读定义
             ↓
生成 AGENT_RULES.md
             ↓
生成 Adapter 规则
```

最终：

- Profile Operation Specs 是操作真相源；
- Policy Definitions 是策略真相源；
- Lifecycle Definitions 是状态真相源；
- Schema Registry 是数据真相源；
- `AGENT_RULES.md` 是生成的人类可读投影；
- Cursor、Claude Code 等规则是 Adapter 产物。

### 3.5 LLM 只负责语义性工作

凡是能够由状态机、Schema、正则、文件系统、Git、静态分析或确定性脚本完成的操作，都不应要求 LLM 自觉执行。

LLM 适合负责：

- 理解用户任务；
- 判断任务涉及哪些领域；
- 生成代码或文档候选；
- 提取候选经验；
- 解释冲突；
- 生成候选摘要。

Core 负责：

- 状态是否合法；
- 文档格式是否合法；
- 是否允许写入；
- 是否需要审批；
- 是否满足完成条件；
- 哪些文档进入 Context；
- 哪些操作需要阻止；
- 写入是否具有原子性和幂等性。

---

## 4. 目标架构

```text
┌──────────────────────────────────────────────┐
│ External Agent Harness                       │
│ Cursor / Claude Code / Codex / IDE / MCP     │
└─────────────────────┬────────────────────────┘
                      │
      Instructions / Tool Schema / Context
                      │
┌─────────────────────▼────────────────────────┐
│ Adapter Layer                                │
│ - 平台能力探测                               │
│ - 指令渲染                                   │
│ - Tool Schema 映射                           │
│ - Hook 映射                                  │
│ - Context 注入                               │
│ - 错误结果转换                               │
└─────────────────────┬────────────────────────┘
                      │
              Structured Operations
                      │
┌─────────────────────▼────────────────────────┐
│ CLI / Application API                        │
│ - 参数解析                                   │
│ - JSON / Text 输出                           │
│ - Exit Code                                  │
│ - 用户确认                                   │
│ - 调用 Core                                  │
└─────────────────────┬────────────────────────┘
                      │
┌─────────────────────▼────────────────────────┐
│ Shared Core                                  │
│ - Config                                     │
│ - OKF Parser                                 │
│ - Schema Registry                            │
│ - Policy Engine                              │
│ - State Machine Engine                       │
│ - Event Store                                │
│ - Projection Engine                          │
│ - Context Planner                            │
│ - Transaction Layer                          │
│ - Diagnostics                                │
│ - Migration                                  │
└─────────────────────┬────────────────────────┘
                      │
              Profile Extension Points
                      │
┌─────────────────────▼────────────────────────┐
│ Coding Profile                               │
│ - Coding Schemas                             │
│ - Task/Session Lifecycle                     │
│ - Repository/Git Scope                       │
│ - File/Symbol Context Signals                │
│ - Test/Build Evidence                        │
│ - Coding Policies                            │
│ - Coding Operations                          │
└─────────────────────┬────────────────────────┘
                      │
┌─────────────────────▼────────────────────────┐
│ Repository Storage                           │
│ knowledge/  OKF canonical knowledge          │
│ logs/       append-only events/history       │
│ runtime/    generated current projections    │
│ Git         versioning/audit for coding       │
└──────────────────────────────────────────────┘
```

---

## 5. Shared Core 与 Profile 的责任边界

### 5.1 Shared Core 负责的内容

Shared Core 只包含领域中立能力。

| 能力 | Core 职责 |
|---|---|
| 配置 | 加载、合并、校验配置 |
| OKF | 解析 Markdown 和 YAML frontmatter |
| Schema | 注册、查找和执行 Schema 校验 |
| Policy | 执行确定性规则，汇总 Policy Decision |
| Lifecycle | 通用状态机、状态迁移、并发和幂等控制 |
| Event | 追加事件、校验事件结构、读取事件流 |
| Projection | 从事件构建当前状态 |
| Context | 执行候选合并、关系扩展、预算裁剪 |
| Transaction | 原子写入、临时文件、锁和失败恢复 |
| Diagnostics | 聚合检查结果和错误代码 |
| Migration | 配置、Schema 和目录迁移 |
| Result | 返回统一结构化 Operation Result |

Core 不应直接理解：

- Git branch；
- commit；
- repository；
- code symbol；
- test；
- build；
- pull request；
- 用户敏感信息；
-联系人；
-日历；
-健康数据。

### 5.2 Coding Profile 负责的内容

| 能力 | Coding Profile 职责 |
|---|---|
| Scope | repository、branch、worktree、module、path、symbol |
| Lifecycle | PlanRun、TaskRun、CodingSession、Checkpoint |
| Context | 文件路径、符号、Git diff、测试和依赖信号 |
| Evidence | test result、lint result、build result、commit state |
| Policies | 完成条件、工作区状态、受保护架构文档 |
| Schema | architecture、ADR、repository contract、coding task |
| Operations | task start/complete、session checkpoint 等 |
| Adapter Contract | 编程 Agent 最小操作指令 |

### 5.3 Adapter 负责的内容

| 能力 | Adapter 职责 |
|---|---|
| 平台指令 | 将通用操作规则渲染成平台规则格式 |
| 工具暴露 | 映射 CLI、MCP 或 function calling |
| Hook | 将会话开始、工具执行后、会话结束映射到 Paradigma |
| Context | 把 Context Manifest 中选定的内容提供给模型 |
| Error | 把结构化错误变成 Agent 可处理的 Observation |
| Capability | 检测平台是否支持 Hook、Tool Call、动态 Context 等 |

Adapter 不得：

- 自行判断 Task 是否允许完成；
- 自行解析 OKF；
- 自行决定哪些知识受保护；
- 自行实现任务状态机；
- 自行修改 canonical knowledge；
- 复制 Profile Schema。

---

## 6. Profile Contract 设计

### 6.1 不采用单一巨型接口

不建议设计如下接口：

```python
class AgentProfile:
    def everything(...):
        ...
```

这种接口会迅速变成 God Object。

建议 Profile 是多个能力组件组成的不可变 Bundle。

### 6.2 ProfileDescriptor

```python
from dataclasses import dataclass
from typing import Mapping

@dataclass(frozen=True)
class ProfileDescriptor:
    profile_id: str
    display_name: str
    profile_version: str
    contract_version: str
    description: str
    experimental: bool
    metadata: Mapping[str, str]
```

首个 Coding Profile：

```python
ProfileDescriptor(
    profile_id="coding",
    display_name="Coding Agent",
    profile_version="0.1",
    contract_version="0.1",
    description="Repository-aware profile for coding agents.",
    experimental=False,
    metadata={},
)
```

### 6.3 ProfileBundle

```python
@dataclass(frozen=True)
class ProfileBundle:
    descriptor: ProfileDescriptor
    schema_providers: tuple["SchemaProvider", ...]
    lifecycle_providers: tuple["LifecycleProvider", ...]
    policy_providers: tuple["PolicyProvider", ...]
    context_providers: tuple["ContextSignalProvider", ...]
    operation_providers: tuple["OperationProvider", ...]
    projection_providers: tuple["ProjectionProvider", ...]
```

Profile 本身不执行文件写入；它提供规则和定义，Core 执行这些定义。

### 6.4 SchemaProvider

```python
class SchemaProvider(Protocol):
    def schemas(self) -> tuple[SchemaDefinition, ...]:
        ...

    def validate_profile_config(
        self,
        config: Mapping[str, object],
    ) -> tuple[ValidationIssue, ...]:
        ...
```

Coding Profile 注册：

- `paradigma-project-brief`
- `paradigma-architecture`
- `paradigma-contract`
- `paradigma-adr`
- `paradigma-plan`
- `paradigma-coding-domain`
- `paradigma-coding-manual`

首期不必修改全部现有 `type` 名称，可以先将现有类型映射到 `coding` Profile。

### 6.5 LifecycleProvider

```python
class LifecycleProvider(Protocol):
    def definitions(self) -> tuple[LifecycleDefinition, ...]:
        ...
```

示例：

```python
LifecycleDefinition(
    entity_type="coding.task_run",
    initial_state="pending",
    terminal_states={"completed", "aborted"},
    transitions={
        ("pending", "start"): "active",
        ("active", "block"): "blocked",
        ("blocked", "unblock"): "active",
        ("active", "suspend"): "suspended",
        ("suspended", "resume"): "active",
        ("active", "complete"): "completed",
        ("active", "abort"): "aborted",
        ("blocked", "abort"): "aborted",
        ("suspended", "abort"): "aborted",
    },
)
```

非法迁移必须由 Core 拒绝，例如：

```text
completed → active
```

如需重新开启，必须使用单独的 `reopen` 语义并创建明确事件，或者创建新的 Task Run。

### 6.6 PolicyProvider

```python
class PolicyProvider(Protocol):
    def rules(self) -> tuple[PolicyRule, ...]:
        ...
```

策略输入必须结构化：

```python
PolicyContext(
    operation="coding.task.complete",
    actor=...,
    entity=...,
    workspace=...,
    evidence=...,
)
```

策略输出：

```python
PolicyDecision(
    allowed=False,
    violations=[
        PolicyViolation(
            code="CODING_TEST_EVIDENCE_MISSING",
            message="No required test evidence was recorded.",
            severity="error",
            remediation="Run required tests and attach results.",
        )
    ],
)
```

Core 只负责执行规则、合并结果和阻止非法操作。

### 6.7 ContextSignalProvider

```python
class ContextSignalProvider(Protocol):
    def extract_signals(
        self,
        request: ContextRequest,
        workspace: WorkspaceSnapshot,
    ) -> tuple[ContextSignal, ...]:
        ...
```

Coding Profile 可产生：

```text
file_path
directory
symbol
module
git_diff_path
test_name
error_signature
task_tag
repository_domain
```

例如：

```python
ContextSignal(
    kind="symbol",
    value="ContextPlanner",
    source="user_request",
    weight=1.0,
)
```

Core 负责：

1. 合并信号；
2. 查询 OKF metadata；
3. 查找 hints、symbols 和 relations；
4. 去重；
5. 过滤 deprecated；
6. 应用 Policy；
7. 按预算裁剪；
8. 生成 Context Manifest。

### 6.8 OperationProvider

Operation 是提供给 CLI 和 Adapter 的统一动作定义。

```python
class OperationProvider(Protocol):
    def operations(self) -> tuple[OperationSpec, ...]:
        ...
```

示例：

```python
OperationSpec(
    operation_id="coding.task.start",
    cli_path=("task", "start"),
    description="Start a coding task run.",
    input_schema=...,
    output_schema=...,
    mutates_state=True,
    confirmation="never",
    idempotency="supported",
)
```

通过 OperationSpec 可以同时生成：

- CLI 命令；
- JSON Schema；
- MCP Tool；
- Harness Tool Definition；
- Agent 操作说明；
- 文档索引。

---

## 7. Profile 注册和加载

### 7.1 首期采用静态注册

首期不允许从任意路径动态 import Profile。

```python
BUILTIN_PROFILES = {
    "coding": load_coding_profile,
}
```

加载流程：

```text
读取 config.yaml
    ↓
取得 profile.active
    ↓
在 BUILTIN_PROFILES 中查找
    ↓
检查 contract_version
    ↓
加载 ProfileBundle
    ↓
注册 Schema/Lifecycle/Policy/Operation
```

未知 Profile 应返回明确错误：

```json
{
  "success": false,
  "error": {
    "code": "PROFILE_NOT_SUPPORTED",
    "message": "Profile 'personal_assistant' is not supported by this build."
  }
}
```

### 7.2 暂不使用 Python Entry Points

暂不支持：

```python
importlib.metadata.entry_points(group="paradigma.profiles")
```

原因包括：

- 未建立 Profile 权限边界；
- 未建立第三方代码信任模型；
- Profile 可执行任意 Python；
- Contract 尚未经过第二个真实 Profile 验证；
- 版本兼容矩阵尚不稳定。

---

## 8. 配置与版本模型

### 8.1 当前问题

当前 `VERSION` 表示 `0.5.0`，但 `.paradigma/config.yaml` 仍记录 `paradigma_harness_version: "0.4.2"`。citeturn967349view1turn967349view4

配置、发行版本和 Profile 版本应分离。

### 8.2 新配置结构

建议 `.paradigma/config.yaml`：

```yaml
config_schema_version: "0.2"
okf_version: "0.1"

profile:
  active: coding
  schema_version: "0.1"

knowledge:
  roots:
    - memory-bank/knowledge
    - docs/rfc
  reserved_filenames:
    - index.md
    - log.md

runtime:
  root: memory-bank/runtime
  event_root: memory-bank/logs/events
  projection_mode: generated

templates:
  root: memory-bank-template

context:
  default_profile: standard
  budgets:
    quick: 4000
    standard: 12000
    deep: 24000
```

### 8.3 新增 lock 文件

建议增加 `.paradigma/lock.yaml`：

```yaml
distribution_version: "0.6.0"
profile_contract_version: "0.1"

profiles:
  coding: "0.1"

adapters:
  cursor: "0.2"

generated_at: "2026-07-20T00:00:00Z"
```

职责划分：

- 根目录 `VERSION`：Paradigma 源码仓库发行版本；
- `config.yaml`：用户配置；
- `lock.yaml`：当前工作区实际部署的 Paradigma、Profile 和 Adapter 版本；
- 文档中的 `schema_version`：文档 Schema 版本。

### 8.4 兼容策略

迁移期内：

- 缺少 `profile.active` 时，默认解释为 `coding`；
- CLI 输出 deprecation warning；
- `pd migrate --to-config-schema 0.2` 自动补齐；
- 到下一个重大兼容节点后，缺少 Profile 视为错误。

---

## 9. 目标代码结构

### 9.1 框架开发仓库

```text
paradigma/
├── pyproject.toml
├── VERSION
├── src/
│   └── paradigma/
│       ├── core/
│       │   ├── config.py
│       │   ├── results.py
│       │   ├── errors.py
│       │   ├── okf/
│       │   │   ├── parser.py
│       │   │   ├── document.py
│       │   │   └── writer.py
│       │   ├── schemas/
│       │   │   ├── registry.py
│       │   │   └── validator.py
│       │   ├── policies/
│       │   │   ├── engine.py
│       │   │   └── models.py
│       │   ├── lifecycle/
│       │   │   ├── engine.py
│       │   │   ├── definition.py
│       │   │   └── transition.py
│       │   ├── events/
│       │   │   ├── store.py
│       │   │   ├── models.py
│       │   │   └── jsonl.py
│       │   ├── projections/
│       │   │   ├── engine.py
│       │   │   └── store.py
│       │   ├── context/
│       │   │   ├── planner.py
│       │   │   ├── manifest.py
│       │   │   ├── signals.py
│       │   │   └── budget.py
│       │   ├── transactions/
│       │   │   ├── atomic_write.py
│       │   │   └── lock.py
│       │   └── migrations/
│       │       ├── runner.py
│       │       └── registry.py
│       │
│       ├── profiles/
│       │   ├── contract.py
│       │   ├── registry.py
│       │   └── coding/
│       │       ├── profile.py
│       │       ├── descriptor.py
│       │       ├── schemas.py
│       │       ├── lifecycle.py
│       │       ├── policies.py
│       │       ├── context.py
│       │       ├── operations.py
│       │       └── projections.py
│       │
│       ├── cli/
│       │   ├── main.py
│       │   ├── output.py
│       │   ├── exit_codes.py
│       │   └── commands/
│       │
│       └── adapters/
│           ├── contract.py
│           ├── manifest.py
│           ├── cursor/
│           └── generic_cli/
│
├── templates/
│   └── coding/
│       ├── memory-bank-template/
│       ├── config.yaml
│       └── adapter-templates/
│
├── tests/
│   ├── unit/
│   ├── contract/
│   ├── integration/
│   ├── migration/
│   ├── conformance/
│   └── fixtures/
│
└── .paradigma/
    └── tools/
        ├── pd-check-all.py
        └── compatibility wrappers
```

### 9.2 兼容包装器

现有命令暂时保留：

```bash
python .paradigma/tools/pd-check-all.py
```

但内部改为：

```python
from paradigma.cli.main import main

if __name__ == "__main__":
    raise SystemExit(main(["check", "all"]))
```

包装器不再包含领域逻辑。

### 9.3 用户项目结构

长期建议用户项目不再复制整个框架源码，只保留：

```text
user-project/
├── .paradigma/
│   ├── config.yaml
│   ├── lock.yaml
│   └── generated/
│       └── adapters/
├── memory-bank/
├── memory-bank-template/
└── project source
```

Paradigma CLI 作为固定版本工具安装或由项目工具环境提供。

在公开 Package 之前，可暂时保留 repo-local runtime，但应把该方式视为过渡方案。

---

## 10. Coding Profile 数据模型

### 10.1 RepositoryScope

```python
@dataclass(frozen=True)
class RepositoryScope:
    repository_id: str
    root: str
    branch: str | None
    worktree: str | None
    paths: tuple[str, ...]
    symbols: tuple[str, ...]
```

### 10.2 CodingTaskRun

```python
@dataclass(frozen=True)
class CodingTaskRun:
    task_id: str
    title: str
    status: str
    repository_scope: RepositoryScope
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    acceptance_criteria: tuple[str, ...]
    required_evidence: tuple[str, ...]
```

### 10.3 CodingSession

```python
@dataclass(frozen=True)
class CodingSession:
    session_id: str
    task_id: str
    started_at: datetime
    ended_at: datetime | None
    base_commit: str | None
    head_commit: str | None
    touched_paths: tuple[str, ...]
```

### 10.4 Checkpoint

```python
@dataclass(frozen=True)
class CodingCheckpoint:
    checkpoint_id: str
    task_id: str
    session_id: str
    created_at: datetime
    summary: str
    completed_steps: tuple[str, ...]
    remaining_steps: tuple[str, ...]
    blocked_by: tuple[str, ...]
    validation_results: tuple[str, ...]
```

Checkpoint 中的摘要可以由 LLM 生成候选，但以下字段应由工具确定：

- task ID；
- session ID；
- Git commit；
- changed files；
- test result；
- current state；
- timestamp。

---

## 11. 事件与投影

### 11.1 Event Log 是运行事实源

建议使用 JSONL：

```json
{"event_id":"EV-001","type":"coding.task_started","entity_id":"TASK-023","at":"2026-07-20T10:00:00Z"}
{"event_id":"EV-002","type":"coding.session_started","entity_id":"S-041","task_id":"TASK-023","at":"2026-07-20T10:01:00Z"}
{"event_id":"EV-003","type":"coding.checkpoint_created","entity_id":"CP-004","task_id":"TASK-023","at":"2026-07-20T11:00:00Z"}
```

### 11.2 Runtime Markdown 是投影

以下文件应由工具生成：

```text
memory-bank/runtime/active-task.md
memory-bank/runtime/current-session.md
memory-bank/runtime/handoff.md
```

模型不应直接修改 generated block。

### 11.3 事件写入要求

每次写入必须满足：

- 使用唯一 event ID；
- 追加写；
- 支持 idempotency key；
- 对同一 aggregate 使用文件锁；
- 先写事件，再更新投影；
- 投影失败时可由事件重建；
- 不允许只修改投影、不记录事件。

---

## 12. Context Builder 与 Profile 的关系

### 12.1 ContextRequest

```python
@dataclass(frozen=True)
class ContextRequest:
    intent: str
    operation_id: str | None
    entity_id: str | None
    explicit_paths: tuple[str, ...]
    explicit_symbols: tuple[str, ...]
    user_keywords: tuple[str, ...]
    budget_tokens: int
    mode: str
```

### 12.2 Coding Profile 信号提取

Coding Profile 根据以下信息生成 Context Signal：

- 用户请求；
- 当前 Task；
- Git diff；
- touched paths；
-显式文件；
-显式符号；
-错误输出；
-测试名称；
-当前 repository；
-当前 branch；
-当前 Plan；
-已有 checkpoint。

### 12.3 Core 的确定性处理流程

```text
ContextRequest
    ↓
Profile Signal Extraction
    ↓
Mandatory Documents
    ↓
Metadata/Hint/Symbol Matching
    ↓
Relation Expansion
    ↓
Validity/Lifecycle Filter
    ↓
Policy Filter
    ↓
Deduplication
    ↓
Token Budget Trim
    ↓
Context Manifest
```

### 12.4 Context Manifest

```yaml
manifest_version: "0.1"
profile: coding
task_id: TASK-023
mode: standard
budget_tokens: 12000
estimated_tokens: 8450

documents:
  - path: memory-bank/knowledge/architecture.md
    priority: required
    reasons:
      - mandatory_hot_document
      - relation_from: TASK-023

  - path: memory-bank/knowledge/domains/tooling.md
    priority: required
    reasons:
      - path_match: .paradigma/tools/
      - symbol_match: ContextPlanner

excluded:
  - path: memory-bank/knowledge/manuals/design-wizard.md
    reason: budget_trimmed

warnings: []
```

同一个 Request 和同一个仓库状态应产生相同 Manifest，不应因所使用的模型不同而变化。

---

## 13. Agent Contract Manifest

Profile 不直接生成 Prompt，而是输出统一 Manifest。

```yaml
contract_version: "0.1"
profile: coding

mandatory_instructions:
  - id: start-task
    text: Start or resume a Paradigma task before making substantial changes.
  - id: context-build
    text: Use the provided context operation rather than scanning the entire memory bank.
  - id: protected-knowledge
    text: Do not directly mutate protected canonical knowledge.
  - id: complete-task
    text: Complete a task through the Paradigma operation and address returned violations.

operations:
  - id: coding.task.start
    mutates_state: true
  - id: coding.task.complete
    mutates_state: true
  - id: core.context.build
    mutates_state: false
```

Adapter 根据平台能力决定：

- 渲染为静态规则；
- 暴露为 native tool；
- 暴露为 Shell 命令；
- 注册 session hook；
- 将返回结果放入 Observation。

### 13.1 Prompt 长度控制

建议验收目标：

- Adapter 固定指令控制在约 800 tokens 以内；
- 不在 Prompt 中列举完整 Schema；
- 不在 Prompt 中复制状态迁移表；
- 不在 Prompt 中解释索引生成算法；
- 不要求模型手工维护 checksum；
- 不要求模型判断合法状态；
- 所有可查询细节通过工具按需返回。

---

## 14. CLI 设计

### 14.1 Core CLI

```bash
pd version
pd config validate
pd profile show
pd profile validate
pd check
pd diagnose
pd migrate
pd context build
pd context explain
pd knowledge validate
```

### 14.2 Coding Profile CLI

```bash
pd task start
pd task status
pd task block
pd task unblock
pd task suspend
pd task resume
pd task complete
pd task abort

pd session start
pd session status
pd session checkpoint
pd session end

pd plan status
pd handoff build
```

### 14.3 输出格式

所有命令支持：

```bash
pd task status
pd task status --format json
```

结构化返回格式：

```json
{
  "success": true,
  "operation": "coding.task.status",
  "result": {},
  "warnings": [],
  "metadata": {
    "profile": "coding",
    "profile_version": "0.1"
  }
}
```

### 14.4 建议退出码

| Exit Code | 含义 |
|---:|---|
| 0 | 成功 |
| 2 | 输入或 Schema 校验失败 |
| 3 | Policy 拒绝 |
| 4 | 非法状态迁移或并发冲突 |
| 5 | 配置错误 |
| 6 | Profile 不支持或不兼容 |
| 7 | 存储或事务错误 |
| 8 | Adapter 生成错误 |
| 10 | 未预期内部错误 |

---

## 15. AGENT_RULES 与 Adapter 迁移

### 15.1 第一阶段

`AGENT_RULES.md` 继续作为协议文档，但开始标记：

```text
部分规则将由 Profile Contract 生成。
禁止在新 Adapter 中复制未结构化的业务规则。
```

### 15.2 第二阶段

将规则拆分为：

```text
Profile Operation Specs
Profile Policy Definitions
Lifecycle Definitions
Adapter Rendering Templates
```

新增：

```bash
pd agent-contract build
pd adapter generate cursor
pd adapter check cursor
```

### 15.3 第三阶段

`AGENT_RULES.md` 变为 generated document：

```markdown
<!-- BEGIN PARADIGMA GENERATED AGENT CONTRACT -->
...
<!-- END PARADIGMA GENERATED AGENT CONTRACT -->
```

人工内容只能写在 generated block 之外。

### 15.4 Adapter Drift 检查

CI 执行：

```bash
pd adapter check --all
```

如生成结果与仓库内容不一致，则失败。

---

## 16. 分阶段实施路线

# Phase 0：Profile 架构冻结与基线修复

**建议版本：v0.5.1**

### 目标

在不改变现有用户行为的情况下，冻结 Profile 边界并修复当前自洽性问题。

### 工作项

1. 新增 RFC：
   - Core–CLI–Adapter Architecture；
   - Agent Profile Contract；
   - Runtime Event and Projection Model；
   - Context Manifest。

2. 在配置中增加：

```yaml
profile:
  active: coding
  schema_version: "0.1"
```

3. 缺省 Profile 暂时解释为 `coding`。

4. 修复 `VERSION` 和 `paradigma_harness_version` 分裂。

5. 引入 `.paradigma/lock.yaml`。

6. 修复已完成 active task 未归档问题。

7. 修正根索引递归膨胀。

8. 将自然语言状态识别改为严格状态枚举。

9. 明确 Coding-specific 清单：
   - repository；
   - Git；
   - branch；
   - symbol；
   - test；
   - task；
   - checkpoint。

10. 为后续重构建立 characterization tests，锁定当前脚本行为。

### 退出条件

- 当前全部工具行为有基础回归测试；
- 配置可识别 `coding`；
- 未知 Profile 会失败；
- 版本信息一致；
- 无行为破坏；
- RFC 获得确认。

---

# Phase 1：Shared Core 提取

**建议版本：v0.6.0**

### 目标

将独立 Python 脚本中的重复逻辑提取为 Core。

### 推荐提取顺序

1. `errors.py` 和 `results.py`
2. Config Loader
3. Frontmatter/OKF Parser
4. Schema Registry
5. Link Graph
6. Atomic Writer
7. Diagnostics Aggregator
8. CLI Output
9. 旧脚本包装器

### 工作项

- 使用标准 YAML 解析库；
- 消除各脚本中的自定义重复解析器；
- 所有 Core 方法返回对象，不直接 `print`；
- 所有写操作支持 `--dry-run`；
- 原子替换文件；
- 临时目录集成测试；
- Windows 和 POSIX 路径测试；
- 保留旧命令入口。

### 退出条件

- 现有脚本不再自行解析 YAML；
- `pd-check-all.py` 只是聚合入口；
- Core 单元测试覆盖主要失败路径；
- 异常中断不会产生半写文件；
- 无 Coding Profile 动态插件能力。

---

# Phase 2：内部 Coding Profile

**建议版本：v0.7.0**

### 目标

将编程领域逻辑正式迁移到内部 `coding` Profile。

### 工作项

1. 建立 `ProfileDescriptor`。
2. 建立 `ProfileBundle`。
3. 建立静态 `ProfileRegistry`。
4. 将编程文档类型注册移入 Coding Profile。
5. 将 repository、branch、path、symbol 规则移入 Coding Profile。
6. 将 Task 状态机移入 Coding Profile。
7. 将测试、Git 和完成证据策略移入 Coding Profile。
8. 新增：
   - `pd profile show`
   - `pd profile validate`
9. 增加 Core 泄漏检查：
   - Core 中禁止 import `git`；
   - Core 中禁止出现 `repository`、`symbol` 等领域模型；
   - 通过架构测试检查模块依赖方向。

### 退出条件

- Core 在不加载 Coding Profile 时仍可独立 import；
- Coding Profile 通过 Profile Contract 测试；
- 所有现有用户操作由 Coding Profile 提供；
- CLI 行为保持兼容；
- 未引入 Personal Assistant 代码。

---

# Phase 3：确定性 Lifecycle

**建议版本：v0.7.x 或 v0.8.0 前半**

### 目标

将任务纪律从 Prompt 迁移到状态机、事件和 Policy。

### 工作项

- CodingTaskRun 状态机；
- CodingSession；
- Checkpoint；
- JSONL Event Store；
- Runtime Projection；
- 自动生成 active-task；
- 自动生成 handoff；
- task suspend/resume；
- event replay；
- 幂等操作；
- 并发文件锁；
- completion evidence。

### 退出条件

- 新会话能够从事件和投影恢复；
- 不需要扫描全部 progress log；
- LLM 无法通过直接调用官方工具制造非法状态；
- Task complete 必须通过 Policy；
- Handoff 不再要求模型手工维护。

---

# Phase 4：确定性 Context Builder

**建议版本：v0.8.0**

### 目标

实现 OKF-only、可解释、可复现的上下文装配。

### 工作项

- ContextRequest；
- ContextSignal；
- ContextManifest；
- Coding path matcher；
- symbol matcher；
- relation expansion；
- lifecycle filter；
- budget trim；
- quick/standard/deep 模式；
- context explain；
- manifest checksum；
- Context Golden Tests。

### 退出条件

- 同一输入产生相同 Manifest；
- 每个文档都有选择理由；
- 根索引不随知识总量无限膨胀；
- 不依赖 embedding；
- 必要知识召回率达到预设目标；
- 默认 Context Token 明显低于全量 HOT 加载。

---

# Phase 5：Adapter Contract

**建议版本：v0.9.0**

### 目标

让不同 Harness 使用同一 Profile 操作和 Context。

### 工作项

- Agent Contract Manifest；
- Adapter Capability Manifest；
- Generic CLI Adapter；
- Cursor Adapter 重构；
- 第二个编程 Harness Adapter；
- Adapter Generator；
- Adapter Drift Check；
- Adapter Parity Scenarios。

### 退出条件

- Cursor Adapter 不再包含状态机；
- 两个 Harness 对同一操作产生等价 Core 调用；
- Adapter 中没有重复 Schema；
- 固定 Prompt 达到长度预算；
- CLI/MCP/Tool Schema 使用统一 OperationSpec。

---

# Phase 6：Coding Profile 稳定化

**建议版本：v0.9.x–v1.0**

### 目标

在真实仓库中验证 Coding Profile。

### 稳定门槛

- 至少多个真实仓库持续使用；
- 多种模型完成同一 Conformance Scenario；
- suspend/resume 恢复稳定；
- Context Recall 和 Precision 可测；
- 配置迁移可回滚；
- starter 与框架开发仓库分离；
- Profile Contract 内部稳定；
- Core 不含明显 Coding-only 假设；
- 发布正式 migration guide。

---

# Phase 7：Personal Assistant 实验 Profile

**建议时间：Coding Profile 接近或达到 v1.0 后**

实验范围只包括：

- 用户明确偏好；
-长期目标；
-临时计划；
-记忆确认；
-时间有效性；
-真实删除；
-敏感性等级。

该 Profile 用于验证：

- 非 Git Storage Backend；
- 非 Task Lifecycle；
- Consent Policy；
- Retention；
- Delete Semantics；
- Entity/Time Context Routing。

此阶段仍不接入：

- 邮件；
-日历；
-健康；
-财务；
-联系人；
-第三方隐私；
-跨设备同步。

只有该实验 Profile 成功后，才冻结公共 Profile SDK。

---

## 17. 测试体系

### 17.1 Unit Tests

覆盖：

- Config；
- YAML/frontmatter；
- Schema；
- Lifecycle；
- Policy；
- Context signals；
-预算；
-原子写入；
-事件追加；
-投影重建。

### 17.2 Profile Contract Tests

每个 Profile 必须通过：

```text
descriptor_valid
schema_ids_unique
operation_ids_unique
lifecycle_ids_unique
all_operations_have_input_schema
all_mutating_operations_declare_idempotency
all_states_reachable
terminal_states_have_no_implicit_outgoing_transition
policies_return_stable_error_codes
context_providers_are_deterministic
```

### 17.3 Conformance Scenarios

建议建立：

```text
01-bootstrap-coding-workspace
02-start-new-task
03-resume-existing-task
04-suspend-and-switch-task
05-reject-illegal-transition
06-complete-without-test-evidence
07-create-checkpoint
08-rebuild-runtime-projection
09-build-context-from-symbol
10-build-context-from-diff
11-protected-knowledge-edit
12-adapter-parity
13-migrate-from-0.5
14-crash-during-event-write
15-profile-not-supported
```

### 17.4 Golden Tests

Context Manifest、Agent Contract Manifest 和 Adapter 输出使用 Golden File。

任何变化必须明确审查，而不是自动覆盖。

### 17.5 Model-in-the-loop Tests

模型测试不应进入基础正确性门禁，只用于测量 Harness 行为差异。

建议记录：

- 模型是否主动调用 `task start`；
- 是否遵守 Context Manifest；
- 是否绕过 protected knowledge；
- 是否正确处理 Policy rejection；
- 是否在换会话后恢复；
- 所需 Prompt tokens；
- 用户纠正次数。

---

## 18. CI 门禁

建议 CI 顺序：

```text
1. format/lint
2. type check
3. unit tests
4. profile contract tests
5. migration tests
6. conformance tests
7. generated artifact drift
8. current repository pd check
```

PR 必须阻断：

- Core import Coding Profile；
- Adapter 包含状态机常量；
- generated Adapter 未同步；
-非法 Schema；
-非法状态迁移；
- Profile Contract 版本不兼容；
-配置迁移缺失；
-投影与事件不一致。

---

## 19. 可观测性与审计

每次 CLI 操作建议记录：

```json
{
  "operation_id": "coding.task.complete",
  "operation_run_id": "OP-...",
  "profile": "coding",
  "profile_version": "0.1",
  "actor": "agent",
  "started_at": "...",
  "finished_at": "...",
  "success": false,
  "policy_violations": ["CODING_TEST_EVIDENCE_MISSING"]
}
```

注意区分：

- 操作日志；
- Agent 对话；
-长期知识；
-运行事件。

不应将完整 Chain of Thought 保存为 Paradigma Memory。

---

## 20. 迁移策略

### 20.1 从 0.5.0 迁移

新增命令：

```bash
pd migrate plan
pd migrate apply
pd migrate verify
```

迁移步骤：

1. 备份 `.paradigma/` 和 `memory-bank/`；
2. 读取旧配置；
3. 创建 `lock.yaml`；
4. 增加 `profile.active: coding`；
5. 标记现有 Schema 属于 Coding Profile；
6. 保留旧工具包装器；
7. 检查 active-task；
8. 重新生成 index；
9. 运行全量校验；
10. 生成迁移报告。

### 20.2 迁移要求

- 默认 dry-run；
- 显示文件 diff；
- 不自动删除未知文件；
- 可重复执行；
- 每一步有 migration ID；
- 失败后可回滚；
- 迁移完成写入 lock；
- 支持 `--format json`。

---

## 21. 风险与控制

### 风险一：过早抽象

**表现：** 为 Personal Assistant 设计大量当前没有用到的接口。

**控制：**

- 只实现 Coding Profile；
- Contract 标记 internal；
- 不公开动态插件；
- 第二个 Profile 出现前不承诺稳定 API。

### 风险二：Coding 语义泄漏到 Core

**表现：** Core 中出现 Git、repository、symbol、test。

**控制：**

- 架构依赖测试；
- Core 禁止 import Profile；
- Coding-specific 类型只能位于 `profiles/coding`。

### 风险三：Profile 成为另一套 Prompt 模板

**表现：** Profile 只包含长篇规则文本。

**控制：**

- Profile 必须提供机器可读 Schema、Lifecycle、Policy 和 Operation；
- Prompt 是 Manifest 的投影；
- Prompt 不能是唯一执行机制。

### 风险四：Adapter 逻辑分叉

**表现：** Cursor、Claude、Codex 各自实现任务完成规则。

**控制：**

- Adapter 只能调用 Operation；
- Adapter Golden Tests；
- Adapter Drift Check；
- Adapter Parity Scenario。

### 风险五：兼容层长期不删除

**控制：**

- 为旧脚本定义 deprecation schedule；
- 新文档只使用 `pd` CLI；
- 统计旧入口使用情况；
- 在重大版本删除包装器。

### 风险六：Profile Contract 过于庞大

**控制：**

- 使用多个 Provider；
- 不使用 God Interface；
- Profile 通过组合构建；
- 每个 Provider 只负责一种扩展点。

---

## 22. 建议工程批次

以下是单人配合 Coding Agent 的粗略工程量，用于排序，不作为交付承诺。

| 批次 | 内容 | 参考规模 |
|---|---|---:|
| A | RFC、配置和版本自洽 | 2–4 个工程日 |
| B | Core Parser/Config/Result 提取 | 4–7 个工程日 |
| C | Schema、Policy 和 Profile Registry | 4–6 个工程日 |
| D | Coding Lifecycle/Event/Projection | 6–10 个工程日 |
| E | Context Builder | 6–10 个工程日 |
| F | Adapter Contract 与 Cursor 重构 | 5–8 个工程日 |
| G | Migration、Conformance、稳定化 | 5–10 个工程日 |

实施时应按小批次合并，每批保持：

- 测试通过；
- 当前仓库可用；
- 旧命令兼容；
- 文档同步；
- 可独立回滚。

---

## 23. 最终验收标准

Agent Profile 第一阶段实施完成，应同时满足：

1. 配置明确声明 `profile.active: coding`。
2. Profile 通过静态 Registry 加载。
3. Core 不包含 repository、Git、symbol、test 等编程语义。
4. Coding Profile 注册 Schema、Lifecycle、Policy、Context 和 Operation。
5. CLI 从 Profile 中发现命令。
6. Adapter 从 Agent Contract Manifest 生成规则。
7. Prompt 不再承担状态机和 Schema 校验。
8. Task 生命周期由 Core 强制执行。
9. Context Builder 不依赖模型和 embedding。
10. 同一 Context Request 产生确定性 Manifest。
11. Runtime 投影可由事件重建。
12. 旧 `pd-*.py` 脚本仅为兼容包装器。
13. 从 0.5.0 有可重复、可回滚的迁移路径。
14. Coding Profile 通过全部 Contract Tests。
15. 未开放任意第三方 Profile 加载。
16. Personal Assistant Profile 尚未进入生产范围。
17. Shared Core 已为非 Git Storage、其他 Lifecycle 类型保留边界，但没有过度实现。
18. Paradigma 自身使用同一套 Coding Profile，并通过全部门禁。

---

## 24. 建议立即启动的首批任务

建议第一批只完成以下内容：

### Task 1：RFC 冻结

创建：

```text
docs/rfc/core-cli-adapter-architecture.md
docs/rfc/agent-profile-contract.md
docs/rfc/runtime-event-projection.md
docs/rfc/context-manifest.md
```

### Task 2：配置迁移

- 增加 `profile.active: coding`；
- 增加 `lock.yaml`；
- 修复版本真相源；
- 编写 config migration。

### Task 3：测试基线

在重构前，为现有七个工具建立 characterization tests。

### Task 4：Core Skeleton

创建：

```text
src/paradigma/core/
src/paradigma/profiles/
src/paradigma/cli/
src/paradigma/adapters/
```

暂不迁移全部逻辑。

### Task 5：最小 CodingProfile

仅实现：

- Descriptor；
- 静态 Registry；
- SchemaProvider；
- `pd profile show`；
- `pd profile validate`。

第一批不实现新 Lifecycle、Context Builder 或多 Adapter。

完成以上五项后，再进入 Core 提取和 Task Lifecycle，可以显著降低一次性重构风险。

---

## 25. 结论

Paradigma 引入 Agent Profile 的正确方式不是立刻建设一个通用插件生态，而是分三个成熟阶段：

```text
阶段一：架构边界
Shared Core + 固定 Coding Profile

阶段二：内部契约
Coding Profile 通过稳定的 Provider Contract 扩展 Core

阶段三：真实验证
使用 Personal Assistant Experimental Profile 检验通用性
```

近期最重要的目标是：

> 将目前隐含在编程 Agent Prompt、目录约定和独立脚本中的领域假设，明确迁移到内部 Coding Profile；同时让 Core 只保留确定性的通用机制。

当 Coding Profile 能稳定驱动 Task Lifecycle、Context Builder 和多个 Harness Adapter，并且第二个实验 Profile 无需大幅修改 Core 时，Paradigma 才具备公开 Profile SDK 的条件。