"""Stable application error types."""

from __future__ import annotations

from pathlib import Path

from .diagnostics import Diagnostic


class ParadigmaError(Exception):
    code = "PD_ERROR"
    exit_code = 1

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        exit_code: int | None = None,
    ):
        self.code = code or self.code
        self.exit_code = self.exit_code if exit_code is None else exit_code
        super().__init__(message)

    def format(self) -> str:
        return f"[{self.code}] {self}"


class DiagnosticError(ParadigmaError):
    def __init__(self, diagnostic: Diagnostic, *, exit_code: int = 1):
        self.diagnostic = diagnostic
        super().__init__(
            diagnostic.message,
            code=diagnostic.code,
            exit_code=exit_code,
        )

    def format(self) -> str:
        return self.diagnostic.format()


class ParseFailure(DiagnosticError, ValueError):
    """Raised when YAML, UTF-8, or frontmatter parsing fails."""


class ConfigFailure(DiagnosticError, ValueError):
    """Raised when repository configuration cannot be loaded safely."""


class SchemaFailure(DiagnosticError, ValueError):
    """Raised when the schema registry itself is invalid."""


class AtomicWriteFailure(ParadigmaError, OSError):
    def __init__(self, path: Path, operation: str, error: OSError):
        self.path = path
        self.operation = operation
        super().__init__(
            f"{operation} failed for {path}: {error}",
            code="PD_ATOMIC_WRITE_ERROR",
            exit_code=2,
        )

