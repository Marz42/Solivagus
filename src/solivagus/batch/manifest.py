"""Batch job manifest writer."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from solivagus.util.text import atomic_write_json


def write_batch_manifest(
    output_dir: Path,
    *,
    batch_dir: Path,
    profile: str,
    documents: list[dict[str, Any]],
    totals: dict[str, Any] | None = None,
    when: datetime | None = None,
) -> Path:
    instant = when or datetime.now(timezone.utc)
    stamp = instant.astimezone().strftime("%Y%m%d-%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": instant.isoformat(timespec="seconds"),
        "batch_dir": str(batch_dir),
        "profile": profile,
        "document_count": len(documents),
        "totals": totals or {},
        "documents": documents,
    }
    path = output_dir / f"batch-manifest-{stamp}.json"
    atomic_write_json(path, payload)
    # Also keep a stable latest pointer for overnight inspection.
    atomic_write_json(output_dir / "batch-manifest-latest.json", payload)
    return path
