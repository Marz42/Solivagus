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


if __name__ == "__main__":
    unittest.main()
