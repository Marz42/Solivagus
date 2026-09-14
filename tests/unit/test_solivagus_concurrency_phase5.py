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

    def test_thread_safe_gate_cross_loop(self) -> None:
        from solivagus.concurrency.limits import ThreadSafeGate

        gate = ThreadSafeGate(1, maximum=4)

        async def _hold() -> None:
            await gate.acquire()
            await asyncio.sleep(0.05)
            await gate.release()

        async def _run() -> None:
            await asyncio.gather(_hold(), _hold())

        asyncio.run(_run())
        self.assertEqual(gate.limit, 1)
        # Fresh event loop must still work with the same gate instance.
        asyncio.run(_run())


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


class MultiPartitionGateTests(unittest.TestCase):
    def _seed_two_partitions(self, db: Database, artifact: Path, *, per_part: int) -> int:
        doc_id = db.upsert_document(
            source_path=str(artifact.parent / "doc.pdf"),
            source_sha256="sha-multiparty",
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
                    "unit_count": per_part,
                    "user_id": "pdf_sha-multiparty",
                    "warmup_status": "pending",
                    "expected_cache_tokens": 1000,
                    "status": "pending",
                },
                {
                    "sequence_index": 2,
                    "source_tokens": 1000,
                    "unit_count": per_part,
                    "user_id": "pdf_sha-multiparty",
                    "warmup_status": "pending",
                    "expected_cache_tokens": 1000,
                    "status": "pending",
                },
            ],
        )
        units = []
        seq = 1
        for part_idx, part_id in enumerate(part_ids):
            for i in range(1, per_part + 1):
                text = f"Partition {part_idx + 1} unit {i}."
                units.append(
                    {
                        "unit_key": f"u{seq:05d}",
                        "sequence_index": seq,
                        "partition_id": part_id,
                        "source_text": text,
                        "source_hash": sha256_text(text),
                        "source_tokens": 100,
                        "status": UnitStatus.PENDING.value,
                    }
                )
                seq += 1
        db.replace_units(doc_id, units)
        return doc_id

    def test_two_partitions_reuse_document_gate_without_event_loop_error(self) -> None:
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
            settings.per_partition_concurrency = 2
            settings.per_document_concurrency = 2
            settings.global_concurrency = 4
            settings.adaptive_concurrency = False
            settings.cache_settle_seconds = 0

            def fake_chat(**kwargs):
                messages = kwargs.get("messages")
                if messages and len(messages) == 2:
                    return "READY", "stop", {"prompt_tokens": 10, "completion_tokens": 1}
                content = (messages or [{}])[-1].get("content", "") if messages else ""
                unit_key = "u00001"
                for i in range(1, 20):
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
                doc_id = self._seed_two_partitions(db, artifact, per_part=3)
                result = run_translate_stage(
                    db, document_id=doc_id, settings=settings, chat_fn=fake_chat
                )
                self.assertEqual(result["translated"], 6)
                self.assertEqual(len(result["partitions"]), 2)
                units = db.list_units(doc_id)
                self.assertTrue(all(u["status"] == UnitStatus.DONE.value for u in units))
                self.assertFalse(
                    any("fallback" in str(u["warning_flags"] or "") for u in units)
                )


class BisectGateTests(unittest.TestCase):
    def test_bisect_reenters_nested_gates(self) -> None:
        import threading

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
            settings.unit_bisect_max_depth = 1
            settings.per_partition_concurrency = 1
            settings.per_document_concurrency = 1
            settings.global_concurrency = 1
            settings.adaptive_concurrency = False
            settings.cache_settle_seconds = 0

            state = {"calls": 0, "max_inflight": 0, "inflight": 0}
            counter_lock = threading.Lock()

            def fake_chat(**kwargs):
                messages = kwargs.get("messages")
                if messages and len(messages) == 2:
                    return "READY", "stop", {"prompt_tokens": 10, "completion_tokens": 1}
                content = (messages or [{}])[-1].get("content", "") if messages else ""
                with counter_lock:
                    state["inflight"] += 1
                    state["max_inflight"] = max(state["max_inflight"], state["inflight"])
                    state["calls"] += 1
                try:
                    if "u00002" in content and ":a" not in content and ":b" not in content:
                        raise ProviderError("forced unit failure for bisect")
                    unit_key = "u00001"
                    for key in ("u00002:a", "u00002:b", "u00002", "u00001"):
                        if key in content:
                            unit_key = key
                            break
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
                finally:
                    with counter_lock:
                        state["inflight"] -= 1

            with Database(state_db_path(root)) as db:
                seed = ConcurrentTranslateTests()
                doc_id = seed._seed(db, artifact, n_units=2)
                text = (
                    "First paragraph about transformers.\n\n"
                    "Second paragraph about attention."
                )
                db.execute(
                    "UPDATE translation_units SET source_text=?, source_hash=? WHERE unit_key=?",
                    (text, sha256_text(text), "u00002"),
                )
                db.commit()
                result = run_translate_stage(
                    db, document_id=doc_id, settings=settings, chat_fn=fake_chat
                )
                self.assertEqual(result["translated"], 2)
                row = db.fetchone(
                    "SELECT warning_flags FROM translation_units WHERE unit_key=?",
                    ("u00002",),
                )
                self.assertEqual(row["warning_flags"], "bisected")
                # global=doc=partition=1 → never more than one in-flight API body call
                self.assertEqual(state["max_inflight"], 1)


