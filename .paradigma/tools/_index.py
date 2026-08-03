"""Deprecated import shim for package derived-index services."""

from _bootstrap import ensure_package

ROOT = ensure_package()

from paradigma.application.indexing import (
    BEGIN_MARKER,
    END_MARKER,
    GENERATED_BY,
    Concept,
    IndexFailure,
    IndexSettings,
    RebuildResult,
    VerificationItem,
    all_concepts,
    atomic_write_text,
    collect_concepts,
    desired_local_index,
    desired_root_navigation,
    inventory_lines,
    load_settings as _load_settings,
    local_index_targets,
    normalize_newlines,
    rebuild_indexes,
    render_machine_index,
    root_navigation_targets,
    verify_indexes,
)


def load_settings(repository_root=ROOT):
    return _load_settings(repository_root)


__all__ = [name for name in globals() if not name.startswith("_")]
