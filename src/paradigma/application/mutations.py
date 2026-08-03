"""Application services for the canonical memory mutation lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from paradigma.config import require_valid_config
from paradigma.errors import ParadigmaError
from paradigma.kernel import (
    MemoryRecord,
    MemoryRelation,
    MemoryScope,
    MemoryStatus,
    ProvenanceRef,
    commit_candidate,
    forget_record,
    generate_memory_id,
    revise_record,
    supersede_record,
)
from paradigma.storage.catalog import SQLiteMemoryCatalog
from paradigma.storage.contract import StoredMemory
from paradigma.storage.markdown import MarkdownMemoryStore

from .outcomes import CommandOutcome


class MemoryInputError(ParadigmaError, ValueError):
    code = "PD_MEMORY_INPUT_ERROR"
    exit_code = 2


class MemoryMutationError(ParadigmaError):
    code = "PD_MEMORY_MUTATION_ERROR"
    exit_code = 2


class MemoryCatalogRefreshError(MemoryMutationError):
    code = "PD_MEMORY_CATALOG_REFRESH"
    exit_code = 4


@dataclass(frozen=True)
class MemoryMutationResult:
    record: MemoryRecord
    path: Path
    content_hash: str
    source_hash: str
    written: bool
    catalog_refreshed: bool


@dataclass(frozen=True)
class MemoryValidationResult:
    stored: StoredMemory


@dataclass(frozen=True)
class _Runtime:
    root: Path
    store: MarkdownMemoryStore
    catalog: SQLiteMemoryCatalog


_PAYLOAD_FIELDS = {
    "memory_type",
    "title",
    "content",
    "scope",
    "provenance",
    "validity",
    "confidence",
    "sensitivity",
    "tags",
    "relations",
}
_REQUIRED_PROPOSAL_FIELDS = {
    "memory_type",
    "title",
    "content",
    "scope",
    "provenance",
}


def propose_memory(
    repository_root: Path,
    payload: Mapping[str, Any],
    *,
    write: bool = False,
    memory_id: str | None = None,
    at: datetime | None = None,
    randomness: bytes | None = None,
) -> MemoryMutationResult:
    runtime = _runtime(repository_root)
    instant = _instant(at)
    identifier = memory_id or generate_memory_id(instant, randomness=randomness)
    record = _record_from_payload(
        payload,
        memory_id=identifier,
        status=MemoryStatus.CANDIDATE,
        revision=1,
        created_at=instant,
        updated_at=instant,
    )
    path = runtime.store.path_for(identifier)
    if path.exists() or path.is_symlink():
        raise MemoryMutationError(f"memory document already exists: {path}")
    if not write:
        return _preview(runtime.store, record)
    stored = runtime.store.create(record)
    _refresh_catalog(runtime, stored)
    return _written(stored)


def validate_memory(
    repository_root: Path, memory_id: str
) -> MemoryValidationResult:
    return MemoryValidationResult(_runtime(repository_root).store.read(memory_id))


def commit_memory(
    repository_root: Path,
    memory_id: str,
    *,
    expected_source_hash: str,
    write: bool = False,
    at: datetime | None = None,
) -> MemoryMutationResult:
    runtime = _runtime(repository_root)
    current = _current(runtime, memory_id, expected_source_hash)
    try:
        updated = commit_candidate(current.record, at=_instant(at))
    except ValueError as error:
        raise MemoryMutationError(str(error)) from error
    return _publish_update(runtime, updated, current, write=write)


def revise_memory(
    repository_root: Path,
    memory_id: str,
    changes: Mapping[str, Any],
    *,
    expected_source_hash: str,
    write: bool = False,
    at: datetime | None = None,
) -> MemoryMutationResult:
    runtime = _runtime(repository_root)
    current = _current(runtime, memory_id, expected_source_hash)
    if not isinstance(changes, Mapping) or not changes:
        raise MemoryInputError("revision input must be a non-empty mapping")
    unknown = sorted(set(changes) - _PAYLOAD_FIELDS)
    if unknown:
        raise MemoryInputError(f"revision input has unknown fields: {', '.join(unknown)}")
    if "provenance" not in changes:
        raise MemoryInputError("revision input must provide provenance")
    merged = _record_payload(current.record)
    merged.update(dict(changes))
    template = _record_from_payload(
        merged,
        memory_id=current.record.memory_id,
        status=current.record.status,
        revision=current.record.revision,
        created_at=current.record.created_at,
        updated_at=current.record.updated_at,
    )
    mutation_fields = {
        field: getattr(template, field)
        for field in (
            "memory_type",
            "title",
            "content",
            "scope",
            "provenance",
            "valid_from",
            "valid_until",
            "confidence",
            "sensitivity",
            "tags",
            "relations",
        )
    }
    try:
        updated = revise_record(
            current.record,
            changes=mutation_fields,
            at=_instant(at),
        )
    except ValueError as error:
        raise MemoryMutationError(str(error)) from error
    return _publish_update(runtime, updated, current, write=write)


def supersede_memory(
    repository_root: Path,
    memory_id: str,
    replacement_id: str,
    *,
    expected_source_hash: str,
    write: bool = False,
    at: datetime | None = None,
) -> MemoryMutationResult:
    runtime = _runtime(repository_root)
    current = _current(runtime, memory_id, expected_source_hash)
    replacement = runtime.store.read(replacement_id)
    if replacement.record.status is not MemoryStatus.ACTIVE:
        raise MemoryMutationError("replacement memory must be active")
    try:
        updated = supersede_record(
            current.record,
            replacement_id=replacement.record.memory_id,
            at=_instant(at),
        )
    except ValueError as error:
        raise MemoryMutationError(str(error)) from error
    return _publish_update(runtime, updated, current, write=write)


def forget_memory(
    repository_root: Path,
    memory_id: str,
    *,
    expected_source_hash: str,
    write: bool = False,
    at: datetime | None = None,
) -> MemoryMutationResult:
    runtime = _runtime(repository_root)
    current = _current(runtime, memory_id, expected_source_hash)
    try:
        updated = forget_record(current.record, at=_instant(at))
    except ValueError as error:
        raise MemoryMutationError(str(error)) from error
    return _publish_update(runtime, updated, current, write=write)


def mutation_outcome(
    command: str,
    result: MemoryMutationResult,
    *,
    repository_root: Path,
) -> CommandOutcome:
    root = repository_root.resolve()
    try:
        path = result.path.relative_to(root).as_posix()
    except ValueError:
        path = str(result.path)
    return CommandOutcome(
        command=command,
        data={
            "memory_id": result.record.memory_id,
            "status": result.record.status.value,
            "revision": result.record.revision,
            "path": path,
            "content_hash": result.content_hash,
            "source_hash": result.source_hash,
            "written": result.written,
            "catalog_refreshed": result.catalog_refreshed,
        },
        messages=(
            "Memory mutation preview completed."
            if not result.written
            else "Memory mutation committed and catalog refreshed."
        ,),
        changed=result.written,
        dry_run=not result.written,
    )


def validation_outcome(
    repository_root: Path,
    result: MemoryValidationResult,
    *,
    dry_run: bool = False,
) -> CommandOutcome:
    stored = result.stored
    root = repository_root.resolve()
    try:
        path = stored.path.relative_to(root).as_posix()
    except ValueError:
        path = str(stored.path)
    return CommandOutcome(
        command="memory validate",
        data={
            "memory_id": stored.record.memory_id,
            "status": stored.record.status.value,
            "revision": stored.record.revision,
            "path": path,
            "content_hash": stored.content_hash,
            "source_hash": stored.source_hash,
            "canonical": stored.canonical,
        },
        messages=("Memory document is valid.",),
        dry_run=dry_run,
    )


def _runtime(repository_root: Path) -> _Runtime:
    config = require_valid_config(repository_root)
    store = MarkdownMemoryStore(config.memory_root)
    return _Runtime(
        config.repository_root,
        store,
        SQLiteMemoryCatalog(
            config.catalog_path,
            store,
            path_base=config.repository_root,
        ),
    )


def _current(
    runtime: _Runtime, memory_id: str, expected_source_hash: str
) -> StoredMemory:
    _require_source_hash(expected_source_hash)
    current = runtime.store.read(memory_id)
    if current.source_hash != expected_source_hash:
        raise MemoryMutationError(
            "memory document changed since validation; refusing mutation"
        )
    return current


def _publish_update(
    runtime: _Runtime,
    updated: MemoryRecord,
    current: StoredMemory,
    *,
    write: bool,
) -> MemoryMutationResult:
    if not write:
        return _preview(runtime.store, updated)
    stored = runtime.store.update(
        updated,
        expected_source_hash=current.source_hash,
    )
    _refresh_catalog(runtime, stored)
    return _written(stored)


def _refresh_catalog(runtime: _Runtime, stored: StoredMemory) -> None:
    try:
        runtime.catalog.rebuild()
    except Exception as error:
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        raise MemoryCatalogRefreshError(
            "canonical memory mutation succeeded but catalog refresh failed; "
            f"run 'pd catalog rebuild' before querying ({stored.record.memory_id}): "
            f"{error}"
        ) from error


def _preview(store: MarkdownMemoryStore, record: MemoryRecord) -> MemoryMutationResult:
    source = store.codec.encode(record)
    return MemoryMutationResult(
        record,
        store.path_for(record.memory_id),
        store.codec.content_hash(record),
        store.codec.source_hash(source),
        False,
        False,
    )


def _written(stored: StoredMemory) -> MemoryMutationResult:
    return MemoryMutationResult(
        stored.record,
        stored.path,
        stored.content_hash,
        stored.source_hash,
        True,
        True,
    )


def _instant(value: datetime | None) -> datetime:
    instant = value or datetime.now(timezone.utc)
    if not isinstance(instant, datetime) or instant.tzinfo is None:
        raise MemoryInputError("mutation time must be timezone-aware")
    return instant


def _require_source_hash(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith("sha256:")
        or len(value) != 71
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise MemoryInputError(
            "expected_source_hash must be a canonical sha256 digest"
        )
    return value


def _record_from_payload(
    payload: Mapping[str, Any],
    *,
    memory_id: str,
    status: MemoryStatus,
    revision: int,
    created_at: datetime,
    updated_at: datetime,
) -> MemoryRecord:
    if not isinstance(payload, Mapping):
        raise MemoryInputError("memory input must be a mapping")
    unknown = sorted(set(payload) - _PAYLOAD_FIELDS)
    missing = sorted(_REQUIRED_PROPOSAL_FIELDS - set(payload))
    if unknown or missing:
        details = []
        if missing:
            details.append(f"missing {', '.join(missing)}")
        if unknown:
            details.append(f"unknown {', '.join(unknown)}")
        raise MemoryInputError(f"memory input fields invalid: {'; '.join(details)}")
    try:
        scope_data = _mapping_fields(
            payload["scope"],
            "scope",
            {
                "namespace",
                "workspace_id",
                "project_id",
                "task_id",
                "session_id",
                "entity_ids",
            },
            required={"namespace"},
        )
        provenance_data = _list(payload["provenance"], "provenance")
        validity_data = _mapping_fields(
            payload.get("validity", {}), "validity", {"from", "until"}
        )
        relation_data = _list(payload.get("relations", []), "relations")
        scope = MemoryScope(
            namespace=_text(scope_data.get("namespace"), "scope.namespace"),
            workspace_id=_optional_text(scope_data.get("workspace_id"), "scope.workspace_id"),
            project_id=_optional_text(scope_data.get("project_id"), "scope.project_id"),
            task_id=_optional_text(scope_data.get("task_id"), "scope.task_id"),
            session_id=_optional_text(scope_data.get("session_id"), "scope.session_id"),
            entity_ids=_text_tuple(scope_data.get("entity_ids", []), "scope.entity_ids"),
        )
        provenance_items = []
        for index, value in enumerate(provenance_data):
            field = f"provenance[{index}]"
            item = _mapping_fields(
                value,
                field,
                {
                    "source_type",
                    "source_uri",
                    "source_id",
                    "observed_at",
                    "excerpt_hash",
                    "actor",
                },
                required={"source_type"},
            )
            provenance_items.append(
                ProvenanceRef(
                    source_type=_text(item.get("source_type"), f"{field}.source_type"),
                    source_uri=_optional_text(item.get("source_uri"), f"{field}.source_uri"),
                    source_id=_optional_text(item.get("source_id"), f"{field}.source_id"),
                    observed_at=_optional_datetime(item.get("observed_at"), f"{field}.observed_at"),
                    excerpt_hash=_optional_text(item.get("excerpt_hash"), f"{field}.excerpt_hash"),
                    actor=_optional_text(item.get("actor"), f"{field}.actor"),
                )
            )
        provenance = tuple(provenance_items)
        relation_items = []
        for index, value in enumerate(relation_data):
            field = f"relations[{index}]"
            item = _mapping_fields(
                value,
                field,
                {"relation_type", "target_memory_id"},
                required={"relation_type", "target_memory_id"},
            )
            relation_items.append(
                MemoryRelation(
                    _text(item.get("relation_type"), f"{field}.relation_type"),
                    _text(item.get("target_memory_id"), f"{field}.target_memory_id"),
                )
            )
        relations = tuple(relation_items)
        return MemoryRecord(
            memory_id=memory_id,
            memory_type=_text(payload["memory_type"], "memory_type"),
            title=_text(payload["title"], "title"),
            content=_text(payload["content"], "content"),
            scope=scope,
            provenance=provenance,
            status=status,
            revision=revision,
            valid_from=_optional_datetime(validity_data.get("from"), "validity.from"),
            valid_until=_optional_datetime(validity_data.get("until"), "validity.until"),
            confidence=payload.get("confidence"),
            sensitivity=_text(payload.get("sensitivity", "internal"), "sensitivity"),
            tags=_text_tuple(payload.get("tags", []), "tags"),
            relations=relations,
            created_at=created_at,
            updated_at=updated_at,
        )
    except MemoryInputError:
        raise
    except (TypeError, ValueError) as error:
        raise MemoryInputError(f"invalid memory input: {error}") from error


def _record_payload(record: MemoryRecord) -> dict[str, Any]:
    return {
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
        "provenance": [
            {
                "source_type": item.source_type.value,
                "source_uri": item.source_uri,
                "source_id": item.source_id,
                "observed_at": _datetime_text(item.observed_at),
                "excerpt_hash": item.excerpt_hash,
                "actor": item.actor,
            }
            for item in record.provenance
        ],
        "validity": {
            "from": _datetime_text(record.valid_from),
            "until": _datetime_text(record.valid_until),
        },
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
    }


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise MemoryInputError(f"{field} must be a mapping with string keys")
    return value


def _mapping_fields(
    value: Any,
    field: str,
    allowed: set[str],
    *,
    required: set[str] | None = None,
) -> Mapping[str, Any]:
    mapping = _mapping(value, field)
    missing = sorted((required or set()) - set(mapping))
    unknown = sorted(set(mapping) - allowed)
    if missing or unknown:
        details = []
        if missing:
            details.append(f"missing {', '.join(missing)}")
        if unknown:
            details.append(f"unknown {', '.join(unknown)}")
        raise MemoryInputError(f"{field} fields invalid: {'; '.join(details)}")
    return mapping


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise MemoryInputError(f"{field} must be a list")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise MemoryInputError(f"{field} must be a string")
    return value


def _optional_text(value: Any, field: str) -> str | None:
    return None if value is None else _text(value, field)


def _text_tuple(value: Any, field: str) -> tuple[str, ...]:
    return tuple(
        _text(item, f"{field}[{index}]")
        for index, item in enumerate(_list(value, field))
    )


def _optional_datetime(value: Any, field: str) -> datetime | None:
    if value is None:
        return None
    text = _text(value, field)
    try:
        instant = datetime.fromisoformat(text)
    except ValueError as error:
        raise MemoryInputError(f"{field} must be an ISO 8601 datetime") from error
    if instant.tzinfo is None:
        raise MemoryInputError(f"{field} must be timezone-aware")
    return instant


def _datetime_text(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat(timespec="microseconds")
