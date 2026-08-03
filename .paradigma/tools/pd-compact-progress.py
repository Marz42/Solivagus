#!/usr/bin/env python3
"""Compatibility adapter for package-backed progress compaction."""

from __future__ import annotations

import argparse
import sys

from _bootstrap import ensure_package

ROOT = ensure_package()

from paradigma.application.progress import CompactFailure, compact_outcome
from paradigma.errors import ParseFailure


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    try:
        outcome = compact_outcome(ROOT, dry_run=not args.write)
    except ParseFailure as error:
        print(f"ERROR: {error.diagnostic.format()}", file=sys.stderr)
        return 1
    except CompactFailure as error:
        print(f"ERROR: {error.format()}", file=sys.stderr)
        return 1
    if args.write:
        print(
            f"Wrote {outcome.data['summary_path']} with "
            f"{outcome.data['source_log_count']} source log(s)."
        )
    else:
        print(outcome.data["summary"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
