"""Recoverable CodingTask lifecycle application service."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..config import require_valid_config
from ..errors import ParadigmaError
from ..integrations.coding import (
    CodingTask,
    RepositoryScope,
    TaskAction,
    TaskStatus,
    TaskTransitionError,
    transition_task,
)
from ..runtime import (
    ActiveSessionPointer,
    ActiveTaskPointer,
    CodingRuntimeConflictError,
    CodingRuntimeNotFoundError,
    CodingRuntimeStore,
)
from .outcomes import CommandOutcome


class CodingTaskLifecycleError(ParadigmaError):
    code = "PD_TASK_LIFECYCLE_ERROR"


def _store(repository_root: Path) -> CodingRuntimeStore:
    config = require_valid_config(repository_root)
    return CodingRuntimeStore(config.repository_root / config.runtime_root_name)


def _now(value: datetime | None) -> datetime:
    instant = value or datetime.now().astimezone()
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise CodingTaskLifecycleError(
            "task lifecycle time must be timezone-aware",
            code="PD_TASK_INVALID_TIME",
        )
    return instant


def _task_data(task: CodingTask, *, source_hash: str | None = None, revision: int | None = None) -> dict[str, object]:
    return {
        "task_id": task.task_id,
        "title": task.title,
        "goal": task.goal,
        "status": task.status.value,
        "status_reason": task.status_reason,
        "workspace_id": task.repository.workspace_id,
        "repository_id": task.repository.repository_id,
        "repository_path": task.repository.repository_path,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "snapshot_revision": revision,
        "source_hash": source_hash,
    }


def task_status_outcome(repository_root: Path, *, dry_run: bool = False) -> CommandOutcome:
    store = _store(repository_root)
    active = store.read_active_task()
    pointer = active.pointer
    assert isinstance(pointer, ActiveTaskPointer)
    if pointer.task_id is None:
        return CommandOutcome(
            command="task status",
            data={"active": False, "task": None},
            messages=("No active CodingTask.",),
            dry_run=dry_run,
        )
    stored = store.read_task(pointer.task_id)
    return CommandOutcome(
        command="task status",
        data={
            "active": True,
            "task": _task_data(
                stored.task,
                source_hash=stored.source_hash,
                revision=stored.snapshot_revision,
            ),
        },
        messages=(f"Active task {stored.task.task_id}: {stored.task.status.value}.",),
        dry_run=dry_run,
    )


def start_task_outcome(
    repository_root: Path,
    *,
    task_id: str,
    title: str,
    goal: str,
    workspace_id: str,
    repository_id: str,
    repository_path: str = ".",
    remote_url: str | None = None,
    parent_task_id: str | None = None,
    write: bool = False,
    at: datetime | None = None,
) -> CommandOutcome:
    store = _store(repository_root)
    instant = _now(at)
    pointer_stored = store.read_active_task()
    pointer = pointer_stored.pointer
    assert isinstance(pointer, ActiveTaskPointer)
    if pointer.task_id is not None:
        raise CodingTaskLifecycleError(
            f"active task already exists: {pointer.task_id}",
            code="PD_TASK_ALREADY_ACTIVE",
            exit_code=3,
        )
    try:
        pending = CodingTask(
            task_id=task_id,
            repository=RepositoryScope(
                workspace_id,
                repository_id,
                repository_path,
                remote_url,
            ),
            title=title,
            goal=goal,
            status=TaskStatus.PENDING,
            created_at=instant,
            updated_at=instant,
            parent_task_id=parent_task_id,
        )
        active = transition_task(pending, TaskAction.START, at=instant)
    except ValueError as error:
        raise CodingTaskLifecycleError(
            str(error), code="PD_TASK_INPUT_ERROR"
        ) from error
    if not write:
        return CommandOutcome(
            command="task start",
            data={"task": _task_data(active), "written": False},
            messages=("Task start plan validated; dry-run made no changes.",),
            dry_run=True,
        )

    try:
        try:
            stored = store.create_task(active)
        except CodingRuntimeConflictError:
            stored = store.read_task(task_id)
            comparable = (
                stored.task.repository == active.repository
                and stored.task.title == active.title
                and stored.task.goal == active.goal
                and stored.task.status is TaskStatus.ACTIVE
                and stored.task.parent_task_id == active.parent_task_id
            )
            if not comparable:
                raise
        store.set_active_task(
            ActiveTaskPointer(task_id, instant),
            expected_source_hash=pointer_stored.source_hash,
        )
        store.rebuild_projections()
    except (CodingRuntimeConflictError, CodingRuntimeNotFoundError) as error:
        raise CodingTaskLifecycleError(str(error), code=error.code, exit_code=error.exit_code) from error
    return CommandOutcome(
        command="task start",
        data={
            "task": _task_data(
                stored.task,
                source_hash=stored.source_hash,
                revision=stored.snapshot_revision,
            ),
            "written": True,
        },
        messages=(f"Task {task_id} started and projections rebuilt.",),
        changed=True,
    )


def transition_task_outcome(
    repository_root: Path,
    action: TaskAction | str,
    *,
    reason: str | None = None,
    write: bool = False,
    at: datetime | None = None,
) -> CommandOutcome:
    store = _store(repository_root)
    instant = _now(at)
    pointer_stored = store.read_active_task()
    pointer = pointer_stored.pointer
    assert isinstance(pointer, ActiveTaskPointer)
    if pointer.task_id is None:
        raise CodingTaskLifecycleError(
            "no active CodingTask", code="PD_TASK_NOT_ACTIVE", exit_code=3
        )
    stored = store.read_task(pointer.task_id)
    try:
        checked_action = TaskAction(action)
    except ValueError as error:
        raise CodingTaskLifecycleError(str(error), code="PD_TASK_INVALID_ACTION") from error
    terminal = checked_action in (TaskAction.COMPLETE, TaskAction.ABORT)

    if terminal and stored.task.status in (TaskStatus.COMPLETED, TaskStatus.ABORTED):
        target = TaskStatus.COMPLETED if checked_action is TaskAction.COMPLETE else TaskStatus.ABORTED
        if stored.task.status is not target:
            raise CodingTaskLifecycleError(
                f"cannot {checked_action.value} task in {stored.task.status.value} status",
                code="PD_TASK_INVALID_TRANSITION",
                exit_code=3,
            )
        next_task = stored.task
        recovery_only = True
    else:
        try:
            next_task = transition_task(
                stored.task, checked_action, at=instant, reason=reason
            )
        except TaskTransitionError as error:
            raise CodingTaskLifecycleError(
                str(error), code="PD_TASK_INVALID_TRANSITION", exit_code=3
            ) from error
        recovery_only = False

    if not write:
        return CommandOutcome(
            command=f"task {checked_action.value}",
            data={"task": _task_data(next_task), "written": False},
            messages=(
                f"Task {checked_action.value} plan validated; dry-run made no changes.",
            ),
            dry_run=True,
        )

    if terminal:
        active_session = store.read_active_session().pointer
        assert isinstance(active_session, ActiveSessionPointer)
        if active_session.session_id is not None:
            raise CodingTaskLifecycleError(
                "active session must end before task can become terminal",
                code="PD_TASK_ACTIVE_SESSION",
                exit_code=3,
            )
    try:
        if not recovery_only:
            stored = store.update_task(
                next_task, expected_source_hash=stored.source_hash
            )
        if terminal:
            store.set_active_task(
                ActiveTaskPointer(None, instant),
                expected_source_hash=pointer_stored.source_hash,
            )
        store.rebuild_projections()
    except CodingRuntimeConflictError as error:
        raise CodingTaskLifecycleError(str(error), code=error.code, exit_code=error.exit_code) from error
    return CommandOutcome(
        command=f"task {checked_action.value}",
        data={
            "task": _task_data(
                stored.task,
                source_hash=stored.source_hash,
                revision=stored.snapshot_revision,
            ),
            "written": True,
            "active": not terminal,
        },
        messages=(
            f"Task {stored.task.task_id} transitioned to {stored.task.status.value}.",
        ),
        changed=True,
    )
