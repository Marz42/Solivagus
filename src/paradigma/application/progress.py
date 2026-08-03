"""Progress-log compaction service that preserves canonical source logs."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re

from ..atomic import atomic_replace_text
from ..errors import AtomicWriteFailure, ParadigmaError
from ..parser import flatten_mapping, parse_markdown_text, read_utf8_text
from .outcomes import CommandOutcome


EXCLUDED = {"index.md", "summary.md"}


class CompactFailure(ParadigmaError, RuntimeError):
    pass


def title_for(path: Path, text: str) -> str:
    if text.splitlines()[:1] == ["---"]:
        metadata = flatten_mapping(parse_markdown_text(text, source=str(path)).metadata)
        title = metadata.get("title")
        if isinstance(title, str) and title.strip():
            return title.strip()
    heading_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return heading_match.group(1).strip() if heading_match else path.stem


def first_nonempty_bullet(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            return stripped[2:].strip()
    return "No bullet summary recorded."


def collect_logs(repository_root: Path) -> list[tuple[Path, str, str]]:
    progress_root = repository_root.resolve() / "memory-bank" / "logs" / "progress"
    if not progress_root.exists():
        return []
    logs: list[tuple[Path, str, str]] = []
    for path in sorted(progress_root.glob("*.md")):
        if path.name in EXCLUDED:
            continue
        text = read_utf8_text(path)
        logs.append((path, title_for(path, text), first_nonempty_bullet(text)))
    return logs


def render_summary(
    repository_root: Path,
    logs: list[tuple[Path, str, str]],
    *,
    current_time: datetime | None = None,
) -> str:
    progress_root = repository_root.resolve() / "memory-bank" / "logs" / "progress"
    generated_at = current_time or datetime.now().astimezone()
    lines = [
        "# Progress Summary",
        "",
        f"Generated at: {generated_at:%Y-%m-%d %H:%M}",
        "",
        "This file summarizes progress logs without deleting or rewriting the source session logs.",
        "",
        "| Log | Title | First Signal |",
        "|-----|-------|--------------|",
    ]
    for path, title, signal in logs:
        relative = path.relative_to(progress_root).as_posix()
        escaped_signal = signal.replace("|", "\\|")
        lines.append(f"| [{relative}]({relative}) | {title} | {escaped_signal} |")
    lines.append("")
    return "\n".join(lines)


def write_summary(path: Path, content: str) -> None:
    try:
        atomic_replace_text(path, content)
    except AtomicWriteFailure as error:
        raise CompactFailure(
            f"failed to write {path}: {error}",
            code="PD_COMPACT_IO_ERROR",
        ) from error


def compact_outcome(
    repository_root: Path,
    *,
    dry_run: bool = True,
    current_time: datetime | None = None,
) -> CommandOutcome:
    root = repository_root.resolve()
    summary_path = root / "memory-bank" / "logs" / "progress" / "summary.md"
    logs = collect_logs(root)
    summary = render_summary(root, logs, current_time=current_time)
    if not dry_run:
        write_summary(summary_path, summary)
    return CommandOutcome(
        command="progress compact",
        data={
            "source_log_count": len(logs),
            "summary_path": summary_path.relative_to(root).as_posix(),
            "summary": summary,
        },
        messages=(
            "Progress compaction plan generated."
            if dry_run
            else "Progress summary written.",
        ),
        changed=not dry_run,
        dry_run=dry_run,
    )
