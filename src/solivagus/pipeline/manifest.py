"""Per-document manifest.json writer."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from solivagus.artifacts import write_manifest
from solivagus.util.text import sha256_text


def build_document_manifest(
    *,
    document_id: int,
    display_name: str,
    source_sha256: str | None,
    artifact_dir: Path,
    status: str,
    model: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifact_dir = Path(artifact_dir)
    files: dict[str, Any] = {}
    for name in (
        "source.md",
        "translated.zh.md",
        "translated.bilingual.md",
        "qa-report.md",
        "usage-report.json",
        "plan-report.json",
        "preflight.json",
    ):
        path = artifact_dir / name
        if path.is_file():
            files[name] = {
                "path": str(path),
                "sha256": sha256_text(path.read_text(encoding="utf-8")),
                "bytes": path.stat().st_size,
            }
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "document_id": document_id,
        "display_name": display_name,
        "source_sha256": source_sha256,
        "status": status,
        "model": model,
        "artifact_dir": str(artifact_dir),
        "files": files,
    }
    if extra:
        payload["extra"] = extra
    return payload


def write_document_manifest(
    artifact_dir: Path,
    *,
    document_id: int,
    display_name: str,
    source_sha256: str | None,
    status: str,
    model: str | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    payload = build_document_manifest(
        document_id=document_id,
        display_name=display_name,
        source_sha256=source_sha256,
        artifact_dir=artifact_dir,
        status=status,
        model=model,
        extra=extra,
    )
    return write_manifest(
        Path(artifact_dir),
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )
