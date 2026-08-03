"""Application services for the derived memory catalog."""

from __future__ import annotations

from pathlib import Path

from ..config import require_valid_config
from ..diagnostics import Diagnostic
from ..storage.catalog import SQLiteMemoryCatalog
from ..storage.markdown import MarkdownMemoryStore
from .outcomes import CommandOutcome


def _catalog(repository_root: Path) -> SQLiteMemoryCatalog:
    config = require_valid_config(repository_root)
    return SQLiteMemoryCatalog(
        config.catalog_path,
        MarkdownMemoryStore(config.memory_root),
        path_base=config.repository_root,
    )


def _relative(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def catalog_rebuild_outcome(
    repository_root: Path, *, dry_run: bool = False
) -> CommandOutcome:
    root = repository_root.resolve()
    result = _catalog(root).rebuild(dry_run=dry_run)
    return CommandOutcome(
        command="catalog rebuild",
        data={
            "catalog_path": _relative(root, result.catalog_path),
            "record_count": result.record_count,
            "source_digest": result.source_digest,
            "written": result.written,
        },
        messages=(
            "Catalog rebuild preview completed."
            if dry_run
            else "Catalog rebuilt from canonical Markdown."
        ,),
        changed=result.written,
        dry_run=dry_run,
    )


def catalog_verify_outcome(
    repository_root: Path, *, dry_run: bool = False
) -> CommandOutcome:
    root = repository_root.resolve()
    result = _catalog(root).verify()
    diagnostics = tuple(
        Diagnostic(
            "PD_CATALOG_DRIFT",
            issue,
            _relative(root, result.catalog_path),
        )
        for issue in result.issues
    )
    return CommandOutcome(
        command="catalog verify",
        data={
            "catalog_path": _relative(root, result.catalog_path),
            "current": result.current,
            "source_count": result.source_count,
            "catalog_count": result.catalog_count,
            "source_digest": result.source_digest,
            "issues": list(result.issues),
        },
        messages=(
            "Catalog matches canonical Markdown."
            if result.current
            else "Catalog verification found drift."
        ,),
        diagnostics=diagnostics,
        dry_run=dry_run,
    )


def catalog_stats_outcome(
    repository_root: Path, *, dry_run: bool = False
) -> CommandOutcome:
    root = repository_root.resolve()
    result = _catalog(root).stats()
    return CommandOutcome(
        command="catalog stats",
        data={
            "catalog_path": _relative(root, result.catalog_path),
            "record_count": result.record_count,
            "tag_count": result.tag_count,
            "relation_count": result.relation_count,
            "statuses": dict(result.status_counts),
            "memory_types": dict(result.type_counts),
        },
        messages=("Catalog statistics loaded.",),
        dry_run=dry_run,
    )
