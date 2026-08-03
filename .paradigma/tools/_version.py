"""Deprecated import shim for package version services."""

from _bootstrap import ensure_package

ensure_package()

from paradigma.application.versioning import (
    SEMVER_PATTERN,
    VersionInfo,
    VersionModelError,
    read_distribution_version,
    read_installed_distribution_version,
    read_top_level_scalars,
    read_version_info,
    validate_version_messages as validate_version_info,
)

__all__ = [
    "SEMVER_PATTERN",
    "VersionInfo",
    "VersionModelError",
    "read_distribution_version",
    "read_installed_distribution_version",
    "read_top_level_scalars",
    "read_version_info",
    "validate_version_info",
]
