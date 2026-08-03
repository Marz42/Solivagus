# 变更日志

> 🌡️ WARM 知识 — 记录 Solivagus 的版本发布历史。
>
> 格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)。

---

## [Unreleased]

### Added
- 从 Paradigma 模板初始化项目 Memory-Bank。
- 写入 Solivagus project-brief / architecture / conventions / glossary。
- 新增 CLI、workspace-artifact、repository 契约与 document-pipeline 领域文档。
- 新增 `plans/solivagus-v1-roadmap.md`（Phase 0–8）。
- 新增 ADR-001：包名/CLI/工作区统一为 `solivagus`。
- 记录环境决策：Python 3.11 基线 / 推荐 3.12、uv、OAI-compatible + 仅 `deepseek-v4-flash`、批目录 `D:\PDFS`。
- 提交 `requirements-gpu.txt`（已跑通 GPU/OCR 钉选）；整目录忽略 `example/`。
- 加固 `.gitignore`（`.env`、`.solivagus/`、`example/`、PDF）并添加 `.env.example`。
- Phase 0：归档 `legacy/pdf_translate_cli_v0_2.py`，新增 MVP baseline manual 与 `tests/characterization/test_mvp_baseline.py`。
- Phase 1：新增 `src/solivagus`（Typer CLI + SQLite + MVP 导入 + translate stage），`config.example.yaml`，发行包名改为 `solivagus` 并保留 `pd` 入口。
