# Contracts Index

* [Repository Contract](repository-contract.md) - Current repository-level contract boundaries.

<!-- BEGIN PARADIGMA AUTO-INDEX -->
<!-- checksum: bcb097441ee943c8 -->
<!-- generated_by: pd-index.py -->

| Path | Type | Title | Hints | Symbols | Relations |
|------|------|-------|-------|---------|-----------|
| [cli-contract.md](cli-contract.md) | `paradigma-contract` | CLI Contract | CLI 命令<br>run batch plan<br>退出码 ... | solivagus run<br>solivagus batch<br>solivagus plan ... | depends_on:/architecture.md<br>depends_on:/contracts/workspace-artifact-contract.md<br>depends_on:/decisions/adr-001-package-name-solivagus.md<br>informed_by:/project-brief.md |
| [repository-contract.md](repository-contract.md) | `paradigma-contract` | Repository Contract | 仓库契约<br>目录边界<br>所有权 ... | memory-bank<br>src/solivagus<br>src/paradigma ... | informed_by:/architecture.md<br>informed_by:/decisions/adr-001-package-name-solivagus.md<br>related_to:/contracts/cli-contract.md<br>related_to:/contracts/workspace-artifact-contract.md |
| [workspace-artifact-contract.md](workspace-artifact-contract.md) | `paradigma-contract` | Workspace and Artifact Contract | 工作区<br>artifact<br>SQLite ... | state.db<br>source.md<br>translated.zh.md ... | depends_on:/architecture.md<br>depends_on:/decisions/adr-001-package-name-solivagus.md<br>related_to:/contracts/cli-contract.md<br>informed_by:/project-brief.md |

<!-- END PARADIGMA AUTO-INDEX -->
