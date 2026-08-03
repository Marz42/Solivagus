#!/usr/bin/env python3
"""Compatibility adapter for the package-backed aggregate quality gate."""

from __future__ import annotations

import argparse
import sys

from _bootstrap import ensure_package

ROOT = ensure_package()

from paradigma.application.validation import check_outcome
from paradigma.errors import ParadigmaError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep-going", action="store_true")
    args = parser.parse_args()
    try:
        outcome = check_outcome(ROOT)
    except ParadigmaError as error:
        print(f"ERROR: {error.format()}")
        return 1
    failures = 0
    displayed = 0
    for step in outcome.data["steps"]:
        displayed += 1
        print(f"--- {step['name']} ---")
        for diagnostic in step["diagnostics"]:
            print(
                f"  {diagnostic['severity'].upper()}: "
                f"[{diagnostic['code']}] {diagnostic['source']}: "
                f"{diagnostic['message']}"
            )
        if step["ok"]:
            print("  OK")
        else:
            failures += 1
            print("  FAILED (exit 1)")
        print()
        if failures and not args.keep_going:
            print(f"{failures}/{displayed} check(s) failed (stopped early).")
            return 1
    if failures:
        print(f"{failures}/{outcome.data['total']} check(s) failed.")
        return 1
    print(f"All {outcome.data['total']} checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
