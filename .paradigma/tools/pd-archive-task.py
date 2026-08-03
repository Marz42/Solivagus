#!/usr/bin/env python3
"""Compatibility adapter for package-backed active-task archiving."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

from _bootstrap import ensure_package

ROOT = ensure_package()

from paradigma.application.tasks import (
    ArchiveFailure,
    ArchivePlan,
    archive_outcome,
    build_archive_plan,
    execute_archive_plan,
)
from paradigma.errors import ParseFailure
from paradigma.parser import read_utf8_text
from paradigma.task_state import TaskStateFailure, TaskStatus, parse_task_status


def now_local() -> datetime:
    return datetime.now().astimezone()


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def parse_status(text: str) -> TaskStatus:
    try:
        return parse_task_status(text)
    except TaskStateFailure as error:
        raise ArchiveFailure(
            str(error), code="PD_ARCHIVE_INVALID_STATUS"
        ) from error


def is_completed(text: str) -> bool:
    return parse_status(text) is TaskStatus.COMPLETED


def format_plan(plan: ArchivePlan) -> str:
    archive_action = "CREATE" if plan.create_archive else "KEEP (already created)"
    return "\n".join(
        [
            "Mutation plan:",
            f"  task_id: {plan.task_id}",
            f"  status: {plan.status.value}",
            f"  archive_id: {plan.archive_id}",
            f"  {archive_action}: {display_path(plan.target)}",
            f"  REPLACE: {display_path(plan.paths.active_task)} -> status=pending",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        preview = archive_outcome(ROOT, dry_run=True, force=args.force)
        if preview.data.get("already_archived"):
            print(
                "Already archived; active task is the pending reset state "
                f"for archive {preview.data['archive_id']}."
            )
            return 0
        plan = build_archive_plan(ROOT, now_local(), force=args.force)
        print(format_plan(plan))
        if not args.write:
            print("Dry run only. Pass --write to apply this mutation plan.")
            return 0
        execute_archive_plan(plan)
        print(
            f"Archived active task to {display_path(plan.target)} and reset "
            f"{display_path(plan.paths.active_task)}."
        )
        return 0
    except ParseFailure as error:
        print(f"ERROR: {error.diagnostic.format()}", file=sys.stderr)
        return 2
    except ArchiveFailure as error:
        print(f"ERROR: {error.format()}", file=sys.stderr)
        return error.exit_code


if __name__ == "__main__":
    sys.exit(main())
