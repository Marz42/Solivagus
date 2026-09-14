"""Solivagus — local technical PDF translation CLI."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def _detect_version() -> str:
    try:
        return version("solivagus")
    except PackageNotFoundError:
        pass
    root_version = Path(__file__).resolve().parents[2] / "VERSION"
    if root_version.is_file():
        text = root_version.read_text(encoding="utf-8").strip()
        if text:
            return text
    return "0.0.0+local"


__version__ = _detect_version()
