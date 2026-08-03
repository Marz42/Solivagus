#!/usr/bin/env python3
"""Compatibility wrapper for the pre-v0.5.2 index synchronization CLI."""

from __future__ import annotations

import argparse
import sys

from _index import (
    IndexFailure,
    inventory_lines,
    load_settings,
    rebuild_indexes,
    verify_indexes,
)
from _paradigma_yaml import ParseFailure
from paradigma.errors import ParadigmaError


def display_path(settings, path) -> str:
    try:
        return path.relative_to(settings.repository_root).as_posix()
    except ValueError:
        return str(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write", action="store_true", help="compatibility alias for pd-index.py rebuild"
    )
    parser.add_argument(
        "--check", action="store_true", help="compatibility alias for pd-index.py verify"
    )
    args = parser.parse_args()
    if args.write and args.check:
        parser.error("--write and --check are mutually exclusive")

    try:
        settings = load_settings()
        if args.write:
            result = rebuild_indexes(settings)
            print(
                f"Rebuilt {result.local_index_count} local index(es) and machine "
                f"cache with {result.concept_count} concept(s); "
                f"updated_markdown={result.updated_markdown_count}."
            )
            return 0
        if args.check:
            items = verify_indexes(settings)
            stale = sum(not item.current for item in items)
            for item in items:
                state = "OK" if item.current else "STALE"
                print(
                    f"{state}: {item.label}: {display_path(settings, item.path)}"
                )
            print(f"Checked indexes; stale={stale}.")
            return 1 if stale else 0
        lines = inventory_lines(settings)
        print("\n".join(lines))
        print(
            f"Found {len(lines)} concept(s). Use pd-index.py rebuild or verify; "
            "this wrapper remains for compatibility."
        )
        return 0
    except ParseFailure as error:
        print(f"ERROR: {error.diagnostic.format()}")
        return 1
    except IndexFailure as error:
        print(f"ERROR: {error.format()}")
        return 1
    except ParadigmaError as error:
        print(f"ERROR: {error.format()}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
