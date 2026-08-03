"""Durable atomic single-file publication helpers."""

from __future__ import annotations

from pathlib import Path
import os
import tempfile

from .errors import AtomicWriteFailure


def write_temp_file(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as error:
        temporary_path.unlink(missing_ok=True)
        raise AtomicWriteFailure(path, "temporary write", error) from error
    return temporary_path


def atomic_replace_text(path: Path, content: str) -> None:
    temporary_path = write_temp_file(path, content)
    try:
        os.replace(temporary_path, path)
    except OSError as error:
        raise AtomicWriteFailure(path, "atomic replace", error) from error
    finally:
        temporary_path.unlink(missing_ok=True)


def atomic_create_text(path: Path, content: str) -> None:
    temporary_path = write_temp_file(path, content)
    try:
        os.link(temporary_path, path)
    except FileExistsError:
        raise
    except OSError as error:
        raise AtomicWriteFailure(path, "atomic create", error) from error
    finally:
        temporary_path.unlink(missing_ok=True)

