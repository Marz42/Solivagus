from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from solivagus.cache.local import translation_cache_key
from solivagus.config import clear_settings_cache, get_settings
from solivagus.database import Database
from solivagus.models import DocumentStatus, UnitStatus
from solivagus.pipeline.translate import run_translate_stage
from solivagus.providers.prompts import build_stable_prefix
from solivagus.style.capsule import (
    StyleCapsule,
    build_next_capsule,
    empty_capsule,
    extract_boundary_context,
    provisional_from_seed,
    select_seed_unit,
)
from solivagus.util.text import sha256_text
from solivagus.workspace import state_db_path


class CapsuleUnitTests(unittest.TestCase):
    def test_empty_capsule_hash_stable(self) -> None:
        a = empty_capsule()
        b = empty_capsule()
        self.assertEqual(a.content_hash(), b.content_hash())

    def test_to_prompt_text_includes_sections(self) -> None:
        capsule = StyleCapsule(
            version=1,
            terminology={"affordance": "示能"},
            examples=[{"source": "Hello", "translation": "你好"}],
            boundary_context={"source_tail": "prev", "translation_tail": "前"},
        )
        text = capsule.to_prompt_text()
        self.assertIn("style_rules:", text)
        self.assertIn("affordance: 示能", text)
        self.assertIn("representative_examples:", text)
        self.assertIn("boundary_context:", text)

    def test_build_stable_prefix_hash_changes_with_capsule(self) -> None:
        units = [{"unit_key": "u00001", "source_text": "Hello"}]
        _, _, h1 = build_stable_prefix(
            document_title="Doc",
            target_language="简体中文",
            units=units,
            style_capsule=empty_capsule().to_prompt_text(),
        )
        _, _, h2 = build_stable_prefix(
            document_title="Doc",
            target_language="简体中文",
            units=units,
            style_capsule=StyleCapsule(version=1, terminology={"a": "甲"}).to_prompt_text(),
        )
        self.assertNotEqual(h1, h2)

    def test_translation_cache_key_includes_capsule_hash(self) -> None:
        k1 = translation_cache_key(
            source_text="x",
            provider="openai-compatible",
            model="deepseek-v4-flash",
            prompt_version="translate-v1",
            target_language="简体中文",
            style_capsule_hash="aaa",
        )
        k2 = translation_cache_key(
            source_text="x",
            provider="openai-compatible",
            model="deepseek-v4-flash",
            prompt_version="translate-v1",
            target_language="简体中文",
            style_capsule_hash="bbb",
        )
        self.assertNotEqual(k1, k2)

    def test_select_seed_unit_skips_table_like(self) -> None:
        units = [
            {"unit_key": "u1", "source_text": "<table><tr><td>a</td></tr></table>", "source_tokens": 4000},
            {
                "unit_key": "u2",
                "source_text": "This is a normal technical paragraph about transformers and attention. " * 40,
                "source_tokens": 3500,
            },
        ]
        seed = select_seed_unit(units)
        self.assertIsNotNone(seed)
        self.assertEqual(seed["unit_key"], "u2")

    def test_build_next_capsule_increments_version(self) -> None:
        prev = empty_capsule()
        assembled = [
            {
                "source_text": "We study affordance (affordance) in UI.",
                "translation_text": "我们研究界面中的示能（affordance）。",
            },
            {
                "source_text": "Second unit text for boundary.",
                "translation_text": "用于边界的第二段译文。",
            },
        ]
        nxt = build_next_capsule(prev, assembled)
        self.assertEqual(nxt.version, 1)
        self.assertFalse(nxt.provisional)
        self.assertLessEqual(len(nxt.examples), 4)
        self.assertIn("affordance", nxt.terminology)
        boundary = extract_boundary_context(assembled)
        self.assertIn("Second unit", boundary["source_tail"])

    def test_provisional_from_seed(self) -> None:
        base = empty_capsule()
        prov = provisional_from_seed(base, source_text="Src", translation_text="译")
        self.assertTrue(prov.provisional)
        self.assertEqual(prov.version, 0)
        self.assertEqual(prov.examples[0]["source"], "Src")
        self.assertNotEqual(prov.content_hash(), base.content_hash())


