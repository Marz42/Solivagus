"""Object-returning Application API and outcomes for memory retrieval/explain."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from paradigma.errors import ParadigmaError
from paradigma.kernel import MemoryRecord, MemoryResult, MemoryStatus
from paradigma.storage.catalog import (
    CatalogQuery,
    CatalogVerification,
    SQLiteMemoryCatalog,
)
from paradigma.storage.contract import StoredMemory
from paradigma.storage.markdown import MarkdownMemoryStore

from ..config import require_valid_config
from .outcomes import CommandOutcome


@dataclass(frozen=True)
class MemoryExplanation:
    stored: StoredMemory
    evaluated_at: datetime
    ordinary_status_eligible: bool
    valid_at_evaluation: bool
    catalog_current: bool
    catalog_issues: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class _MemoryRuntime:
    root: Path
    store: MarkdownMemoryStore
    catalog: SQLiteMemoryCatalog


def query_memories(
    repository_root: Path, request: CatalogQuery
) -> tuple[MemoryResult, ...]:
    """Query the current derived catalog without exposing CLI concerns."""

    return _runtime(repository_root).catalog.query(request)


def explain_memory(
    repository_root: Path,
    memory_id: str,
    *,
    at: datetime | None = None,
) -> MemoryExplanation:
    """Explain canonical record state even when the derived catalog is stale."""

    runtime = _runtime(repository_root)
    stored = runtime.store.read(memory_id)
    evaluated_at = at or datetime.now(timezone.utc)
    if not isinstance(evaluated_at, datetime) or evaluated_at.tzinfo is None:
        raise ValueError("explain time must be timezone-aware")
    warnings = []
    ordinary_status_eligible = stored.record.status is MemoryStatus.ACTIVE
    if not ordinary_status_eligible:
        warnings.append(
            f"excluded from ordinary queries: status {stored.record.status.value}"
        )
    valid_at_evaluation = stored.record.is_valid_at(evaluated_at)
    if not valid_at_evaluation:
        warnings.append("validity interval does not include explanation time")
    if not stored.canonical:
        warnings.append("document is valid but not in canonical managed formatting")
    try:
        verification = runtime.catalog.verify()
    except (OSError, ParadigmaError) as error:
        verification = CatalogVerification(
            runtime.catalog.path,
            False,
            0,
            0,
            "",
            (f"catalog verification unavailable: {error}",),
        )
    if not verification.current:
        warnings.extend(f"catalog: {issue}" for issue in verification.issues)
    return MemoryExplanation(
        stored,
        evaluated_at,
        ordinary_status_eligible,
        valid_at_evaluation,
        verification.current,
        verification.issues,
        tuple(warnings),
    )


def memory_query_outcome(
    repository_root: Path,
    request: CatalogQuery,
    *,
    dry_run: bool = False,
) -> CommandOutcome:
    root = repository_root.resolve()
    runtime = _runtime(root)
    results = runtime.catalog.query(request)
    return CommandOutcome(
        command="memory query",
        data={
            "count": len(results),
            "results": [
                _result_payload(
                    root,
                    item,
                    runtime.store.path_for(item.record.memory_id),
                )
                for item in results
            ],
        },
        messages=(f"Memory query returned {len(results)} result(s).",),
        dry_run=dry_run,
    )


def memory_explain_outcome(
    repository_root: Path,
    memory_id: str,
    *,
    at: datetime | None = None,
    dry_run: bool = False,
) -> CommandOutcome:
    root = repository_root.resolve()
    explanation = explain_memory(root, memory_id, at=at)
    payload = _stored_payload(root, explanation.stored)
    payload.update(
        {
            "evaluated_at": _instant(explanation.evaluated_at),
            "ordinary_status_eligible": explanation.ordinary_status_eligible,
            "valid_at_evaluation": explanation.valid_at_evaluation,
            "catalog_current": explanation.catalog_current,
            "catalog_issues": list(explanation.catalog_issues),
            "warnings": list(explanation.warnings),
        }
    )
    return CommandOutcome(
        command="memory explain",
        data=payload,
        messages=(f"Memory explanation loaded for {memory_id}.",),
        dry_run=dry_run,
    )


def _runtime(repository_root: Path) -> _MemoryRuntime:
    config = require_valid_config(repository_root)
    store = MarkdownMemoryStore(config.memory_root)
    return _MemoryRuntime(
        config.repository_root,
        store,
        SQLiteMemoryCatalog(
            config.catalog_path,
            store,
            path_base=config.repository_root,
        ),
    )


def _result_payload(
    root: Path, result: MemoryResult, path: Path
) -> dict[str, Any]:
    payload = _record_payload(result.record)
    payload.update(
        {
            "path": _relative(root, path),
            "score": result.score,
            "matched_fields": list(result.matched_fields),
            "match_reasons": list(result.match_reasons),
            "relation_source_id": result.relation_source_id,
            "warnings": list(result.warnings),
        }
    )
    return payload


def _stored_payload(root: Path, stored: StoredMemory) -> dict[str, Any]:
    payload = _record_payload(stored.record)
    payload.update(
        {
            "path": _relative(root, stored.path),
            "content_hash": stored.content_hash,
            "source_hash": stored.source_hash,
            "canonical": stored.canonical,
        }
    )
    return payload


def _record_payload(record: MemoryRecord) -> dict[str, Any]:
    return {
        "memory_id": record.memory_id,
        "memory_type": record.memory_type.value,
        "title": record.title,
        "content": record.content,
        "scope": {
            "namespace": record.scope.namespace,
            "workspace_id": record.scope.workspace_id,
            "project_id": record.scope.project_id,
            "task_id": record.scope.task_id,
            "session_id": record.scope.session_id,
            "entity_ids": list(record.scope.entity_ids),
        },
        "validity": {
            "from": _instant(record.valid_from),
            "until": _instant(record.valid_until),
        },
        "status": record.status.value,
        "provenance": [
            {
                "source_type": item.source_type.value,
                "source_uri": item.source_uri,
                "source_id": item.source_id,
                "observed_at": _instant(item.observed_at),
                "excerpt_hash": item.excerpt_hash,
                "actor": item.actor,
            }
            for item in record.provenance
        ],
        "confidence": record.confidence,
        "sensitivity": record.sensitivity,
        "tags": list(record.tags),
        "relations": [
            {
                "relation_type": item.relation_type,
                "target_memory_id": item.target_memory_id,
            }
            for item in record.relations
        ],
        "revision": record.revision,
        "created_at": _instant(record.created_at),
        "updated_at": _instant(record.updated_at),
    }


def _instant(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat(timespec="microseconds")


def _relative(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)
