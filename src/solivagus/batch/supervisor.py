"""Dual-queue batch supervisor with fair FIFO scheduling."""

from __future__ import annotations

import time
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Lock
from typing import Any, Callable

from solivagus.batch.discover import discover_pdfs, resolve_batch_dir
from solivagus.batch.manifest import write_batch_manifest
from solivagus.batch.profiles import BatchProfile, apply_profile
from solivagus.batch.usage import aggregate_usage_reports
from solivagus.concurrency.limits import ThreadSafeGate
from solivagus.config import Settings
from solivagus.database import Database
from solivagus.models import DocumentStatus
from solivagus.ocr.checkpoints import OcrConfig
from solivagus.ocr.locks import LockError, acquire_lock, release_lock
from solivagus.ocr.report import write_nightly_report
from solivagus.ocr.runner import OcrStageError, run_ocr_stage
from solivagus.ocr.sleep import enable_prevent_sleep
from solivagus.pipeline.plan import PlanStageError, run_plan_stage
from solivagus.pipeline.translate import run_translate_stage
from solivagus.qa import QAStageError, run_qa_stage
from solivagus.util.text import sha256_file, sha256_text
from solivagus.workspace import ensure_workspace, state_db_path, workspace_root


OcrFn = Callable[..., dict[str, Any]]
PlanFn = Callable[..., dict[str, Any]]
TranslateFn = Callable[..., dict[str, Any]]
QaFn = Callable[..., dict[str, Any]]


def _persist_document_failed(
    workspace: Path,
    document_id: int,
    *,
    ocr: bool = False,
    translation: bool = False,
    attempts: int = 8,
) -> bool:
    """Best-effort FAILED落库 under transient SQLite busy/locked."""
    last: Exception | None = None
    for i in range(max(1, attempts)):
        try:
            with _open_db(workspace) as db:
                db.update_document_status(
                    int(document_id),
                    status=DocumentStatus.FAILED.value,
                    ocr_status="failed" if ocr else None,
                    translation_status="failed" if translation else None,
                )
            return True
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(min(2.0, 0.05 * (2**i)))
    if last is not None:
        return False
    return False


@dataclass
class BatchJob:
    pdf_path: Path
    index: int
    status: str = "queued"
    document_id: int | None = None
    artifact_dir: str | None = None
    error: str | None = None
    stages: dict[str, Any] = field(default_factory=dict)


class BatchSupervisorError(RuntimeError):
    pass


def _open_db(workspace: Path) -> Database:
    ensure_workspace(workspace)
    return Database(state_db_path(workspace))


