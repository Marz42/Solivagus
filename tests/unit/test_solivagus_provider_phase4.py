from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from solivagus.cache.local import cache_path, load_translation, store_translation, translation_cache_key
from solivagus.config import clear_settings_cache, get_settings
from solivagus.database import Database
from solivagus.models import DocumentStatus, UnitStatus
from solivagus.pipeline.translate import run_translate_stage
from solivagus.pipeline.warmup import ProbeDecision, evaluate_probe
from solivagus.providers.prompts import (
    build_stable_prefix,
    build_unit_messages,
    extract_unit_translation,
)
from solivagus.providers.usage import UsageRecord
from solivagus.util.text import sha256_text
from solivagus.workspace import state_db_path, translation_cache_root


class UsageTests(unittest.TestCase):
    def test_usage_from_api_maps_cache_fields(self) -> None:
        record = UsageRecord.from_api(
            {
                "prompt_tokens": 1000,
                "prompt_cache_hit_tokens": 700,
                "prompt_cache_miss_tokens": 300,
                "completion_tokens": 50,
            }
        )
        self.assertEqual(record.cache_hit_tokens, 700)
        self.assertEqual(record.cache_miss_tokens, 300)


class ProbeTests(unittest.TestCase):
    def test_evaluate_probe_thresholds(self) -> None:
        self.assertEqual(
            evaluate_probe(hit_tokens=7000, expected_tokens=10000),
            ProbeDecision.FULL,
        )
        self.assertEqual(
            evaluate_probe(hit_tokens=6000, expected_tokens=10000),
            ProbeDecision.LOW,
        )
        self.assertEqual(
            evaluate_probe(hit_tokens=4000, expected_tokens=10000),
            ProbeDecision.DEGRADED,
        )


class PromptTests(unittest.TestCase):
    def test_build_unit_messages_repeat_includes_tail(self) -> None:
        system, user, _hash = build_stable_prefix(
            document_title="Doc",
            target_language="简体中文",
            units=[{"unit_key": "u00001", "source_text": "Hello world"}],
        )
        messages = build_unit_messages(
            stable_system=system,
            stable_user=user,
            warmup_assistant="PARTITION_READY_ACTUAL",
            unit_key="u00001",
            source_text="Hello world",
            target_mode="repeat",
        )
        self.assertEqual(len(messages), 4)
        self.assertEqual(messages[2]["content"], "PARTITION_READY_ACTUAL")
        self.assertIn('<translation-unit id="u00001">', messages[3]["content"])
        self.assertIn("Hello world", messages[3]["content"])

    def test_extract_unit_markers(self) -> None:
        raw = "<<<UNIT:u00001:BEGIN>>>\n你好\n<<<UNIT:u00001:END>>>"
        self.assertEqual(extract_unit_translation(raw, "u00001").strip(), "你好")


