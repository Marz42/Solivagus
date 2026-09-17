"""Phase 8 batch supervisor, profiles, discover, usage rollup."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from solivagus.batch.discover import BatchDirError, discover_pdfs, resolve_batch_dir
from solivagus.batch.manifest import write_batch_manifest
from solivagus.batch.profiles import apply_profile, get_profile
from solivagus.batch.supervisor import run_batch
from solivagus.batch.usage import aggregate_usage_reports
from solivagus.config import clear_settings_cache, get_settings
from solivagus.database import Database
from solivagus.models import DocumentStatus
from solivagus.util.text import atomic_write_json, sha256_text
from solivagus.workspace import state_db_path


class DiscoverAndProfileTests(unittest.TestCase):
    def test_resolve_batch_dir_requires_explicit_path(self) -> None:
        clear_settings_cache()
        settings = get_settings()
        settings.batch_dir = None
        with self.assertRaises(BatchDirError):
            resolve_batch_dir(None, settings)

    def test_resolve_batch_dir_from_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clear_settings_cache()
            settings = get_settings()
            settings.batch_dir = root
            self.assertEqual(resolve_batch_dir(None, settings), root.resolve())

    def test_discover_skips_artifact_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.pdf").write_bytes(b"%PDF")
            nested = root / "paper.solivagus"
            nested.mkdir()
            (nested / "inner.pdf").write_bytes(b"%PDF")
            found = discover_pdfs(root, recursive=True)
            self.assertEqual([p.name for p in found], ["a.pdf"])

    def test_profiles_apply_concurrency(self) -> None:
        clear_settings_cache()
        settings = get_settings()
        profile = apply_profile(settings, "throughput")
        self.assertEqual(profile.name, "throughput")
        self.assertEqual(settings.global_concurrency, 32)
        self.assertEqual(get_profile("conservative").ocr_workers, 1)


class BatchSupervisorTests(unittest.TestCase):
    def test_dual_queue_continue_on_error_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            batch_dir = root / "pdfs"
            batch_dir.mkdir()
            pdf_ok = batch_dir / "ok.pdf"
            pdf_bad = batch_dir / "bad.pdf"
            pdf_ok.write_bytes(b"%PDF-ok")
            pdf_bad.write_bytes(b"%PDF-bad")

            clear_settings_cache()
            settings = get_settings()
            settings.workspace = root
            settings.batch_dir = batch_dir
            settings.llm_api_key = "test"

            order: list[str] = []

            def fake_ocr(db, **kwargs):
                pdf = Path(kwargs["pdf_path"])
                order.append(f"ocr:{pdf.name}")
                if pdf.name == "bad.pdf":
                    raise RuntimeError("ocr boom")
                doc_id = db.upsert_document(
                    source_path=str(pdf),
                    source_sha256=sha256_text(pdf.name),
                    display_name=pdf.name,
                    artifact_dir=str(root / f"{pdf.stem}.solivagus"),
                    status=DocumentStatus.OCR_COMPLETE.value,
                    ocr_status="complete",
                )
                artifact = Path(root / f"{pdf.stem}.solivagus")
                artifact.mkdir(exist_ok=True)
                return {
                    "document_id": doc_id,
                    "artifact_dir": str(artifact),
                    "status": DocumentStatus.OCR_COMPLETE.value,
                }

            def fake_plan(db, **kwargs):
                order.append(f"plan:{kwargs['document_id']}")
                return {"ok": True}

            def fake_translate(db, **kwargs):
                order.append(f"translate:{kwargs['document_id']}")
                doc = db.fetchone(
                    "SELECT * FROM documents WHERE id = ?", (kwargs["document_id"],)
                )
                artifact = Path(str(doc["artifact_dir"]))
                atomic_write_json(
                    artifact / "usage-report.json",
                    {
                        "totals": {
                            "prompt_tokens": 10,
                            "cache_hit_tokens": 5,
                            "cache_miss_tokens": 5,
                            "completion_tokens": 2,
                            "api_calls": 1,
                            "local_cache_hits": 0,
                        }
                    },
                )
                db.update_document_status(
                    kwargs["document_id"],
                    status=DocumentStatus.TRANSLATION_COMPLETE.value,
                    translation_status="complete",
                )
                return {"translated": 1}

            def fake_qa(db, **kwargs):
                order.append(f"qa:{kwargs['document_id']}")
                db.update_document_status(
                    kwargs["document_id"],
                    status=DocumentStatus.QA_COMPLETE.value,
                    qa_status="pass",
                )
                return {"qa_status": "pass"}

            result = run_batch(
                settings=settings,
                batch_dir=batch_dir,
                profile="balanced",
                continue_on_error=True,
                prevent_sleep=False,
                ocr_fn=fake_ocr,
                plan_fn=fake_plan,
                translate_fn=fake_translate,
                qa_fn=fake_qa,
            )
            self.assertEqual(result["total"], 2)
            self.assertEqual(result["completed"], 1)
            self.assertEqual(result["failed"], 1)
            self.assertTrue(Path(result["manifest"]).is_file())
            self.assertTrue(Path(result["global_usage"]).is_file())
            self.assertTrue(Path(result["nightly_md"]).is_file())
            # Fair OCR FIFO: bad before ok alphabetically? bad.pdf before ok.pdf
            self.assertEqual(order[0], "ocr:bad.pdf")
            self.assertIn("ocr:ok.pdf", order)
            self.assertTrue(any(x.startswith("translate:") for x in order))
            usage = json.loads(Path(result["global_usage"]).read_text(encoding="utf-8"))
            self.assertEqual(usage["totals"]["prompt_tokens"], 10)

            with Database(state_db_path(root)) as db:
                failed = [
                    r for r in db.list_documents() if r["status"] == DocumentStatus.FAILED.value
                ]
                self.assertEqual(len(failed), 1)

    def test_batch_rerun_preserves_done_units_zero_provider(self) -> None:
        """Full batch twice: OCR cache hit keeps DONE/bindings; second translate is zero-API."""
        from unittest import mock

        from solivagus.ocr.checkpoints import OcrConfig, write_done
        from solivagus.ocr.preflight import PreflightResult
        from solivagus.ocr.runner import run_ocr_stage
        from solivagus.util.text import sha256_text

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            batch_dir = root / "pdfs"
            batch_dir.mkdir()
            pdf = batch_dir / "paper.pdf"
            pdf.write_bytes(b"%PDF-preserve")

            clear_settings_cache()
            settings = get_settings()
            settings.workspace = root
            settings.batch_dir = batch_dir
            settings.llm_api_key = "test"

            worker_calls = 0
            provider_calls = 0
            snapshot_after_first: list[tuple] = []

            def fake_worker(
                pdf_path: Path,
                artifact_dir: Path,
                batch_index: int,
                page_range,
                config: OcrConfig,
                config_hash: str,
            ) -> dict:
                nonlocal worker_calls
                worker_calls += 1
                directory = artifact_dir / "ocr" / f"batch-{batch_index:04d}"
                directory.mkdir(parents=True, exist_ok=True)
                text = "<!-- source-page: 1 -->\n\nHello preserve.\n"
                (directory / "source.md").write_text(text, encoding="utf-8")
                write_done(
                    directory,
                    batch_index=batch_index,
                    page_range=page_range,
                    config_hash=config_hash,
                    source_hash=sha256_text(text),
                    extra={"failed_pages": []},
                )
                return {
                    "batch_index": batch_index,
                    "page_start": page_range.start,
                    "page_end": page_range.end,
                    "failed_pages": [],
                    "config_hash": config_hash,
                }

            preflight = PreflightResult(
                path=str(pdf),
                page_count=1,
                encrypted=False,
                source_sha256="sha-batch-preserve",
            )

            def ocr_fn(db, **kwargs):
                with mock.patch(
                    "solivagus.ocr.runner.preflight_pdf", return_value=preflight
                ):
                    return run_ocr_stage(
                        db,
                        pdf_path=kwargs["pdf_path"],
                        workspace=kwargs["workspace"],
                        config=OcrConfig(batch_pages=8),
                        chunk_chars=kwargs.get("chunk_chars", 50_000),
                        force=False,
                        prevent_sleep=False,
                        acquire_supervisor_lock=False,
                        worker_fn=fake_worker,
                    )

            def plan_fn(db, **kwargs):
                document_id = int(kwargs["document_id"])
                units = db.list_units(document_id)
                if units and all(u["partition_id"] is not None for u in units):
                    return {"skipped": True, "unit_count": len(units)}
                part_ids = db.replace_partitions(
                    document_id,
                    [
                        {
                            "sequence_index": 1,
                            "source_tokens": 10,
                            "context_tokens": 0,
                            "unit_count": len(units),
                            "user_id": "batch-user",
                            "warmup_status": "done",
                            "expected_cache_tokens": 10,
                            "status": "complete",
                        }
                    ],
                )
                db.replace_units(
                    document_id,
                    [
                        {
                            "unit_key": str(u["unit_key"]),
                            "sequence_index": int(u["sequence_index"]),
                            "partition_id": part_ids[0],
                            "source_text": str(u["source_text"]),
                            "source_hash": str(u["source_hash"]),
                            "status": str(u["status"]),
                            "translation_text": u["translation_text"],
                            "translation_hash": u["translation_hash"],
                            "source_file": u["source_file"],
                        }
                        for u in units
                    ],
                )
                return {"skipped": False, "unit_count": len(units), "partition_id": part_ids[0]}

            def translate_fn(db, **kwargs):
                nonlocal provider_calls, snapshot_after_first
                document_id = int(kwargs["document_id"])
                units = db.list_units(document_id)
                if units and all(
                    str(u["status"]) == DocumentStatus.TRANSLATION_COMPLETE.value
                    or str(u["status"]) == "done"
                    for u in units
                ) and all(u["translation_text"] for u in units):
                    # Already translated — zero provider.
                    return {"translated": 0, "skipped": len(units)}
                provider_calls += 1
                db.replace_units(
                    document_id,
                    [
                        {
                            "unit_key": str(u["unit_key"]),
                            "sequence_index": int(u["sequence_index"]),
                            "partition_id": u["partition_id"],
                            "source_text": str(u["source_text"]),
                            "source_hash": str(u["source_hash"]),
                            "status": "done",
                            "translation_text": "已完成译文",
                            "translation_hash": sha256_text("已完成译文"),
                            "source_file": u["source_file"],
                        }
                        for u in units
                    ],
                )
                db.update_document_status(
                    document_id,
                    status=DocumentStatus.TRANSLATION_COMPLETE.value,
                    translation_status="complete",
                )
                artifact = Path(str(db.fetchone(
                    "SELECT artifact_dir FROM documents WHERE id = ?", (document_id,)
                )["artifact_dir"]))
                atomic_write_json(
                    artifact / "usage-report.json",
                    {
                        "totals": {
                            "prompt_tokens": 1,
                            "cache_hit_tokens": 0,
                            "cache_miss_tokens": 1,
                            "completion_tokens": 1,
                            "api_calls": 1,
                            "local_cache_hits": 0,
                        }
                    },
                )
                snapshot_after_first = [
                    (str(u["status"]), u["translation_text"], u["partition_id"])
                    for u in db.list_units(document_id)
                ]
                return {"translated": len(units), "skipped": 0}

            def qa_fn(db, **kwargs):
                document_id = int(kwargs["document_id"])
                db.update_document_status(
                    document_id,
                    status=DocumentStatus.QA_COMPLETE.value,
                    qa_status="pass",
                )
                return {"qa_status": "pass"}

            run1 = run_batch(
                settings=settings,
                batch_dir=batch_dir,
                profile="conservative",
                continue_on_error=False,
                prevent_sleep=False,
                ocr_fn=ocr_fn,
                plan_fn=plan_fn,
                translate_fn=translate_fn,
                qa_fn=qa_fn,
            )
            self.assertEqual(run1["failed"], 0)
            self.assertEqual(worker_calls, 1)
            self.assertEqual(provider_calls, 1)
            self.assertTrue(snapshot_after_first)
            self.assertEqual(snapshot_after_first[0][0], "done")
            self.assertEqual(snapshot_after_first[0][1], "已完成译文")
            self.assertIsNotNone(snapshot_after_first[0][2])

            run2 = run_batch(
                settings=settings,
                batch_dir=batch_dir,
                profile="conservative",
                continue_on_error=False,
                prevent_sleep=False,
                ocr_fn=ocr_fn,
                plan_fn=plan_fn,
                translate_fn=translate_fn,
                qa_fn=qa_fn,
            )
            self.assertEqual(run2["failed"], 0)
            self.assertEqual(worker_calls, 1, "second OCR must be cache-only")
            self.assertEqual(provider_calls, 1, "second translate must be zero-provider")
            with Database(state_db_path(root)) as db:
                rows = db.list_units(int(db.list_documents()[0]["id"]))
                after = [
                    (str(u["status"]), u["translation_text"], u["partition_id"])
                    for u in rows
                ]
                self.assertEqual(after, snapshot_after_first)


class ManifestUsageTests(unittest.TestCase):
    def test_write_manifest_and_usage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            artifact = out / "doc.solivagus"
            artifact.mkdir()
            atomic_write_json(
                artifact / "usage-report.json",
                {"totals": {"prompt_tokens": 3, "cache_hit_tokens": 0, "cache_miss_tokens": 3, "completion_tokens": 1, "api_calls": 1, "local_cache_hits": 0}},
            )
            docs = [
                {
                    "display_name": "doc.pdf",
                    "status": "qa_complete",
                    "artifact_dir": str(artifact),
                }
            ]
            path = write_batch_manifest(
                out, batch_dir=out, profile="balanced", documents=docs, totals={"total": 1}
            )
            self.assertTrue(path.is_file())
            usage_path, report = aggregate_usage_reports(docs, output_dir=out)
            self.assertEqual(report["totals"]["prompt_tokens"], 3)
            self.assertTrue(usage_path.is_file())


if __name__ == "__main__":
    unittest.main()