def _run_translate_pipeline(
    db: Database,
    *,
    document_id: int,
    settings: Settings,
    plan_fn: PlanFn,
    translate_fn: TranslateFn,
    qa_fn: QaFn,
    skip_plan: bool = False,
    global_gate: Any = None,
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    if not skip_plan:
        results["plan"] = plan_fn(db, document_id=document_id, settings=settings)
    translate_kwargs: dict[str, Any] = {
        "document_id": document_id,
        "settings": settings,
    }
    if global_gate is not None:
        translate_kwargs["global_gate"] = global_gate
    results["translate"] = translate_fn(db, **translate_kwargs)
    results["qa"] = qa_fn(db, document_id=document_id, settings=settings, force=True)
    return results


def run_batch(
    *,
    settings: Settings,
    batch_dir: Path | None = None,
    recursive: bool = False,
    continue_on_error: bool | None = None,
    prevent_sleep: bool | None = None,
    profile: str | BatchProfile = "balanced",
    ocr_fn: OcrFn | None = None,
    plan_fn: PlanFn | None = None,
    translate_fn: TranslateFn | None = None,
    qa_fn: QaFn | None = None,
    pdfs: list[Path] | None = None,
) -> dict[str, Any]:
    """Process a directory of PDFs with OCR + translate dual queues."""
    resolved_profile = apply_profile(settings, profile)
    cont = (
        resolved_profile.continue_on_error
        if continue_on_error is None
        else continue_on_error
    )
    sleep = (
        resolved_profile.prevent_sleep if prevent_sleep is None else prevent_sleep
    )
    enable_prevent_sleep(bool(sleep))

    if pdfs is not None:
        pdf_list = [p.expanduser().resolve() for p in pdfs]
        if batch_dir is not None:
            root = batch_dir.expanduser().resolve()
        elif settings.batch_dir is not None:
            root = Path(settings.batch_dir).expanduser().resolve()
        else:
            root = pdf_list[0].parent if pdf_list else Path(".")
    else:
        root = resolve_batch_dir(batch_dir, settings)
        pdf_list = discover_pdfs(root, recursive=recursive)

    if not pdf_list:
        raise BatchSupervisorError(f"no PDF files found under {root}")

    jobs = [BatchJob(pdf_path=p, index=i) for i, p in enumerate(pdf_list)]
    ocr_queue: Queue[BatchJob | None] = Queue()
    translate_queue: Queue[BatchJob | None] = Queue()
    for job in jobs:
        ocr_queue.put(job)

    ocr_impl = ocr_fn or run_ocr_stage
    plan_impl = plan_fn or run_plan_stage
    translate_impl = translate_fn or run_translate_stage
    qa_impl = qa_fn or run_qa_stage

    ocr_config = OcrConfig(
        pipeline_version=settings.ocr_pipeline_version,
        device=settings.ocr_device,
        use_orientation=settings.ocr_use_orientation,
        use_unwarping=settings.ocr_use_unwarping,
        use_chart_recognition=settings.ocr_use_chart_recognition,
        batch_pages=settings.ocr_batch_pages,
        drop_footnotes=settings.ocr_drop_footnotes,
        drop_aside_text=settings.ocr_drop_aside_text,
    )

    results_lock = Lock()
    stop_translate = Event()
    ocr_done_count = 0
    ocr_total = len(jobs)
    batch_global_gate = ThreadSafeGate(
        settings.global_concurrency,
        maximum=settings.max_global_concurrency,
    )

    ws_root = workspace_root(settings.workspace)
    ensure_workspace(settings.workspace)
    batch_lock = ws_root / "supervisor.lock"
    try:
        acquire_lock(batch_lock, command=f"batch {root}")
    except LockError as exc:
        raise BatchSupervisorError(str(exc)) from exc

    def mark(job: BatchJob, **fields: Any) -> None:
        with results_lock:
            for key, value in fields.items():
                setattr(job, key, value)

    def do_ocr(job: BatchJob) -> None:
        nonlocal ocr_done_count
        mark(job, status="ocr_running")
        try:
            with _open_db(settings.workspace) as db:
                result = ocr_impl(
                    db,
                    pdf_path=job.pdf_path,
                    workspace=settings.workspace,
                    config=ocr_config,
                    chunk_chars=settings.chunk_chars,
                    force=False,
                    prevent_sleep=False,
                    acquire_supervisor_lock=False,
                )
            mark(
                job,
                status="ocr_complete",
                document_id=int(result["document_id"]),
                artifact_dir=str(result.get("artifact_dir") or ""),
                stages={**job.stages, "ocr": result},
            )
            translate_queue.put(job)
        except Exception as exc:  # noqa: BLE001
            mark(
                job,
                status="failed",
                error=f"ocr: {exc}",
                stages={**job.stages, "ocr_error": traceback.format_exc()},
            )
            try:
                from solivagus.workspace import default_artifact_dir

                sha = (
                    sha256_file(job.pdf_path)
                    if job.pdf_path.is_file()
                    else sha256_text(str(job.pdf_path))
                )
                artifact = default_artifact_dir(job.pdf_path)
                last_upsert_err: Exception | None = None
                doc_id: int | None = None
                for i in range(8):
                    try:
                        with _open_db(settings.workspace) as db:
                            doc_id = db.upsert_document(
                                source_path=str(job.pdf_path),
                                source_sha256=sha,
                                display_name=job.pdf_path.name,
                                artifact_dir=str(artifact),
                                status=DocumentStatus.FAILED.value,
                                ocr_status="failed",
                            )
                            db.commit()
                        break
                    except Exception as upsert_exc:  # noqa: BLE001
                        last_upsert_err = upsert_exc
                        time.sleep(min(2.0, 0.05 * (2**i)))
                if doc_id is not None:
                    mark(job, document_id=doc_id, artifact_dir=str(artifact))
                elif last_upsert_err is not None:
                    mark(
                        job,
                        stages={
                            **job.stages,
                            "ocr_failed_persist_error": repr(last_upsert_err),
                        },
                    )
            except Exception as persist_exc:  # noqa: BLE001
                mark(
                    job,
                    stages={
                        **job.stages,
                        "ocr_failed_persist_error": repr(persist_exc),
                    },
                )
            if not cont:
                stop_translate.set()
                raise
        finally:
            with results_lock:
                ocr_done_count += 1
                if ocr_done_count >= ocr_total:
                    for _ in range(max(1, resolved_profile.translate_workers)):
                        translate_queue.put(None)

    def do_translate(job: BatchJob) -> None:
        mark(job, status="translation_running")
        try:
            with _open_db(settings.workspace) as db:
                doc_id = job.document_id
                if doc_id is None:
                    sha = sha256_file(job.pdf_path)
                    row = db.get_document_by_path_or_sha(
                        path=job.pdf_path, sha256=sha
                    )
                    if row is None:
                        raise BatchSupervisorError(
                            f"document not registered after OCR: {job.pdf_path}"
                        )
                    doc_id = int(row["id"])
                    mark(job, document_id=doc_id, artifact_dir=str(row["artifact_dir"]))
                pipeline = _run_translate_pipeline(
                    db,
                    document_id=doc_id,
                    settings=settings,
                    plan_fn=plan_impl,
                    translate_fn=translate_impl,
                    qa_fn=qa_impl,
                    global_gate=batch_global_gate,
                )
            mark(
                job,
                status="qa_complete",
                stages={**job.stages, **pipeline},
            )
        except Exception as exc:  # noqa: BLE001
            mark(
                job,
                status="failed",
                error=f"translate: {exc}",
                stages={**job.stages, "translate_error": traceback.format_exc()},
            )
            if job.document_id is not None:
                ok = _persist_document_failed(
                    settings.workspace,
                    int(job.document_id),
                    translation=True,
                )
                if not ok:
                    mark(
                        job,
                        stages={
                            **job.stages,
                            "translate_failed_persist_error": "database failed mark did not stick",
                        },
                    )
            if not cont:
                stop_translate.set()
                raise

    try:
        # OCR is intentionally serial (GPU / Paddle); translate pool is fair FIFO.
        translate_workers = max(1, int(resolved_profile.translate_workers))
        with ThreadPoolExecutor(max_workers=translate_workers) as translate_pool:
            translate_futures: list[Future[None]] = []

            def translate_worker() -> None:
                while not stop_translate.is_set():
                    try:
                        item = translate_queue.get(timeout=0.2)
                    except Empty:
                        continue
                    if item is None:
                        return
                    do_translate(item)

            for _ in range(translate_workers):
                translate_futures.append(translate_pool.submit(translate_worker))

            while True:
                try:
                    job = ocr_queue.get_nowait()
                except Empty:
                    break
                if job is None:
                    break
                try:
                    do_ocr(job)
                except Exception:
                    if not cont:
                        stop_translate.set()
                        for _ in range(translate_workers):
                            translate_queue.put(None)
                        break
            for fut in translate_futures:
                fut.result()
    finally:
        release_lock(batch_lock)
        enable_prevent_sleep(False)

    doc_rows = []
    failed = 0
    completed = 0
    for job in jobs:
        if job.status == "failed":
            failed += 1
        elif job.status in {
            DocumentStatus.QA_COMPLETE.value,
            "qa_complete",
            DocumentStatus.TRANSLATION_COMPLETE.value,
        }:
            completed += 1
        doc_rows.append(
            {
                "display_name": job.pdf_path.name,
                "path": str(job.pdf_path),
                "status": job.status,
                "document_id": job.document_id,
                "artifact_dir": job.artifact_dir,
                "error": job.error,
                "index": job.index,
            }
        )

    reports_dir = workspace_root(settings.workspace) / "reports"
    manifest_path = write_batch_manifest(
        reports_dir,
        batch_dir=root,
        profile=resolved_profile.name,
        documents=doc_rows,
        totals={"completed": completed, "failed": failed, "total": len(jobs)},
    )
    usage_path, usage_report = aggregate_usage_reports(doc_rows, output_dir=reports_dir)

    nightly_docs = []
    with _open_db(settings.workspace) as db:
        for doc in db.list_documents():
            batches = db.fetchall(
                "SELECT status FROM ocr_batches WHERE document_id = ?",
                (int(doc["id"]),),
            )
            ok = sum(
                1
                for item in batches
                if str(item["status"]).startswith("done")
                or item["status"] == "skipped_done"
            )
            nightly_docs.append(
                {
                    "display_name": doc["display_name"],
                    "status": doc["status"],
                    "ocr_batches_ok": ok,
                    "failed_pages": None,
                    "artifact_dir": doc["artifact_dir"],
                }
            )
    md_path, json_path = write_nightly_report(reports_dir, documents=nightly_docs)

    return {
        "batch_dir": str(root),
        "profile": resolved_profile.name,
        "total": len(jobs),
        "completed": completed,
        "failed": failed,
        "continue_on_error": cont,
        "manifest": str(manifest_path),
        "global_usage": str(usage_path),
        "usage_totals": usage_report.get("totals"),
        "nightly_md": str(md_path),
        "nightly_json": str(json_path),
        "documents": doc_rows,
    }


def retry_failed_documents(
    *,
    settings: Settings,
    pdf: Path | None = None,
    all_failed: bool = False,
    profile: str | BatchProfile = "balanced",
    ocr_fn: OcrFn | None = None,
    plan_fn: PlanFn | None = None,
    translate_fn: TranslateFn | None = None,
    qa_fn: QaFn | None = None,
) -> dict[str, Any]:
    """Retry one failed PDF or all documents currently marked failed."""
    apply_profile(settings, profile)
    with _open_db(settings.workspace) as db:
        if pdf is not None:
            pdf = pdf.expanduser().resolve()
            sha = sha256_file(pdf) if pdf.is_file() else None
            row = db.get_document_by_path_or_sha(path=pdf, sha256=sha)
            if row is None:
                raise BatchSupervisorError(f"document not registered: {pdf}")
            targets = [row]
        elif all_failed:
            targets = [
                row
                for row in db.list_documents()
                if str(row["status"]) == DocumentStatus.FAILED.value
            ]
        else:
            raise BatchSupervisorError("pass a PDF path or --all-failed")

    pdfs: list[Path] = []
    for row in targets:
        path = Path(str(row["source_path"]))
        if path.is_file():
            pdfs.append(path)

    if not pdfs:
        return {"retried": 0, "documents": []}

    # Reset failed docs to queued so pipeline can proceed.
    with _open_db(settings.workspace) as db:
        for row in targets:
            db.update_document_status(
                int(row["id"]),
                status=DocumentStatus.QUEUED.value,
                translation_status=None,
                ocr_status=None,
                qa_status=None,
            )

    result = run_batch(
        settings=settings,
        batch_dir=pdfs[0].parent,
        profile=profile,
        pdfs=pdfs,
        continue_on_error=True,
        ocr_fn=ocr_fn,
        plan_fn=plan_fn,
        translate_fn=translate_fn,
        qa_fn=qa_fn,
    )
    result["retried"] = len(pdfs)
    return result
