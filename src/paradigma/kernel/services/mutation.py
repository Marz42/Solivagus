"""Pure lifecycle transitions for immutable MemoryRecord values."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any, Mapping

from ..models._validation import require_aware_datetime
from ..models.memory import MemoryRecord, MemoryStatus
from ..models.relation import MemoryRelation


class MemoryTransitionError(ValueError):
    """Raised when a requested lifecycle transition is not allowed."""


_REVISION_FIELDS = {
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
}


def commit_candidate(record: MemoryRecord, *, at: datetime) -> MemoryRecord:
    _require_record(record)
    _require_state(record, (MemoryStatus.CANDIDATE,), "commit")
    return _replace_revision(record, at=at, status=MemoryStatus.ACTIVE)


def revise_record(
    record: MemoryRecord, *, changes: Mapping[str, Any], at: datetime
) -> MemoryRecord:
    _require_record(record)
    _require_state(
        record,
        (MemoryStatus.CANDIDATE, MemoryStatus.ACTIVE),
        "revise",
    )
    if not isinstance(changes, Mapping) or not changes:
        raise MemoryTransitionError("revise changes must be a non-empty mapping")
    unknown = sorted(set(changes) - _REVISION_FIELDS)
    if unknown:
        raise MemoryTransitionError(
            f"revise cannot change reserved fields: {', '.join(unknown)}"
        )
    if "provenance" not in changes:
        raise MemoryTransitionError("revise must provide provenance for the new revision")
    return _replace_revision(record, at=at, **dict(changes))


def supersede_record(
    record: MemoryRecord, *, replacement_id: str, at: datetime
) -> MemoryRecord:
    _require_record(record)
    _require_state(record, (MemoryStatus.ACTIVE,), "supersede")
    relation = MemoryRelation("superseded_by", replacement_id)
    if relation in record.relations:
        raise MemoryTransitionError("record already names that replacement")
    return _replace_revision(
        record,
        at=at,
        status=MemoryStatus.SUPERSEDED,
        relations=(*record.relations, relation),
    )


def forget_record(record: MemoryRecord, *, at: datetime) -> MemoryRecord:
    _require_record(record)
    if record.status is MemoryStatus.TOMBSTONED:
        raise MemoryTransitionError("record is already tombstoned")
    return _replace_revision(record, at=at, status=MemoryStatus.TOMBSTONED)


def _replace_revision(
    record: MemoryRecord, *, at: datetime, **changes: Any
) -> MemoryRecord:
    instant = require_aware_datetime(at, "at")
    if instant < record.updated_at:
        raise MemoryTransitionError("transition time must not precede updated_at")
    try:
        return replace(
            record,
            revision=record.revision + 1,
            updated_at=instant,
            **changes,
        )
    except ValueError as error:
        if isinstance(error, MemoryTransitionError):
            raise
        raise MemoryTransitionError(str(error)) from error


def _require_record(record: object) -> MemoryRecord:
    if not isinstance(record, MemoryRecord):
        raise MemoryTransitionError("record must be a MemoryRecord")
    return record


def _require_state(
    record: MemoryRecord, allowed: tuple[MemoryStatus, ...], operation: str
) -> None:
    if record.status not in allowed:
        values = ", ".join(item.value for item in allowed)
        raise MemoryTransitionError(
            f"{operation} requires status {values}; found {record.status.value}"
        )
