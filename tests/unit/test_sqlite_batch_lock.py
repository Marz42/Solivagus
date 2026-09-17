"""Small concurrent repro: SQLite lock amplifier + FAILED落库 under busy."""

from __future__ import annotations

import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path

from solivagus.batch.supervisor import _persist_document_failed, run_batch
from solivagus.config import clear_settings_cache, get_settings
from solivagus.database import Database
from solivagus.models import DocumentStatus
from solivagus.workspace import state_db_path


class SqliteLockAmplifierTests(unittest.TestCase):
    def test_uncommitted_insert_blocks_peer_writer(self) -> None:
        """Anti-pattern: open write txn across a wait → peer UPDATE sees locked."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"
            with Database(db_path) as setup:
                doc_id = setup.upsert_document(
                    source_path="a.pdf",
                    source_sha256="sha-a",
                    display_name="a.pdf",
                    artifact_dir=str(Path(tmp) / "a"),
                    status=DocumentStatus.OCR_COMPLETE.value,
                    ocr_status="complete",
                )

            holder = sqlite3.connect(db_path, timeout=0.1)
            holder.execute("PRAGMA busy_timeout = 100")
            holder.execute(
                """
                INSERT INTO ocr_batches(
                  document_id, page_start, page_end, status, attempt_count,
                  config_hash, output_path, error_message, started_at, finished_at
                ) VALUES (?, 1, 1, 'done', 1, 'h', NULL, NULL, 't', 't')
                """,
                (doc_id,),
            )
            # Intentionally no commit — models pre-fix OCR _record_batch.

            peer_err: list[BaseException] = []

            def peer_update() -> None:
                peer = sqlite3.connect(db_path, timeout=0.2)
                peer.execute("PRAGMA busy_timeout = 200")
                try:
                    peer.execute(
                        "UPDATE documents SET status = ?, updated_at = ? WHERE id = ?",
                        (DocumentStatus.FAILED.value, "t", doc_id),
                    )
                    peer.commit()
                except Exception as exc:  # noqa: BLE001
                    peer_err.append(exc)
                finally:
                    peer.close()

            t = threading.Thread(target=peer_update)
            t.start()
            t.join(timeout=5)
            holder.rollback()
            holder.close()

            self.assertTrue(peer_err, "peer writer should fail while holder txn open")
            self.assertTrue(
                any("locked" in str(e).lower() or "busy" in str(e).lower() for e in peer_err),
                peer_err,
            )

    def test_commit_before_wait_allows_peer_writer(self) -> None:
        """Mitigation pattern: commit then wait → peer UPDATE succeeds."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"
            with Database(db_path) as setup:
                doc_id = setup.upsert_document(
                    source_path="b.pdf",
                    source_sha256="sha-b",
                    display_name="b.pdf",
                    artifact_dir=str(Path(tmp) / "b"),
                    status=DocumentStatus.OCR_COMPLETE.value,
                    ocr_status="complete",
                )

            holder = sqlite3.connect(db_path, timeout=1.0)
            holder.execute("PRAGMA busy_timeout = 1000")
            holder.execute(
                """
                INSERT INTO ocr_batches(
                  document_id, page_start, page_end, status, attempt_count,
                  config_hash, output_path, error_message, started_at, finished_at
                ) VALUES (?, 1, 1, 'done', 1, 'h', NULL, NULL, 't', 't')
                """,
                (doc_id,),
            )
            holder.commit()  # models fixed _record_batch + pre-worker commit

            peer_ok = threading.Event()
            peer_err: list[BaseException] = []

            def peer_update() -> None:
                try:
                    with Database(db_path) as peer:
                        peer.update_document_status(
                            doc_id,
                            status=DocumentStatus.FAILED.value,
                            translation_status="failed",
                        )
                    peer_ok.set()
                except Exception as exc:  # noqa: BLE001
                    peer_err.append(exc)

            t = threading.Thread(target=peer_update)
            t.start()
            time.sleep(0.3)  # OCR-style wait with no open write txn
            t.join(timeout=5)
            holder.close()

            self.assertFalse(peer_err, peer_err)
            self.assertTrue(peer_ok.is_set())
            with Database(db_path) as check:
                row = check.fetchone("SELECT status, translation_status FROM documents WHERE id = ?", (doc_id,))
                assert row is not None
                self.assertEqual(row["status"], DocumentStatus.FAILED.value)
                self.assertEqual(row["translation_status"], "failed")


