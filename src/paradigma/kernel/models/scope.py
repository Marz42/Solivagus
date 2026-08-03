"""Domain-neutral memory scope."""

from __future__ import annotations

from dataclasses import dataclass

from ._validation import optional_text, require_text, require_unique_text_tuple


@dataclass(frozen=True)
class MemoryScope:
    namespace: str
    workspace_id: str | None = None
    project_id: str | None = None
    task_id: str | None = None
    session_id: str | None = None
    entity_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_text(self.namespace, "namespace")
        optional_text(self.workspace_id, "workspace_id")
        optional_text(self.project_id, "project_id")
        optional_text(self.task_id, "task_id")
        optional_text(self.session_id, "session_id")
        require_unique_text_tuple(self.entity_ids, "entity_ids")
