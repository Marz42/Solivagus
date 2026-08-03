#!/usr/bin/env python3
"""Compatibility adapter for package-backed HOT/runtime size checks."""

from __future__ import annotations

import argparse
import sys

from _bootstrap import ensure_package

ROOT = ensure_package()

from paradigma.application.validation import hot_size_outcome
from paradigma.diagnostics import Severity
from paradigma.errors import ParadigmaError


_CATEGORY_LABELS = {
    "runtime": "runtime active task",
    "progress": "progress index",
    "knowledge": "HOT knowledge",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fail-on-warn", action="store_true")
    args = parser.parse_args()
    try:
        outcome = hot_size_outcome(ROOT)
    except ParadigmaError as error:
        print(f"ERROR: {error.format()}")
        return 1
    if any(item.severity is Severity.ERROR for item in outcome.diagnostics):
        for item in outcome.diagnostics:
            print(f"ERROR: {item.format()}")
        return 1
    errors = warnings = 0
    severities = {item.source: item.severity for item in outcome.diagnostics}
    for item in outcome.data.get("items", []):
        severity = severities.get(item["path"])
        level = (
            "ERROR"
            if severity is Severity.ERROR
            else "WARN"
            if severity is Severity.WARNING
            else "OK"
        )
        errors += level == "ERROR"
        warnings += level == "WARN"
        category = _CATEGORY_LABELS.get(item["category"], item["category"])
        print(
            f"{level}: {item['path']}: {item['lines']} lines "
            f"({category}; warn>{item['warn_at']}, error>{item['error_at']})"
        )
    print(
        f"Checked {len(outcome.data.get('items', []))} HOT/runtime file(s); "
        f"errors={errors}, warnings={warnings}."
    )
    return 1 if errors or (warnings and args.fail_on_warn) else 0


if __name__ == "__main__":
    sys.exit(main())