class CapsuleIntegrationTests(unittest.TestCase):
    def _seed_two_partitions(self, db: Database, artifact: Path) -> int:
        doc_id = db.upsert_document(
            source_path=str(artifact.parent / "doc.pdf"),
            source_sha256="sha-phase6",
            display_name="doc.pdf",
            artifact_dir=str(artifact),
            status=DocumentStatus.PLANNING.value,
        )
        part_ids = db.replace_partitions(
            doc_id,
            [
                {
                    "sequence_index": 1,
                    "source_tokens": 800,
                    "unit_count": 2,
                    "user_id": "pdf_sha-phase6",
                    "warmup_status": "pending",
                    "expected_cache_tokens": 800,
                    "status": "pending",
                },
                {
                    "sequence_index": 2,
                    "source_tokens": 800,
                    "unit_count": 2,
                    "user_id": "pdf_sha-phase6",
                    "warmup_status": "pending",
                    "expected_cache_tokens": 800,
                    "status": "pending",
                },
            ],
        )
        units = []
        for part_idx, part_id in enumerate(part_ids, start=1):
            for i in range(1, 3):
                key = f"p{part_idx}u{i}"
                text = (
                    f"Partition {part_idx} unit {i} discusses progressive disclosure "
                    f"and agentic workflow in technical systems. " * 20
                )
                units.append(
                    {
                        "unit_key": key,
                        "sequence_index": (part_idx - 1) * 2 + i,
                        "partition_id": part_id,
                        "source_text": text,
                        "source_hash": sha256_text(text),
                        "source_tokens": 600,
                        "status": UnitStatus.PENDING.value,
                    }
                )
        db.replace_units(doc_id, units)
        return doc_id

    def test_partition1_provisional_rewarmup_and_handoff(self) -> None:
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
            settings.adaptive_concurrency = False

            warmups: list[str] = []
            capsule_seen: list[str] = []

            def fake_chat(**kwargs):
                messages = kwargs.get("messages")
                if messages and len(messages) == 2:
                    warmups.append(messages[1]["content"])
                    return "READY", "stop", {"prompt_tokens": 10, "completion_tokens": 1}
                content = messages[-1]["content"] if messages else ""
                # Capture style capsule text from stable user (message[1]).
                if messages and len(messages) >= 2:
                    capsule_seen.append(messages[1]["content"])
                unit_key = "p1u1"
                for key in ("p1u1", "p1u2", "p2u1", "p2u2"):
                    if key in content:
                        unit_key = key
                        break
                body = (
                    f"<<<UNIT:{unit_key}:BEGIN>>>\n"
                    f"译文含示能（affordance）与渐进式披露（progressive disclosure）。\n"
                    f"<<<UNIT:{unit_key}:END>>>"
                )
                return (
                    body,
                    "stop",
                    {
                        "prompt_tokens": 1000,
                        "prompt_cache_hit_tokens": 800,
                        "prompt_cache_miss_tokens": 200,
                        "completion_tokens": 20,
                    },
                )

            with Database(state_db_path(root)) as db:
                doc_id = self._seed_two_partitions(db, artifact)
                result = run_translate_stage(
                    db, document_id=doc_id, settings=settings, chat_fn=fake_chat
                )
                self.assertEqual(result["translated"], 4)
                # Partition 1: initial warm-up + provisional re-warmup.
                self.assertGreaterEqual(len(warmups), 3)
                self.assertTrue(any("provisional: true" in w for w in warmups))
                # Concurrent units after rewarm should see provisional capsule.
                self.assertTrue(any("provisional: true" in c for c in capsule_seen))
                capsules = db.list_style_capsules(doc_id)
                self.assertGreaterEqual(len(capsules), 2)
                versions = [int(c["version"]) for c in capsules]
                self.assertIn(1, versions)
                self.assertIn(2, versions)
                # Partition 2 should inherit boundary/examples from partition 1.
                v2 = StyleCapsule.from_db_row(db.get_style_capsule(doc_id, 2))
                self.assertTrue(v2.boundary_context.get("source_tail"))
                self.assertTrue((artifact / "style_capsules" / "v1.json").is_file())
                units = db.list_units(doc_id)
                self.assertTrue(any(u["style_capsule_version"] for u in units))


