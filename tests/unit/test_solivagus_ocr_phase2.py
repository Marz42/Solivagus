from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from solivagus.database import Database
from solivagus.ocr.checkpoints import (
    OcrConfig,
    PageRange,
    find_done_batch,
    plan_batches,
    split_range,
    write_done,
)
from solivagus.ocr.locks import LockError, acquire_lock, release_lock
from solivagus.ocr.preflight import PreflightResult
from solivagus.ocr.report import write_nightly_report
from solivagus.ocr.runner import run_ocr_stage
from solivagus.util.text import sha256_text
from solivagus.workspace import state_db_path


class CheckpointTests(unittest.TestCase):
    def test_plan_and_split(self) -> None:
        batches = plan_batches(20, 8)
        self.assertEqual(
            [(b.start, b.end) for b in batches],
            [(1, 8), (9, 16), (17, 20)],
        )
        self.assertEqual(
            [(p.start, p.end) for p in split_range(PageRange(1, 8))],
            [(1, 4), (5, 8)],
        )
        self.assertEqual(split_range(PageRange(3, 3)), [])


class LockTests(unittest.TestCase):
    def test_acquire_release_and_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / "supervisor.lock"
            info = acquire_lock(lock, command="test")
            self.assertTrue(lock.is_file())
            self.assertEqual(info.pid > 0, True)
            with self.assertRaises(LockError):
                acquire_lock(lock, command="other")
            release_lock(lock)
            # Stale pid should be replaceable.
            lock.write_text(
                json.dumps(
                    {
                        "pid": 999999,
                        "hostname": "x",
                        "started_at": "t",
                        "command": "old",
                    }
                ),
                encoding="utf-8",
            )
            acquire_lock(lock, command="fresh")
            release_lock(lock)


