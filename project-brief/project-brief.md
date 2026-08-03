# PaddleOCR-VL + DeepSeek 技术文献翻译器项目方案

## 1. 项目概述

### 1.1 项目名称

暂定名称：

**Solivagus — 技术文献智能翻译 CLI**

### 1.2 项目目标

建立一个面向个人研究、技术阅读和批量文档处理的本地 PDF 翻译工具。系统使用 PaddleOCR-VL 完成 PDF 版面理解和结构化提取，使用 DeepSeek API 完成英文到简体中文的技术翻译，并输出适合 Obsidian、Markdown 阅读器和后续知识整理的中文及双语文档。

项目应优先满足以下目标：

1. 能可靠处理论文、技术报告和书籍级长文档。
2. 支持断点续跑和夜间无人值守。
3. 支持批量目录处理。
4. 利用 DeepSeek KV Cache 降低长文档翻译成本。
5. 利用 API 并发能力缩短整体处理时间。
6. 保留标题、段落、公式、代码、图片、页码和引用结构。
7. 单个页面、翻译单元或文档失败时，不阻塞整个批次。
8. 保持 CLI 产品形态，不建设 Web UI、服务端或多用户系统。

### 1.3 当前基础

当前 MVP 已经验证以下核心链路：

```text
PDF
→ PaddleOCR-VL
→ Markdown
→ 分块
→ OpenAI-compatible API 翻译
→ 中文 Markdown
→ 双语 Markdown
```

已验证：

* PaddleOCR-VL 可以在 RTX 4060 上运行；
* 普通技术 PDF 可以完成 OCR 和结构化提取；
* 翻译 Token 成本可接受；
* 中断后可以从翻译块继续；
* HTML 表格可以暂时整体保留，避免占位符导致任务停止；
* 单文件 CLI 能满足基本个人使用需求。

正式项目应在此基础上重构，不更换已验证的核心技术路线。

---

# 2. 项目范围

## 2.1 第一阶段支持范围

输入：

* 本地 PDF 文件；
* 包含 PDF 的本地目录；
* 可选递归扫描子目录。

文档类型：

* 英文技术论文；
* 技术报告；
* 英文教材和专著；
* 双栏论文；
* 含图片、公式、代码和表格的 PDF；
* 普通扫描件。

输出：

```text
source.md
translated.zh.md
translated.bilingual.md
qa-report.md
usage-report.json
manifest.json
```

附属文件：

```text
assets/
ocr/
units/
partitions/
logs/
```

## 2.2 暂不支持

以下内容不进入首个正式版本：

* 按原版式重新生成翻译 PDF；
* 图形化用户界面；
* SaaS 或多用户服务；
* 用户账户和权限系统；
* 移动端；
* 向量数据库；
* RAG 问答；
* Agent 工作流；
* 自动发布到 Obsidian；
* 图片内部文字的完整翻译重绘；
* 完整参考文献本地化；
* 多 GPU 分布式调度；
* 自托管大语言模型。

---

# 3. DeepSeek API 设计基线

正式项目以 DeepSeek OpenAI-compatible Chat Completions 接口为第一设计目标。

默认模型：

```text
deepseek-v4-flash
```

复杂修复和质量复核可选：

```text
deepseek-v4-pro
```

截至 2026 年 7 月 30 日，DeepSeek V4 Flash 和 V4 Pro 均支持 1M 上下文和最大 384K 输出；V4 Flash 的当前人民币价格为缓存命中输入 0.02 元/百万 Token、缓存未命中输入 1 元/百万 Token、输出 2 元/百万 Token。V4 Flash 和 V4 Pro 的账号并发上限分别为 2500 和 500。

这些是平台上限，不应直接作为客户端默认并发。项目初始建议：

```yaml
global_concurrency: 16
per_document_concurrency: 8
per_partition_concurrency: 8
max_global_concurrency: 64
```

DeepSeek 默认开启思考模式，而普通翻译不需要推理过程，因此翻译请求应显式设置：

```json
{
  "thinking": {
    "type": "disabled"
  }
}
```

思考模式关闭后，才能可靠控制 temperature 等采样参数。

---

# 4. 核心设计原则

## 4.1 文档结构优先

不能简单地按固定字符数切割文档。分割顺序应当是：

```text
文档
→ 章
→ 节
→ 小节
→ 自然段
→ 句子
```

表格、公式、代码、图片和 HTML 结构必须作为独立节点处理，不能混入普通正文翻译器。

## 4.2 每个阶段都应可恢复

以下阶段必须拥有独立 checkpoint：

```text
PDF 预检
OCR 页面或页面批次
Markdown 重组
结构分析
Token 规划
缓存分区
翻译单元
文档组装
QA 检查
```

系统崩溃后，不应重新执行已经成功的阶段。

## 4.3 失败隔离

失败粒度从大到小依次为：

```text
批处理任务
文档
OCR 页面批次
缓存分区
翻译单元
结构节点
```

一个单元失败时，应尽可能保留英文原文并继续，而不是停止整个文档。

## 4.4 内容寻址与幂等

所有重要中间产物使用内容哈希标识。

相同的：

* 原文；
* 模型；
* 提示词版本；
* 术语表；
* 翻译配置；

应产生相同的缓存键。

重复运行同一任务不能产生重复 API 请求或重复文件。

## 4.5 缓存优化不能损害翻译边界

DeepSeek KV Cache 命中率是优化指标，但不能为了提高缓存命中率，让模型自己从几十万 Token 中定位待翻译章节。

生产模式应同时提供：

