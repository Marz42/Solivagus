"""Import MVP `*.translation` directories into Solivagus SQLite state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from solivagus.artifacts import ensure_artifact_layout
from solivagus.database import Database
from solivagus.models import DocumentStatus, UnitStatus
from solivagus.util.text import read_json, sha256_file, sha256_text
from solivagus.workspace import default_artifact_dir


class MvpImportError(ValueError):
    pass


def import_mvp_translation_dir(
    db: Database,
    *,
    translation_dir: Path,
    pdf_path: Path | None = None,
    artifact_dir: Path | None = None,
) -> dict[str, Any]:
    translation_dir = translation_dir.expanduser().resolve()
    state_path = translation_dir / "state.json"
    if not state_path.is_file():
        raise MvpImportError(f"missing state.json: {state_path}")

    state = read_json(state_path)
    if not state:
        raise MvpImportError(f"invalid or empty state.json: {state_path}")

    source_sha = str(state.get("source_pdf_sha256") or "")
    if pdf_path is not None:
        pdf_path = pdf_path.expanduser().resolve()
        if not pdf_path.is_file():
            raise MvpImportError(f"PDF not found: {pdf_path}")
        file_sha = sha256_file(pdf_path)
        if source_sha and source_sha != file_sha:
            raise MvpImportError(
                "PDF sha256 does not match state.json source_pdf_sha256: "
                f"{file_sha} != {source_sha}"
            )
        source_sha = file_sha
        source_path = str(pdf_path)
        display_name = pdf_path.name
    else:
        source_path = str(state.get("source_pdf") or translation_dir)
        display_name = Path(source_path).name
        if not source_sha:
            raise MvpImportError("state.json missing source_pdf_sha256")

    target_artifact = (artifact_dir or translation_dir).expanduser().resolve()
    ensure_artifact_layout(target_artifact)

    # Reuse MVP directory as artifact root when importing in place.
    if target_artifact != translation_dir:
        # Minimal copy of critical outputs for a new artifact root.
        for name in ("source.md", "translated.zh.md", "translated.bilingual.md"):
            src = translation_dir / name
            if src.is_file():
                dest = target_artifact / name
                dest.write_bytes(src.read_bytes())

    chunks = state.get("chunks") or []
    if not isinstance(chunks, list) or not chunks:
        raise MvpImportError("state.json contains no chunks")

    translation_meta = state.get("translation") if isinstance(state.get("translation"), dict) else {}
    completed = bool(state.get("completed"))
    doc_status = (
        DocumentStatus.TRANSLATION_COMPLETE.value
        if completed
        else DocumentStatus.TRANSLATION_RUNNING.value
    )

    document_id = db.upsert_document(
        source_path=source_path,
        source_sha256=source_sha,
        display_name=display_name,
        artifact_dir=str(target_artifact),
        status=doc_status,
        ocr_status="complete" if (translation_dir / "source.md").exists() else None,
        translation_status="complete" if completed else "running",
        active_config_hash=None,
    )

    units: list[dict[str, Any]] = []
    for index, item in enumerate(chunks, start=1):
        if not isinstance(item, dict):
            continue
        unit_key = str(item.get("id") or f"b{index:05d}")
        source_rel = str(item.get("source_file") or f"chunks/{unit_key}.source.md")
        translated_rel = str(item.get("translated_file") or f"chunks/{unit_key}.zh.md")
        source_file = translation_dir / source_rel
        translated_file = translation_dir / translated_rel
        if not source_file.is_file():
            raise MvpImportError(f"missing chunk source: {source_file}")
        source_text = source_file.read_text(encoding="utf-8")
        source_hash = str(item.get("source_sha256") or sha256_text(source_text))
        status_raw = str(item.get("status") or "pending")
        if status_raw == "done":
            status = UnitStatus.DONE.value
        elif status_raw in {"failed", "error"}:
            status = UnitStatus.FAILED.value
        else:
            status = UnitStatus.PENDING.value
        translation_text = None
        translation_hash = None
        if translated_file.is_file():
            translation_text = translated_file.read_text(encoding="utf-8")
            translation_hash = sha256_text(translation_text)
        units.append(
            {
                "unit_key": unit_key,
                "sequence_index": index,
                "source_text": source_text,
                "source_hash": source_hash,
                "status": status,
                "translation_text": translation_text,
                "translation_hash": translation_hash,
                "provider": "openai-compatible",
                "model": translation_meta.get("model"),
                "prompt_version": "mvp-v0.2",
                "attempt_count": 1 if status == UnitStatus.DONE.value else 0,
                "source_file": source_rel,
                "translated_file": translated_rel,
            }
        )

    db.replace_units(document_id, units)
    for artifact_type, name in (
        ("source", "source.md"),
        ("translated_zh", "translated.zh.md"),
        ("translated_bilingual", "translated.bilingual.md"),
        ("mvp_state", "state.json"),
    ):
        path = translation_dir / name
        if path.is_file():
            db.record_artifact(
                document_id,
                artifact_type,
                str(path),
                sha256_file(path),
            )
    db.commit()

    return {
        "document_id": document_id,
        "source_sha256": source_sha,
        "artifact_dir": str(target_artifact),
        "unit_count": len(units),
        "completed": completed,
        "suggested_artifact_dir": str(
            default_artifact_dir(pdf_path) if pdf_path else target_artifact
        ),
    }


def export_import_report(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2) + "\n"
