from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paradigma.atomic import atomic_replace_text
from paradigma.config import load_config
from paradigma.diagnostics import Diagnostic, Severity
from paradigma.errors import AtomicWriteFailure, ParseFailure
from paradigma.parser import flatten_mapping, parse_markdown_text
from paradigma.results import OperationResult
from paradigma.schema import load_schema_registry, validate_concept


class PackageParserTests(unittest.TestCase):
    def test_parser_preserves_protocol_strings_and_diagnostics(self) -> None:
        parsed = parse_markdown_text(
            """---
title: 中文
timestamp: 2026-07-23T22:25:12+08:00
paradigma:
  tags: [one, two]
---

# Body
""",
            source="concept.md",
        )
        flattened = flatten_mapping(parsed.metadata)
        self.assertEqual("2026-07-23T22:25:12+08:00", flattened["timestamp"])
        self.assertEqual(["one", "two"], flattened["paradigma.tags"])

        with self.assertRaises(ParseFailure) as raised:
            parse_markdown_text("---\ntitle: one\ntitle: two\n---\n")
        self.assertEqual("YAML_DUPLICATE_KEY", raised.exception.code)


class PackageConfigTests(unittest.TestCase):
    def test_repository_config_loads_without_diagnostics(self) -> None:
        config = load_config(ROOT)
        self.assertEqual("0.4", config.config_schema_version)
        self.assertEqual(ROOT / "memory-bank" / "memories", config.memory_root)
        self.assertEqual(
            ROOT / ".paradigma" / "cache" / "catalog.sqlite3",
            config.catalog_path,
        )
        self.assertEqual("0.7.0", config.installed_distribution_version)
        self.assertEqual((), config.validate())

    def test_v0_5_1_config_uses_v0_6_memory_path_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_root = root / ".paradigma"
            config_root.mkdir()
            (config_root / "config.yaml").write_text(
                """config_schema_version: "0.3"
okf_version: "0.1"
installed_distribution_version: "0.5.1"
knowledge_roots: [memory-bank/knowledge]
machine_index_path: .paradigma/cache/knowledge-index.json
""",
                encoding="utf-8",
            )

            config = load_config(root)

            self.assertEqual(
                (root / "memory-bank" / "memories").resolve(),
                config.memory_root.resolve(),
            )
            self.assertEqual(
                (root / ".paradigma" / "cache" / "catalog.sqlite3").resolve(),
                config.catalog_path.resolve(),
            )
            self.assertEqual((), config.validate())

    def test_cache_path_cannot_escape_repository_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_root = root / ".paradigma"
            config_root.mkdir()
            (config_root / "config.yaml").write_text(
                """config_schema_version: "0.3"
okf_version: "0.1"
installed_distribution_version: "0.5.1"
knowledge_roots: [memory-bank/knowledge]
machine_index_path: ../outside.json
""",
                encoding="utf-8",
            )
            diagnostics = load_config(root).validate()
            self.assertEqual(
                ["PD_CONFIG_CACHE_PATH_INVALID"],
                [item.code for item in diagnostics],
            )

    def test_memory_and_catalog_paths_are_confined_to_their_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_root = root / ".paradigma"
            config_root.mkdir()
            (config_root / "config.yaml").write_text(
                """config_schema_version: "0.4"
okf_version: "0.1"
installed_distribution_version: "0.5.1"
knowledge_roots: [memory-bank/knowledge]
memory_root: .paradigma/cache/memories
catalog_path: catalog.sqlite3
""",
                encoding="utf-8",
            )
            codes = [item.code for item in load_config(root).validate()]
            self.assertEqual(
                ["PD_CONFIG_CATALOG_PATH_INVALID", "PD_CONFIG_MEMORY_ROOT_INVALID"],
                codes,
            )


class PackageSchemaTests(unittest.TestCase):
    def test_registry_loads_and_validator_returns_structured_findings(self) -> None:
        registry = load_schema_registry(
            ROOT / ".paradigma" / "schemas" / "paradigma-types.schema.yaml"
        )
        diagnostics = validate_concept(
            {
                "type": "paradigma-architecture",
                "title": "Architecture",
                "description": "Test",
                "tags": ["test"],
                "timestamp": "yesterday",
            },
            "# Overview\n",
            registry,
            source="architecture.md",
        )
        codes = {item.code for item in diagnostics}
        self.assertIn("PD_SCHEMA_TIMESTAMP_INVALID", codes)
        self.assertIn("PD_SCHEMA_PARADIGMA_FIELD_MISSING", codes)
        self.assertIn("PD_SCHEMA_SECTION_MISSING", codes)


class PackageAtomicWriterTests(unittest.TestCase):
    def test_replace_failure_preserves_target_and_cleans_temp_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "state.yaml"
            path.write_text("old\n", encoding="utf-8")
            before = path.read_bytes()
            with mock.patch(
                "paradigma.atomic.os.replace", side_effect=OSError("injected")
            ):
                with self.assertRaises(AtomicWriteFailure) as raised:
                    atomic_replace_text(path, "new\n")
            self.assertEqual("PD_ATOMIC_WRITE_ERROR", raised.exception.code)
            self.assertEqual(before, path.read_bytes())
            self.assertEqual([], list(path.parent.glob(".state.yaml.*.tmp")))


class PackageResultTests(unittest.TestCase):
    def test_result_is_value_based_and_serializable(self) -> None:
        warning = Diagnostic(
            "PD_TEST_WARNING", "warning", severity=Severity.WARNING
        )
        result = OperationResult(value={"count": 1}, diagnostics=(warning,))
        self.assertTrue(result.ok)
        self.assertEqual(0, result.exit_code)
        self.assertEqual("warning", result.to_dict()["diagnostics"][0]["severity"])


if __name__ == "__main__":
    unittest.main()