* 完整缓存分区作为公共上下文；
* 在请求末尾再次提供本次目标原文。

即：

```text
完整上下文用于理解
目标副本用于明确输出边界
```

---

# 5. 总体架构

```text
                         ┌────────────────────┐
                         │      CLI 层         │
                         │ run / batch / plan  │
                         │ status / retry      │
                         └─────────┬──────────┘
                                   │
                         ┌─────────▼──────────┐
                         │   Batch Supervisor  │
                         │ 队列、锁、恢复、日志 │
                         └──────┬───────┬─────┘
                                │       │
               ┌────────────────┘       └────────────────┐
               │                                         │
     ┌─────────▼──────────┐                   ┌──────────▼─────────┐
     │      OCR Worker     │                   │ Translation Manager │
     │ 独立子进程，单 GPU   │                   │ asyncio 并发调度     │
     └─────────┬──────────┘                   └──────────┬─────────┘
               │                                         │
     ┌─────────▼──────────┐                   ┌──────────▼─────────┐
     │ Structure Processor │                   │ DeepSeek Provider   │
     │ 标题、段落、结构节点 │                   │ 缓存、限流、重试     │
     └─────────┬──────────┘                   └──────────┬─────────┘
               │                                         │
     ┌─────────▼──────────┐                   ┌──────────▼─────────┐
     │ Token & Plan Engine │                   │ Translation Units   │
     │ Unit / Partition    │                   │ 译文、usage、状态    │
     └─────────┬──────────┘                   └──────────┬─────────┘
               │                                         │
               └────────────────┬────────────────────────┘
                                │
                      ┌─────────▼──────────┐
                      │ SQLite State Store │
                      └─────────┬──────────┘
                                │
                     ┌──────────▼──────────┐
                     │ Assembly & QA Engine │
                     └──────────┬──────────┘
                                │
                      ┌─────────▼──────────┐
                      │ Markdown Artifacts │
                      └────────────────────┘
```

## 5.1 双流水线设计

正式项目应同时维护两个独立队列：

```text
OCR Queue
Translation Queue
```

RTX 4060 上默认：

```text
OCR Worker：1
Translation Worker：16 个异步请求槽
```

这样可以实现：

```text
GPU 正在 OCR 文档 B
同时 DeepSeek API 正在翻译文档 A
```

OCR 使用本地 GPU，翻译主要占用网络和远程计算，两者可以重叠执行。

---

# 6. 推荐项目结构

```text
pdf2zh/
├── pyproject.toml
├── README.md
├── PROJECT_BRIEF.md
├── config.example.yaml
├── .env.example
├── src/
│   └── pdf2zh/
│       ├── __init__.py
│       ├── cli.py
│       ├── config.py
│       ├── database.py
│       ├── models.py
│       ├── supervisor.py
│       │
│       ├── preflight/
│       │   ├── pdf_inspector.py
│       │   └── estimator.py
│       │
│       ├── ocr/
│       │   ├── worker.py
│       │   ├── paddle_pipeline.py
│       │   ├── checkpoints.py
│       │   └── restructuring.py
│       │
│       ├── structure/
│       │   ├── markdown_parser.py
│       │   ├── heading_tree.py
│       │   ├── html_tables.py
│       │   └── protected_nodes.py
│       │
│       ├── planning/
│       │   ├── tokenizer.py
│       │   ├── unit_builder.py
│       │   ├── partition_builder.py
│       │   └── cost_estimator.py
│       │
│       ├── providers/
│       │   ├── base.py
│       │   └── deepseek.py
│       │
│       ├── translation/
│       │   ├── prompts.py
│       │   ├── scheduler.py
│       │   ├── rate_limiter.py
│       │   ├── cache_warmer.py
│       │   ├── style_capsule.py
│       │   └── fallback.py
│       │
│       ├── qa/
│       │   ├── structural.py
│       │   ├── numerical.py
│       │   ├── terminology.py
│       │   └── report.py
│       │
│       └── assembly/
│           ├── markdown.py
│           └── bilingual.py
│
├── tests/
│   ├── fixtures/
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
└── scripts/
    └── migrate_mvp_workspace.py
```

## 6.1 依赖建议

核心依赖：

```text
paddleocr[doc-parser]
paddlepaddle
httpx
typer
pydantic
pydantic-settings
aiosqlite
PyYAML
PyMuPDF
beautifulsoup4
```

开发依赖：

```text
pytest
pytest-asyncio
respx
ruff
mypy
```

不建议首版引入：

```text
SQLAlchemy
Celery
Redis
FastAPI
Docker Compose 服务栈
消息队列
```

SQLite、asyncio 和独立子进程已经足以支撑个人及小规模批处理。

---

# 7. 数据模型

建议使用工作区级 SQLite：

```text
<workspace>/.pdf2zh/state.db
```

每份文档的输出文件仍保存在自身 artifact 目录。

## 7.1 documents

```text
id
source_path
source_sha256
display_name
page_count
language
status
ocr_status
translation_status
qa_status
created_at
updated_at
active_config_hash
```

状态：

```text
queued
preflight
ocr_running
ocr_complete
ocr_complete_with_warnings
planning
translation_running
translation_complete
translation_complete_with_warnings
qa_complete
failed
cancelled
```

## 7.2 ocr_batches

```text
id
document_id
page_start
page_end
status
attempt_count
source_hash
config_hash
output_path
error_type
error_message
started_at
finished_at
```

## 7.3 structural_nodes

```text
id
document_id
parent_id
node_type
sequence_index
heading_level
heading_path
source_pages
source_text
source_hash
token_count
metadata_json
```

