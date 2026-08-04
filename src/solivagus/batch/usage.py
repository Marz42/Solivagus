"""Aggregate per-document usage-report.json into a workspace rollup."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from solivagus.reporting.usage_report import empty_usage_totals
from solivagus.util.text import atomic_write_json


def _merge_totals(dst: dict[str, int], src: dict[str, Any] | None) -> None:
    if not src:
        return
    for key in empty_usage_totals():
        dst[key] = int(dst.get(key) or 0) + int(src.get(key) or 0)


def aggregate_usage_reports(
    documents: list[dict[str, Any]],
    *,
    output_dir: Path,
    when: datetime | None = None,
) -> tuple[Path, dict[str, Any]]:
    instant = when or datetime.now(timezone.utc)
    stamp = instant.astimezone().strftime("%Y-%m-%d")
    output_dir.mkdir(parents=True, exist_ok=True)
    totals = empty_usage_totals()
    per_doc: list[dict[str, Any]] = []

    for doc in documents:
        artifact = Path(str(doc.get("artifact_dir") or ""))
        usage_path = artifact / "usage-report.json"
        entry: dict[str, Any] = {
            "display_name": doc.get("display_name"),
            "status": doc.get("status"),
            "usage_report": str(usage_path) if usage_path.is_file() else None,
            "totals": None,
        }
        if usage_path.is_file():
            try:
                payload = json.loads(usage_path.read_text(encoding="utf-8"))
                doc_totals = payload.get("totals") or {}
                entry["totals"] = doc_totals
                _merge_totals(totals, doc_totals)
            except (OSError, json.JSONDecodeError):
                entry["error"] = "unreadable_usage_report"
        per_doc.append(entry)

    report = {
        "date": stamp,
        "generated_at": instant.isoformat(timespec="seconds"),
        "document_count": len(documents),
        "totals": totals,
        "documents": per_doc,
    }
    path = output_dir / f"global-usage-{stamp}.json"
    atomic_write_json(path, report)
    atomic_write_json(output_dir / "global-usage-latest.json", report)
    return path, report
