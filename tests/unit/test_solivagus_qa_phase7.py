"""Phase 7 mechanical QA, repair, HTML tables, references."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from solivagus.config import clear_settings_cache, get_settings
from solivagus.database import Database
from solivagus.models import DocumentStatus, UnitStatus
from solivagus.qa.checks import check_unit
from solivagus.qa.models import QAFinding, QAReportSummary, Severity
from solivagus.qa.repair import build_repair_prompt
from solivagus.qa.report import write_qa_report
from solivagus.qa.runner import run_qa_stage
from solivagus.structure.html_tables import (
    extract_cell_texts,
    refill_table_cells,
    translate_html_table,
)
from solivagus.structure.references import apply_references_mode
from solivagus.util.text import sha256_text
from solivagus.workspace import state_db_path


class MechanicalCheckTests(unittest.TestCase):
    def test_html_table_must_not_mutate(self) -> None:
        table = "<table><tr><td>0.05</td><td>A</td></tr></table>"
        result = check_unit(
            unit_key="u1",
            source_text=f"See data:\n{table}\n",
            translation_text="见数据：\n<table><tr><td>0.5</td><td>A</td></tr></table>\n",
        )
        codes = {f.code for f in result.findings}
        self.assertIn("html_table_mutated", codes)
        self.assertEqual(result.status, "fail")

    def test_html_table_passthrough_passes(self) -> None:
        table = "<table><tr><td>0.05</td></tr></table>"
        result = check_unit(
            unit_key="u1",
            source_text=table,
            translation_text=table,
        )
        self.assertEqual(result.status, "pass")
        self.assertEqual(result.html_tables_kept, 1)

    def test_number_and_citation_mismatch(self) -> None:
        result = check_unit(
            unit_key="u2",
            source_text="We use 0.05 and cite [12] in Fig. 3.",
            translation_text="我们使用 0.5，并引用图 3。",
        )
        codes = {f.code for f in result.findings}
        self.assertIn("number_mismatch", codes)
        self.assertIn("citation_mismatch", codes)
        self.assertEqual(result.status, "warn")

    def test_fallback_is_high_and_unit_local(self) -> None:
        result = check_unit(
            unit_key="p002-u010",
            source_text="English",
            translation_text="English",
            unit_status="fallback",
            warning_flags="fallback",
        )
        self.assertEqual(result.status, "fallback")
        self.assertEqual(result.unit_key, "p002-u010")
        self.assertTrue(result.high_count)

    def test_length_ratio_flags_truncation_like_output(self) -> None:
        result = check_unit(
            unit_key="u3",
            source_text="A" * 200,
            translation_text="短",
        )
        self.assertTrue(any(f.code == "length_ratio" for f in result.findings))
        self.assertNotEqual(result.status, "pass")


class ReportAndRepairTests(unittest.TestCase):
    def test_write_qa_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = QAReportSummary(
                unit_count=2,
                passed=1,
                repaired=1,
                html_tables_kept=2,
            )
            finding = QAFinding(
                code="number_mismatch",
                message="数字不一致",
                detail="0.05",
                repaired=True,
            )
            from solivagus.qa.models import UnitQAResult

            summary.units.append(
                UnitQAResult(
                    unit_key="p002-u007",
                    status="repaired",
                    findings=[finding],
                )
            )
            path = write_qa_report(Path(tmp), summary)
            text = path.read_text(encoding="utf-8")
            self.assertIn("# 翻译质量报告", text)
            self.assertIn("p002-u007", text)
            self.assertIn("数字不一致", text)
            self.assertIn("已修复", text)

    def test_build_repair_prompt_lists_errors(self) -> None:
        prompt = build_repair_prompt(
            source="x=0.05",
            translation="x=0.5",
            findings=[
                QAFinding(
                    code="number_mismatch",
                    message="数字不一致",
                    detail="0.05",
                    severity=Severity.MEDIUM,
                )
            ],
            unit_key="u1",
        )
        self.assertIn("只修复列出的问题", prompt)
        self.assertIn("数字不一致", prompt)
        self.assertIn("0.05", prompt)


class HtmlTableAndReferencesTests(unittest.TestCase):
    def test_refill_preserves_tags_and_attrs(self) -> None:
        html = '<table class="t"><tr><th id="a">Name</th><td data-x="1">Value</td></tr></table>'
        cells = extract_cell_texts(html)
        self.assertEqual(cells, ["Name", "Value"])
        out = refill_table_cells(html, ["名称", "取值"])
        self.assertIn('class="t"', out)
        self.assertIn('id="a"', out)
        self.assertIn('data-x="1"', out)
        self.assertIn(">名称</th>", out)
        self.assertIn(">取值</td>", out)
        self.assertEqual(extract_cell_texts(out), ["名称", "取值"])

    def test_translate_keep_mode_unchanged(self) -> None:
        html = "<table><tr><td>Hello</td></tr></table>"
        self.assertEqual(translate_html_table(html, mode="keep"), html)

    def test_translate_cells_via_json(self) -> None:
        html = "<table><tr><td>Hello</td><td>World</td></tr></table>"

        def fake_chat(**kwargs):
            return json.dumps(["你好", "世界"], ensure_ascii=False), "stop", {}

        out = translate_html_table(
            html, mode="translate_cells", chat_fn=fake_chat, model="m"
        )
        self.assertEqual(extract_cell_texts(out), ["你好", "世界"])
        self.assertIn("<table>", out)

    def test_translate_cells_rejects_non_stop(self) -> None:
        html = "<table><tr><td>Hello</td></tr></table>"

        def fake_chat(**kwargs):
            return '["你好"]', "length", {}

        with self.assertRaises(Exception):
            translate_html_table(html, mode="translate_cells", chat_fn=fake_chat)

    def test_references_keep_translates_heading_only(self) -> None:
        md = "# References\n\n[1] Smith, J. DOI: 10.1000/xyz\n"
        out = apply_references_mode(md, "keep")
        self.assertIn("# 参考文献", out)
        self.assertIn("[1] Smith, J. DOI: 10.1000/xyz", out)


class QAStageIntegrationTests(unittest.TestCase):
    def _seed(self, db: Database, artifact: Path, units: list[dict]) -> int:
        doc_id = db.upsert_document(
            source_path=str(artifact.parent / "doc.pdf"),
            source_sha256="sha-phase7",
            display_name="doc.pdf",
            artifact_dir=str(artifact),
            status=DocumentStatus.TRANSLATION_COMPLETE.value,
            translation_status="complete",
        )
        payload = []
        for i, u in enumerate(units, start=1):
            src = u["source_text"]
            payload.append(
                {
                    "unit_key": u["unit_key"],
                    "sequence_index": i,
                    "source_text": src,
                    "source_hash": sha256_text(src),
                    "source_tokens": 100,
                    "status": u.get("status", UnitStatus.DONE.value),
                    "translation_text": u.get("translation_text", src),
                    "translation_hash": sha256_text(u.get("translation_text", src)),
                    "warning_flags": u.get("warning_flags"),
                }
            )
        db.replace_units(doc_id, payload)
        return doc_id

    def test_runner_repairs_and_writes_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "doc.solivagus"
            artifact.mkdir()
            clear_settings_cache()
            settings = get_settings()
            settings.workspace = root
            settings.qa_auto_repair = True
            settings.qa_max_repair_attempts = 1
            settings.qa_strict = False
            settings.llm_api_key = "test"

            calls: list[str] = []

            table = "<table><tr><td>ok</td></tr></table>"

            def fake_chat(**kwargs):
                calls.append(kwargs.get("user_prompt") or "")
                # Fix the number; keep HTML table intact.
                return f"结果为 0.05。\n{table}\n", "stop", {}

            with Database(state_db_path(root)) as db:
                doc_id = self._seed(
                    db,
                    artifact,
                    [
                        {
                            "unit_key": "u1",
                            "source_text": f"Value is 0.05.\n{table}\n",
                            "translation_text": f"结果为 0.5。\n{table}\n",
                        },
                        {
                            "unit_key": "u2",
                            "source_text": "Plain paragraph about attention.",
                            "translation_text": "关于注意力的普通段落。",
                        },
                    ],
                )
                result = run_qa_stage(
                    db, document_id=doc_id, settings=settings, chat_fn=fake_chat
                )
                self.assertFalse(result["skipped"])
                self.assertEqual(result["status"], DocumentStatus.QA_COMPLETE.value)
                self.assertGreaterEqual(result["repaired"], 1)
                self.assertGreaterEqual(result["html_tables_kept"], 1)
                self.assertTrue(Path(result["qa_report"]).is_file())
                self.assertTrue(calls)
                row = db.fetchone("SELECT qa_status, status FROM documents WHERE id = ?", (doc_id,))
                self.assertEqual(row["status"], DocumentStatus.QA_COMPLETE.value)
                self.assertIn(row["qa_status"], {"pass", "warnings"})
                unit = db.fetchone(
                    "SELECT translation_text, warning_flags FROM translation_units WHERE unit_key = ?",
                    ("u1",),
                )
                self.assertIn("0.05", unit["translation_text"])
                self.assertEqual(unit["warning_flags"], "qa_repaired")

    def test_errors_are_unit_localizable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "doc.solivagus"
            artifact.mkdir()
            clear_settings_cache()
            settings = get_settings()
            settings.workspace = root
            settings.qa_auto_repair = False
            settings.llm_api_key = "test"

            with Database(state_db_path(root)) as db:
                doc_id = self._seed(
                    db,
                    artifact,
                    [
                        {
                            "unit_key": "bad-unit",
                            "source_text": "x",
                            "translation_text": "x",
                            "status": UnitStatus.FALLBACK.value,
                            "warning_flags": "fallback",
                        }
                    ],
                )
                result = run_qa_stage(db, document_id=doc_id, settings=settings)
                report = Path(result["qa_report"]).read_text(encoding="utf-8")
                self.assertIn("bad-unit", report)
                self.assertIn("英文原文", report)


if __name__ == "__main__":
    unittest.main()
