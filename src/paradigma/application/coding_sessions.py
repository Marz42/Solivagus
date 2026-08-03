"""CodingSession and checkpoint lifecycle application service."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import require_valid_config
from ..errors import ParadigmaError
from ..integrations.coding import (
    BuildEvidence,
    CodingCheckpoint,
    CodingSession,
    GitEvidence,
    SessionStatus,
    TaskStatus,
    TestEvidence,
)
from ..runtime import (
    ActiveSessionPointer,
    ActiveTaskPointer,
    CodingCheckpointStore,
    CodingRuntimeConflictError,
    CodingRuntimeStore,
)
from .outcomes import CommandOutcome


class CodingSessionLifecycleError(ParadigmaError):
    code = "PD_SESSION_LIFECYCLE_ERROR"


def _stores(root: Path) -> tuple[CodingRuntimeStore, CodingCheckpointStore]:
    config = require_valid_config(root)
    runtime_root = config.repository_root / config.runtime_root_name
    return CodingRuntimeStore(runtime_root), CodingCheckpointStore(runtime_root)


def _now(value: datetime | None) -> datetime:
    result = value or datetime.now().astimezone()
    if result.tzinfo is None or result.utcoffset() is None:
        raise CodingSessionLifecycleError(
            "session time must be timezone-aware", code="PD_SESSION_INVALID_TIME"
        )
    return result


def _session_data(stored) -> dict[str, object]:
    value = stored.session
    return {
        "session_id": value.session_id,
        "task_id": value.task_id,
        "status": value.status.value,
        "agent_id": value.agent_id,
        "started_at": value.started_at.isoformat(),
        "updated_at": value.updated_at.isoformat(),
        "ended_at": value.ended_at.isoformat() if value.ended_at else None,
        "current_checkpoint_id": value.current_checkpoint_id,
        "snapshot_revision": stored.snapshot_revision,
        "source_hash": stored.source_hash,
    }


def session_status_outcome(root: Path, *, dry_run: bool = False) -> CommandOutcome:
    store, _ = _stores(root)
    pointer = store.read_active_session().pointer
    assert isinstance(pointer, ActiveSessionPointer)
    if pointer.session_id is None:
        return CommandOutcome(
            command="session status",
            data={"active": False, "session": None},
            messages=("No active CodingSession.",),
            dry_run=dry_run,
        )
    stored = store.read_session(pointer.session_id)
    return CommandOutcome(
        command="session status",
        data={"active": True, "session": _session_data(stored)},
        messages=(f"Active session {stored.session.session_id}.",),
        dry_run=dry_run,
    )


def start_session_outcome(
    root: Path,
    *,
    session_id: str,
    agent_id: str | None = None,
    write: bool = False,
    at: datetime | None = None,
) -> CommandOutcome:
    store, _ = _stores(root)
    instant = _now(at)
    task_pointer = store.read_active_task().pointer
    assert isinstance(task_pointer, ActiveTaskPointer)
    if task_pointer.task_id is None:
        raise CodingSessionLifecycleError(
            "session requires an active task", code="PD_SESSION_TASK_NOT_ACTIVE", exit_code=3
        )
    task = store.read_task(task_pointer.task_id).task
    if task.status is not TaskStatus.ACTIVE:
        raise CodingSessionLifecycleError(
            f"session requires active task status, got {task.status.value}",
            code="PD_SESSION_TASK_NOT_ACTIVE",
            exit_code=3,
        )
    pointer_stored = store.read_active_session()
    pointer = pointer_stored.pointer
    assert isinstance(pointer, ActiveSessionPointer)
    if pointer.session_id is not None:
        if write and pointer.session_id == session_id and pointer.task_id == task.task_id:
            stored = store.read_session(session_id)
            if (
                stored.session.status is SessionStatus.ACTIVE
                and stored.session.repository == task.repository
                and stored.session.agent_id == agent_id
            ):
                store.rebuild_projections()
                return CommandOutcome(
                    command="session start",
                    data={"session": _session_data(stored), "written": True},
                    messages=(f"Session {session_id} is active; projections rebuilt.",),
                    changed=True,
                )
        raise CodingSessionLifecycleError(
            f"active session already exists: {pointer.session_id}",
            code="PD_SESSION_ALREADY_ACTIVE",
            exit_code=3,
        )
    try:
        session = CodingSession(
            session_id,
            task.task_id,
            task.repository,
            SessionStatus.ACTIVE,
            instant,
            instant,
            agent_id=agent_id,
        )
    except ValueError as error:
        raise CodingSessionLifecycleError(str(error), code="PD_SESSION_INPUT_ERROR") from error
    if not write:
        return CommandOutcome(
            command="session start",
            data={"session_id": session_id, "task_id": task.task_id, "status": "active", "written": False},
            messages=("Session start plan validated; dry-run made no changes.",),
            dry_run=True,
        )
    try:
        try:
            stored = store.create_session(session)
        except CodingRuntimeConflictError:
            stored = store.read_session(session_id)
            if not (
                stored.session.task_id == task.task_id
                and stored.session.repository == task.repository
                and stored.session.status is SessionStatus.ACTIVE
                and stored.session.agent_id == agent_id
            ):
                raise
        store.set_active_session(
            ActiveSessionPointer(
                session_id,
                task.task_id,
                instant,
                last_session_id=pointer.last_session_id,
            ),
            expected_source_hash=pointer_stored.source_hash,
        )
        store.rebuild_projections()
    except CodingRuntimeConflictError as error:
        raise CodingSessionLifecycleError(str(error), code=error.code, exit_code=error.exit_code) from error
    return CommandOutcome(
        command="session start",
        data={"session": _session_data(stored), "written": True},
        messages=(f"Session {session_id} started.",),
        changed=True,
    )


def checkpoint_session_outcome(
    root: Path,
    *,
    checkpoint_id: str,
    git: GitEvidence | None = None,
    tests: tuple[TestEvidence, ...] = (),
    builds: tuple[BuildEvidence, ...] = (),
    narrative: dict[str, Any] | None = None,
    write: bool = False,
    at: datetime | None = None,
) -> CommandOutcome:
    store, checkpoints = _stores(root)
    instant = _now(at)
    pointer = store.read_active_session().pointer
    assert isinstance(pointer, ActiveSessionPointer)
    if pointer.session_id is None or pointer.task_id is None:
        raise CodingSessionLifecycleError(
            "checkpoint requires an active session", code="PD_SESSION_NOT_ACTIVE", exit_code=3
        )
    session = store.read_session(pointer.session_id)
    task = store.read_task(pointer.task_id)
    if session.session.status is not SessionStatus.ACTIVE:
        raise CodingSessionLifecycleError(
            "checkpoint requires active session status", code="PD_SESSION_NOT_ACTIVE", exit_code=3
        )
    values = _narrative(narrative or {})
    if instant < session.session.updated_at or instant < task.task.updated_at:
        raise CodingSessionLifecycleError(
            "checkpoint time must not be before current task/session state",
            code="PD_CHECKPOINT_INVALID_TIME",
        )
    if git is not None and git.repository_id != task.task.repository.repository_id:
        raise CodingSessionLifecycleError(
            "Git evidence repository_id must match active task",
            code="PD_CHECKPOINT_INPUT_ERROR",
        )
    touched = git.worktree_paths if git else ()
    try:
        checkpoint = CodingCheckpoint(
            checkpoint_id,
            task.task.task_id,
            session.session.session_id,
            instant,
            task.task.status,
            git=git,
            tests=tests,
            builds=builds,
            touched_paths=touched,
            **values,
        )
    except ValueError as error:
        raise CodingSessionLifecycleError(str(error), code="PD_CHECKPOINT_INPUT_ERROR") from error
    if not write:
        return CommandOutcome(
            command="session checkpoint",
            data={"checkpoint_id": checkpoint_id, "written": False},
            messages=("Checkpoint plan validated; commands were not executed and no files changed.",),
            dry_run=True,
        )
    try:
        try:
            stored_checkpoint = checkpoints.create(checkpoint)
        except CodingRuntimeConflictError:
            stored_checkpoint = checkpoints.read(checkpoint_id)
            if (
                stored_checkpoint.checkpoint.task_id != task.task.task_id
                or stored_checkpoint.checkpoint.session_id != session.session.session_id
            ):
                raise CodingSessionLifecycleError(
                    "checkpoint ID belongs to another task/session",
                    code="PD_CHECKPOINT_CONFLICT",
                    exit_code=3,
                )
        next_session = replace(
            session.session,
            current_checkpoint_id=checkpoint_id,
            updated_at=instant,
        )
        if session.session.current_checkpoint_id != checkpoint_id:
            session = store.update_session(
                next_session, expected_source_hash=session.source_hash
            )
        store.rebuild_projections()
    except CodingRuntimeConflictError as error:
        raise CodingSessionLifecycleError(str(error), code=error.code, exit_code=error.exit_code) from error
    return CommandOutcome(
        command="session checkpoint",
        data={
            "checkpoint_id": checkpoint_id,
            "source_hash": stored_checkpoint.source_hash,
            "session_revision": session.snapshot_revision,
            "written": True,
        },
        messages=(f"Checkpoint {checkpoint_id} recorded and handoff rebuilt.",),
        changed=True,
    )


def end_session_outcome(
    root: Path, *, write: bool = False, at: datetime | None = None
) -> CommandOutcome:
    store, _ = _stores(root)
    instant = _now(at)
    pointer_stored = store.read_active_session()
    pointer = pointer_stored.pointer
    assert isinstance(pointer, ActiveSessionPointer)
    if pointer.session_id is None:
        if write and pointer.last_session_id is not None:
            stored = store.read_session(pointer.last_session_id)
            if stored.session.status is SessionStatus.ENDED:
                store.rebuild_projections()
                return CommandOutcome(
                    command="session end",
                    data={"session": _session_data(stored), "written": True, "active": False},
                    messages=(
                        f"Session {stored.session.session_id} is ended; projections rebuilt.",
                    ),
                    changed=True,
                )
        raise CodingSessionLifecycleError(
            "no active CodingSession", code="PD_SESSION_NOT_ACTIVE", exit_code=3
        )
    stored = store.read_session(pointer.session_id)
    recovery = stored.session.status is SessionStatus.ENDED
    if not recovery and stored.session.status is not SessionStatus.ACTIVE:
        raise CodingSessionLifecycleError(
            f"cannot end session in {stored.session.status.value} status",
            code="PD_SESSION_INVALID_TRANSITION",
            exit_code=3,
        )
    ended = stored.session if recovery else replace(
        stored.session,
        status=SessionStatus.ENDED,
        updated_at=instant,
        ended_at=instant,
    )
    if not write:
        return CommandOutcome(
            command="session end",
            data={"session_id": ended.session_id, "status": "ended", "written": False},
            messages=("Session end plan validated; dry-run made no changes.",),
            dry_run=True,
        )
    try:
        if not recovery:
            stored = store.update_session(ended, expected_source_hash=stored.source_hash)
        store.set_active_session(
            ActiveSessionPointer(
                None,
                None,
                instant,
                last_session_id=stored.session.session_id,
            ),
            expected_source_hash=pointer_stored.source_hash,
        )
        store.rebuild_projections()
    except CodingRuntimeConflictError as error:
        raise CodingSessionLifecycleError(str(error), code=error.code, exit_code=error.exit_code) from error
    return CommandOutcome(
        command="session end",
        data={"session": _session_data(stored), "written": True, "active": False},
        messages=(f"Session {stored.session.session_id} ended.",),
        changed=True,
    )


def handoff_build_outcome(root: Path, *, dry_run: bool = False) -> CommandOutcome:
    store, _ = _stores(root)
    before = store.verify_projections()
    after = store.rebuild_projections(dry_run=dry_run)
    return CommandOutcome(
        command="handoff build",
        data={"current": after.current if not dry_run else before.current, "would_change": not before.handoff_current},
        messages=("Handoff projection validated." if dry_run else "Handoff projection rebuilt from Session/Checkpoint YAML facts.",),
        changed=(not dry_run and not before.handoff_current),
        dry_run=dry_run,
    )


def _narrative(raw: dict[str, Any]) -> dict[str, object]:
    expected = {"summary", "completed_work", "remaining_work", "blockers", "next_steps"}
    unknown = set(raw) - expected
    if unknown:
        raise CodingSessionLifecycleError(
            f"unknown checkpoint narrative fields: {', '.join(sorted(unknown))}",
            code="PD_CHECKPOINT_INPUT_ERROR",
        )
    result: dict[str, object] = {"summary": raw.get("summary")}
    for field in ("completed_work", "remaining_work", "blockers", "next_steps"):
        value = raw.get(field, [])
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise CodingSessionLifecycleError(
                f"{field} must be a list of strings", code="PD_CHECKPOINT_INPUT_ERROR"
            )
        result[field] = tuple(value)
    return result