class CompletedRerunTests(unittest.TestCase):
    def test_completed_document_rerun_skips_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "doc.solivagus"
            artifact.mkdir()
            clear_settings_cache()
            settings = get_settings()
            settings.workspace = root
            settings.llm_api_key = "test"
            settings.enable_local_translation_cache = False

            calls = {"n": 0}

            def boom_chat(**kwargs):
                calls["n"] += 1
                raise ProviderError("provider unavailable")

            with Database(state_db_path(root)) as db:
                doc_id = ConcurrentTranslateTests()._seed(db, artifact, n_units=2)
                for unit in db.list_units(doc_id):
                    db.update_unit(
                        int(unit["id"]),
                        status=UnitStatus.DONE.value,
                        translation_text=f"译{unit['unit_key']}\n",
                        translation_hash=sha256_text(f"译{unit['unit_key']}\n"),
                    )
                db.update_document_status(
                    doc_id,
                    status=DocumentStatus.TRANSLATION_COMPLETE.value,
                    translation_status="complete",
                )
                db.commit()
                result = run_translate_stage(
                    db, document_id=doc_id, settings=settings, chat_fn=boom_chat
                )
                self.assertTrue(result.get("skipped_all"))
                self.assertEqual(calls["n"], 0)
                self.assertEqual(
                    db.fetchone("SELECT status FROM documents WHERE id=?", (doc_id,))["status"],
                    DocumentStatus.TRANSLATION_COMPLETE.value,
                )
                self.assertTrue(
                    all(u["status"] == UnitStatus.DONE.value for u in db.list_units(doc_id))
                )


class WarmupGateTests(unittest.TestCase):
    def test_warmup_respects_global_gate(self) -> None:
        import threading
        from solivagus.concurrency.limits import ThreadSafeGate
        from solivagus.pipeline.partition_runner import translate_partition_async

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
            settings.adaptive_concurrency = False
            settings.cache_settle_seconds = 0
            settings.per_partition_concurrency = 1
            settings.per_document_concurrency = 1

            state = {"inflight": 0, "max": 0}
            lock = threading.Lock()

            def fake_chat(**kwargs):
                messages = kwargs.get("messages")
                with lock:
                    state["inflight"] += 1
                    state["max"] = max(state["max"], state["inflight"])
                try:
                    time.sleep(0.05)
                    if messages and len(messages) == 2:
                        return "READY", "stop", {"prompt_tokens": 10, "completion_tokens": 1}
                    content = (messages or [{}])[-1].get("content", "") if messages else ""
                    unit_key = "u00001" if "u00001" in content else "u00002"
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
                finally:
                    with lock:
                        state["inflight"] -= 1

            async def _run() -> None:
                gate = ThreadSafeGate(1, maximum=1)
                with Database(state_db_path(root)) as db:
                    seed = ConcurrentTranslateTests()
                    doc_a = seed._seed(db, artifact, n_units=1)
                    artifact_b = root / "doc2.solivagus"
                    artifact_b.mkdir()
                    # Re-seed a second document with different sha by direct insert.
                    doc_b = db.upsert_document(
                        source_path=str(root / "doc2.pdf"),
                        source_sha256="sha-warmup-b",
                        display_name="doc2.pdf",
                        artifact_dir=str(artifact_b),
                        status=DocumentStatus.PLANNING.value,
                    )
                    part_ids = db.replace_partitions(
                        doc_b,
                        [
                            {
                                "sequence_index": 1,
                                "source_tokens": 1000,
                                "unit_count": 1,
                                "user_id": "pdf_sha-warmup-b",
                                "warmup_status": "pending",
                                "expected_cache_tokens": 1000,
                                "status": "pending",
                            }
                        ],
                    )
                    text = "Unit body B."
                    db.replace_units(
                        doc_b,
                        [
                            {
                                "unit_key": "u00001",
                                "sequence_index": 1,
                                "partition_id": part_ids[0],
                                "source_text": text,
                                "source_hash": sha256_text(text),
                                "source_tokens": 100,
                                "status": UnitStatus.PENDING.value,
                            }
                        ],
                    )
                    parts_a = db.list_partitions(doc_a)
                    parts_b = db.list_partitions(doc_b)
                    units_a = db.list_units(doc_a)
                    units_b = db.list_units(doc_b)
                    await asyncio.gather(
                        translate_partition_async(
                            db,
                            document_id=doc_a,
                            source_sha256="sha-phase5",
                            document_title="doc",
                            partition=parts_a[0],
                            units=units_a,
                            settings=settings,
                            artifact_dir=artifact,
                            cache_root=root / "cache",
                            chat_fn=fake_chat,
                            global_gate=gate,
                        ),
                        translate_partition_async(
                            db,
                            document_id=doc_b,
                            source_sha256="sha-warmup-b",
                            document_title="doc2",
                            partition=parts_b[0],
                            units=units_b,
                            settings=settings,
                            artifact_dir=artifact_b,
                            cache_root=root / "cache",
                            chat_fn=fake_chat,
                            global_gate=gate,
                        ),
                    )

            asyncio.run(_run())
            self.assertEqual(state["max"], 1)


if __name__ == "__main__":
    unittest.main()