`node_type`：

```text
heading
paragraph
list
blockquote
formula
code
image
html_table
markdown_table
page_marker
reference
unknown
```

## 7.4 translation_units

```text
id
document_id
partition_id
sequence_index
heading_path
source_pages
source_text
source_hash
source_tokens
estimated_output_tokens
status
translation_text
translation_hash
provider
model
prompt_version
style_capsule_version
attempt_count
warning_flags
```

## 7.5 cache_partitions

```text
id
document_id
sequence_index
source_tokens
context_tokens
unit_count
prefix_hash
user_id
warmup_status
expected_cache_tokens
actual_probe_hit_tokens
status
```

## 7.6 translation_attempts

```text
id
unit_id
attempt_number
request_hash
started_at
finished_at
latency_ms
http_status
finish_reason
prompt_tokens
cache_hit_tokens
cache_miss_tokens
completion_tokens
error_type
error_message
raw_response_path
```

## 7.7 style_capsules

```text
id
document_id
version
source_partition_id
rules_json
terminology_json
examples_json
boundary_context_json
content_hash
created_at
```

## 7.8 artifacts

```text
id
document_id
artifact_type
path
content_hash
created_at
```

---

# 8. PDF 预检

在启动 PaddleOCR 前，使用 PyMuPDF 执行快速预检。

输出：

```text
页数
PDF 是否加密
页面尺寸
页面旋转
每页原生文字数量
疑似扫描页
疑似空白页
异常超大页面
估计源字符数
估计 Token 数
```

示例：

```text
文档：book.pdf
页数：426
原生文本页：419
疑似扫描页：7
旋转异常页：0
预计英文 Token：214,000
预计翻译单元：22
预计缓存分区：2
```

预检只用于：

* 估计工作量；
* 判断 OCR 参数；
* 提前发现损坏和加密文件；
* 生成处理计划；
* 检查 OCR 输出是否异常。

第一版不直接使用 PDF 原生文字层替代 PaddleOCR。

---

# 9. OCR 子系统

## 9.1 进程隔离

每份 PDF 应由独立 OCR 子进程处理：

```text
Supervisor
→ 启动 OCR Worker
→ Worker 加载 PaddleOCR
→ 完成或失败
→ Worker 退出
```

这样每份文档完成后，CUDA 和 Paddle 资源可以由操作系统彻底回收。

## 9.2 页面批次 checkpoint

默认：

```yaml
ocr_batch_pages: 8
```

一份 100 页 PDF：

```text
1–8
9–16
17–24
……
97–100
```

每个批次完成后，原子写入：

```text
ocr/batch-0001/result.json
ocr/batch-0001/source.md
ocr/batch-0001/done.json
```

崩溃重启后：

```text
有 done.json：跳过
无 done.json：重新运行该批次
```

## 9.3 批次失败降级

```text
8 页批次失败
→ 重试一次
→ 拆成两个 4 页批次
→ 仍失败则逐页处理
→ 单页持续失败则记录缺页并继续
```

最终 Markdown 中插入：

```markdown
<!-- OCR FAILED: source-page 47 -->

> [OCR 警告] 原 PDF 第 47 页处理失败。
```

文档状态：

```text
ocr_complete_with_warnings
```

## 9.4 OCR 配置签名

OCR 缓存键必须包含：

```text
PDF SHA-256
PaddleOCR 版本
PaddlePaddle 版本
pipeline_version
device
orientation
unwarping
chart_recognition
ignore_labels
ocr_batch_pages
```

配置发生变化时，不得静默复用旧 OCR。

## 9.5 脚注策略

默认保留：

```text
footnote
aside_text
```

默认忽略：

```text
page number
header
footer
header image
footer image
```

用户可显式开启：

```text
--drop-footnotes
--drop-aside-text
```

---

# 10. 文档结构解析

OCR 输出不应立即进入翻译。

先构造文档树：

```text
Document
├── Chapter 1
│   ├── Section 1.1
│   │   ├── Paragraph
│   │   ├── Formula
│   │   └── Paragraph
│   └── Section 1.2
│       └── HTML Table
└── Chapter 2
```

## 10.1 页码元数据

以下内容不发送给模型：

```html
<!-- source-page: 33 -->
<a id="source-page-33"></a>
```

程序将其转换为结构节点，在组装阶段重新插入。

## 10.2 HTML 表格

首个正式版本继续采用稳定策略：

```text
检测完整 <table>...</table>
→ 作为独立节点
→ 不进入普通翻译器
→ 原样保留
```

后续版本增加专用表格翻译器：

```text
解析行列
→ 提取单元格文本
→ 使用 JSON 翻译
→ 本地回填原 HTML 结构
```

禁止再将每个 `<tr>`、`<td>` 单独转换为占位符。

## 10.3 公式和代码

以下节点不调用翻译 API：

```text
纯公式块
纯代码块
图片节点
空白结构节点
```

混合自然语言的代码注释或图注可以单独生成翻译单元。

---

# 11. Token 规划

DeepSeek 官方提供离线 tokenizer，并建议实际用量以 API 返回的 usage 为准。没有 tokenizer 时，可临时使用“英文字符约 0.3 Token、中文字符约 0.6 Token”的粗略估计。

正式项目必须封装：

```python
class TokenCounter:
    def count(self, text: str) -> int:
        ...
```

优先级：

```text
DeepSeek 官方 tokenizer
→ 本地兼容 tokenizer
→ 字符比例估计
```

每个估算结果记录：

```text
exact
approximate
```

---

# 12. 翻译单元规划

