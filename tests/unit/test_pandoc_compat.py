"""Regression: Pandoc-native images, tight inline math, XeLaTeX PDF."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from solivagus.structure.parser import parse_markdown_structure
from solivagus.structure.models import NodeType
from solivagus.util.markdown import protect_markdown, restore_markdown
from solivagus.util.pandoc_compat import (
    html_images_to_pandoc,
    normalize_for_pandoc,
    normalize_inline_math_delimiters,
)


# Minimal valid 1x1 JPEG
_JPEG_BYTES = bytes(
    [
        0xFF,
        0xD8,
        0xFF,
        0xE0,
        0x00,
        0x10,
        0x4A,
        0x46,
        0x49,
        0x46,
        0x00,
        0x01,
        0x01,
        0x00,
        0x00,
        0x01,
        0x00,
        0x01,
        0x00,
        0x00,
        0xFF,
        0xDB,
        0x00,
        0x43,
        0x00,
        0x08,
        0x06,
        0x06,
        0x07,
        0x06,
        0x05,
        0x08,
        0x07,
        0x07,
        0x07,
        0x09,
        0x09,
        0x08,
        0x0A,
        0x0C,
        0x14,
        0x0D,
        0x0C,
        0x0B,
        0x0B,
        0x0C,
        0x19,
        0x12,
        0x13,
        0x0F,
        0x14,
        0x1D,
        0x1A,
        0x1F,
        0x1E,
        0x1D,
        0x1A,
        0x1C,
        0x1C,
        0x20,
        0x24,
        0x2E,
        0x27,
        0x20,
        0x22,
        0x2C,
        0x23,
        0x1C,
        0x1C,
        0x28,
        0x37,
        0x29,
        0x2C,
        0x30,
        0x31,
        0x34,
        0x34,
        0x34,
        0x1F,
        0x27,
        0x39,
        0x3D,
        0x38,
        0x32,
        0x3C,
        0x2E,
        0x33,
        0x34,
        0x32,
        0xFF,
        0xC0,
        0x00,
        0x0B,
        0x08,
        0x00,
        0x01,
        0x00,
        0x01,
        0x01,
        0x01,
        0x11,
        0x00,
        0xFF,
        0xC4,
        0x00,
        0x1F,
        0x00,
        0x00,
        0x01,
        0x05,
        0x01,
        0x01,
        0x01,
        0x01,
        0x01,
        0x01,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x01,
        0x02,
        0x03,
        0x04,
        0x05,
        0x06,
        0x07,
        0x08,
        0x09,
        0x0A,
        0x0B,
        0xFF,
        0xC4,
        0x00,
        0xB5,
        0x10,
        0x00,
        0x02,
        0x01,
        0x03,
        0x03,
        0x02,
        0x04,
        0x03,
        0x05,
        0x05,
        0x04,
        0x04,
        0x00,
        0x00,
        0x01,
        0x7D,
        0x01,
        0x02,
        0x03,
        0x00,
        0x04,
        0x11,
        0x05,
        0x12,
        0x21,
        0x31,
        0x41,
        0x06,
        0x13,
        0x51,
        0x61,
        0x07,
        0x22,
        0x71,
        0x14,
        0x32,
        0x81,
        0x91,
        0xA1,
        0x08,
        0x23,
        0x42,
        0xB1,
        0xC1,
        0x15,
        0x52,
        0xD1,
        0xF0,
        0x24,
        0x33,
        0x62,
        0x72,
        0x82,
        0x09,
        0x0A,
        0x16,
        0x17,
        0x18,
        0x19,
        0x1A,
        0x25,
        0x26,
        0x27,
        0x28,
        0x29,
        0x2A,
        0x34,
        0x35,
        0x36,
        0x37,
        0x38,
        0x39,
        0x3A,
        0x43,
        0x44,
        0x45,
        0x46,
        0x47,
        0x48,
        0x49,
        0x4A,
        0x53,
        0x54,
        0x55,
        0x56,
        0x57,
        0x58,
        0x59,
        0x5A,
        0x63,
        0x64,
        0x65,
        0x66,
        0x67,
        0x68,
        0x69,
        0x6A,
        0x73,
        0x74,
        0x75,
        0x76,
        0x77,
        0x78,
        0x79,
        0x7A,
        0x83,
        0x84,
        0x85,
        0x86,
        0x87,
        0x88,
        0x89,
        0x8A,
        0x92,
        0x93,
        0x94,
        0x95,
        0x96,
        0x97,
        0x98,
        0x99,
        0x9A,
        0xA2,
        0xA3,
        0xA4,
        0xA5,
        0xA6,
        0xA7,
        0xA8,
        0xA9,
        0xAA,
        0xB2,
        0xB3,
        0xB4,
        0xB5,
        0xB6,
        0xB7,
        0xB8,
        0xB9,
        0xBA,
        0xC2,
        0xC3,
        0xC4,
        0xC5,
        0xC6,
        0xC7,
        0xC8,
        0xC9,
        0xCA,
        0xD2,
        0xD3,
        0xD4,
        0xD5,
        0xD6,
        0xD7,
        0xD8,
        0xD9,
        0xDA,
        0xE1,
        0xE2,
        0xE3,
        0xE4,
        0xE5,
        0xE6,
        0xE7,
        0xE8,
        0xE9,
        0xEA,
        0xF1,
        0xF2,
        0xF3,
        0xF4,
        0xF5,
        0xF6,
        0xF7,
        0xF8,
        0xF9,
        0xFA,
        0xFF,
        0xDA,
        0x00,
        0x08,
        0x01,
        0x01,
        0x00,
        0x00,
        0x3F,
        0x00,
        0x7F,
        0x46,
        0xFF,
        0xD9,
    ]
)


class TestPandocCompatNormalize(unittest.TestCase):
    def test_centered_html_img_to_pandoc_image(self) -> None:
        raw = (
            '<div style="text-align: center;">'
            '<img src="assets/page_0002/0001_img_in_image_box_141_756_1714_1027.jpg" '
            'alt="Image" width="81%" />'
            "</div>"
        )
        out = html_images_to_pandoc(raw)
        self.assertEqual(
            out,
            "![Image](assets/page_0002/0001_img_in_image_box_141_756_1714_1027.jpg)"
            "{width=81%}",
        )
        self.assertNotIn("<img", out)
        self.assertNotIn("<div", out)

    def test_spaced_inline_math_tightened(self) -> None:
        raw = "sweep $ 20^{\\circ} $ and $ 33^{\\circ} $"
        out = normalize_inline_math_delimiters(raw)
        self.assertEqual(out, "sweep $20^{\\circ}$ and $33^{\\circ}$")

    def test_display_math_and_code_untouched(self) -> None:
        raw = "$$  x + y  $$\n\n```\n$  keep  $\n```\n"
        out = normalize_inline_math_delimiters(raw)
        self.assertIn("$$  x + y  $$", out)
        self.assertIn("$  keep  $", out)

    def test_fenced_html_img_not_converted(self) -> None:
        raw = "```html\n<img src=\"example.png\">\n```\n"
        out = normalize_for_pandoc(raw)
        self.assertIn('<img src="example.png">', out)
        self.assertNotIn("![Image]", out)

    def test_inline_code_math_not_converted(self) -> None:
        raw = "Use `$ x $` in docs."
        out = normalize_for_pandoc(raw)
        self.assertEqual(out, "Use `$ x $` in docs.")

    def test_currency_dollars_not_converted(self) -> None:
        raw = "Price $5 and $10."
        out = normalize_for_pandoc(raw)
        self.assertEqual(out, "Price $5 and $10.")

    def test_prose_spaced_ident_still_tightened(self) -> None:
        raw = "variable $ x $ here"
        out = normalize_for_pandoc(raw)
        self.assertEqual(out, "variable $x$ here")

    def test_normalize_combined_and_structure_image(self) -> None:
        raw = (
            '<div style="text-align: center;">'
            '<img src="assets/a.jpg" alt="Image" width="50%" /></div>\n\n'
            "Angle $ 200^{\\circ} $.\n"
        )
        out = normalize_for_pandoc(raw)
        self.assertIn("![Image](assets/a.jpg){width=50%}", out)
        self.assertIn("$200^{\\circ}$", out)
        nodes = parse_markdown_structure(out)
        types = [n.node_type for n in nodes]
        self.assertIn(NodeType.IMAGE, types)

    def test_protect_restore_keeps_image_attrs(self) -> None:
        text = "See ![Image](assets/a.jpg){width=81%} here."
        protected, placeholders = protect_markdown(text)
        self.assertNotIn("![Image]", protected)
        restored = restore_markdown(protected, placeholders)
        self.assertEqual(restored, text)


@unittest.skipUnless(shutil.which("pandoc"), "pandoc not on PATH")
class TestPandocAstRegression(unittest.TestCase):
    def test_pandoc_sees_image_and_inline_math(self) -> None:
        md = normalize_for_pandoc(
            '<div style="text-align: center;">'
            '<img src="assets/a.jpg" alt="Image" width="81%" /></div>\n\n'
            "Pitch $ 20^{\\circ} $.\n"
        )
        proc = subprocess.run(
            ["pandoc", "-f", "markdown", "-t", "json"],
            input=md,
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        blob = json.dumps(payload)
        self.assertIn('"t": "Image"', blob)
        self.assertIn('"t": "Math"', blob)
        self.assertIn("InlineMath", blob)
        # Must not leave RawInline HTML for the figure
        self.assertNotIn("<img", blob)


@unittest.skipUnless(
    shutil.which("pandoc") and shutil.which("xelatex"),
    "pandoc+xelatex required for one-shot PDF",
)
class TestPandocXelatexPdfRegression(unittest.TestCase):
    def test_oneshot_pdf_with_image_and_degree_math(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets = root / "assets"
            assets.mkdir()
            (assets / "a.jpg").write_bytes(_JPEG_BYTES)
            md_path = root / "doc.md"
            md_path.write_text(
                normalize_for_pandoc(
                    "# Title\n\n"
                    '<div style="text-align: center;">'
                    '<img src="assets/a.jpg" alt="Image" width="50%" /></div>\n\n'
                    "Sweep angle $ 20^{\\circ} $.\n"
                ),
                encoding="utf-8",
            )
            pdf_path = root / "doc.pdf"
            proc = subprocess.run(
                [
                    "pandoc",
                    str(md_path),
                    "-o",
                    str(pdf_path),
                    "--pdf-engine=xelatex",
                    "-V",
                    "mainfont=Times New Roman",
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
                encoding="utf-8",
                errors="replace",
            )
            self.assertEqual(
                proc.returncode,
                0,
                f"stderr:\n{proc.stderr}\nstdout:\n{proc.stdout}",
            )
            self.assertTrue(pdf_path.is_file())
            self.assertGreater(pdf_path.stat().st_size, 1000)
            combined = (proc.stderr or "") + (proc.stdout or "")
            self.assertNotIn("Missing character", combined)
            self.assertNotIn("hPutChar", combined)


if __name__ == "__main__":
    unittest.main()
