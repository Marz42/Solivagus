from __future__ import annotations

from pathlib import Path

WORKSPACE_DIRNAME = ".solivagus"
STATE_DB_NAME = "state.db"
TRANSLATION_CACHE_DIR = Path("cache") / "translations"
ARTIFACT_DIR_SUFFIX = ".solivagus"
MVP_ARTIFACT_SUFFIX = ".translation"


def workspace_root(base: Path) -> Path:
    return base.expanduser().resolve() / WORKSPACE_DIRNAME


def state_db_path(base: Path) -> Path:
    return workspace_root(base) / STATE_DB_NAME


def translation_cache_root(base: Path) -> Path:
    return workspace_root(base) / TRANSLATION_CACHE_DIR


def default_artifact_dir(pdf_path: Path) -> Path:
    stem = pdf_path.stem
    # Keep filesystem-safe directory names aligned with MVP sanitize rules.
    from solivagus.util.text import sanitize_stem

    return pdf_path.parent / f"{sanitize_stem(stem)}{ARTIFACT_DIR_SUFFIX}"


def ensure_workspace(base: Path) -> Path:
    root = workspace_root(base)
    root.mkdir(parents=True, exist_ok=True)
    (root / "cache" / "translations").mkdir(parents=True, exist_ok=True)
    return root