## 12.1 默认参数

```yaml
translation_unit:
  target_tokens: 12000
  max_tokens: 24000
  min_tokens: 1500
```

## 12.2 切分规则

优先保持完整章节或小节：

```text
小节 <= 24K
→ 整节作为一个 Unit

小节 > 24K
→ 按三级标题切分

仍然 > 24K
→ 按自然段组合

单个自然段 > 24K
→ 按句子安全切分
```

不得拆开：

```text
代码围栏
块公式
HTML 表格
Markdown 表格行
图片链接
```

## 12.3 参考文献

默认：

```yaml
references_mode: keep
```

即：

* “References”标题翻译为“参考文献”；
* 文献条目保持英文；
* DOI、作者名、期刊名和页码不修改。

可选：

```text
keep
translate_titles
translate_all
```

---

# 13. DeepSeek 缓存分区

## 13.1 分区定义

缓存分区是多个连续章节或翻译单元的集合。

推荐默认值：

```yaml
partition:
  first_target_tokens: 96000
  normal_target_tokens: 220000
  max_tokens: 300000
```

第一个分区较小，是为了尽快建立：

* 初始译文；
* 文档术语；
* 风格 few-shot；
* 输出 Token 比例统计。

## 13.2 打包算法

按原文顺序遍历章节：

```text
当前分区 + 下一章 <= target
→ 加入

超过 target
→ 关闭当前分区
→ 创建新分区
```

单章超过分区上限：

```text
按小节拆分
```

任何情况下都必须保留：

```text
source_sequence_index
```

保证最终组装顺序确定。

---

# 14. DeepSeek 公共缓存前缀

每个分区构造一个完全稳定的公共前缀。

```text
SYSTEM
固定翻译规则
提示词版本
目标语言
结构保护规则
完整性要求

USER
<document-context>
文档标题
文档摘要
章节目录
全局术语表
风格胶囊
</document-context>

<partition-source>
[UNIT id="p001-u001"]
完整源文本……

[UNIT id="p001-u002"]
完整源文本……
</partition-source>

请读取以上分区并回复固定字符串：
PARTITION_READY
```

所有后续请求必须逐 Token 保持该前缀不变。

以下内容不能出现在稳定前缀中：

```text
当前时间
随机 ID
请求序号
动态重试提示
当前 Unit ID
变化的日志信息
```

## 14.1 user_id

DeepSeek 使用 `user_id` 隔离 KV Cache，因此同一文档应使用稳定的 `user_id`。该字段不能含隐私信息，并需符合 DeepSeek 的字符规则。

默认：

```python
user_id = "pdf_" + document_sha256[:20]
```

同一文档的所有分区沿用同一 `user_id`。

---

# 15. 缓存预热

DeepSeek 缓存默认开启，但属于 best-effort，缓存构建需要数秒，且通常在数小时至数天不使用后清除。API 会返回 `prompt_cache_hit_tokens` 和 `prompt_cache_miss_tokens`。

## 15.1 预热流程

```text
1. 发送分区固定前缀
2. 模型返回 PARTITION_READY
3. 保存实际 assistant 返回内容
4. 等待短暂缓存落盘窗口
5. 串行发送第一个真实翻译 Unit
6. 检查 cache hit tokens
7. 命中达到阈值后打开并发闸门
```

后续请求：

```python
messages = [
    {
        "role": "system",
        "content": stable_system_prompt
    },
    {
        "role": "user",
        "content": stable_partition_prompt
    },
    {
        "role": "assistant",
        "content": actual_warmup_response
    },
    {
        "role": "user",
        "content": dynamic_unit_request
    }
]
```

必须使用真实 warm-up 返回内容，不能假设模型一定精确返回预期字符串。

## 15.2 缓存探测阈值

```yaml
cache:
  probe_min_ratio: 0.70
  warning_ratio: 0.50
```

计算：

```text
cache_probe_ratio =
actual_cache_hit_tokens / expected_stable_prefix_tokens
```

行为：

```text
>= 70%
→ 正常开启分区并发

50%～70%
→ 开启低并发并记录警告

< 50%
→ 再探测一次
→ 仍低则退化为普通章节模式
```

缓存命中失败不能使文档失败。

---

# 16. 动态翻译请求

生产默认使用：

```text
target_mode: repeat
```

动态尾部：

```text
翻译任务：
只翻译 UNIT p001-u007。
保持 Markdown 结构。
不要输出其他 Unit。
必须输出开始和结束标记。

以下是目标文本的副本：

<translation-unit id="p001-u007">
……
</translation-unit>
```

模型输出：

```text
<<<UNIT:p001-u007:BEGIN>>>

译文……

<<<UNIT:p001-u007:END>>>
```

这样虽然目标原文在公共分区中已经存在，但再次放在请求尾部可以：

* 明确目标边界；
* 降低定位错误；
* 避免翻译相邻章节；
* 便于校验；
* 提高长上下文中的注意力稳定性。

实验模式：

```text
target_mode: id_only
```

只提供 Unit ID，不重复目标正文。该模式缓存 Token 比例更高，但不能作为默认生产模式。

---

# 17. 风格胶囊

## 17.1 目的

分区内部并发意味着各翻译单元不能依赖彼此的即时输出。为了保持术语和语言风格一致，应在每个分区开始前冻结一个风格胶囊。

## 17.2 结构