class OcrRunnerTests(unittest.TestCase):
    def test_batch_checkpoints_resume_and_page_failure_continue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "doc.pdf"
            pdf.write_bytes(b"%PDF-1.4 fake")
            artifact = root / "doc.solivagus"
            calls: list[tuple[int, int, int]] = []

            def fake_worker(
                pdf_path: Path,
                artifact_dir: Path,
                batch_index: int,
                page_range: PageRange,
                config: OcrConfig,
                config_hash: str,
            ) -> dict:
                calls.append((batch_index, page_range.start, page_range.end))
                # Always fail the combined 1-2 range so retry then split kicks in.
                if page_range.start == 1 and page_range.end == 2:
                    raise RuntimeError("boom")
                # Hard-fail single page 2.
                if page_range.start == 2 and page_range.end == 2:
                    raise RuntimeError("page2 dead")
                directory = artifact_dir / "ocr" / f"batch-{batch_index:04d}"
                directory.mkdir(parents=True, exist_ok=True)
                text = "\n".join(
                    f"<!-- source-page: {page} -->\n\npage {page}\n"
                    for page in range(page_range.start, page_range.end + 1)
                )
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
                page_count=2,
                encrypted=False,
                source_sha256="abc123",
            )
            with mock.patch(
                "solivagus.ocr.runner.preflight_pdf", return_value=preflight
            ), Database(state_db_path(root)) as db:
                result = run_ocr_stage(
                    db,
                    pdf_path=pdf,
                    workspace=root,
                    config=OcrConfig(batch_pages=2),
                    worker_fn=fake_worker,
                    artifact_dir=artifact,
                )
                self.assertEqual(result["page_count"], 2)
                self.assertIn(2, result["failed_pages"])
                self.assertTrue((artifact / "source.md").is_file())
                source = (artifact / "source.md").read_text(encoding="utf-8")
                self.assertIn("OCR FAILED: source-page 2", source)
                self.assertGreater(result["unit_count"], 0)

                # Second run should skip completed batches via done.json.
                before = len(calls)
                result2 = run_ocr_stage(
                    db,
                    pdf_path=pdf,
                    workspace=root,
                    config=OcrConfig(batch_pages=2),
                    worker_fn=fake_worker,
                    artifact_dir=artifact,
                )
                self.assertEqual(len(calls), before)
                self.assertEqual(result2["source_sha256"], "abc123")
                reused = find_done_batch(
                    artifact,
                    PageRange(1, 1),
                    config_hash=result["config_hash"],
                )
                self.assertIsNotNone(reused)

    def test_cache_hit_preserves_done_units_and_bindings(self) -> None:
        """OCR checkpoint hit must not wipe DONE translations / partition_id."""
        from solivagus.models import DocumentStatus, UnitStatus
        from solivagus.util.text import sha256_text as h

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "doc.pdf"
            pdf.write_bytes(b"%PDF-1.4 fake")
            artifact = root / "doc.solivagus"
            calls: list[int] = []

            def fake_worker(
                pdf_path: Path,
                artifact_dir: Path,
                batch_index: int,
                page_range: PageRange,
                config: OcrConfig,
                config_hash: str,
            ) -> dict:
                calls.append(batch_index)
                directory = artifact_dir / "ocr" / f"batch-{batch_index:04d}"
                directory.mkdir(parents=True, exist_ok=True)
                text = "\n".join(
                    f"<!-- source-page: {page} -->\n\npage {page} body\n"
                    for page in range(page_range.start, page_range.end + 1)
                )
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
                source_sha256="sha-preserve",
            )
            with mock.patch(
                "solivagus.ocr.runner.preflight_pdf", return_value=preflight
            ), Database(state_db_path(root)) as db:
                first = run_ocr_stage(
                    db,
                    pdf_path=pdf,
                    workspace=root,
                    config=OcrConfig(batch_pages=8),
                    worker_fn=fake_worker,
                    artifact_dir=artifact,
                    chunk_chars=50_000,
                )
                self.assertEqual(len(calls), 1)
                self.assertTrue(first.get("ocr_worker_ran"))
                units = db.list_units(int(first["document_id"]))
                self.assertGreaterEqual(len(units), 1)
                # Simulate post-plan / translate state.
                part_ids = db.replace_partitions(
                    int(first["document_id"]),
                    [
                        {
                            "sequence_index": 1,
                            "source_tokens": 10,
                            "context_tokens": 0,
                            "unit_count": len(units),
                            "prefix_hash": None,
                            "user_id": "u",
                            "warmup_status": "done",
                            "expected_cache_tokens": 10,
                            "actual_probe_hit_tokens": 10,
                            "status": "complete",
                            "unit_keys": [str(u["unit_key"]) for u in units],
                        }
                    ],
                )
                db.replace_units(
                    int(first["document_id"]),
                    [
                        {
                            "unit_key": str(u["unit_key"]),
                            "sequence_index": int(u["sequence_index"]),
                            "partition_id": part_ids[0],
                            "source_text": str(u["source_text"]),
                            "source_hash": str(u["source_hash"]),
                            "status": UnitStatus.DONE.value,
                            "translation_text": "已完成译文",
                            "translation_hash": h("已完成译文"),
                            "source_file": u["source_file"],
                        }
                        for u in units
                    ],
                )
                db.update_document_status(
                    int(first["document_id"]),
                    status=DocumentStatus.TRANSLATION_COMPLETE.value,
                    translation_status="complete",
                )
                before = [
                    (str(u["status"]), u["translation_text"], u["partition_id"])
                    for u in db.list_units(int(first["document_id"]))
                ]
                self.assertEqual(before[0][0], UnitStatus.DONE.value)
                self.assertEqual(before[0][1], "已完成译文")
                self.assertEqual(before[0][2], part_ids[0])

                second = run_ocr_stage(
                    db,
                    pdf_path=pdf,
                    workspace=root,
                    config=OcrConfig(batch_pages=8),
                    worker_fn=fake_worker,
                    artifact_dir=artifact,
                    chunk_chars=50_000,
                )
                self.assertEqual(len(calls), 1, "cache hit must not re-run worker")
                self.assertFalse(second.get("ocr_worker_ran"))
                after = [
                    (str(u["status"]), u["translation_text"], u["partition_id"])
                    for u in db.list_units(int(first["document_id"]))
                ]
                self.assertEqual(after, before)


class ReportTests(unittest.TestCase):
    def test_nightly_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            md, js = write_nightly_report(
                Path(tmp),
                documents=[{"display_name": "a.pdf", "status": "ocr_complete", "ocr_batches_ok": 1}],
            )
            self.assertTrue(md.is_file())
            self.assertTrue(js.is_file())


if __name__ == "__main__":
    unittest.main()
