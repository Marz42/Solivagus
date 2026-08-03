#!/usr/bin/env python3
"""Compatibility adapter for package-backed Markdown link checks."""

from __future__ import annotations

import argparse
import sys

from _bootstrap import ensure_package

ROOT = ensure_package()

from paradigma.application.validation import link_outcome
from paradigma.diagnostics import Severity
from paradigma.errors import ParadigmaError


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-warnings", action="store_true")
    args = parser.parse_args()
    try:
        outcome = link_outcome(ROOT)
    except ParadigmaError as error:
        print(f"ERROR: {error.format()}")
        return 1
    for diagnostic in outcome.diagnostics:
        level = "WARN" if diagnostic.severity is Severity.WARNING else "ERROR"
        print(f"{level}: {diagnostic.source}: {diagnostic.message}")
    errors = outcome.data["errors"]
    warnings = outcome.data["warnings"]
    print(
        f"Checked {outcome.data['file_count']} markdown file(s); "
        f"errors={errors}, warnings={warnings}."
    )
    return 1 if errors or (warnings and not args.allow_warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
