from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from solivagus.assembly import assemble_outputs
from solivagus.config import clear_settings_cache, get_settings
from solivagus.database import Database
from solivagus.migrate.mvp import import_mvp_translation_dir
from solivagus.models import DocumentStatus, UnitStatus
from solivagus.pipeline.translate import run_translate_stage
from solivagus.util.markdown import (
    protect_markdown,
    restore_markdown,
    split_passthrough_segments,
)
from solivagus.util.text import sha256_text
from solivagus.workspace import state_db_path


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_QWEN = ROOT / "example" / "Qwen3_TTS.translation"
EXAMPLE_PDF = ROOT / "example" / "Qwen3_TTS.pdf"


class UtilPortTests(unittest.TestCase):
    def test_html_table_passthrough(self) -> None:
        html = "<table><tr><td>a</td></tr></table>\n\nHello.\n"
        segments = split_passthrough_segments(html)
        self.assertTrue(any(kind == "html_table" for kind, _ in segments))

    def test_protect_roundtrip(self) -> None:
        source = "eq $$a=1$$ and `code`"
        protected, placeholders = protect_markdown(source)
        self.assertIn("@@PRESERVE_", protected)
        self.assertEqual(restore_markdown(protected, placeholders), source)


class DatabaseTests(unittest.TestCase):
    def test_schema_and_upsert(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / ".solivagus" / "state.db"
            with Database(db_path) as db:
                doc_id = db.upsert_document(
                    source_path=str(Path(tmp) / "a.pdf"),
                    source_sha256="abc",
                    display_name="a.pdf",
                    artifact_dir=str(Path(tmp) / "a.solivagus"),
                    status=DocumentStatus.QUEUED.value,
                )
                self.assertGreater(doc_id, 0)
                db.replace_units(
                    doc_id,
                    [
                        {
                            "unit_key": "b00001",
                            "sequence_index": 1,
                            "source_text": "Hello",
                            "source_hash": sha256_text("Hello"),
                            "status": UnitStatus.PENDING.value,
                        }
                    ],
                )
                units = db.list_units(doc_id)
                self.assertEqual(len(units), 1)
                version = db.fetchone(
                    "SELECT value FROM schema_meta WHERE key='schema_version'"
                )
                self.assertEqual(version["value"], "1")


class TranslateStageTests(unittest.TestCase):
    def test_translate_stage_with_fake_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "doc.solivagus"
            artifact.mkdir()
            db_path = state_db_path(root)
            clear_settings_cache()
            settings = get_settings()
            settings.workspace = root
            settings.llm_api_key = "test-key"
            settings.retries = 1

            def fake_chat(**_kwargs):
                return "你好", "stop", {"prompt_tokens": 1, "completion_tokens": 1}

            with Database(db_path) as db:
                doc_id = db.upsert_document(
                    source_path=str(root / "doc.pdf"),
                    source_sha256="sha-doc",
                    display_name="doc.pdf",
                    artifact_dir=str(artifact),
                    status=DocumentStatus.OCR_COMPLETE.value,
                    ocr_status="complete",
                )
                db.replace_units(
                    doc_id,
                    [
                        {
                            "unit_key": "b00001",
                            "sequence_index": 1,
                            "source_text": "Hello world.",
                            "source_hash": sha256_text("Hello world."),
                            "status": UnitStatus.PENDING.value,
                        }
                    ],
                )
                result = run_translate_stage(
                    db,
                    document_id=doc_id,
                    settings=settings,
                    chat_fn=fake_chat,
                )
                self.assertEqual(result["translated"], 1)
                self.assertTrue((artifact / "translated.zh.md").is_file())
                unit = db.list_units(doc_id)[0]
                self.assertEqual(unit["status"], UnitStatus.DONE.value)
                self.assertIn("你好", unit["translation_text"])


@unittest.skipUnless(EXAMPLE_QWEN.is_dir(), "local Qwen MVP workspace missing")
class MvpImportTests(unittest.TestCase):
    def test_import_qwen_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with Database(state_db_path(root)) as db:
                pdf = EXAMPLE_PDF if EXAMPLE_PDF.is_file() else None
                result = import_mvp_translation_dir(
                    db,
                    translation_dir=EXAMPLE_QWEN,
                    pdf_path=pdf,
                )
                self.assertGreater(result["unit_count"], 0)
                doc = db.fetchone(
                    "SELECT * FROM documents WHERE id = ?",
                    (result["document_id"],),
                )
                self.assertIsNotNone(doc)
                units = db.list_units(int(doc["id"]))
                self.assertEqual(len(units), result["unit_count"])
                self.assertTrue(all(unit["status"] == "done" for unit in units))


class AssembleTests(unittest.TestCase):
    def test_assemble(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            assemble_outputs(
                work,
                [
                    {
                        "unit_key": "b00001",
                        "source_text": "Hello",
                        "translation_text": "你好",
                    }
                ],
                document_title="Demo",
                pdf_name="demo.pdf",
                model="deepseek-v4-flash",
            )
            self.assertIn("你好", (work / "translated.zh.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
