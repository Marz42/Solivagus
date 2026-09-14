# 变更日志

> 🌡️ WARM 知识 — 记录 Solivagus 的版本发布历史。
>
> 格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)。

---

## [Unreleased]

### Fixed
- CI 安装改为 `pip install ".[dev]"`；`pyproject`/`solivagus.__version__` 与根 `VERSION` 对齐。
- 单文档多 Partition 共用一个事件循环，避免跨 loop 复用 `ConcurrencyGate`。
- Batch Supervisor 持有 `ThreadSafeGate` 作为批级 global gate。
- 二分重试重新进入 `NestedGates`；校准写入加进程+文件锁并按 model/语言/tokenizer 分桶。
- Plan 幂等键改为 config+source（不含 live sample_count）；强制重规划按 source_hash 保留已完成 Unit。
- 全量已完成文档/分区跳过 warm-up，避免重跑把 complete 降为 failed。
- warm-up / probe 进入 NestedGates；`inspect-data` 按分区推进风格胶囊。
- 分区全部 DONE 但胶囊未落库时，恢复路径按完成译文重建并持久化胶囊。
- 重规划清空旧 style capsules；翻译始终从空胶囊进入 Partition 1。
- Legacy `plan:{config_hash}` 一律重规划（不再静默升级 source hash）。
- Plan 报告仍记录校准指纹；`inspect-data` 输出逐 Partition 请求清单，修复 `--sample 0`。

### Changed
- 批处理 PDF 根目录：`Settings.batch_dir` 默认改为 `null`；通过 `SOLIVAGUS_BATCH_DIR`、配置或 CLI 显式指定，不再默认 `D:\PDFS`。
- OCR §9.5：默认保留 footnote/aside；`--drop-footnotes` / `--drop-aside-text` 拆开丢弃。
- `references_mode` 扩展模式收缩为暂缓（ADR-002）；生产默认 `keep`。
- ADR-002：明确生产浸泡前仍不可关闭（见 known-issue `production-gate-concurrency-ci`）。

### Added
- ADR-002 后续：输出比例滚动校准、`inspect-data`、并发硬上限 + Retry-After / 503−25%。
- `--config` YAML 加载（`config_loader.py`）作为可复现配置入口。
- TokenCounter：优先 `deepseek-tokenizer` / 本地 tokenizer 文件，否则近似。
- Unit 二分重试（§19.2）：失败后先拆半再英文回退。
- 文档 `manifest.json` 在 translate/QA 终态稳定写出。
- Phase 8：`solivagus batch` / `retry`、OCR/翻译双队列、profiles、batch manifest、global usage、Task Scheduler 手册与 `scripts/night-batch.ps1`。
- 从 Paradigma 模板初始化项目 Memory-Bank。
- 写入 Solivagus project-brief / architecture / conventions / glossary。
- 新增 CLI、workspace-artifact、repository 契约与 document-pipeline 领域文档。
- 新增 `plans/solivagus-v1-roadmap.md`（Phase 0–8）。
- 新增 ADR-001：包名/CLI/工作区统一为 `solivagus`。
- 记录环境决策：Python 3.11 基线 / 推荐 3.12、uv、OAI-compatible + 仅 `deepseek-v4-flash`；批目录可配置（不默认 `D:\PDFS`）。
- 提交 `requirements-gpu.txt`（已跑通 GPU/OCR 钉选）；整目录忽略 `example/`。
- 加固 `.gitignore`（`.env`、`.solivagus/`、`example/`、PDF）并添加 `.env.example`。
- Phase 0：归档 `legacy/pdf_translate_cli_v0_2.py`，新增 MVP baseline manual 与 `tests/characterization/test_mvp_baseline.py`。
- Phase 1：新增 `src/solivagus`（Typer CLI + SQLite + MVP 导入 + translate stage），`config.example.yaml`，发行包名改为 `solivagus` 并保留 `pd` 入口。
- Phase 2：OCR 子进程 worker、pypdfium2 预检、页面批次 checkpoint/失败拆分、锁与防睡眠、`solivagus report` 夜间汇总。
- 本机 GPU 验收：F1 `Attention Is All You Need.pdf` → `ocr_complete`（`manuals/solivagus-phase2-ocr-gpu.md`）。
- 环境说明：`paddlepaddle-gpu` 须从 Paddle 官方索引安装（`known-issues/paddlepaddle-gpu-not-on-pypi.md`）；README 补充 Solivagus 快速开始。
- Phase 3：结构树解析、Token Unit/Partition 规划、成本预估、`solivagus plan` / `run --stage plan`；规划产物 `plan-report.json`。
- Phase 4：分区 warm-up/probe、本地翻译缓存、`usage-report.json`、低命中自动降级；`translation_attempts` 记录 cache hit。
- Phase 5：asyncio 分区内并发（warm-up barrier 后放量）、global/document/partition 闸门、429 自适应减半、SQLite 单 writer。
- Phase 6：风格胶囊（分区冻结、P1 provisional re-warmup、跨区 handoff、`style_capsules/vN.json`）。
- Phase 7：机械 QA + 定向修复（最多 1 次）、`qa-report.md`、HTML 表格单元格翻译器、`references_mode=keep`。
