#!/usr/bin/env python3
"""Rebuild or verify Paradigma derived indexes."""

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
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("rebuild", help="rebuild local Markdown indexes and machine cache")
    subcommands.add_parser("verify", help="verify navigation, local indexes, and machine cache")
    subcommands.add_parser("inventory", help="print the complete canonical concept inventory")
    args = parser.parse_args()

    try:
        settings = load_settings()
        if args.command == "rebuild":
            result = rebuild_indexes(settings)
            print(
                f"Rebuilt {result.local_index_count} local index(es) and "
                f"{display_path(settings, result.cache_path)} with "
                f"{result.concept_count} concept(s); "
                f"updated_markdown={result.updated_markdown_count}."
            )
            return 0
        if args.command == "verify":
            items = verify_indexes(settings)
            for item in items:
                state = "OK" if item.current else "STALE"
                print(
                    f"{state}: {item.label}: {display_path(settings, item.path)}"
                )
            stale = sum(not item.current for item in items)
            print(f"Verified derived indexes; stale={stale}.")
            return 1 if stale else 0
        lines = inventory_lines(settings)
        print("\n".join(lines))
        print(f"Found {len(lines)} canonical concept(s).")
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
