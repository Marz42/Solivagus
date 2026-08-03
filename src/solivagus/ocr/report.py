from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def write_nightly_report(
    output_dir: Path,
    *,
    documents: Iterable[dict[str, Any]],
    when: datetime | None = None,
) -> tuple[Path, Path]:
    instant = when or datetime.now().astimezone()
    stamp = instant.strftime("%Y-%m-%d")
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = list(documents)
    completed = sum(1 for row in rows if str(row.get("status", "")).startswith("ocr_complete") or "translation_complete" in str(row.get("status", "")) or row.get("status") == "qa_complete")
    failed = sum(1 for row in rows if row.get("status") == "failed")
    warned = sum(1 for row in rows if "with_warnings" in str(row.get("status", "")))
    payload = {
        "date": stamp,
        "generated_at": instant.isoformat(timespec="seconds"),
        "documents_total": len(rows),
        "completed": completed,
        "failed": failed,
        "with_warnings": warned,
        "documents": rows,
    }
    json_path = output_dir / f"nightly-{stamp}.json"
    md_path = output_dir / f"nightly-{stamp}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        f"# Nightly report {stamp}",
        "",
        f"- documents: {len(rows)}",
        f"- completed-ish: {completed}",
        f"- with_warnings: {warned}",
        f"- failed: {failed}",
        "",
        "## Documents",
        "",
    ]
    for row in rows:
        lines.append(
            f"- `{row.get('display_name')}` status={row.get('status')} "
            f"ocr_batches_ok={row.get('ocr_batches_ok')} failed_pages={row.get('failed_pages')}"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, json_path