```yaml
version: 2

style_rules:
  - 使用正式、简洁的技术书面语
  - 不解释原文
  - 保留原文证据强度
  - 保留标题编号
  - 产品名和模型名保留英文

terminology:
  affordance: 示能
  progressive disclosure: 渐进式披露
  agentic workflow: 代理式工作流

representative_examples:
  - source: "..."
    translation: "..."
  - source: "..."
    translation: "..."

boundary_context:
  source_tail: "上一分区最后两个自然段"
  translation_tail: "对应译文"
```

## 17.3 第一分区启动

第一分区尚无译文样例：

```text
选择代表性 Unit
→ 串行翻译
→ 校验
→ 将该译文加入 provisional style capsule
→ 重新构造第一分区稳定前缀
→ 预热缓存
→ 并发处理剩余 Unit
```

代表性 Unit 应满足：

* 普通正文占比高；
* 包含典型技术术语；
* 不包含大型表格；
* 不以参考文献为主；
* 长度约 2K～6K Token。

## 17.4 后续分区

```text
分区 N 完成
→ 从成功译文中选择 2～4 个代表样例
→ 合并确认术语
→ 加入边界上下文
→ 生成 style_capsule_vN
→ 固定用于分区 N+1
```

风格胶囊只在分区边界更新，分区内部不得变化，否则会破坏缓存前缀并导致并发 Unit 使用不同上下文。

---

# 18. 并发调度

## 18.1 基础模型

```text
整本文档：
分区之间串行

单个分区：
翻译 Unit 并行
```

即：

```text
Partition 1
  Unit 1 ─┐
  Unit 2 ─┼─ 并行
  Unit 3 ─┘
      ↓ 全部完成
生成 Style Capsule
      ↓
Partition 2
```

## 18.2 初始并发参数

```yaml
concurrency:
  global: 16
  per_document: 8
  per_partition: 8
  max_global: 64
```

不要因为 DeepSeek 平台上限较高而直接设置 500 或 2000。平台限制只是允许的在途请求数量，不代表该账户余额、网络、错误率和文档调度适合使用相同规模。

## 18.3 异步实现

建议：

```python
httpx.AsyncClient
asyncio.Semaphore
asyncio.Queue
```

共享一个连接池：

```yaml
http:
  max_connections: 64
  max_keepalive_connections: 32
  connect_timeout: 30
  read_timeout: 900
```

DeepSeek 请求可能较长，不能使用普通短 HTTP timeout。

## 18.4 自适应并发

初始：

```text
16
```

行为：

```text
连续 30 次成功
且 p95 延迟稳定
且无 429/503
→ 并发 +2

出现 429
→ 当前并发减半

出现 503 或 insufficient_system_resource
→ 当前并发减少 25%

连续超时
→ 当前并发减半
```

最低：

```text
1
```

最高：

```text
配置中的 max_global
```

## 18.5 公平调度

多文档批量时，使用文档级配额：

```text
全局 32

文档 A：8
文档 B：8
文档 C：8
文档 D：8
```

避免一本超长书独占所有请求槽。

---

# 19. API 响应处理

只有以下条件同时满足，才能将翻译单元标记为成功：

```text
HTTP 2xx
finish_reason == stop
存在预期 Unit 起止标记
译文非空
结构校验通过
```

DeepSeek 可能返回：

```text
stop
length
content_filter
tool_calls
insufficient_system_resource
```

其中 `length` 表示输出达到 max_tokens 或上下文限制，`insufficient_system_resource` 表示后端资源不足导致请求中断。二者都不能作为成功结果。

## 19.1 错误分类

不可重试：

```text
400 参数错误
401 密钥错误
402 余额不足
403 权限错误
404 模型错误
413 请求过大
422 参数校验错误
```

可重试：

```text
408
429
500
502
503
504
网络中断
连接重置
insufficient_system_resource
```

内容级失败：

```text
输出截断
Unit 标记缺失
占位符错误
译文为空
Markdown 结构异常
数字严重缺失
```

## 19.2 重试策略

```text
第一次失败
→ 正常重试

第二次失败
→ 缩小 max output 风险或调整请求

结构性失败
→ 将 Unit 二分

持续失败
→ 使用 deepseek-v4-pro 修复一次

仍失败
→ 保留英文原文并继续
```

指数退避：

```text
Retry-After 优先
否则 exponential backoff + jitter
```

---

# 20. 本地翻译缓存

DeepSeek KV Cache 只能减少远端输入成本，不能替代本地结果缓存。

本地缓存键：

```text
SHA256(
  source_text
  + provider
  + model
  + prompt_version
  + target_language
  + glossary_hash
  + style_capsule_hash
  + translation_parameters
)
```

缓存目录：

```text
.pdf2zh/cache/translations/
└── ab/
    └── abcdef....json
```

缓存内容：

```json
{
  "source_hash": "...",
  "translation": "...",
  "model": "deepseek-v4-flash",
  "prompt_version": "translate-v3",
  "usage": {},
  "created_at": "..."
}
```

命中本地缓存时：

```text
不调用 DeepSeek
不消耗 Token
直接复用结果
```

---

# 21. 成本预估

## 21.1 计划阶段估计

对每个分区计算：

```text
首次缓存前缀未命中 Token
后续缓存命中 Token
每个目标 Unit 重复输入 Token
预计输出 Token
预热请求 Token
失败重试预算
```

V4 Flash 当前成本公式：

```text
预计费用 =
缓存命中 Token ÷ 1,000,000 × 0.02元
+ 缓存未命中 Token ÷ 1,000,000 × 1元
+ 输出 Token ÷ 1,000,000 × 2元
```

价格必须作为可配置 profile 保存，不应写死在业务逻辑中。DeepSeek 官方明确表示价格可能调整。

## 21.2 输出比例校准

