"""Distribution and schema version reporting service."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re

from ..diagnostics import Diagnostic
from ..parser import load_flat_yaml_file
from .outcomes import CommandOutcome


SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


class VersionModelError(ValueError):
    """Raised when required distribution metadata cannot be read."""


@dataclass(frozen=True)
class VersionInfo:
    distribution_version: str
    installed_distribution_version: str
    config_schema_version: str
    okf_version: str
    document_schema_version: str
    legacy_harness_version: str | None = None
    legacy_config_schema_version: str | None = None
    legacy_document_schema_version: str | None = None

    def public_dict(self) -> dict[str, str]:
        data = asdict(self)
        return {
            key: value
            for key, value in data.items()
            if not key.startswith("legacy_") and isinstance(value, str)
        }


def read_top_level_scalars(path: Path) -> dict[str, str]:
    flattened = load_flat_yaml_file(path, missing_ok=True)
    return {
        key: value
        for key, value in flattened.items()
        if "." not in key and isinstance(value, str)
    }


def read_distribution_version(repository_root: Path) -> str:
    version_path = repository_root.resolve() / "VERSION"
    if not version_path.exists():
        raise VersionModelError("missing root VERSION")
    version = version_path.read_text(encoding="utf-8-sig").strip()
    if not version:
        raise VersionModelError("root VERSION is empty")
    return version


def read_installed_distribution_version(
    repository_root: Path,
) -> tuple[str, str | None]:
    config = read_top_level_scalars(
        repository_root.resolve() / ".paradigma" / "config.yaml"
    )
    installed = config.get("installed_distribution_version", "")
    legacy = config.get("paradigma_harness_version", "") or None
    return installed or legacy or "", legacy


def read_version_info(repository_root: Path) -> VersionInfo:
    root = repository_root.resolve()
    distribution = read_distribution_version(root)
    config = read_top_level_scalars(root / ".paradigma" / "config.yaml")
    schema = read_top_level_scalars(
        root / ".paradigma" / "schemas" / "paradigma-types.schema.yaml"
    )
    installed, legacy_harness = read_installed_distribution_version(root)
    return VersionInfo(
        distribution_version=distribution,
        installed_distribution_version=installed,
        config_schema_version=config.get("config_schema_version", ""),
        okf_version=config.get("okf_version", ""),
        document_schema_version=schema.get("document_schema_version", ""),
        legacy_harness_version=legacy_harness,
        legacy_config_schema_version=config.get("schema_version") or None,
        legacy_document_schema_version=schema.get("schema_version") or None,
    )


def validate_version_messages(info: VersionInfo) -> list[str]:
    """Return the stable v0.5.1 compatibility error strings."""
    errors: list[str] = []
    for field_name, value in info.public_dict().items():
        if not value:
            errors.append(f"missing {field_name}")
    for field_name in ("distribution_version", "installed_distribution_version"):
        value = getattr(info, field_name)
        if value and not SEMVER_PATTERN.fullmatch(value):
            errors.append(f"{field_name} is not SemVer: {value}")
    if (
        info.distribution_version
        and info.installed_distribution_version
        and info.distribution_version != info.installed_distribution_version
    ):
        errors.append(
            "installed_distribution_version does not match root VERSION: "
            f"{info.installed_distribution_version} != {info.distribution_version}"
        )
    if info.legacy_harness_version is not None:
        errors.append(
            "legacy paradigma_harness_version is present; migrate to "
            "installed_distribution_version"
        )
    if info.legacy_config_schema_version is not None:
        errors.append(
            "legacy config schema_version is present; migrate to "
            "config_schema_version"
        )
    if info.legacy_document_schema_version is not None:
        errors.append(
            "legacy registry schema_version is present; migrate to "
            "document_schema_version"
        )
    return errors


def validate_version_info(info: VersionInfo) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    required = info.public_dict()
    for field_name, value in required.items():
        if not value:
            diagnostics.append(
                Diagnostic(
                    "PD_VERSION_REQUIRED_FIELD",
                    f"missing {field_name}",
                    "version metadata",
                    details={"field": field_name},
                )
            )
    for field_name in ("distribution_version", "installed_distribution_version"):
        value = required[field_name]
        if value and not SEMVER_PATTERN.fullmatch(value):
            diagnostics.append(
                Diagnostic(
                    "PD_VERSION_INVALID_SEMVER",
                    f"{field_name} is not SemVer: {value}",
                    "version metadata",
                    details={"field": field_name, "value": value},
                )
            )
    if (
        info.distribution_version
        and info.installed_distribution_version
        and info.distribution_version != info.installed_distribution_version
    ):
        diagnostics.append(
            Diagnostic(
                "PD_VERSION_DISTRIBUTION_DRIFT",
                "installed_distribution_version does not match root VERSION: "
                f"{info.installed_distribution_version} != "
                f"{info.distribution_version}",
                "version metadata",
            )
        )
    legacy_fields = {
        "paradigma_harness_version": info.legacy_harness_version,
        "config schema_version": info.legacy_config_schema_version,
        "registry schema_version": info.legacy_document_schema_version,
    }
    for field_name, value in legacy_fields.items():
        if value is not None:
            diagnostics.append(
                Diagnostic(
                    "PD_VERSION_LEGACY_FIELD",
                    f"legacy {field_name} is present",
                    "version metadata",
                    details={"field": field_name},
                )
            )
    return tuple(diagnostics)


def version_outcome(
    repository_root: Path, *, dry_run: bool = False
) -> CommandOutcome:
    try:
        info = read_version_info(repository_root)
    except VersionModelError as error:
        return CommandOutcome(
            command="version",
            diagnostics=(
                Diagnostic(
                    "PD_VERSION_READ_ERROR",
                    str(error),
                    str(repository_root.resolve()),
                ),
            ),
            dry_run=dry_run,
        )
    diagnostics = validate_version_info(info)
    return CommandOutcome(
        command="version",
        data=info.public_dict(),
        messages=(
            "Version metadata is consistent."
            if not diagnostics
            else "Version metadata validation failed.",
        ),
        diagnostics=diagnostics,
        dry_run=dry_run,
    )
