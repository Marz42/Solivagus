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