初始：

```text
estimated_output_tokens =
source_tokens × 1.3 + 512
```

完成前 5 个 Unit 后：

```text
ratio =
completion_tokens / source_tokens
```

使用滚动 P90：

```text
estimated_output_tokens =
source_tokens × rolling_p90_ratio × 1.2
```

同时设置：

```text
minimum_output_tokens
maximum_output_tokens
model_output_limit
```

## 21.3 plan 命令

```powershell
pdf2zh plan "book.pdf" --model deepseek-v4-flash
```

输出：

```text
源文件：book.pdf
页数：426
预计源 Token：214,382

翻译单元：19
缓存分区：2

Partition 1：
  源 Token：96,320
  Unit：8

Partition 2：
  源 Token：118,062
  Unit：11

预计缓存未命中输入：238,000
预计缓存命中输入：2,041,000
预计输出：196,000
预计费用：0.67元

估计模式：approximate
```

实际费用始终以 API usage 为准。

---

# 22. QA 系统

QA 分为机械检查和定向修复。

## 22.1 机械检查

结构：

```text
Unit ID
标题层级
页码标记
图片路径
代码围栏
公式
HTML 标签
Markdown 表格结构
```

内容：

```text
数字
百分比
年份
单位
引用编号
图号
表号
公式编号
URL
DOI
```

长度：

```text
译文长度 / 原文长度
```

术语：

```text
术语表命中
同一术语的不同译法
缩写首次出现
```

## 22.2 定向修复

只有 QA 失败时，才调用修复模型：

```text
原文
当前译文
明确列出的机械错误
```

提示：

```text
只修复列出的问题。
不要重新改写其他内容。
```

最多修复一次。

## 22.3 QA 报告

```markdown
# 翻译质量报告

## 总体

- Unit：19
- 直接通过：17
- 自动修复：1
- 英文回退：1
- HTML 表格原样保留：4

## 警告

### p002-u007

- 数字不一致
- 原文：0.05
- 译文：0.5
- 修复结果：已通过

### p002-u010

- API 连续失败
- 已保留英文原文
```

---

# 23. 输出组装

最终组装只依赖：

```text
sequence_index
```

而不依赖 API 返回顺序。

输出：

## 23.1 中文版

```text
translated.zh.md
```

## 23.2 双语版

默认采用折叠英文：

```html
<details>
<summary>查看英文原文</summary>

Original text...

</details>

中文译文……
```

## 23.3 使用统计

```json
{
  "documents": 1,
  "pages": 426,
  "translation_units": 19,
  "prompt_tokens": 2279000,
  "cache_hit_tokens": 2041000,
  "cache_miss_tokens": 238000,
  "completion_tokens": 196000,
  "cache_hit_ratio": 0.8955,
  "estimated_cost_cny": 0.67,
  "retries": 3,
  "fallback_units": 1
}
```

---

# 24. CLI 设计

## 24.1 单文件执行

```powershell
pdf2zh run "paper.pdf"
```

## 24.2 只做 OCR

```powershell
pdf2zh run "paper.pdf" --stage ocr
```

## 24.3 只做翻译

```powershell
pdf2zh run "paper.pdf" --stage translate
```

## 24.4 查看计划

```powershell
pdf2zh plan "paper.pdf"
```

## 24.5 批量运行

```powershell
pdf2zh batch "D:\Papers" `
  --recursive `
  --continue-on-error `
  --prevent-sleep
```

## 24.6 状态

```powershell
pdf2zh status
pdf2zh status "paper.pdf"
```

## 24.7 重试失败项

```powershell
pdf2zh retry "paper.pdf"
pdf2zh retry --all-failed
```

## 24.8 强制重新执行

```powershell
pdf2zh run "paper.pdf" --force-ocr
pdf2zh run "paper.pdf" --force-translate
pdf2zh run "paper.pdf" --force-plan
```

## 24.9 检查和诊断

```powershell
pdf2zh inspect "paper.pdf"
pdf2zh inspect "paper.pdf" --unit p002-u007
pdf2zh report "paper.pdf"
```

---

# 25. 配置文件

```yaml
workspace: "D:/PDF2ZH-Workspace"

ocr:
  pipeline_version: "v1.6"
  device: "gpu:0"
  batch_pages: 8
  orientation: false
  unwarping: false
  chart_recognition: false
  keep_footnotes: true
  keep_aside_text: true

provider:
  name: "deepseek"
  base_url: "https://api.deepseek.com"
  model: "deepseek-v4-flash"
  repair_model: "deepseek-v4-pro"
  thinking: "disabled"
  temperature: 0.2
  timeout_seconds: 900

planning:
  unit_target_tokens: 12000
  unit_max_tokens: 24000
  first_partition_tokens: 96000
  partition_target_tokens: 220000
  partition_max_tokens: 300000
  target_mode: "repeat"

concurrency:
  global: 16
  per_document: 8
  per_partition: 8
  max_global: 64
  adaptive: true

cache:
  enable_deepseek_kv: true
  enable_local_translation_cache: true
  probe_min_ratio: 0.70
  warning_ratio: 0.50

translation:
  target_language: "zh-CN"
  references_mode: "keep"
  fallback_to_source: true
  strict: false

qa:
  numerical_check: true
  unit_check: true
  citation_check: true
  terminology_check: true
  auto_repair: true
  max_repair_attempts: 1

batch:
  continue_on_error: true
  prevent_sleep: true
  ocr_workers: 1
