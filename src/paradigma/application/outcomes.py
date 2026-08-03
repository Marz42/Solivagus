"""Adapter-neutral command outcome model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..diagnostics import Diagnostic, Severity


@dataclass(frozen=True)
class CommandOutcome:
    command: str
    data: dict[str, Any] = field(default_factory=dict)
    messages: tuple[str, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
    changed: bool = False
    dry_run: bool = False
    exit_code_override: int | None = None

    @property
    def ok(self) -> bool:
        if self.exit_code_override is not None:
            return self.exit_code_override == 0
        return not any(
            diagnostic.severity is Severity.ERROR
            for diagnostic in self.diagnostics
        )

    @property
    def exit_code(self) -> int:
        if self.exit_code_override is not None:
            return self.exit_code_override
        return 0 if self.ok else 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "ok": self.ok,
            "changed": self.changed,
            "dry_run": self.dry_run,
            "data": self.data,
            "messages": list(self.messages),
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }
