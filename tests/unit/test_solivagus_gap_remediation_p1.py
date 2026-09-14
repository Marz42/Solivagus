"""ADR-002 remaining: calibration, inspect-data, concurrency caps/Retry-After."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from solivagus.concurrency.limits import ConcurrencyGate
from solivagus.config import clear_settings_cache, get_settings
from solivagus.database import Database
from solivagus.models import DocumentStatus, UnitStatus
from solivagus.pipeline.inspect_data import (
    build_inspect_data_report,
    format_inspect_data_report,
)
from solivagus.planning.calibration import (
    OutputCalibration,
    load_calibration,
    save_calibration,
)
from solivagus.planning.unit_builder import build_translation_units
from solivagus.providers.async_openai import backoff_sleep
from solivagus.providers.openai_compatible import ProviderError, parse_retry_after
from solivagus.structure.models import NodeType, StructuralNode
from solivagus.util.text import sha256_text
from solivagus.workspace import state_db_path


class CalibrationTests(unittest.TestCase):
    def test_default_estimate_before_samples(self) -> None:
        cal = OutputCalibration()
        est = cal.estimate_output_tokens(1000)
        self.assertEqual(est, int(1000 * 1.3) + 512)

    def test_rolling_p90_after_five_samples(self) -> None:
        cal = OutputCalibration()
        for ratio in (1.0, 1.1, 1.2, 1.5, 2.0):
            cal.record(source_tokens=1000, completion_tokens=int(ratio * 1000))
        self.assertIsNotNone(cal.rolling_p90())
        est = cal.estimate_output_tokens(1000)
        # Uses p90 * 1.2 safety, not the raw 1.3+512 default.
        self.assertNotEqual(est, int(1000 * 1.3) + 512)
        self.assertGreater(est, 1000)

    def test_persist_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cal = OutputCalibration()
            for _ in range(5):
                cal.record(source_tokens=500, completion_tokens=800)
            save_calibration(root, cal)
            loaded = load_calibration(root)
            self.assertEqual(loaded.sample_count, 5)
            self.assertAlmostEqual(loaded.rolling_p90() or 0, cal.rolling_p90() or 0)

    def test_concurrent_record_keeps_all_samples(self) -> None:
        from concurrent.futures import ThreadPoolExecutor

        from solivagus.planning.calibration import record_calibration_sample

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def _one(_: int) -> None:
                record_calibration_sample(
                    root,
                    source_tokens=100,
                    completion_tokens=130,
                    model="m",
                    target_language="zh",
                    tokenizer_mode="approximate",
                )

            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(_one, range(8)))
            loaded = load_calibration(root)
            loaded.use_bucket("m|zh|approximate")
            self.assertEqual(loaded.sample_count, 8)

    def test_unit_builder_uses_estimate_fn(self) -> None:
        nodes = [
            StructuralNode(
                node_type=NodeType.PARAGRAPH,
                sequence_index=1,
                source_text="Hello world " * 40 + "\n",
                source_hash="a",
                token_count=50,
                heading_path="",
                temp_id="n1",
            )
        ]
        units = build_translation_units(
            nodes, count_fn=lambda t: 50, estimate_output_fn=lambda n: n * 2
        )
        self.assertEqual(units[0].estimated_output_tokens, 100)


class InspectDataTests(unittest.TestCase):
    def test_report_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "doc.solivagus"
            artifact.mkdir()
            clear_settings_cache()
            settings = get_settings()
            settings.workspace = root
            with Database(state_db_path(root)) as db:
                doc_id = db.upsert_document(
                    source_path=str(root / "doc.pdf"),
                    source_sha256="sha-inspect",
                    display_name="doc.pdf",
                    artifact_dir=str(artifact),
                    status=DocumentStatus.OCR_COMPLETE.value,
                )
                text = "Attention is all you need.\n"
                db.replace_units(
                    doc_id,
                    [
                        {
                            "unit_key": "u00001",
                            "sequence_index": 1,
                            "source_text": text,
                            "source_hash": sha256_text(text),
                            "source_tokens": 10,
                            "status": UnitStatus.PENDING.value,
                        }
                    ],
                )
                report = build_inspect_data_report(
                    db, document_id=doc_id, settings=settings, sample_limit=3
                )
            self.assertFalse(report.uploads_pdf)
            self.assertTrue(report.sends_ocr_text_only)
            self.assertEqual(report.unit_count, 1)
            self.assertTrue(report.user_id.startswith("pdf_"))
            self.assertEqual(len(report.partitions), 1)
            text = format_inspect_data_report(report)
            self.assertIn("sends_ocr_text_only", text)
            self.assertIn("u00001", text)

    def test_sample_zero_does_not_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "doc.solivagus"
            artifact.mkdir()
            clear_settings_cache()
            settings = get_settings()
            settings.workspace = root
            with Database(state_db_path(root)) as db:
                doc_id = db.upsert_document(
                    source_path=str(root / "doc.pdf"),
                    source_sha256="sha-inspect-0",
                    display_name="doc.pdf",
                    artifact_dir=str(artifact),
                    status=DocumentStatus.OCR_COMPLETE.value,
                )
                text = "Hello.\n"
                db.replace_units(
                    doc_id,
                    [
                        {
                            "unit_key": "u00001",
                            "sequence_index": 1,
                            "source_text": text,
                            "source_hash": sha256_text(text),
                            "source_tokens": 2,
                            "status": UnitStatus.PENDING.value,
                        }
                    ],
                )
                report = build_inspect_data_report(
                    db, document_id=doc_id, settings=settings, sample_limit=0
                )
            self.assertEqual(report.sample_units, [])
            self.assertEqual(len(report.partitions), 1)
            format_inspect_data_report(report)

class ConcurrencyAndRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_bump_respects_maximum(self) -> None:
        gate = ConcurrencyGate(2, maximum=4)
        for _ in range(30):
            await gate.record_success(adaptive=True, bump_every=30)
        # One bump of +2 from 2 → 4, capped.
        for _ in range(30):
            await gate.record_success(adaptive=True, bump_every=30)
        self.assertEqual(gate.limit, 4)

    async def test_503_reduces_by_quarter(self) -> None:
        gate = ConcurrencyGate(8, maximum=64)
        await gate.record_rate_limit(adaptive=True, kind="503")
        self.assertEqual(gate.limit, 6)

    async def test_429_halves(self) -> None:
        gate = ConcurrencyGate(8, maximum=64)
        await gate.record_rate_limit(adaptive=True, kind="429")
        self.assertEqual(gate.limit, 4)

    def test_parse_retry_after(self) -> None:
        self.assertEqual(parse_retry_after("2"), 2.0)
        self.assertIsNone(parse_retry_after("Wed, 01 Jan 2020 00:00:00 GMT"))

    async def test_backoff_prefers_retry_after(self) -> None:
        exc = ProviderError("HTTP 429", retry_after=0.01)
        started = asyncio.get_event_loop().time()
        await backoff_sleep(1, exc)
        elapsed = asyncio.get_event_loop().time() - started
        self.assertGreaterEqual(elapsed, 0.01)


if __name__ == "__main__":
    unittest.main()
