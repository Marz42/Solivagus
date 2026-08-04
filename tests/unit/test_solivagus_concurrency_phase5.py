from __future__ import annotations

import asyncio
import tempfile
import time
import unittest
from pathlib import Path

from solivagus.concurrency.limits import ConcurrencyGate, partition_limit_for_probe, ConcurrencyConfig
from solivagus.config import clear_settings_cache, get_settings
from solivagus.database import Database
from solivagus.models import DocumentStatus, UnitStatus
from solivagus.pipeline.translate import run_translate_stage
from solivagus.providers.async_openai import is_rate_limited_error
from solivagus.providers.openai_compatible import ProviderError
from solivagus.util.text import sha256_text
from solivagus.workspace import state_db_path


class GateTests(unittest.TestCase):
    def test_halve_on_429(self) -> None:
        async def _run() -> None:
            gate = ConcurrencyGate(8)
            await gate.record_rate_limit(adaptive=True)
            self.assertEqual(gate.limit, 4)
            await gate.record_rate_limit(adaptive=True)
            self.assertEqual(gate.limit, 2)

        asyncio.run(_run())

    def test_partition_limit_for_probe(self) -> None:
        cfg = ConcurrencyConfig(per_partition_limit=8, low_probe_limit=2)
        self.assertEqual(partition_limit_for_probe("full", cfg), 8)
        self.assertEqual(partition_limit_for_probe("low", cfg), 2)
        self.assertEqual(partition_limit_for_probe("degraded", cfg), 1)

    def test_is_rate_limited(self) -> None:
        self.assertTrue(is_rate_limited_error(ProviderError("HTTP 429: slow down")))
        self.assertTrue(is_rate_limited_error(ProviderError("insufficient_system_resource")))
        self.assertFalse(is_rate_limited_error(ProviderError("HTTP 400: bad")))


class ConcurrentTranslateTests(unittest.TestCase):
    def _seed(self, db: Database, artifact: Path, n_units: int = 5) -> int:
        doc_id = db.upsert_document(
            source_path=str(artifact.parent / "doc.pdf"),
            source_sha256="sha-phase5",
            display_name="doc.pdf",
            artifact_dir=str(artifact),
            status=DocumentStatus.PLANNING.value,
        )
        part_ids = db.replace_partitions(
            doc_id,
            [
                {
                    "sequence_index": 1,
                    "source_tokens": 1000,
                    "unit_count": n_units,
                    "user_id": "pdf_sha-phase5",
                    "warmup_status": "pending",
                    "expected_cache_tokens": 1000,
                    "status": "pending",
                }
            ],
        )
        units = []
        for i in range(1, n_units + 1):
            text = f"Unit body {i}."
            units.append(
                {
                    "unit_key": f"u{i:05d}",
                    "sequence_index": i,
                    "partition_id": part_ids[0],
                    "source_text": text,
                    "source_hash": sha256_text(text),
                    "source_tokens": 100,
                    "status": UnitStatus.PENDING.value,
                }
            )
        db.replace_units(doc_id, units)
        return doc_id

    def test_concurrent_faster_than_serial_wall_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "doc.solivagus"
            artifact.mkdir()
            clear_settings_cache()
            settings = get_settings()
            settings.workspace = root
            settings.llm_api_key = "test"
            settings.retries = 1
            settings.enable_local_translation_cache = False
            settings.per_partition_concurrency = 4
            settings.global_concurrency = 8
            settings.per_document_concurrency = 8
            settings.adaptive_concurrency = False

            def fake_chat(**kwargs):
                messages = kwargs.get("messages")
                if messages and len(messages) == 2:
                    return "READY", "stop", {"prompt_tokens": 10, "completion_tokens": 1}
                time.sleep(0.08)
                content = (messages or [{}])[-1].get("content", "") if messages else ""
                unit_key = "u00001"
                for i in range(1, 10):
                    key = f"u{i:05d}"
                    if key in content:
                        unit_key = key
                        break
                body = f"<<<UNIT:{unit_key}:BEGIN>>>\n译{unit_key}\n<<<UNIT:{unit_key}:END>>>"
                return (
                    body,
                    "stop",
                    {
                        "prompt_tokens": 1200,
                        "prompt_cache_hit_tokens": 900,
                        "prompt_cache_miss_tokens": 300,
                        "completion_tokens": 10,
                    },
                )

            with Database(state_db_path(root)) as db:
                doc_id = self._seed(db, artifact, n_units=5)
                started = time.perf_counter()
                result = run_translate_stage(
                    db, document_id=doc_id, settings=settings, chat_fn=fake_chat
                )
                elapsed = time.perf_counter() - started
                self.assertEqual(result["translated"], 5)
                self.assertEqual(result["partitions"][0]["probe_decision"], "full")
                # warm-up + probe (~0.08) + 4 concurrent (~0.08) ≈ 0.16–0.35s
                # serial would be warm-up + 5*0.08 ≈ 0.48s+
                self.assertLess(elapsed, 0.55)
                self.assertGreaterEqual(result["partitions"][0]["partition_concurrency"], 4)
                units = db.list_units(doc_id)
                self.assertEqual(len(units), 5)
                self.assertTrue(all(u["status"] == UnitStatus.DONE.value for u in units))
                # Assembly order follows sequence_index regardless of completion order.
                zh = (artifact / "translated.zh.md").read_text(encoding="utf-8")
                pos = [zh.index(f"译u{i:05d}") for i in range(1, 6)]
                self.assertEqual(pos, sorted(pos))

    def test_429_halves_gate_during_retries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "doc.solivagus"
            artifact.mkdir()
            clear_settings_cache()
            settings = get_settings()
            settings.workspace = root
            settings.llm_api_key = "test"
            settings.retries = 3
            settings.enable_local_translation_cache = False
            settings.per_partition_concurrency = 8
            settings.adaptive_concurrency = True

            state = {"calls": 0}

            def fake_chat(**kwargs):
                messages = kwargs.get("messages")
                if messages and len(messages) == 2:
                    return "READY", "stop", {"prompt_tokens": 10, "completion_tokens": 1}
                state["calls"] += 1
                # First unit probe succeeds with high hit; second unit hits 429 once.
                content = messages[-1]["content"] if messages else ""
                if "u00002" in content and state["calls"] <= 2:
                    raise ProviderError("HTTP 429: rate limit")
                unit_key = "u00002" if "u00002" in content else "u00001"
                body = f"<<<UNIT:{unit_key}:BEGIN>>>\nok\n<<<UNIT:{unit_key}:END>>>"
                return (
                    body,
                    "stop",
                    {
                        "prompt_tokens": 1000,
                        "prompt_cache_hit_tokens": 800,
                        "prompt_cache_miss_tokens": 200,
                        "completion_tokens": 5,
                    },
                )

            with Database(state_db_path(root)) as db:
                doc_id = self._seed(db, artifact, n_units=2)
                result = run_translate_stage(
                    db, document_id=doc_id, settings=settings, chat_fn=fake_chat
                )
                self.assertEqual(result["translated"], 2)
                self.assertNotEqual(
                    db.fetchone("SELECT status FROM documents WHERE id=?", (doc_id,))["status"],
                    DocumentStatus.FAILED.value,
                )


if __name__ == "__main__":
    unittest.main()
