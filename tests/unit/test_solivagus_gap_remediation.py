"""Gap remediation: OCR labels, config YAML, bisect, tokenizer, manifest."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from solivagus.config import clear_settings_cache, get_settings
from solivagus.config_loader import apply_config_dict, load_yaml_file
from solivagus.ocr.checkpoints import OcrConfig
from solivagus.ocr.labels import BASE_IGNORE_LABELS, build_ignore_labels
from solivagus.pipeline.bisect import bisect_source_text
from solivagus.pipeline.manifest import write_document_manifest
from solivagus.planning.tokenizer import TokenCounter, TokenMode, clear_tokenizer_cache
from solivagus.util.text import atomic_write_text


class OcrLabelPolicyTests(unittest.TestCase):
    def test_default_keeps_footnote_and_aside(self) -> None:
        labels = build_ignore_labels()
        self.assertNotIn("footnote", labels)
        self.assertNotIn("aside_text", labels)
        self.assertIn("header", labels)
        self.assertEqual(OcrConfig().resolved_ignore_labels(), BASE_IGNORE_LABELS)

    def test_drop_flags_are_independent(self) -> None:
        only_fn = build_ignore_labels(drop_footnotes=True, drop_aside_text=False)
        self.assertIn("footnote", only_fn)
        self.assertNotIn("aside_text", only_fn)
        only_aside = build_ignore_labels(drop_footnotes=False, drop_aside_text=True)
        self.assertNotIn("footnote", only_aside)
        self.assertIn("aside_text", only_aside)


class ConfigYamlTests(unittest.TestCase):
    def test_apply_yaml_maps_nested_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cfg.yaml"
            path.write_text(
                "provider:\n  model: deepseek-v4-pro\n  timeout_seconds: 900\n"
                "ocr:\n  drop_footnotes: true\n  keep_aside_text: false\n"
                "concurrency:\n  global: 32\n",
                encoding="utf-8",
            )
            clear_settings_cache()
            settings = get_settings()
            apply_config_dict(settings, load_yaml_file(path))
            self.assertEqual(settings.llm_model, "deepseek-v4-pro")
            self.assertEqual(settings.timeout_seconds, 900)
            self.assertTrue(settings.ocr_drop_footnotes)
            self.assertTrue(settings.ocr_drop_aside_text)  # keep_aside_text: false
            self.assertEqual(settings.global_concurrency, 32)


class BisectTests(unittest.TestCase):
    def test_bisect_by_blocks(self) -> None:
        text = "First paragraph about transformers.\n\nSecond paragraph about attention."
        halves = bisect_source_text(text)
        self.assertIsNotNone(halves)
        assert halves is not None
        self.assertIn("First", halves[0])
        self.assertIn("Second", halves[1])

    def test_unsplittable_short_text(self) -> None:
        self.assertIsNone(bisect_source_text("Too short."))


class ManifestTests(unittest.TestCase):
    def test_write_document_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp)
            atomic_write_text(artifact / "translated.zh.md", "# hi\n")
            path = write_document_manifest(
                artifact,
                document_id=1,
                display_name="doc.pdf",
                source_sha256="abc",
                status="qa_complete",
                model="deepseek-v4-flash",
            )
            self.assertTrue(path.is_file())
            text = path.read_text(encoding="utf-8")
            self.assertIn("translated.zh.md", text)
            self.assertIn("qa_complete", text)


class TokenizerTests(unittest.TestCase):
    def test_approximate_fallback(self) -> None:
        clear_tokenizer_cache()
        counter = TokenCounter(force_approximate=True)
        counted = counter.count("你好 world")
        self.assertEqual(counted.mode, TokenMode.APPROXIMATE)
        self.assertGreater(counted.tokens, 0)


if __name__ == "__main__":
    unittest.main()