```

API Key 只放入 `.env`：

```dotenv
DEEPSEEK_API_KEY=...
```

---

# 26. 无人值守运行

## 26.1 Windows 防睡眠

批处理启动时调用：

```text
SetThreadExecutionState
```

保持系统运行，但允许关闭显示器。

## 26.2 运行锁

工作区锁：

```text
.pdf2zh/supervisor.lock
```

文档锁：

```text
<document-artifact>/.run.lock
```

锁记录：

```text
PID
hostname
started_at
command
```

陈旧锁应通过 PID 检查自动识别。

## 26.3 原子写入

所有状态文件：

```text
写入 .tmp
fsync
rename
```

SQLite 使用：

```text
WAL mode
busy_timeout
单 writer 或短事务
```

## 26.4 夜间报告

```text
nightly-2026-07-30.md
nightly-2026-07-30.json
```

包括：

```text
发现文档
完成文档
带警告完成
失败文档
完成页数
失败页数
翻译 Unit
缓存命中率
Token 消耗
估计费用
重试次数
```

---

# 27. 日志与可观测性

每次 API 请求至少记录：

```text
request_id
document_id
partition_id
unit_id
attempt
model
latency
HTTP status
finish_reason
prompt_tokens
cache_hit_tokens
cache_miss_tokens
completion_tokens
estimated_cost
```

关键指标：

```text
OCR 页/分钟
OCR 批次失败率
翻译 Unit/分钟
p50/p95 API 延迟
429 比例
503 比例
缓存 Token 命中率
本地缓存命中率
输出截断率
自动修复率
英文回退率
每文档费用
```

需要区分：

```text
请求缓存命中率
Token 缓存命中率
本地结果缓存命中率
```

---

# 28. 安全和隐私

默认策略：

* PDF 和图片保留在本地；
* 只向 DeepSeek 发送 OCR 后的文本；
* 不上传原 PDF；
* 不在日志中记录 API Key；
* `user_id` 使用文档哈希，不包含文件名、作者或用户信息；
* 原始 API 响应只在失败或 debug 模式下保存；
* 日志中可选择对源文本片段脱敏；
* `.env` 加入 `.gitignore`；
* 工作区中保存完整的发送内容清单，便于审计。

提供：

```text
pdf2zh inspect-data "paper.pdf"
```

显示将向 API 发送哪些内容。

---

# 29. 实施阶段

## Phase 0：冻结 MVP 基线

目标：

确认现有单文件版本的行为，避免重构时破坏已经跑通的能力。

实施：

1. 将当前热修脚本归档为 `legacy/pdf_translate_cli_v0_2.py`。
2. 选择 5 份固定测试 PDF：

   * 普通论文；
   * 双栏公式论文；
   * HTML 表格文档；
   * 长篇书籍；
   * 扫描件。
3. 保存当前输出作为 characterization fixtures。
4. 建立测试：

   * HTML 表格不会产生大量逐标签占位符；
   * OCR-only 后可继续翻译；
   * 翻译中断后可续跑；
   * 失败块可英文回退；
   * 中英文输出可正常组装。

验收：

```text
现有已跑通 PDF 在新项目中仍能获得等价输出
```

## Phase 1：项目骨架和 SQLite

实施：

1. 建立 `pyproject.toml`。
2. 建立 Typer CLI。
3. 建立配置加载。
4. 建立 SQLite schema。
5. 建立 artifact 目录约定。
6. 将单文件中的通用函数迁入模块。
7. 实现旧工作目录导入工具。

验收：

```text
pdf2zh status
pdf2zh inspect
pdf2zh run --stage translate
```

能够基于 SQLite 状态运行。

## Phase 2：无人值守 OCR

实施：

1. OCR 独立子进程。
2. PDF 预检。
3. 页面批次 checkpoint。
4. 批次失败拆分。
5. 单页失败继续。
6. 防睡眠。
7. 运行锁。
8. 夜间报告。

验收测试：

```text
处理中强制终止进程
→ 重启后从未完成批次继续

加入损坏 PDF
→ 其余文档继续

制造单页失败
→ 文档带警告完成
```

## Phase 3：结构树和 Token Planner

实施：

1. Markdown 结构解析。
2. 标题树。
3. 结构节点分类。
4. HTML 表格独立节点。
5. DeepSeek tokenizer。
6. Translation Unit 生成。
7. Cache Partition 生成。
8. `plan` 命令。
9. 成本预估。

验收：

```text
同一输入和配置始终产生相同 Unit 和 Partition
无公式、代码或表格被错误拆开
计划 Token 与 API 实际 Token 偏差可观测
```

## Phase 4：DeepSeek Provider 与 KV Cache

实施：

1. `DeepSeekProvider`。
2. thinking disabled。
3. 稳定 `user_id`。
4. usage 解析。
5. `finish_reason` 处理。
6. 公共前缀构建。
7. 缓存 warm-up。
8. cache probe。
9. 缓存降级模式。
10. 本地内容寻址缓存。

验收：

```text
第二个真实 Unit 起出现 prompt_cache_hit_tokens
缓存低命中时自动降级
缓存失效不会导致任务失败
```

## Phase 5：异步并发

实施：

1. `httpx.AsyncClient`。
2. 全局 Semaphore。
3. 文档级 Semaphore。
4. 分区级 Semaphore。
5. 分区 barrier。
6. 公平队列。
7. 自适应并发。
8. 429/503 退避。
9. 单 writer 状态提交。

验收：

```text
并发 16 的吞吐量显著高于串行
无 SQLite 写入冲突
结果顺序与请求完成顺序无关
触发 429 后能自动降速
```

## Phase 6：风格胶囊

实施：

1. 首个代表性 Unit 选择。
2. provisional capsule。
3. few-shot 选择器。
4. 边界上下文。
5. 术语合并。
6. capsule 版本化。
7. 分区边界冻结。

验收：

```text
并发 Unit 使用完全相同 capsule
跨分区术语一致
修改 capsule 后只使受影响缓存失效
```

## Phase 7：QA 与专用结构处理

实施：

1. 数字和单位检查。
2. 引用编号检查。
3. Markdown 结构检查。
4. 定向修复。
5. QA 报告。
6. HTML 表格单元格翻译器。
7. 参考文献模式。

验收：

```text
表格结构不被模型修改
截断输出不会被标记为成功
高风险错误能够定位到具体 Unit
```

## Phase 8：批量生产化

实施：

1. OCR 和翻译双队列。
2. 多文档公平调度。
3. 批量 manifest。
4. 全局 usage 报告。
5. 失败文档重试。
6. Windows Task Scheduler 使用说明。
7. 配置档案：

   * conservative；
   * balanced；
   * throughput。

验收：

```text
整夜批量处理后无需人工干预
单文件失败不影响其他文档
第二天可通过一份报告了解所有结果
```

---

# 30. 推荐实施顺序

实际开发不应同时推进全部模块。

建议严格按以下顺序：

```text
第一步：
冻结 MVP 和测试样本

