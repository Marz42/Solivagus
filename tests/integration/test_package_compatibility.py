from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
TOOLS = ROOT / ".paradigma" / "tools"
for location in (str(SRC), str(TOOLS)):
    if location not in sys.path:
        sys.path.insert(0, location)

from paradigma.config import load_config
from paradigma.errors import ParseFailure
from paradigma.parser import parse_flat_frontmatter, parse_markdown_text
from paradigma.schema import load_schema_registry, validate_concept


def load_legacy_parser():
    spec = importlib.util.spec_from_file_location(
        "compatibility_legacy_parser", TOOLS / "_paradigma_yaml.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load legacy parser")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PackageCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.legacy = load_legacy_parser()

    def test_package_parser_matches_legacy_canonical_documents(self) -> None:
        config = load_config(ROOT)
        for knowledge_root in config.knowledge_roots:
            for path in sorted(knowledge_root.rglob("*.md")):
                if path.name in config.reserved_filenames:
                    continue
                with self.subTest(path=path.relative_to(ROOT)):
                    self.assertEqual(
                        self.legacy.parse_flat_frontmatter(path),
                        parse_flat_frontmatter(path),
                    )

    def test_package_parser_preserves_legacy_error_codes(self) -> None:
        samples = (
            "# missing\n",
            "---\ntitle: unclosed\n",
            "---\ntitle: one\ntitle: two\n---\n",
            "---\ntags: [broken\n---\n",
        )
        for source in samples:
            with self.subTest(source=source):
                with self.assertRaises(self.legacy.ParseFailure) as old_error:
                    self.legacy.parse_markdown_text(source)
                with self.assertRaises(ParseFailure) as new_error:
                    parse_markdown_text(source)
                self.assertEqual(
                    old_error.exception.diagnostic.code,
                    new_error.exception.diagnostic.code,
                )

    def test_package_schema_accepts_repository_concepts(self) -> None:
        config = load_config(ROOT)
        registry = load_schema_registry(
            ROOT / ".paradigma" / "schemas" / "paradigma-types.schema.yaml"
        )
        diagnostics = []
        for knowledge_root in config.knowledge_roots:
            for path in sorted(knowledge_root.rglob("*.md")):
                if path.name in config.reserved_filenames:
                    continue
                metadata, body = parse_flat_frontmatter(path)
                diagnostics.extend(
                    validate_concept(
                        metadata,
                        body,
                        registry,
                        source=str(path),
                    )
                )
        self.assertEqual([], diagnostics)


if __name__ == "__main__":
    unittest.main()
