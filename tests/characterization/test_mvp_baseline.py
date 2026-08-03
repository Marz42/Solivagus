from __future__ import annotations

import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LEGACY_SCRIPT = ROOT / "legacy" / "pdf_translate_cli_v0_2.py"
EXAMPLE = ROOT / "example"
QWEN_PDF = EXAMPLE / "Qwen3_TTS.pdf"
QWEN_WORK = EXAMPLE / "Qwen3_TTS.translation"

# Frozen at Phase 0; see manuals/solivagus-mvp-baseline.md
QWEN_PDF_SHA256 = "b818867cf8f190185eae83238bde3adfc0c47c1864e587efdc59ee8ab5c7d0cb"


def load_mvp():
    if not LEGACY_SCRIPT.is_file():
        raise unittest.SkipTest(f"missing archived MVP script: {LEGACY_SCRIPT}")
    module_name = "solivagus_legacy_pdf_translate_cli_v0_2"
    spec = importlib.util.spec_from_file_location(module_name, LEGACY_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {LEGACY_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class MvpArchiveTests(unittest.TestCase):
    def test_legacy_script_is_archived(self) -> None:
        self.assertTrue(LEGACY_SCRIPT.is_file())
        text = LEGACY_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("SCRIPT_VERSION", text)
        self.assertIn("PaddleOCR-VL", text)


class MvpProtectAndSplitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mvp = load_mvp()

    def test_html_table_is_passthrough_not_placeholder_exploded(self) -> None:
        html = (
            "<div>\n"
            "<table>\n"
            "  <tr><td>alpha</td><td>beta</td></tr>\n"
            "  <tr><td>gamma</td><td>delta</td></tr>\n"
            "</table>\n"
            "</div>\n\n"
            "Translatable paragraph about transformers.\n"
        )
        segments = self.mvp.split_passthrough_segments(html)
        kinds = [kind for kind, _ in segments]
        self.assertIn("html_table_wrapper", kinds)
        table_seg = next(value for kind, value in segments if kind == "html_table_wrapper")
        self.assertIn("<table>", table_seg)
        self.assertIn("</table>", table_seg)

        text_parts = [value for kind, value in segments if kind == "text"]
        self.assertTrue(any("Translatable paragraph" in part for part in text_parts))

        protected, placeholders = self.mvp.protect_markdown(
            "\n".join(text_parts)
        )
        # Tables never enter protect_markdown in the hotfix path; text path must not
        # mint one placeholder per tag.
        self.assertNotIn("<td>", protected)
        self.assertLessEqual(len(placeholders), 5)

    def test_protect_restore_roundtrip_for_formula_and_code(self) -> None:
        source = (
            "See equation $$E = mc^2$$ and code `softmax` plus "
            "![fig](assets/x.png) before the conclusion."
        )
        protected, placeholders = self.mvp.protect_markdown(source)
        self.assertIn("@@PRESERVE_", protected)
        self.assertGreaterEqual(len(placeholders), 3)
        # Simulate a model that keeps placeholders intact.
        restored = self.mvp.restore_markdown(protected, placeholders)
        self.assertEqual(restored, source)
        for token in placeholders:
            self.assertNotIn(token, restored)

    def test_restore_rejects_missing_placeholder(self) -> None:
        protected, placeholders = self.mvp.protect_markdown("value $x_i$ here")
        broken = protected.replace("@@PRESERVE_00001@@", "MISSING")
        with self.assertRaises(self.mvp.AppError):
            self.mvp.restore_markdown(broken, placeholders)

    def test_split_markdown_does_not_split_html_table_block(self) -> None:
        table = (
            "<table>\n"
            + "\n".join(f"<tr><td>cell-{i}</td></tr>" for i in range(40))
            + "\n</table>"
        )
        markdown = f"# Title\n\nIntro paragraph.\n\n{table}\n\nOutro.\n"
        chunks = self.mvp.split_markdown(markdown, chunk_chars=2000)
        joined = "\n\n".join(chunks)
        self.assertIn("<table>", joined)
        self.assertIn("</table>", joined)
        # The oversized table block should appear intact in exactly one chunk.
        owners = [chunk for chunk in chunks if "<table>" in chunk]
        self.assertEqual(len(owners), 1)
        self.assertIn("</table>", owners[0])

    def test_untranslated_fallback_keeps_english_and_warns(self) -> None:
        source = "Original English paragraph remains."
        fallback = self.mvp.make_untranslated_fallback(
            "b00007", source, RuntimeError("boom")
        )
        self.assertIn(source, fallback)
        self.assertIn("b00007", fallback)
        self.assertRegex(fallback, re.compile(r"警告|未翻译|fallback|失败", re.I))


class MvpAssembleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mvp = load_mvp()

    def test_assemble_outputs_zh_and_bilingual(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            chunks_dir = work / "chunks"
            chunks_dir.mkdir()
            (chunks_dir / "b00001.source.md").write_text("Hello world.", encoding="utf-8")
            (chunks_dir / "b00001.zh.md").write_text("你好，世界。", encoding="utf-8")
            (chunks_dir / "b00002.source.md").write_text("Second.", encoding="utf-8")
            (chunks_dir / "b00002.zh.md").write_text("第二段。", encoding="utf-8")

            chunk_infos = [
                {
                    "id": "b00001",
                    "source_file": "chunks/b00001.source.md",
                    "translated_file": "chunks/b00001.zh.md",
                },
                {
                    "id": "b00002",
                    "source_file": "chunks/b00002.source.md",
                    "translated_file": "chunks/b00002.zh.md",
                },
            ]
            self.mvp.assemble_outputs(
                work_dir=work,
                chunks=chunk_infos,
                document_title="Demo",
                pdf_name="demo.pdf",
                model="deepseek-v4-flash",
                pipeline_version="v1.6",
                make_bilingual=True,
            )
            zh = (work / "translated.zh.md").read_text(encoding="utf-8")
            bilingual = (work / "translated.bilingual.md").read_text(encoding="utf-8")
            self.assertIn("你好，世界。", zh)
            self.assertIn("第二段。", zh)
            self.assertIn("Hello world.", bilingual)
            self.assertIn("你好，世界。", bilingual)


@unittest.skipUnless(
    QWEN_WORK.is_dir() and (QWEN_WORK / "state.json").is_file(),
    "local example/Qwen3_TTS.translation not present",
)
class MvpQwenFixtureTests(unittest.TestCase):
    def test_completed_state_matches_frozen_hash_and_outputs(self) -> None:
        state = json.loads((QWEN_WORK / "state.json").read_text(encoding="utf-8"))
        self.assertTrue(state.get("completed"))
        self.assertEqual(state.get("source_pdf_sha256"), QWEN_PDF_SHA256)
        self.assertEqual(state.get("translation", {}).get("model"), "deepseek-v4-flash")

        chunks = state.get("chunks") or []
        self.assertGreaterEqual(len(chunks), 1)
        self.assertTrue(all(item.get("status") == "done" for item in chunks))

        for name in ("source.md", "translated.zh.md", "translated.bilingual.md"):
            path = QWEN_WORK / name
            self.assertTrue(path.is_file(), name)
            self.assertGreater(path.stat().st_size, 1000)

        # No per-tag placeholder explosion in stored chunk translations.
        preserve_total = 0
        for item in chunks:
            zh_rel = item.get("translated_file")
            if not zh_rel:
                continue
            text = (QWEN_WORK / zh_rel).read_text(encoding="utf-8")
            preserve_total += len(re.findall(r"@@PRESERVE_\d+@@", text))
        self.assertLess(preserve_total, 50)

    def test_local_pdf_hash_still_matches_fixture_when_present(self) -> None:
        if not QWEN_PDF.is_file():
            self.skipTest("example/Qwen3_TTS.pdf missing")
        mvp = load_mvp()
        self.assertEqual(mvp.sha256_file(QWEN_PDF), QWEN_PDF_SHA256)


if __name__ == "__main__":
    unittest.main()
