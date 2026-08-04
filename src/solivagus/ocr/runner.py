"""OCR stage supervisor: locks, batches, subprocess workers, failure split."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from solivagus import __version__
from solivagus.artifacts import ensure_artifact_layout
from solivagus.database import Database, utc_now
from solivagus.models import DocumentStatus, UnitStatus
from solivagus.ocr.checkpoints import (
    OcrConfig,
    PageRange,
    assemble_source_markdown,
    batch_dir,
    covered_pages,
    find_done_batch,
    missing_page_stub,
    next_batch_index,
    plan_batches,
    split_range,
    write_done,
)
from solivagus.ocr.locks import LockError, acquire_lock, release_lock
from solivagus.ocr.preflight import PreflightError, preflight_pdf
from solivagus.ocr.sleep import enable_prevent_sleep
from solivagus.util.markdown import split_markdown
from solivagus.util.text import atomic_write_json, sha256_file, sha256_text
from solivagus.workspace import default_artifact_dir, workspace_root


WorkerFn = Callable[[Path, Path, int, PageRange, OcrConfig, str], dict[str, Any]]


class OcrStageError(RuntimeError):
    pass


def _default_worker(
    pdf_path: Path,
    artifact_dir: Path,
    batch_index: int,
    page_range: PageRange,
    config: OcrConfig,
    config_hash: str,
) -> dict[str, Any]:
    config_path = batch_dir(artifact_dir, batch_index) / "worker-config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        config_path,
        {
            "pipeline_version": config.pipeline_version,
            "device": config.device,
            "use_orientation": config.use_orientation,
            "use_unwarping": config.use_unwarping,
            "use_chart_recognition": config.use_chart_recognition,
            "batch_pages": config.batch_pages,
            "ignore_labels": list(config.ignore_labels),
        },
    )
    cmd = [
        sys.executable,
        "-m",
        "solivagus.ocr.worker",
        "--pdf",
        str(pdf_path),
        "--artifact-dir",
        str(artifact_dir),
        "--batch-index",
        str(batch_index),
        "--page-start",
        str(page_range.start),
        "--page-end",
        str(page_range.end),
        "--config-json",
        str(config_path),
        "--config-hash",
        config_hash,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise OcrStageError(
            f"OCR worker failed for batch-{batch_index:04d} "
            f"pages {page_range.start}-{page_range.end}: {detail[:1000]}"
        )
    done = batch_dir(artifact_dir, batch_index) / "done.json"
    if not done.is_file():
        raise OcrStageError(f"worker exited 0 but missing done.json: {done}")
    return json.loads(done.read_text(encoding="utf-8"))


def _record_batch(
    db: Database,
    *,
    document_id: int,
    page_range: PageRange,
    status: str,
    config_hash: str,
    output_path: str | None,
    error_message: str | None = None,
    attempt_count: int = 1,
) -> None:
    db.execute(
        """
        INSERT INTO ocr_batches(
          document_id, page_start, page_end, status, attempt_count,
          config_hash, output_path, error_message, started_at, finished_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            document_id,
            page_range.start,
            page_range.end,
            status,
            attempt_count,
            config_hash,
            output_path,
            error_message,
            utc_now(),
            utc_now(),
        ),
    )


def _seed_units_from_source(
    db: Database,
    *,
    document_id: int,
    artifact_dir: Path,
    chunk_chars: int,
) -> int:
    source_path = artifact_dir / "source.md"
    if not source_path.is_file():
        return 0
    source = source_path.read_text(encoding="utf-8")
    chunks = split_markdown(source, chunk_chars)
    units = []
    units_dir = artifact_dir / "units"
    units_dir.mkdir(parents=True, exist_ok=True)
    for index, chunk in enumerate(chunks, start=1):
        unit_key = f"u{index:05d}"
        source_file = units_dir / f"{unit_key}.source.md"
        source_file.write_text(chunk if chunk.endswith("\n") else chunk + "\n", encoding="utf-8")
        units.append(
            {
                "unit_key": unit_key,
                "sequence_index": index,
                "source_text": chunk,
                "source_hash": sha256_text(chunk),
                "status": UnitStatus.PENDING.value,
                "source_file": str(source_file.relative_to(artifact_dir)).replace("\\", "/"),
            }
        )
    db.replace_units(document_id, units)
    return len(units)


