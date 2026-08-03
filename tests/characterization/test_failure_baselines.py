from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / ".paradigma" / "tools"
SRC = ROOT / "src"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paradigma.application.outcomes import CommandOutcome
from paradigma.application.indexing import BEGIN_MARKER, END_MARKER
from paradigma.application.validation import link_outcome
from paradigma.diagnostics import Diagnostic
from paradigma.parser import parse_flat_frontmatter
from paradigma.schema import (
    DocumentType,
    SchemaRegistry,
    validate_concept,
    validate_generated_index,
)


def load_tool(script: str):
    module_name = "failure_baseline_" + script.removesuffix(".py").replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, TOOLS / script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def run_tool(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOLS / script), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def copy_package_runtime(project: Path, tools: Path) -> None:
    shutil.copy2(TOOLS / "_bootstrap.py", tools / "_bootstrap.py")
    shutil.copytree(SRC / "paradigma", project / "src" / "paradigma")


class LintAndLinkFailureBaselines(unittest.TestCase):
    def test_strict_lint_rejects_schema_and_checksum_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            document = root / "concept.md"
            document.write_text(
                """---
type: test-concept
title: Test
timestamp: yesterday
---

# Wrong Section
                """,
                encoding="utf-8",
            )
            metadata, body = parse_flat_frontmatter(document)
            registry = SchemaRegistry(
                source=root / "schema.yaml",
                document_schema_version="0.2",
                required_frontmatter=("type", "title", "timestamp"),
                required_paradigma_fields=("temperature",),
                allowed_update_policies=(),
                allowed_epistemic_statuses=(),
                allowed_temperatures=(),
                allowed_lifecycles=(),
                document_types={
                    "test-concept": DocumentType(
                        "test-concept", "knowledge", "warm", ("Purpose",)
                    )
                },
            )
            messages = [
                issue.message
                for issue in validate_concept(
                    metadata, body, registry, source=str(document), strict=True
                )
            ]
            self.assertTrue(any("not ISO 8601" in message for message in messages))
            self.assertIn(
                "missing required paradigma field `temperature`", messages
            )
            self.assertIn("missing required section `# Purpose`", messages)

            index_path = root / "index.md"
            index_path.write_text(
                f"""# Index

{BEGIN_MARKER}
<!-- checksum: 0000000000000000 -->
generated content
{END_MARKER}
""",
                encoding="utf-8",
            )
            index_issues = validate_generated_index(
                index_path.read_text(encoding="utf-8"),
                source=str(index_path),
                strict=True,
            )
            self.assertTrue(
                any("checksum is stale" in issue.message for issue in index_issues)
            )

    def test_link_checker_distinguishes_errors_from_planned_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_root = root / ".paradigma"
            config_root.mkdir()
            (config_root / "config.yaml").write_text(
                """config_schema_version: "0.3"
okf_version: "0.1"
installed_distribution_version: "0.5.1"
knowledge_roots: [knowledge]
reserved_filenames: [index.md, log.md]
machine_index_path: .paradigma/cache/knowledge-index.json
""",
                encoding="utf-8",
            )
            document = root / "knowledge" / "concept.md"
            document.parent.mkdir()
            document.write_text(
                """---
type: test-concept
paradigma:
  relations:
    planned:
      - /future.md
---

[Missing](missing.md)
                """,
                encoding="utf-8",
            )
            issues = link_outcome(root).diagnostics
            self.assertEqual(
                [("error", "markdown"), ("warning", "planned")],
                [(issue.severity.value, issue.message.split()[1]) for issue in issues],
            )