class CapsuleRecoveryTests(unittest.TestCase):
    def test_skipped_partition_rebuilds_missing_capsule(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "doc.solivagus"
            artifact.mkdir()
            clear_settings_cache()
            settings = get_settings()
            settings.workspace = root
            settings.llm_api_key = "test"
            settings.enable_local_translation_cache = False
            settings.retries = 1
            settings.cache_settle_seconds = 0
            settings.adaptive_concurrency = False

            seen_capsules: list[str] = []

            def fake_chat(**kwargs):
                messages = kwargs.get("messages")
                if messages and len(messages) == 2:
                    seen_capsules.append(messages[1]["content"])
                    return "READY", "stop", {"prompt_tokens": 10, "completion_tokens": 1}
                content = (messages or [{}])[-1].get("content", "") if messages else ""
                unit_key = "p2u1"
                for key in ("p1u1", "p1u2", "p2u1", "p2u2"):
                    if key in content:
                        unit_key = key
                        break
                body = (
                    f"<<<UNIT:{unit_key}:BEGIN>>>\n"
                    f"译文含示能（affordance）。\n"
                    f"<<<UNIT:{unit_key}:END>>>"
                )
                return (
                    body,
                    "stop",
                    {
                        "prompt_tokens": 1000,
                        "prompt_cache_hit_tokens": 800,
                        "prompt_cache_miss_tokens": 200,
                        "completion_tokens": 12,
                    },
                )

            helper = CapsuleIntegrationTests()
            with Database(state_db_path(root)) as db:
                doc_id = helper._seed_two_partitions(db, artifact)
                parts = db.list_partitions(doc_id)
                p1 = int(parts[0]["id"])
                # Simulate crash after partition-1 units done but before capsule write.
                for unit in db.list_units_for_partition(p1):
                    db.update_unit(
                        int(unit["id"]),
                        status=UnitStatus.DONE.value,
                        translation_text="译文含示能（affordance）。\n",
                        translation_hash=sha256_text("译文含示能（affordance）。\n"),
                    )
                db.commit()
                self.assertIsNone(db.get_style_capsule_for_partition(doc_id, p1))
                result = run_translate_stage(
                    db, document_id=doc_id, settings=settings, chat_fn=fake_chat
                )
                self.assertGreaterEqual(result["translated"], 2)
                frozen = db.get_style_capsule_for_partition(doc_id, p1)
                self.assertIsNotNone(frozen)
                self.assertGreaterEqual(int(frozen["version"]), 1)
                # Partition 2 warm-up must see rebuilt prior-translation context.
                self.assertTrue(any("affordance" in c or "示能" in c for c in seen_capsules))

    def test_force_replan_starts_partition1_with_empty_capsule(self) -> None:
        from solivagus.pipeline.plan import run_plan_stage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "doc.solivagus"
            artifact.mkdir()
            (artifact / "source.md").write_text(
                "# Title\n\n<!-- source-page: 1 -->\n\n"
                "Intro paragraph about progressive disclosure and affordance.\n\n"
                "## Method\n\nMore prose for a second partition budget.\n" * 40,
                encoding="utf-8",
            )
            clear_settings_cache()
            settings = get_settings()
            settings.workspace = root
            settings.llm_api_key = "test"
            settings.enable_local_translation_cache = False
            settings.retries = 1
            settings.cache_settle_seconds = 0
            settings.first_partition_tokens = 50
            settings.partition_target_tokens = 50
            settings.partition_max_tokens = 80
            settings.unit_target_tokens = 40
            settings.unit_max_tokens = 80
            settings.unit_min_tokens = 10

            seen: list[str] = []

            def fake_chat(**kwargs):
                messages = kwargs.get("messages")
                if messages and len(messages) == 2:
                    seen.append(messages[1]["content"])
                    return "READY", "stop", {"prompt_tokens": 10, "completion_tokens": 1}
                content = (messages or [{}])[-1].get("content", "") if messages else ""
                unit_key = "u00001"
                for i in range(1, 20):
                    key = f"u{i:05d}"
                    if key in content:
                        unit_key = key
                        break
                body = f"<<<UNIT:{unit_key}:BEGIN>>>\nok\n<<<UNIT:{unit_key}:END>>>"
                return (
                    body,
                    "stop",
                    {
                        "prompt_tokens": 200,
                        "prompt_cache_hit_tokens": 100,
                        "prompt_cache_miss_tokens": 100,
                        "completion_tokens": 5,
                    },
                )

            with Database(state_db_path(root)) as db:
                doc_id = db.upsert_document(
                    source_path=str(root / "doc.pdf"),
                    source_sha256="sha-replan-capsule",
                    display_name="doc.pdf",
                    artifact_dir=str(artifact),
                    status=DocumentStatus.OCR_COMPLETE.value,
                )
                run_plan_stage(db, document_id=doc_id, settings=settings)
                db.insert_style_capsule(
                    doc_id,
                    version=1,
                    rules_json="[]",
                    terminology_json='{"legacy_term": "旧术语"}',
                    examples_json="[]",
                    boundary_context_json="{}",
                    content_hash="deadbeef",
                    source_partition_id=999,
                )
                db.commit()
                replan = run_plan_stage(db, document_id=doc_id, settings=settings, force=True)
                self.assertEqual(int(replan["preserved_units"]), 0)
                self.assertEqual(db.list_style_capsules(doc_id), [])
                run_translate_stage(
                    db, document_id=doc_id, settings=settings, chat_fn=fake_chat
                )
                self.assertTrue(seen)
                self.assertFalse(any("legacy_term" in c or "旧术语" in c for c in seen))

    def test_all_done_rebuilds_missing_final_capsule_without_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "doc.solivagus"
            artifact.mkdir()
            clear_settings_cache()
            settings = get_settings()
            settings.workspace = root
            settings.llm_api_key = "test"

            calls = {"n": 0}

            def boom_chat(**_kwargs):
                calls["n"] += 1
                raise AssertionError("provider must not be called")

            helper = CapsuleIntegrationTests()
            with Database(state_db_path(root)) as db:
                doc_id = helper._seed_two_partitions(db, artifact)
                for unit in db.list_units(doc_id):
                    text = f"译文含示能（affordance）{unit['unit_key']}\n"
                    db.update_unit(
                        int(unit["id"]),
                        status=UnitStatus.DONE.value,
                        translation_text=text,
                        translation_hash=sha256_text(text),
                    )
                db.update_document_status(
                    doc_id,
                    status=DocumentStatus.TRANSLATION_COMPLETE.value,
                    translation_status="complete",
                )
                db.commit()
                self.assertEqual(db.list_style_capsules(doc_id), [])
                result = run_translate_stage(
                    db, document_id=doc_id, settings=settings, chat_fn=boom_chat
                )
                self.assertTrue(result.get("skipped_all"))
                self.assertEqual(calls["n"], 0)
                capsules = db.list_style_capsules(doc_id)
                self.assertGreaterEqual(len(capsules), 2)
                latest = db.get_latest_style_capsule(doc_id)
                self.assertIsNotNone(latest)
                terms = StyleCapsule.from_db_row(latest).terminology
                self.assertTrue(terms)
                self.assertIn("affordance", terms)
                reconcile = result.get("capsule_reconcile") or {}
                self.assertEqual(len(reconcile.get("rebuilt_partition_ids") or []), 2)

    def test_force_replan_preserving_done_units_rebuilds_capsules_for_qa(self) -> None:
        from solivagus.pipeline.plan import run_plan_stage
        from solivagus.qa.runner import run_qa_stage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "doc.solivagus"
            artifact.mkdir()
            source_md = (
                "# Title\n\n<!-- source-page: 1 -->\n\n"
                "Intro discusses progressive disclosure and affordance in systems.\n\n"
                "## Method\n\n"
                "More prose about agentic workflow and progressive disclosure.\n"
            )
            (artifact / "source.md").write_text(source_md, encoding="utf-8")
            clear_settings_cache()
            settings = get_settings()
            settings.workspace = root
            settings.llm_api_key = "test"
            settings.qa_enabled = True
            settings.qa_max_repair_attempts = 0
            settings.first_partition_tokens = 80
            settings.partition_target_tokens = 80
            settings.partition_max_tokens = 120
            settings.unit_target_tokens = 40
            settings.unit_max_tokens = 80
            settings.unit_min_tokens = 5

            calls = {"n": 0}

            def boom_chat(**_kwargs):
                calls["n"] += 1
                raise AssertionError("provider must not be called for reconcile")

            with Database(state_db_path(root)) as db:
                doc_id = db.upsert_document(
                    source_path=str(root / "doc.pdf"),
                    source_sha256="sha-replan-preserve-capsule",
                    display_name="doc.pdf",
                    artifact_dir=str(artifact),
                    status=DocumentStatus.OCR_COMPLETE.value,
                )
                first = run_plan_stage(db, document_id=doc_id, settings=settings)
                self.assertFalse(first["skipped"])
                old_parts = [int(p["id"]) for p in db.list_partitions(doc_id)]
                for unit in db.list_units(doc_id):
                    text = "译文含示能（affordance）与渐进式披露（progressive disclosure）。\n"
                    db.update_unit(
                        int(unit["id"]),
                        status=UnitStatus.DONE.value,
                        translation_text=text,
                        translation_hash=sha256_text(text),
                    )
                db.insert_style_capsule(
                    doc_id,
                    version=1,
                    rules_json="[]",
                    terminology_json='{"affordance": "示能"}',
                    examples_json="[]",
                    boundary_context_json="{}",
                    content_hash="oldcapsule",
                    source_partition_id=old_parts[0],
                )
                db.commit()
                self.assertEqual(len(db.list_style_capsules(doc_id)), 1)

                replan = run_plan_stage(db, document_id=doc_id, settings=settings, force=True)
                self.assertGreaterEqual(int(replan["preserved_units"]), 1)
                self.assertEqual(db.list_style_capsules(doc_id), [])
                new_parts = [int(p["id"]) for p in db.list_partitions(doc_id)]
                self.assertTrue(all(u["status"] == UnitStatus.DONE.value for u in db.list_units(doc_id)))

                result = run_translate_stage(
                    db, document_id=doc_id, settings=settings, chat_fn=boom_chat
                )
                self.assertTrue(result.get("skipped_all"))
                self.assertEqual(calls["n"], 0)
                capsules = db.list_style_capsules(doc_id)
                self.assertGreaterEqual(len(capsules), 1)
                bound_ids = {
                    int(c["source_partition_id"])
                    for c in capsules
                    if c["source_partition_id"] is not None
                }
                self.assertTrue(bound_ids.issubset(set(new_parts)))
                latest = db.get_latest_style_capsule(doc_id)
                self.assertIsNotNone(latest)
                terms = StyleCapsule.from_db_row(latest).terminology
                self.assertIn("affordance", terms)

                qa = run_qa_stage(db, document_id=doc_id, settings=settings, chat_fn=boom_chat)
                self.assertFalse(qa.get("skipped", False))
                # QA reads latest capsule terminology; reconcile must have restored it.
                self.assertIsNotNone(db.get_latest_style_capsule(doc_id))

    def test_db_committed_json_missing_healed_on_rerun(self) -> None:
        import json
        from unittest import mock

        from solivagus.pipeline import translate as translate_mod
        from solivagus.pipeline.translate import _persist_partition_capsule

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "doc.solivagus"
            artifact.mkdir()
            clear_settings_cache()
            settings = get_settings()
            settings.workspace = root
            settings.llm_api_key = "test"

            helper = CapsuleIntegrationTests()
            db_path = state_db_path(root)
            with Database(db_path) as db:
                doc_id = helper._seed_two_partitions(db, artifact)
                for unit in db.list_units(doc_id):
                    text = f"译文含示能（affordance）{unit['unit_key']}\n"
                    db.update_unit(
                        int(unit["id"]),
                        status=UnitStatus.DONE.value,
                        translation_text=text,
                        translation_hash=sha256_text(text),
                    )
                db.update_document_status(
                    doc_id,
                    status=DocumentStatus.TRANSLATION_COMPLETE.value,
                    translation_status="complete",
                )
                db.commit()
                parts = db.list_partitions(doc_id)
                capsule_dir = artifact / "style_capsules"
                capsule_dir.mkdir(parents=True, exist_ok=True)

                write_calls = {"n": 0}
                real_write = translate_mod.atomic_write_json

                def flaky_write(path: Path, data: dict) -> None:
                    write_calls["n"] += 1
                    if write_calls["n"] == 1:
                        raise OSError("injected crash after DB commit")
                    real_write(path, data)

                # Simulate first partition persist: DB commits, JSON write fails.
                entry = empty_capsule()
                assembled = [
                    {
                        "unit_key": str(u["unit_key"]),
                        "source_text": str(u["source_text"]),
                        "translation_text": str(u["translation_text"]),
                    }
                    for u in db.list_units_for_partition(int(parts[0]["id"]))
                ]
                first_capsule = build_next_capsule(entry, assembled)
                with mock.patch.object(translate_mod, "atomic_write_json", flaky_write):
                    with self.assertRaises(OSError):
                        _persist_partition_capsule(
                            db,
                            document_id=doc_id,
                            part_id=int(parts[0]["id"]),
                            capsule=first_capsule,
                            capsule_dir=capsule_dir,
                        )
                # Second partition: DB only, no JSON (manual crash simulation).
                assembled2 = [
                    {
                        "unit_key": str(u["unit_key"]),
                        "source_text": str(u["source_text"]),
                        "translation_text": str(u["translation_text"]),
                    }
                    for u in db.list_units_for_partition(int(parts[1]["id"]))
                ]
                second_capsule = build_next_capsule(first_capsule, assembled2)
                fields = second_capsule.to_db_fields()
                db.insert_style_capsule(
                    doc_id,
                    version=int(fields["version"]),
                    rules_json=str(fields["rules_json"]),
                    terminology_json=str(fields["terminology_json"]),
                    examples_json=str(fields["examples_json"]),
                    boundary_context_json=str(fields["boundary_context_json"]),
                    content_hash=str(fields["content_hash"]),
                    source_partition_id=int(parts[1]["id"]),
                )
                self.assertEqual(len(db.list_style_capsules(doc_id)), 2)
                self.assertFalse((capsule_dir / "v1.json").is_file())
                self.assertFalse((capsule_dir / "v2.json").is_file())
                expected_hashes = {
                    1: first_capsule.content_hash(),
                    2: second_capsule.content_hash(),
                }

            calls = {"n": 0}

            def boom_chat(**_kwargs):
                calls["n"] += 1
                raise AssertionError("provider must not be called")

            # Re-open DB (SOAK-style process restart) and heal via all-done translate.
            with Database(db_path) as db:
                result = run_translate_stage(
                    db, document_id=doc_id, settings=settings, chat_fn=boom_chat
                )
                self.assertTrue(result.get("skipped_all"))
                self.assertEqual(calls["n"], 0)
                reconcile = result.get("capsule_reconcile") or {}
                self.assertEqual(reconcile.get("rebuilt_partition_ids"), [])
                self.assertEqual(
                    sorted(reconcile.get("json_restored_partition_ids") or []),
                    sorted(int(p["id"]) for p in db.list_partitions(doc_id)),
                )
                for version, expected in expected_hashes.items():
                    path = capsule_dir / f"v{version}.json"
                    self.assertTrue(path.is_file(), msg=f"missing {path.name}")
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    self.assertEqual(payload["content_hash"], expected)
                    self.assertEqual(payload["version"], version)


if __name__ == "__main__":
    unittest.main()