def run_ocr_stage(
    db: Database,
    *,
    pdf_path: Path,
    workspace: Path,
    config: OcrConfig | None = None,
    chunk_chars: int = 12000,
    force: bool = False,
    prevent_sleep: bool = False,
    worker_fn: WorkerFn | None = None,
    artifact_dir: Path | None = None,
    acquire_supervisor_lock: bool = True,
) -> dict[str, Any]:
    pdf_path = pdf_path.expanduser().resolve()
    config = config or OcrConfig()
    worker = worker_fn or _default_worker
    enable_prevent_sleep(prevent_sleep)

    try:
        preflight = preflight_pdf(pdf_path)
    except PreflightError as exc:
        raise OcrStageError(str(exc)) from exc

    artifact = (artifact_dir or default_artifact_dir(pdf_path)).expanduser().resolve()
    ensure_artifact_layout(artifact)
    config_hash = config.config_hash(source_sha256=preflight.source_sha256)

    ws_root = workspace_root(workspace)
    supervisor_lock = ws_root / "supervisor.lock"
    doc_lock = artifact / ".run.lock"
    held_supervisor = False
    if acquire_supervisor_lock:
        acquire_lock(supervisor_lock, command=f"ocr {pdf_path.name}")
        held_supervisor = True
    try:
        acquire_lock(doc_lock, command=f"ocr {pdf_path.name}")
    except LockError:
        if held_supervisor:
            release_lock(supervisor_lock)
        raise

    try:
        document_id = db.upsert_document(
            source_path=str(pdf_path),
            source_sha256=preflight.source_sha256,
            display_name=pdf_path.name,
            artifact_dir=str(artifact),
            status=DocumentStatus.OCR_RUNNING.value,
            page_count=preflight.page_count,
            ocr_status="running",
            active_config_hash=config_hash,
        )
        atomic_write_json(artifact / "preflight.json", preflight.to_dict())

        queue: list[tuple[PageRange, int]] = [
            (page_range, 0) for page_range in plan_batches(preflight.page_count, config.batch_pages)
        ]
        completed_indices: list[int] = []
        failed_pages: list[int] = []
        warnings = 0
        next_index = next_batch_index(artifact)
        already_covered = set() if force else covered_pages(artifact, config_hash=config_hash)
        # Include existing done batch indices for final assemble.
        if already_covered:
            ocr_root = artifact / "ocr"
            for path in sorted(ocr_root.glob("batch-*")):
                if (path / "done.json").is_file() and (path / "source.md").is_file():
                    try:
                        completed_indices.append(int(path.name.split("-", 1)[1]))
                    except (IndexError, ValueError):
                        pass

        while queue:
            page_range, attempts = queue.pop(0)
            needed = set(range(page_range.start, page_range.end + 1))
            if not force and needed and needed.issubset(already_covered):
                existing = find_done_batch(
                    artifact, page_range, config_hash=config_hash
                )
                _record_batch(
                    db,
                    document_id=document_id,
                    page_range=page_range,
                    status="skipped_done",
                    config_hash=config_hash,
                    output_path=(
                        str(batch_dir(artifact, existing)) if existing is not None else None
                    ),
                    attempt_count=attempts,
                )
                continue

            existing = None if force else find_done_batch(
                artifact, page_range, config_hash=config_hash
            )
            if existing is not None:
                completed_indices.append(existing)
                already_covered.update(range(page_range.start, page_range.end + 1))
                _record_batch(
                    db,
                    document_id=document_id,
                    page_range=page_range,
                    status="skipped_done",
                    config_hash=config_hash,
                    output_path=str(batch_dir(artifact, existing)),
                    attempt_count=attempts,
                )
                continue

            batch_index = next_index
            next_index += 1
            directory = batch_dir(artifact, batch_index)

            try:
                result = worker(
                    pdf_path,
                    artifact,
                    batch_index,
                    page_range,
                    config,
                    config_hash,
                )
                completed_indices.append(batch_index)
                already_covered.update(range(page_range.start, page_range.end + 1))
                failed = list(result.get("failed_pages") or [])
                if failed:
                    warnings += 1
                    failed_pages.extend(int(p) for p in failed)
                _record_batch(
                    db,
                    document_id=document_id,
                    page_range=page_range,
                    status="done_with_warnings" if failed else "done",
                    config_hash=config_hash,
                    output_path=str(directory),
                    attempt_count=attempts + 1,
                )
            except Exception as exc:  # noqa: BLE001
                if attempts == 0:
                    queue.insert(0, (page_range, 1))
                    continue
                pieces = split_range(page_range)
                if pieces:
                    for piece in reversed(pieces):
                        queue.insert(0, (piece, 0))
                    _record_batch(
                        db,
                        document_id=document_id,
                        page_range=page_range,
                        status="split",
                        config_hash=config_hash,
                        output_path=None,
                        error_message=str(exc)[:800],
                        attempt_count=attempts + 1,
                    )
                    continue
                # Single page hard failure: write stub batch and continue.
                warnings += 1
                failed_pages.append(page_range.start)
                directory.mkdir(parents=True, exist_ok=True)
                stub = missing_page_stub(page_range.start)
                (directory / "source.md").write_text(stub, encoding="utf-8")
                write_done(
                    directory,
                    batch_index=batch_index,
                    page_range=page_range,
                    config_hash=config_hash,
                    source_hash=sha256_text(stub),
                    extra={"failed_pages": [page_range.start], "hard_failure": True},
                )
                completed_indices.append(batch_index)
                already_covered.add(page_range.start)
                _record_batch(
                    db,
                    document_id=document_id,
                    page_range=page_range,
                    status="failed_continued",
                    config_hash=config_hash,
                    output_path=str(directory),
                    error_message=str(exc)[:800],
                    attempt_count=attempts + 1,
                )

        assemble_source_markdown(
            artifact,
            completed_indices,
            pdf_name=pdf_path.name,
            script_version=__version__,
        )
        unit_count = _seed_units_from_source(
            db,
            document_id=document_id,
            artifact_dir=artifact,
            chunk_chars=chunk_chars,
        )
        final_status = (
            DocumentStatus.OCR_COMPLETE_WITH_WARNINGS.value
            if warnings or failed_pages
            else DocumentStatus.OCR_COMPLETE.value
        )
        db.update_document_status(
            document_id,
            status=final_status,
            ocr_status="complete_with_warnings" if warnings or failed_pages else "complete",
        )
        db.record_artifact(
            document_id,
            "source",
            str(artifact / "source.md"),
            sha256_file(artifact / "source.md") if (artifact / "source.md").is_file() else None,
        )
        db.commit()
        return {
            "document_id": document_id,
            "page_count": preflight.page_count,
            "batches": len(completed_indices),
            "failed_pages": sorted(set(failed_pages)),
            "warnings": warnings,
            "unit_count": unit_count,
            "artifact_dir": str(artifact),
            "status": final_status,
            "config_hash": config_hash,
            "source_sha256": preflight.source_sha256,
        }
    finally:
        release_lock(doc_lock)
        if held_supervisor:
            release_lock(supervisor_lock)