class HotSizeAndVersionFailureBaselines(unittest.TestCase):
    def test_hot_size_threshold_and_fail_on_warn_contract(self) -> None:
        hot_size = load_tool("pd-check-hot-size.py")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_root = root / ".paradigma"
            config_root.mkdir()
            (config_root / "config.yaml").write_text(
                """config_schema_version: "0.3"
okf_version: "0.1"
installed_distribution_version: "0.5.1"
knowledge_roots: [memory-bank/knowledge]
reserved_filenames: [index.md, log.md]
machine_index_path: .paradigma/cache/knowledge-index.json
""",
                encoding="utf-8",
            )
            progress = root / "memory-bank" / "logs" / "progress" / "index.md"
            progress.parent.mkdir(parents=True)
            progress.write_text("line\n" * 161, encoding="utf-8")
            with mock.patch.object(hot_size, "ROOT", root):
                with mock.patch.object(sys, "argv", ["pd-check-hot-size.py"]):
                    with redirect_stdout(StringIO()):
                        self.assertEqual(0, hot_size.main())
                with mock.patch.object(
                    sys, "argv", ["pd-check-hot-size.py", "--fail-on-warn"]
                ):
                    with redirect_stdout(StringIO()):
                        self.assertEqual(1, hot_size.main())

    def test_version_cli_rejects_invalid_semver(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tools = root / ".paradigma" / "tools"
            schemas = root / ".paradigma" / "schemas"
            tools.mkdir(parents=True)
            schemas.mkdir(parents=True)
            for name in ("_paradigma_yaml.py", "_version.py", "pd-version.py"):
                shutil.copy2(TOOLS / name, tools / name)
            copy_package_runtime(root, tools)
            (root / "VERSION").write_text("release-next\n", encoding="utf-8")
            (root / ".paradigma" / "config.yaml").write_text(
                """config_schema_version: "0.3"
okf_version: "0.1"
installed_distribution_version: release-next
""",
                encoding="utf-8",
            )
            (schemas / "paradigma-types.schema.yaml").write_text(
                'document_schema_version: "0.2"\n', encoding="utf-8"
            )
            result = subprocess.run(
                [sys.executable, str(tools / "pd-version.py"), "--check"],
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(1, result.returncode)
            self.assertIn("distribution_version is not SemVer", result.stdout)


class DiagnoseAndCheckAllFailureBaselines(unittest.TestCase):
    def test_diagnose_unknown_workspace_has_machine_readable_exit_two(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = run_tool(
                "pd-diagnose.py",
                "--project",
                temporary,
                "--upstream",
                str(ROOT),
                "--json",
            )
            self.assertEqual(2, result.returncode)
            report = json.loads(result.stdout)
            self.assertEqual("unknown", report["detected_version"])
            self.assertEqual(1, report["summary"]["errors"])
            self.assertEqual("missing", report["gaps"][0]["kind"])

    def test_check_all_stops_on_first_failure_by_default(self) -> None:
        check_all = load_tool("pd-check-all.py")
        outcome = CommandOutcome(
            command="check",
            data={
                "total": 2,
                "steps": [
                    {"name": "version", "ok": False, "diagnostics": []},
                    {"name": "lint", "ok": True, "diagnostics": []},
                ],
            },
            diagnostics=(Diagnostic("PD_TEST", "failure", "test"),),
        )
        with mock.patch.object(check_all, "check_outcome", return_value=outcome) as run:
            with mock.patch.object(sys, "argv", ["pd-check-all.py"]):
                with redirect_stdout(StringIO()):
                    self.assertEqual(1, check_all.main())
        self.assertEqual(1, run.call_count)

    def test_check_all_keep_going_aggregates_failures(self) -> None:
        check_all = load_tool("pd-check-all.py")
        steps = [
            {"name": f"step-{index}", "ok": index not in (0, 2), "diagnostics": []}
            for index in range(6)
        ]
        outcome = CommandOutcome(
            command="check",
            data={"total": 6, "steps": steps},
            diagnostics=(Diagnostic("PD_TEST", "failure", "test"),),
        )
        output = StringIO()
        with mock.patch.object(check_all, "check_outcome", return_value=outcome) as run:
            with mock.patch.object(sys, "argv", ["pd-check-all.py", "--keep-going"]):
                with redirect_stdout(output):
                    self.assertEqual(1, check_all.main())
        self.assertEqual(1, run.call_count)
        self.assertIn("2/6 check(s) failed", output.getvalue())


class CompactFailureBaselines(unittest.TestCase):
    def make_progress_root(self, root: Path) -> tuple[Path, Path]:
        progress = root / "memory-bank" / "logs" / "progress"
        progress.mkdir(parents=True)
        source = progress / "2026-07-23-session.md"
        source.write_text(
            """---
title: Test Session
---

# Session

- Preserved source
""",
            encoding="utf-8",
        )
        return progress, source

    def test_compact_replace_failure_preserves_old_summary_and_sources(self) -> None:
        compact = load_tool("pd-compact-progress.py")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            progress, source = self.make_progress_root(root)
            summary = progress / "summary.md"
            summary.write_text("old summary\n", encoding="utf-8")
            summary_before = summary.read_bytes()
            source_before = source.read_bytes()
            stderr = StringIO()
            with mock.patch.object(compact, "ROOT", root):
                with mock.patch(
                    "paradigma.application.progress.atomic_replace_text",
                    side_effect=compact.CompactFailure(
                        "injected", code="PD_COMPACT_IO_ERROR"
                    ),
                ):
                    with mock.patch.object(
                        sys, "argv", ["pd-compact-progress.py", "--write"]
                    ):
                        with redirect_stderr(stderr):
                            self.assertEqual(1, compact.main())

            self.assertEqual(summary_before, summary.read_bytes())
            self.assertEqual(source_before, source.read_bytes())
            self.assertEqual([], list(progress.glob(".summary.md.*.tmp")))
            self.assertIn("PD_COMPACT_IO_ERROR", stderr.getvalue())

    def test_compact_invalid_source_does_not_replace_summary(self) -> None:
        compact = load_tool("pd-compact-progress.py")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            progress, source = self.make_progress_root(root)
            source.write_text("---\ntitle: [broken\n---\n", encoding="utf-8")
            summary = progress / "summary.md"
            summary.write_text("old summary\n", encoding="utf-8")
            summary_before = summary.read_bytes()
            stderr = StringIO()
            with mock.patch.object(compact, "ROOT", root):
                with mock.patch.object(
                    sys, "argv", ["pd-compact-progress.py", "--write"]
                ):
                    with redirect_stdout(StringIO()), redirect_stderr(stderr):
                        self.assertEqual(1, compact.main())

            self.assertEqual(summary_before, summary.read_bytes())
            self.assertIn("YAML_SYNTAX_ERROR", stderr.getvalue())


class IndexAtomicityBaselines(unittest.TestCase):
    def test_index_replace_failure_preserves_existing_file(self) -> None:
        import paradigma.atomic as atomic

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "knowledge-index.json"
            path.write_text("old index\n", encoding="utf-8")
            before = path.read_bytes()
            with mock.patch.object(atomic.os, "replace", side_effect=OSError("injected")):
                with self.assertRaises(OSError):
                    atomic.atomic_replace_text(path, "new index\n")

            self.assertEqual(before, path.read_bytes())
            self.assertEqual([], list(path.parent.glob(".knowledge-index.json.*.tmp")))


class ExternalWorkspaceBaselineTests(unittest.TestCase):
    def test_relocated_workspace_passes_rebuild_and_quality_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "derived-workspace"
            project.mkdir()
            for directory in (
                ".paradigma/tools",
                ".paradigma/schemas",
                "memory-bank/knowledge",
                "docs/rfc",
            ):
                shutil.copytree(
                    ROOT / directory,
                    project / directory,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                )
            shutil.copytree(SRC / "paradigma", project / "src" / "paradigma")
            for file_name in (
                ".paradigma/config.yaml",
                "VERSION",
                "memory-bank/runtime/active-task.md",
                "memory-bank/logs/progress/index.md",
            ):
                target = project / file_name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / file_name, target)

            tools = project / ".paradigma" / "tools"
            rebuild = subprocess.run(
                [sys.executable, str(tools / "pd-index.py"), "rebuild"],
                cwd=project,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(0, rebuild.returncode, rebuild.stderr)
            self.assertTrue(
                (project / ".paradigma" / "cache" / "knowledge-index.json").exists()
            )

            checks = subprocess.run(
                [sys.executable, str(tools / "pd-check-all.py"), "--keep-going"],
                cwd=project,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(
                0,
                checks.returncode,
                f"stdout:\n{checks.stdout}\nstderr:\n{checks.stderr}",
            )
            self.assertIn("All 6 checks passed", checks.stdout)


class ReleaseMigrationBaselineTests(unittest.TestCase):
    def test_v0_5_0_version_metadata_migration_is_repeatable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            tools = project / ".paradigma" / "tools"
            schemas = project / ".paradigma" / "schemas"
            tools.mkdir(parents=True)
            schemas.mkdir(parents=True)
            for name in ("_paradigma_yaml.py", "_version.py", "pd-version.py"):
                shutil.copy2(TOOLS / name, tools / name)
            copy_package_runtime(project, tools)

            (project / "VERSION").write_text("0.5.1\n", encoding="utf-8")
            config = project / ".paradigma" / "config.yaml"
            config.write_text(
                """okf_version: "0.1"
schema_version: "0.1"
paradigma_harness_version: "0.4.2"
""",
                encoding="utf-8",
            )
            schema = schemas / "paradigma-types.schema.yaml"
            schema.write_text('schema_version: "0.2"\n', encoding="utf-8")

            before = subprocess.run(
                [sys.executable, str(tools / "pd-version.py"), "--check"],
                cwd=project,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(1, before.returncode)
            self.assertIn("legacy paradigma_harness_version", before.stdout)

            config.write_text(
                """config_schema_version: "0.3"
okf_version: "0.1"
installed_distribution_version: "0.5.1"
machine_index_path: .paradigma/cache/knowledge-index.json
""",
                encoding="utf-8",
            )
            schema.write_text(
                'document_schema_version: "0.2"\n', encoding="utf-8"
            )

            for _attempt in range(2):
                after = subprocess.run(
                    [sys.executable, str(tools / "pd-version.py"), "--check"],
                    cwd=project,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                )
                self.assertEqual(0, after.returncode, after.stdout + after.stderr)
                self.assertIn("distribution=0.5.1", after.stdout)


if __name__ == "__main__":
    unittest.main()
