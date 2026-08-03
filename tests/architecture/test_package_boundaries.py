from __future__ import annotations

import ast
from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "src" / "paradigma"


class PackageArchitectureTests(unittest.TestCase):
    def test_pyproject_uses_src_layout_and_root_version(self) -> None:
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(["VERSION"], data["tool"]["setuptools"]["dynamic"]["version"]["file"])
        self.assertEqual(["src"], data["tool"]["setuptools"]["packages"]["find"]["where"])
        self.assertEqual(">=3.11", data["project"]["requires-python"])
        self.assertIn(
            "storage/catalog/*.sql",
            data["tool"]["setuptools"]["package-data"]["paradigma"],
        )

    def test_application_core_has_no_cli_or_legacy_tool_dependencies(self) -> None:
        for path in sorted(PACKAGE.rglob("*.py")):
            if "cli" in path.relative_to(PACKAGE).parts:
                continue
            with self.subTest(module=path.name):
                source = path.read_text(encoding="utf-8")
                self.assertNotIn(".paradigma.tools", source)
                self.assertNotIn("sys.path", source)
                self.assertNotIn("import argparse", source)
                self.assertNotIn("import subprocess", source)
                self.assertNotIn("print(", source)

    def test_legacy_tools_are_adapters_not_business_implementations(self) -> None:
        tools = ROOT / ".paradigma" / "tools"
        forbidden = (
            "import yaml",
            "import hashlib",
            "import tempfile",
            "import subprocess",
            "os.replace(",
            "rglob(\"*.md\")",
            "def parse_markdown_text",
        )
        for path in sorted(tools.glob("*.py")):
            with self.subTest(tool=path.name):
                source = path.read_text(encoding="utf-8")
                for token in forbidden:
                    self.assertNotIn(token, source)
                if path.name != "_bootstrap.py":
                    self.assertTrue(
                        "from paradigma" in source
                        or "from _index import" in source
                        or "from _version import" in source
                    )

    def test_memory_kernel_does_not_depend_on_outer_layers(self) -> None:
        kernel = PACKAGE / "kernel"
        forbidden_roots = {
            "paradigma.adapters",
            "paradigma.application",
            "paradigma.cli",
            "paradigma.integrations",
            "paradigma.storage",
        }
        for path in sorted(kernel.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            relative = path.relative_to(PACKAGE).with_suffix("")
            module_parts = ["paradigma", *relative.parts]
            package_parts = module_parts[:-1]
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    if node.level == 0:
                        imports.append(node.module or "")
                    else:
                        keep = len(package_parts) - (node.level - 1)
                        base = package_parts[:keep]
                        suffix = (node.module or "").split(".")
                        imports.append(".".join([*base, *filter(None, suffix)]))
            with self.subTest(module=path.relative_to(PACKAGE).as_posix()):
                for imported in imports:
                    self.assertFalse(
                        any(
                            imported == root or imported.startswith(f"{root}.")
                            for root in forbidden_roots
                        ),
                        f"kernel imports outer layer {imported}",
                    )

    def test_storage_does_not_depend_on_domain_integrations_or_adapters(self) -> None:
        storage = PACKAGE / "storage"
        forbidden = (
            "paradigma.adapters",
            "paradigma.cli",
            "paradigma.integrations",
            "paradigma.application",
        )
        for path in sorted(storage.rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            with self.subTest(module=path.relative_to(PACKAGE).as_posix()):
                for module in forbidden:
                    self.assertNotIn(module, source)
                self.assertNotIn("from ..integrations", source)
                self.assertNotIn("from ...integrations", source)

    def test_coding_integration_depends_only_on_kernel_and_standard_library(self) -> None:
        coding = PACKAGE / "integrations" / "coding"
        forbidden = (
            "paradigma.adapters",
            "paradigma.application",
            "paradigma.cli",
            "paradigma.integrations.research",
            "paradigma.storage",
        )
        for path in sorted(coding.rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            with self.subTest(module=path.relative_to(PACKAGE).as_posix()):
                for module in forbidden:
                    self.assertNotIn(module, source)
                self.assertNotIn("from ...storage", source)
                self.assertNotIn("from ...application", source)

    def test_runtime_layer_does_not_depend_on_cli_adapters_or_application(self) -> None:
        runtime = PACKAGE / "runtime"
        forbidden = (
            "paradigma.adapters",
            "paradigma.application",
            "paradigma.cli",
            "paradigma.integrations.research",
        )
        for path in sorted(runtime.rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            with self.subTest(module=path.relative_to(PACKAGE).as_posix()):
                for module in forbidden:
                    self.assertNotIn(module, source)

    def test_memory_kernel_contains_no_domain_profile_semantics(self) -> None:
        kernel = PACKAGE / "kernel"
        forbidden = ("coding", "osint", "research profile", "cursor adapter")
        for path in sorted(kernel.rglob("*.py")):
            source = path.read_text(encoding="utf-8").lower()
            with self.subTest(module=path.relative_to(PACKAGE).as_posix()):
                for token in forbidden:
                    self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
