"""Configuration validation service."""

from __future__ import annotations

from pathlib import Path

from ..config import load_config
from .outcomes import CommandOutcome


def config_validate_outcome(
    repository_root: Path, *, dry_run: bool = False
) -> CommandOutcome:
    config = load_config(repository_root)
    diagnostics = config.validate()
    return CommandOutcome(
        command="config validate",
        data={
            "config_schema_version": config.config_schema_version,
            "knowledge_roots": list(config.knowledge_root_names),
            "machine_index_path": config.machine_index_name,
            "runtime_root": config.runtime_root_name,
            "memory_root": config.memory_root_name,
            "catalog_path": config.catalog_name,
        },
        messages=(
            "Configuration is valid."
            if not diagnostics
            else "Configuration validation failed."
        ,),
        diagnostics=diagnostics,
        dry_run=dry_run,
    )