第二步：
项目骨架 + SQLite

第三步：
无人值守 OCR checkpoint

第四步：
结构树 + Token Planner

第五步：
DeepSeek Provider + usage 统计

第六步：
分区缓存 warm-up 和 probe

第七步：
8 并发
→ 16 并发
→ 32 并发
→ 评估 64 并发

第八步：
风格胶囊

第九步：
机械 QA

第十步：
HTML 表格翻译
```

不要先实现：

```text
复杂自动术语生成
整书一次输出
多供应商统一框架
Web UI
本地模型
多 GPU
```

这些内容会分散当前最重要的工程目标。

---

# 31. v1.0 验收标准

## 可靠性

```text
正常 PDF 批处理完成率 >= 98%
单 Unit 失败不会停止文档
单文档失败不会停止批次
进程被终止后可恢复
重复运行不会重复翻译成功 Unit
```

## OCR

```text
页面批次可断点续跑
损坏页可隔离
OCR 配置变化可检测
```

## DeepSeek 缓存

```text
真实记录 hit/miss Token
公共前缀命中率可观测
缓存失败可自动降级
稳定前缀不会被动态字段污染
```

建议性能目标：

```text
缓存预热后的分区前缀 Token 命中率 >= 70%
```

这应作为优化目标，不作为文档成功的硬条件。

## 并发

```text
默认并发 16 稳定运行
可以逐步配置到 32 或 64
429 后自动降速
无请求风暴
```

## 翻译完整性

```text
所有 Translation Unit 均有结果或明确英文回退
所有页码可追溯
代码、公式和图片路径不被破坏
finish_reason != stop 的响应不进入正式译文
```

## 可观测性

```text
每个 Unit 有 usage
每份文档有成本和 QA 报告
每个批次有夜间汇总
```

---

# 32. 关键风险

| 风险                       | 影响        | 处理                            |
| ------------------------ | --------- | ----------------------------- |
| DeepSeek 缓存为 best-effort | 命中率不稳定    | warm-up、probe、自动降级            |
| 超大公共前缀首请求慢               | 延迟和失败成本上升 | 分区限制在约 220K，最大 300K           |
| 并发造成缓存击穿                 | 首批请求同时未命中 | warm-up barrier 后再放量          |
| 并发造成风格漂移                 | 同一章表达不一致  | 固定 style capsule              |
| 长输出被截断                   | 静默漏译      | finish_reason 校验和自动拆分         |
| HTML 表格破坏                | 占位符失败     | 表格独立结构处理器                     |
| OCR 长文档崩溃                | 整份重跑      | 页面批次 checkpoint               |
| API 价格变化                 | 费用预估不准    | 价格 profile 配置化                |
| DeepSeek 模型更新            | 行为变化      | provider capabilities 和模型版本记录 |
| SQLite 并发写入              | 锁冲突       | WAL、短事务、单 writer              |
| 文件移动或重命名                 | 找不到旧任务    | 使用 SHA-256 作为文档身份             |

---

# 33. 最终推荐方案

正式项目的默认处理模式应当是：

```text
PaddleOCR-VL 页面批次 OCR
+ Markdown 结构树
+ DeepSeek Token 规划
+ 章节感知 Translation Unit
+ 约 220K Token Cache Partition
+ 分区间串行
+ 分区内 8～16 并发
+ 公共前缀 warm-up
+ 目标正文尾部重复
+ 风格胶囊跨分区传递
+ SQLite 状态存储
+ 机械 QA
+ 英文回退
+ CLI 批量无人值守
```

推荐的首个生产配置：

```yaml
model: deepseek-v4-flash
thinking: disabled

ocr_batch_pages: 8

unit_target_tokens: 12000
unit_max_tokens: 24000

first_partition_tokens: 96000
partition_target_tokens: 220000
partition_max_tokens: 300000

global_concurrency: 16
per_document_concurrency: 8
max_global_concurrency: 64

target_mode: repeat
cache_probe_min_ratio: 0.70

fallback_to_source: true
strict: false
```

该方案保留了当前 MVP 的简单使用方式，但将内部执行升级为可恢复、可观测、并发和缓存感知的文档处理系统。它既不会退化成一次性脚本，也不会过早膨胀为复杂平台。
