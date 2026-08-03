"""Storage-neutral values for deterministic Coding context assembly."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath
import re


_TASK_ID = re.compile(r"^TASK-[A-Z0-9][A-Z0-9_-]*$")
_SESSION_ID = re.compile(r"^SESSION-[A-Z0-9][A-Z0-9_-]*$")
_CHECKPOINT_ID = re.compile(r"^CHECKPOINT-[A-Z0-9][A-Z0-9_-]*$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field} must be a non-empty string without surrounding whitespace")
    return value


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _text(value, field)


def _tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise ValueError(f"{field} must be a tuple")
    result = tuple(_text(item, f"{field} item") for item in value)
    if len(set(result)) != len(result):
        raise ValueError(f"{field} must not contain duplicates")
    return result


def _path(value: object, field: str, *, directory_signal: bool = False) -> str:
    checked = _text(value, field)
    if "\\" in checked:
        raise ValueError(f"{field} must use repository-relative POSIX paths")
    candidate = checked[:-1] if directory_signal and checked.endswith("/") else checked
    path = PurePosixPath(candidate)
    if (
        not candidate
        or path.is_absolute()
        or candidate in (".", "..")
        or ".." in path.parts
        or path.parts[0].endswith(":")
        or path.as_posix() != candidate
    ):
        raise ValueError(f"{field} must be a canonical repository-relative POSIX path")
    return checked


def _count(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{field} must be an integer of at least {minimum}")
    return value


class ContextSourceKind(str, Enum):
    KNOWLEDGE = "knowledge"
    MEMORY = "memory"


class ContextPriority(str, Enum):
    REQUIRED = "required"
    RELEVANT = "relevant"
    RELATED = "related"


@dataclass(frozen=True)
class ContextRequest:
    intent: str
    task_id: str
    explicit_paths: tuple[str, ...] = ()
    explicit_symbols: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    budget_tokens: int = 12000

    def __post_init__(self) -> None:
        _text(self.intent, "intent")
        if not isinstance(self.task_id, str) or not _TASK_ID.fullmatch(self.task_id):
            raise ValueError("task_id must use the TASK-... format")
        paths = _tuple(self.explicit_paths, "explicit_paths")
        for item in paths:
            _path(item, "explicit_paths item", directory_signal=True)
        _tuple(self.explicit_symbols, "explicit_symbols")
        _tuple(self.keywords, "keywords")
        if (
            isinstance(self.budget_tokens, bool)
            or not isinstance(self.budget_tokens, int)
            or not 1 <= self.budget_tokens <= 1_000_000
        ):
            raise ValueError("budget_tokens must be between 1 and 1000000")


@dataclass(frozen=True)
class ContextDocument:
    document_id: str
    path: str
    source_kind: ContextSourceKind
    title: str
    priority: ContextPriority
    estimated_tokens: int
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.document_id, "document_id")
        _path(self.path, "path")
        try:
            object.__setattr__(self, "source_kind", ContextSourceKind(self.source_kind))
        except (TypeError, ValueError) as error:
            raise ValueError("source_kind must be knowledge or memory") from error
        _text(self.title, "title")
        try:
            object.__setattr__(self, "priority", ContextPriority(self.priority))
        except (TypeError, ValueError) as error:
            raise ValueError("priority must be required, relevant, or related") from error
        _count(self.estimated_tokens, "estimated_tokens", minimum=1)
        reasons = _tuple(self.reasons, "reasons")
        if not reasons:
            raise ValueError("context document requires at least one selection reason")


@dataclass(frozen=True)
class ContextExclusion:
    document_id: str
    path: str
    reason: str
    estimated_tokens: int

    def __post_init__(self) -> None:
        _text(self.document_id, "document_id")
        _path(self.path, "path")
        _text(self.reason, "reason")
        _count(self.estimated_tokens, "estimated_tokens", minimum=1)


@dataclass(frozen=True)
class ContextManifest:
    request: ContextRequest
    session_id: str | None
    checkpoint_id: str | None
    source_digest: str
    estimated_tokens: int
    documents: tuple[ContextDocument, ...]
    excluded: tuple[ContextExclusion, ...]
    warnings: tuple[str, ...]
    checksum: str
    manifest_version: str = "0.1"
    profile: str = "coding"

    def __post_init__(self) -> None:
        if not isinstance(self.request, ContextRequest):
            raise ValueError("request must be a ContextRequest")
        session_id = _optional_text(self.session_id, "session_id")
        if session_id is not None and not _SESSION_ID.fullmatch(session_id):
            raise ValueError("session_id must use the SESSION-... format")
        checkpoint_id = _optional_text(self.checkpoint_id, "checkpoint_id")
        if checkpoint_id is not None and not _CHECKPOINT_ID.fullmatch(checkpoint_id):
            raise ValueError("checkpoint_id must use the CHECKPOINT-... format")
        if not isinstance(self.source_digest, str) or not _DIGEST.fullmatch(
            self.source_digest
        ):
            raise ValueError("source_digest must be a canonical sha256 digest")
        _count(self.estimated_tokens, "estimated_tokens")
        if not isinstance(self.documents, tuple) or not all(
            isinstance(item, ContextDocument) for item in self.documents
        ):
            raise ValueError("documents must contain ContextDocument values")
        if sum(item.estimated_tokens for item in self.documents) != self.estimated_tokens:
            raise ValueError("estimated_tokens must equal the selected document total")
        ids = tuple(item.document_id for item in self.documents)
        if len(set(ids)) != len(ids):
            raise ValueError("documents must not contain duplicate identities")
        if not isinstance(self.excluded, tuple) or not all(
            isinstance(item, ContextExclusion) for item in self.excluded
        ):
            raise ValueError("excluded must contain ContextExclusion values")
        excluded_ids = tuple(item.document_id for item in self.excluded)
        if len(set(excluded_ids)) != len(excluded_ids):
            raise ValueError("excluded must not contain duplicate identities")
        if set(ids).intersection(excluded_ids):
            raise ValueError("selected and excluded identities must be disjoint")
        _tuple(self.warnings, "warnings")
        if not isinstance(self.checksum, str) or not _DIGEST.fullmatch(self.checksum):
            raise ValueError("checksum must be a canonical sha256 digest")
        if self.manifest_version != "0.1":
            raise ValueError("manifest_version must be 0.1")
        if self.profile != "coding":
            raise ValueError("profile must be coding")