class LocalCacheTests(unittest.TestCase):
    def test_corrupt_cache_falls_through(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key = translation_cache_key(
                source_text="x",
                provider="openai-compatible",
                model="deepseek-v4-flash",
                prompt_version="translate-v1",
                target_language="简体中文",
            )
            path = cache_path(root, key)
            path.parent.mkdir(parents=True)
            path.write_text("{not-json", encoding="utf-8")
            self.assertIsNone(load_translation(root, key))


class PartitionTranslateTests(unittest.TestCase):
    def _seed_doc(self, db: Database, artifact: Path) -> int:
        doc_id = db.upsert_document(
            source_path=str(artifact.parent / "doc.pdf"),
            source_sha256="sha-phase4-doc",
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
                    "context_tokens": 0,
                    "unit_count": 2,
                    "user_id": "pdf_sha-phase4-doc"[:24],
                    "warmup_status": "pending",
                    "expected_cache_tokens": 1000,
                    "status": "pending",
                }
            ],
        )
        db.replace_units(
            doc_id,
            [
                {
                    "unit_key": "u00001",
                    "sequence_index": 1,
                    "partition_id": part_ids[0],
                    "source_text": "First unit text.",
                    "source_hash": sha256_text("First unit text."),
                    "source_tokens": 500,
                    "status": UnitStatus.PENDING.value,
                },
                {
                    "unit_key": "u00002",
                    "sequence_index": 2,
                    "partition_id": part_ids[0],
                    "source_text": "Second unit text.",
                    "source_hash": sha256_text("Second unit text."),
                    "source_tokens": 500,
                    "status": UnitStatus.PENDING.value,
                },
            ],
        )
        return doc_id

    def test_warmup_uses_assistant_content_not_literal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "doc.solivagus"
            artifact.mkdir()
            clear_settings_cache()
            settings = get_settings()
            settings.workspace = root
            settings.llm_api_key = "test"
            settings.retries = 1
            settings.cache_settle_seconds = 0
            settings.enable_local_translation_cache = False

            seen_assistants: list[str] = []

            def fake_chat(**kwargs):
                messages = kwargs.get("messages")
                if messages and len(messages) == 2:
                    return "WARMUP_ACTUAL_TEXT", "stop", {"prompt_tokens": 100, "completion_tokens": 2}
                if messages and len(messages) == 4:
                    seen_assistants.append(messages[2]["content"])
                    unit_key = "u00001" if "u00001" in messages[3]["content"] else "u00002"
                    hit = 800 if unit_key == "u00001" else 850
                    body = f"<<<UNIT:{unit_key}:BEGIN>>>\n译{unit_key}\n<<<UNIT:{unit_key}:END>>>"
                    return (
                        body,
                        "stop",
                        {
                            "prompt_tokens": 1200,
                            "prompt_cache_hit_tokens": hit,
                            "prompt_cache_miss_tokens": 400,
                            "completion_tokens": 20,
                        },
                    )
                return "你好", "stop", {"prompt_tokens": 1, "completion_tokens": 1}

            with Database(state_db_path(root)) as db:
                doc_id = self._seed_doc(db, artifact)
                result = run_translate_stage(
                    db, document_id=doc_id, settings=settings, chat_fn=fake_chat
                )
                self.assertEqual(result["mode"], "partition_cache")
                self.assertTrue(seen_assistants)
                self.assertTrue(all(a == "WARMUP_ACTUAL_TEXT" for a in seen_assistants))
                self.assertTrue((artifact / "usage-report.json").is_file())
                attempts = db.fetchall("SELECT * FROM translation_attempts")
                self.assertGreaterEqual(len(attempts), 1)
                part = db.list_partitions(doc_id)[0]
                self.assertEqual(part["actual_probe_hit_tokens"], 800)
                self.assertEqual(result["partitions"][0]["probe_decision"], "full")

    def test_local_cache_hit_skips_chat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "doc.solivagus"
            artifact.mkdir()
            clear_settings_cache()
            settings = get_settings()
            settings.workspace = root
            settings.llm_api_key = "test"
            settings.retries = 1
            settings.enable_local_translation_cache = True
            cache_root = translation_cache_root(root)
            cache_root.mkdir(parents=True, exist_ok=True)

            for text, key_name in (
                ("First unit text.", "u00001"),
                ("Second unit text.", "u00002"),
            ):
                from solivagus.style.capsule import empty_capsule

                key = translation_cache_key(
                    source_text=text,
                    provider="openai-compatible",
                    model=settings.llm_model,
                    prompt_version=settings.prompt_version,
                    target_language=settings.target_language,
                    style_capsule_hash=empty_capsule().content_hash(),
                    translation_parameters=f"target_mode={settings.target_mode}",
                )
                store_translation(
                    cache_root,
                    key,
                    {"translation_text": f"缓存-{key_name}\n", "unit_key": key_name},
                )

            calls = {"n": 0}

            def fake_chat(**kwargs):
                calls["n"] += 1
                messages = kwargs.get("messages")
                if messages and len(messages) == 2:
                    return "READY", "stop", {"prompt_tokens": 10, "completion_tokens": 1}
                raise AssertionError("unit translation should be served from local cache")

            with Database(state_db_path(root)) as db:
                doc_id = self._seed_doc(db, artifact)
                result = run_translate_stage(
                    db, document_id=doc_id, settings=settings, chat_fn=fake_chat
                )
                self.assertEqual(result["local_cache_hits"], 2)
                self.assertEqual(calls["n"], 1)  # warm-up only
                unit = db.list_units(doc_id)[0]
                self.assertIn("缓存", unit["translation_text"])

    def test_degraded_mode_still_completes(self) -> None:
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

            def fake_chat(**kwargs):
                messages = kwargs.get("messages")
                if messages and len(messages) == 2:
                    return "READY", "stop", {"prompt_tokens": 10, "completion_tokens": 1}
                if messages and len(messages) == 4:
                    unit_key = "u00001" if "u00001" in messages[3]["content"] else "u00002"
                    body = f"<<<UNIT:{unit_key}:BEGIN>>>\nKV{unit_key}\n<<<UNIT:{unit_key}:END>>>"
                    return (
                        body,
                        "stop",
                        {
                            "prompt_tokens": 1000,
                            "prompt_cache_hit_tokens": 0,
                            "prompt_cache_miss_tokens": 1000,
                            "completion_tokens": 10,
                        },
                    )
                # degraded flat path
                return "扁平译文", "stop", {"prompt_tokens": 20, "completion_tokens": 5}

            with Database(state_db_path(root)) as db:
                doc_id = self._seed_doc(db, artifact)
                result = run_translate_stage(
                    db, document_id=doc_id, settings=settings, chat_fn=fake_chat
                )
                self.assertEqual(result["partitions"][0]["probe_decision"], "degraded")
                doc = db.fetchone("SELECT * FROM documents WHERE id=?", (doc_id,))
                self.assertNotEqual(doc["status"], DocumentStatus.FAILED.value)
                self.assertTrue(str(doc["status"]).startswith("translation_complete"))
                self.assertTrue((artifact / "usage-report.json").is_file())
                report = json.loads((artifact / "usage-report.json").read_text(encoding="utf-8"))
                self.assertIn("totals", report)


if __name__ == "__main__":
    unittest.main()
