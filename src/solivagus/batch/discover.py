"""Discover PDFs for batch processing."""

from __future__ import annotations

from pathlib import Path

from solivagus.config import Settings


class BatchDirError(ValueError):
    pass


def resolve_batch_dir(
    cli_dir: Path | None,
    settings: Settings,
) -> Path:
    """Resolve batch PDF root: CLI arg > Settings.batch_dir > error."""
    if cli_dir is not None:
        path = cli_dir.expanduser().resolve()
    elif settings.batch_dir is not None:
        path = Path(settings.batch_dir).expanduser().resolve()
    else:
        raise BatchDirError(
            "batch directory not set; pass a directory argument, "
            "set SOLIVAGUS_BATCH_DIR, or configure batch_dir"
        )
    if not path.is_dir():
        raise BatchDirError(f"batch directory not found: {path}")
    return path


def discover_pdfs(root: Path, *, recursive: bool = False) -> list[Path]:
    root = root.expanduser().resolve()
    if recursive:
        found = sorted(p for p in root.rglob("*.pdf") if p.is_file())
    else:
        found = sorted(p for p in root.glob("*.pdf") if p.is_file())
    # Skip PDFs living inside artifact dirs.
    return [
        p
        for p in found
        if not any(
            part.endswith(".solivagus") or part.endswith(".translation")
            for part in p.parts
        )
    ]
