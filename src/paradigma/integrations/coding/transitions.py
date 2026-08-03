"""Pure CodingTask lifecycle transitions."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from enum import Enum

from .models import CodingTask, TaskStatus


class TaskAction(str, Enum):
    START = "start"
    BLOCK = "block"
    UNBLOCK = "unblock"
    SUSPEND = "suspend"
    RESUME = "resume"
    COMPLETE = "complete"
    ABORT = "abort"


class TaskTransitionError(ValueError):
    """Raised when a requested CodingTask state transition is illegal."""


_TRANSITIONS = {
    TaskAction.START: {TaskStatus.PENDING: TaskStatus.ACTIVE},
    TaskAction.BLOCK: {TaskStatus.ACTIVE: TaskStatus.BLOCKED},
    TaskAction.UNBLOCK: {TaskStatus.BLOCKED: TaskStatus.ACTIVE},
    TaskAction.SUSPEND: {
        TaskStatus.ACTIVE: TaskStatus.SUSPENDED,
        TaskStatus.BLOCKED: TaskStatus.SUSPENDED,
    },
    TaskAction.RESUME: {TaskStatus.SUSPENDED: TaskStatus.ACTIVE},
    TaskAction.COMPLETE: {TaskStatus.ACTIVE: TaskStatus.COMPLETED},
    TaskAction.ABORT: {
        TaskStatus.PENDING: TaskStatus.ABORTED,
        TaskStatus.ACTIVE: TaskStatus.ABORTED,
        TaskStatus.BLOCKED: TaskStatus.ABORTED,
        TaskStatus.SUSPENDED: TaskStatus.ABORTED,
    },
}
_REASON_REQUIRED = {TaskAction.BLOCK, TaskAction.SUSPEND, TaskAction.ABORT}


def transition_task(
    task: CodingTask,
    action: TaskAction | str,
    *,
    at: datetime,
    reason: str | None = None,
) -> CodingTask:
    """Return the next immutable task snapshot without performing I/O."""

    if not isinstance(task, CodingTask):
        raise TaskTransitionError("task must be a CodingTask")
    try:
        checked_action = TaskAction(action)
    except (TypeError, ValueError) as error:
        allowed = ", ".join(item.value for item in TaskAction)
        raise TaskTransitionError(f"action must be one of: {allowed}") from error
    if not isinstance(at, datetime) or at.tzinfo is None or at.utcoffset() is None:
        raise TaskTransitionError("transition time must be timezone-aware")
    if at < task.updated_at:
        raise TaskTransitionError("transition time must not be before task updated_at")
    if reason is not None:
        if not isinstance(reason, str) or not reason.strip() or reason != reason.strip():
            raise TaskTransitionError("reason must be a trimmed non-empty string")
    if checked_action in _REASON_REQUIRED and reason is None:
        raise TaskTransitionError(f"{checked_action.value} requires a reason")
    if checked_action not in _REASON_REQUIRED and reason is not None:
        raise TaskTransitionError(f"{checked_action.value} does not accept a reason")
    target = _TRANSITIONS[checked_action].get(task.status)
    if target is None:
        raise TaskTransitionError(
            f"cannot {checked_action.value} task in {task.status.value} status"
        )
    return replace(
        task,
        status=target,
        status_reason=reason if target in (TaskStatus.BLOCKED, TaskStatus.SUSPENDED, TaskStatus.ABORTED) else None,
        updated_at=at,
    )
