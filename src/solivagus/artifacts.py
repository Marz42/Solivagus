from __future__ import annotations

from pathlib import Path

from solivagus.util.text import atomic_write_text


REQUIRED_ARTIFACT_FILES = (
    "source.md",
    "translated.zh.md",
    "translated.bilingual.md",
    "qa-report.md",
    "usage-report.json",
    "manifest.json",
)

REQUIRED_ARTIFACT_DIRS = ("assets", "ocr", "units", "partitions", "logs")


def ensure_artifact_layout(artifact_dir: Path) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    for name in REQUIRED_ARTIFACT_DIRS:
        (artifact_dir / name).mkdir(parents=True, exist_ok=True)


def write_manifest(artifact_dir: Path, payload: str) -> Path:
    path = artifact_dir / "manifest.json"
    atomic_write_text(path, payload if payload.endswith("\n") else payload + "\n")
    return path
