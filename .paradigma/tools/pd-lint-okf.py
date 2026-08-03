#!/usr/bin/env python3
"""Compatibility adapter for package-backed OKF validation."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from _bootstrap import ensure_package

ROOT = ensure_package()

from paradigma.application.validation import lint_outcome
from paradigma.diagnostics import Severity
from paradigma.errors import ParadigmaError


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--normal", action="store_true")
    parser.add_argument("--warn", action="store_true")
    args = parser.parse_args()
    mode = "strict" if args.strict else "warn" if args.warn else "normal"
    try:
        outcome = lint_outcome(ROOT, strict=args.strict)
    except ParadigmaError as error:
        print(f"ERROR: {error.format()}")
        return 1
    for diagnostic in outcome.diagnostics:
        level = "WARN" if diagnostic.severity is Severity.WARNING else "ERROR"
        print(f"{level}: {diagnostic.source}: {diagnostic.message}")
    data = outcome.data
    print(
        f"Checked {data['concept_count']} OKF concept document(s) and "
        f"{data['index_count']} index/log file(s); errors={data['errors']}, "
        f"warnings={data['warnings']}, mode={mode}."
    )
    return 0 if mode == "warn" or data["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
