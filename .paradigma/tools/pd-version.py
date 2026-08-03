#!/usr/bin/env python3
"""Report and validate the Paradigma version model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from _version import VersionModelError, read_version_info, validate_version_info


ROOT = Path(__file__).resolve().parents[2]


def _as_dict(info) -> dict[str, str]:
    return {
        "distribution_version": info.distribution_version,
        "installed_distribution_version": info.installed_distribution_version,
        "config_schema_version": info.config_schema_version,
        "okf_version": info.okf_version,
        "document_schema_version": info.document_schema_version,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report Paradigma distribution and schema versions."
    )
    parser.add_argument(
        "--verbose", action="store_true", help="show every version dimension"
    )
    parser.add_argument(
        "--check", action="store_true", help="fail when version metadata drifts"
    )
    parser.add_argument("--json", action="store_true", help="output JSON")
    args = parser.parse_args()

    try:
        info = read_version_info(ROOT)
    except (OSError, UnicodeError, VersionModelError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    errors = validate_version_info(info)
    values = _as_dict(info)

    if args.json:
        print(json.dumps({**values, "errors": errors}, indent=2))
    elif args.verbose:
        for key, value in values.items():
            print(f"{key}: {value or '<missing>'}")
        for error in errors:
            print(f"ERROR: {error}")
    elif args.check:
        if errors:
            for error in errors:
                print(f"ERROR: {error}")
        else:
            print(
                "OK: version metadata is consistent "
                f"(distribution={info.distribution_version})"
            )
    else:
        print(info.distribution_version)

    return 1 if args.check and errors else 0


if __name__ == "__main__":
    sys.exit(main())