class FailedPersistTests(unittest.TestCase):
    def test_persist_document_failed_retries_under_short_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clear_settings_cache()
            settings = get_settings()
            settings.workspace = root
            db_path = state_db_path(root)
            with Database(db_path) as setup:
                doc_id = setup.upsert_document(
                    source_path="c.pdf",
                    source_sha256="sha-c",
                    display_name="c.pdf",
                    artifact_dir=str(root / "c"),
                    status=DocumentStatus.TRANSLATION_RUNNING.value,
                    translation_status="running",
                )

            ready = threading.Event()
            release = threading.Event()

            def hold_lock() -> None:
                holder = sqlite3.connect(db_path, timeout=5.0, check_same_thread=False)
                holder.execute("BEGIN IMMEDIATE")
                ready.set()
                release.wait(timeout=10)
                holder.commit()
                holder.close()

            holder_thread = threading.Thread(target=hold_lock, daemon=True)
            holder_thread.start()
            self.assertTrue(ready.wait(timeout=5))

            def unlock_soon() -> None:
                time.sleep(0.25)
                release.set()

            threading.Thread(target=unlock_soon, daemon=True).start()
            ok = _persist_document_failed(root, doc_id, translation=True, attempts=12)
            holder_thread.join(timeout=5)

            self.assertTrue(ok)
            with Database(db_path) as check:
                row = check.fetchone(
                    "SELECT status, translation_status FROM documents WHERE id = ?",
                    (doc_id,),
                )
                assert row is not None
                self.assertEqual(row["status"], DocumentStatus.FAILED.value)
                self.assertEqual(row["translation_status"], "failed")

    def test_batch_translate_failure_persists_failed_not_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            batch_dir = root / "pdfs"
            batch_dir.mkdir()
            pdf = batch_dir / "doc.pdf"
            pdf.write_bytes(b"%PDF-lock-test")

            clear_settings_cache()
            settings = get_settings()
            settings.workspace = root
            settings.batch_dir = batch_dir
            settings.llm_api_key = "test"

            def fake_ocr(db, **kwargs):
                path = Path(kwargs["pdf_path"])
                artifact = root / "art"
                artifact.mkdir(exist_ok=True)
                doc_id = db.upsert_document(
                    source_path=str(path),
                    source_sha256="sha-doc",
                    display_name=path.name,
                    artifact_dir=str(artifact),
                    status=DocumentStatus.OCR_COMPLETE.value,
                    ocr_status="complete",
                )
                return {"document_id": doc_id, "artifact_dir": str(artifact)}

            def boom_translate(db, **kwargs):
                document_id = int(kwargs["document_id"])
                db.update_document_status(
                    document_id,
                    status=DocumentStatus.TRANSLATION_RUNNING.value,
                    translation_status="running",
                )
                raise RuntimeError("database is locked")

            def fake_plan(db, **kwargs):
                return {"ok": True}

            def fake_qa(db, **kwargs):
                return {"ok": True}

            result = run_batch(
                settings=settings,
                batch_dir=batch_dir,
                profile="conservative",
                continue_on_error=True,
                prevent_sleep=False,
                ocr_fn=fake_ocr,
                plan_fn=fake_plan,
                translate_fn=boom_translate,
                qa_fn=fake_qa,
            )
            self.assertEqual(result["failed"], 1)
            with Database(state_db_path(root)) as db:
                rows = db.fetchall("SELECT status, translation_status FROM documents")
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["status"], DocumentStatus.FAILED.value)
                self.assertEqual(rows[0]["translation_status"], "failed")
                self.assertNotEqual(
                    rows[0]["status"], DocumentStatus.TRANSLATION_RUNNING.value
                )


if __name__ == "__main__":
    unittest.main()
