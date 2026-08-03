"""Immutable, storage-neutral values for the Coding domain integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import math
from pathlib import PurePosixPath
import re

from ...kernel import MemoryScope


_IDENTIFIER_PATTERNS = {
    "task_id": re.compile(r"^TASK-[A-Z0-9][A-Z0-9_-]*$"),
    "session_id": re.compile(r"^SESSION-[A-Z0-9][A-Z0-9_-]*$"),
    "checkpoint_id": re.compile(r"^CHECKPOINT-[A-Z0-9][A-Z0-9_-]*$"),
}
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{7,64}$")
_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    if value != value.strip():
        raise ValueError(f"{field} must not have surrounding whitespace")
    return value


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _text(value, field)


def _identifier(value: object, field: str) -> str:
    checked = _text(value, field)
    if not _IDENTIFIER_PATTERNS[field].fullmatch(checked):
        prefix = field.removesuffix("_id").upper()
        raise ValueError(f"{field} must use the {prefix}-... format")
    return checked


def _instant(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    if value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value


def _enum(value: object, enum_type: type[Enum], field: str) -> Enum:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as error:
        allowed = ", ".join(str(item.value) for item in enum_type)
        raise ValueError(f"{field} must be one of: {allowed}") from error


def _text_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise ValueError(f"{field} must be a tuple")
    checked = tuple(_text(item, f"{field} item") for item in value)
    if len(set(checked)) != len(checked):
        raise ValueError(f"{field} must not contain duplicates")
    return checked


def _relative_path(value: object, field: str, *, allow_root: bool = False) -> str:
    checked = _text(value, field)
    if allow_root and checked == ".":
        return checked
    if "\\" in checked:
        raise ValueError(f"{field} must use repository-relative POSIX paths")
    path = PurePosixPath(checked)
    if path.is_absolute() or checked != path.as_posix():
        raise ValueError(f"{field} must use repository-relative POSIX paths")
    if checked in (".", "..") or ".." in path.parts:
        raise ValueError(f"{field} must stay inside the repository")
    return checked


def _path_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise ValueError(f"{field} must be a tuple")
    checked = tuple(_relative_path(item, f"{field} item") for item in value)
    if len(set(checked)) != len(checked):
        raise ValueError(f"{field} must not contain duplicates")
    return checked


def _nonnegative_integer(value: object, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer or None")
    return value


def _exit_code(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("exit_code must be an integer or None")
    return value


def _duration(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("duration_seconds must be a non-negative number or None")
    if not math.isfinite(value) or value < 0:
        raise ValueError("duration_seconds must be a non-negative number or None")
    return float(value)


def _digest(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _DIGEST_PATTERN.fullmatch(value):
        raise ValueError("output_hash must be sha256: followed by 64 lowercase hex digits")
    return value


class TaskStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    BLOCKED = "blocked"
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    ABORTED = "aborted"


class SessionStatus(str, Enum):
    ACTIVE = "active"
    ENDED = "ended"
    ABORTED = "aborted"


class EvidenceStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass(frozen=True)
class RepositoryScope:
    workspace_id: str
    repository_id: str
    repository_path: str = "."
    remote_url: str | None = None

    def __post_init__(self) -> None:
        _text(self.workspace_id, "workspace_id")
        _text(self.repository_id, "repository_id")
        _relative_path(self.repository_path, "repository_path", allow_root=True)
        _optional_text(self.remote_url, "remote_url")

    def memory_scope(
        self,
        *,
        task_id: str | None = None,
        session_id: str | None = None,
        entity_ids: tuple[str, ...] = (),
    ) -> MemoryScope:
        """Project this Coding scope into the domain-neutral Kernel scope."""

        if task_id is not None:
            _identifier(task_id, "task_id")
        if session_id is not None:
            _identifier(session_id, "session_id")
        return MemoryScope(
            namespace="coding",
            workspace_id=self.workspace_id,
            project_id=self.repository_id,
            task_id=task_id,
            session_id=session_id,
            entity_ids=_text_tuple(entity_ids, "entity_ids"),
        )


@dataclass(frozen=True)
class CodingTask:
    task_id: str
    repository: RepositoryScope
    title: str
    goal: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    status_reason: str | None = None
    parent_task_id: str | None = None

    def __post_init__(self) -> None:
        _identifier(self.task_id, "task_id")
        if not isinstance(self.repository, RepositoryScope):
            raise ValueError("repository must be a RepositoryScope")
        _text(self.title, "title")
        _text(self.goal, "goal")
        status = _enum(self.status, TaskStatus, "status")
        object.__setattr__(self, "status", status)
        created = _instant(self.created_at, "created_at")
        updated = _instant(self.updated_at, "updated_at")
        if updated < created:
            raise ValueError("updated_at must not be before created_at")
        _optional_text(self.status_reason, "status_reason")
        if status in (TaskStatus.BLOCKED, TaskStatus.SUSPENDED):
            if self.status_reason is None:
                raise ValueError("blocked or suspended tasks require status_reason")
        if self.parent_task_id is not None:
            _identifier(self.parent_task_id, "task_id")
            if self.parent_task_id == self.task_id:
                raise ValueError("parent_task_id must differ from task_id")


@dataclass(frozen=True)
class CodingSession:
    session_id: str
    task_id: str
    repository: RepositoryScope
    status: SessionStatus
    started_at: datetime
    updated_at: datetime
    ended_at: datetime | None = None
    agent_id: str | None = None
    current_checkpoint_id: str | None = None

    def __post_init__(self) -> None:
        _identifier(self.session_id, "session_id")
        _identifier(self.task_id, "task_id")
        if not isinstance(self.repository, RepositoryScope):
            raise ValueError("repository must be a RepositoryScope")
        status = _enum(self.status, SessionStatus, "status")
        object.__setattr__(self, "status", status)
        started = _instant(self.started_at, "started_at")
        updated = _instant(self.updated_at, "updated_at")
        if updated < started:
            raise ValueError("updated_at must not be before started_at")
        if self.ended_at is not None:
            ended = _instant(self.ended_at, "ended_at")
            if ended < started or updated < ended:
                raise ValueError("ended_at must be between started_at and updated_at")
        if status is SessionStatus.ACTIVE and self.ended_at is not None:
            raise ValueError("active session must not have ended_at")
        if status is not SessionStatus.ACTIVE and self.ended_at is None:
            raise ValueError("ended or aborted session requires ended_at")
        _optional_text(self.agent_id, "agent_id")
        if self.current_checkpoint_id is not None:
            _identifier(self.current_checkpoint_id, "checkpoint_id")


@dataclass(frozen=True)
class GitEvidence:
    repository_id: str
    observed_at: datetime
    head_commit: str | None
    branch: str | None
    dirty: bool
    worktree_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.repository_id, "repository_id")
        _instant(self.observed_at, "observed_at")
        if self.head_commit is not None and not _COMMIT_PATTERN.fullmatch(
            self.head_commit
        ):
            raise ValueError("head_commit must be 7 to 64 lowercase hex digits")
        _optional_text(self.branch, "branch")
        if not isinstance(self.dirty, bool):
            raise ValueError("dirty must be a boolean")
        paths = _path_tuple(self.worktree_paths, "worktree_paths")
        if not self.dirty and paths:
            raise ValueError("clean Git evidence must not contain worktree_paths")


@dataclass(frozen=True)
class TestEvidence:
    command: str
    status: EvidenceStatus
    observed_at: datetime
    exit_code: int | None = None
    passed_count: int | None = None
    failed_count: int | None = None
    skipped_count: int | None = None
    duration_seconds: float | None = None
    report_path: str | None = None
    output_hash: str | None = None

    def __post_init__(self) -> None:
        _text(self.command, "command")
        status = _enum(self.status, EvidenceStatus, "status")
        object.__setattr__(self, "status", status)
        _instant(self.observed_at, "observed_at")
        exit_code = _exit_code(self.exit_code)
        _nonnegative_integer(self.passed_count, "passed_count")
        failed_count = _nonnegative_integer(self.failed_count, "failed_count")
        _nonnegative_integer(self.skipped_count, "skipped_count")
        _duration(self.duration_seconds)
        if self.report_path is not None:
            _relative_path(self.report_path, "report_path")
        _digest(self.output_hash)
        if status is EvidenceStatus.PASSED:
            if exit_code not in (None, 0) or failed_count not in (None, 0):
                raise ValueError("passed test evidence cannot report failure")


@dataclass(frozen=True)
class BuildEvidence:
    command: str
    status: EvidenceStatus
    observed_at: datetime
    exit_code: int | None = None
    duration_seconds: float | None = None
    artifact_paths: tuple[str, ...] = ()
    output_hash: str | None = None

    def __post_init__(self) -> None:
        _text(self.command, "command")
        status = _enum(self.status, EvidenceStatus, "status")
        object.__setattr__(self, "status", status)
        _instant(self.observed_at, "observed_at")
        exit_code = _exit_code(self.exit_code)
        _duration(self.duration_seconds)
        _path_tuple(self.artifact_paths, "artifact_paths")
        _digest(self.output_hash)
        if status is EvidenceStatus.PASSED and exit_code not in (None, 0):
            raise ValueError("passed build evidence cannot report a non-zero exit_code")


@dataclass(frozen=True)
class CodingCheckpoint:
    checkpoint_id: str
    task_id: str
    session_id: str
    created_at: datetime
    task_status: TaskStatus
    git: GitEvidence | None = None
    tests: tuple[TestEvidence, ...] = ()
    builds: tuple[BuildEvidence, ...] = ()
    touched_paths: tuple[str, ...] = ()
    summary: str | None = None
    completed_work: tuple[str, ...] = ()
    remaining_work: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    next_steps: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.checkpoint_id, "checkpoint_id")
        _identifier(self.task_id, "task_id")
        _identifier(self.session_id, "session_id")
        _instant(self.created_at, "created_at")
        status = _enum(self.task_status, TaskStatus, "task_status")
        object.__setattr__(self, "task_status", status)
        if self.git is not None and not isinstance(self.git, GitEvidence):
            raise ValueError("git must be GitEvidence or None")
        if not isinstance(self.tests, tuple) or not all(
            isinstance(item, TestEvidence) for item in self.tests
        ):
            raise ValueError("tests must contain only TestEvidence values")
        if not isinstance(self.builds, tuple) or not all(
            isinstance(item, BuildEvidence) for item in self.builds
        ):
            raise ValueError("builds must contain only BuildEvidence values")
        _path_tuple(self.touched_paths, "touched_paths")
        _optional_text(self.summary, "summary")
        _text_tuple(self.completed_work, "completed_work")
        _text_tuple(self.remaining_work, "remaining_work")
        _text_tuple(self.blockers, "blockers")
        _text_tuple(self.next_steps, "next_steps")
        if status is TaskStatus.BLOCKED and not self.blockers:
            raise ValueError("blocked checkpoint must describe at least one blocker")
