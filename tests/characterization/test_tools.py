from __future__ import annotations

import importlib.util
import json
import os
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

from paradigma.application.diagnosis import diagnose_outcome
from paradigma.application.validation import _strip_code_content, hot_size_outcome
from paradigma.errors import AtomicWriteFailure, ParseFailure
from paradigma.parser import parse_flat_frontmatter
import paradigma.application.tasks as task_service
EXPECTED_TOOLS = {
    "pd-archive-task.py",
    "pd-check-all.py",
    "pd-check-hot-size.py",
    "pd-check-links.py",
    "pd-compact-progress.py",
    "pd-diagnose.py",
    "pd-index.py",
    "pd-lint-okf.py",
    "pd-sync-index.py",
    "pd-version.py",
}


def run_tool(
    script: str,
    *args: str,
    cwd: Path = ROOT,
    tools_root: Path = TOOLS,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(tools_root / script), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def load_tool(script: str):
    module_name = "characterization_" + script.removesuffix(".py").replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, TOOLS / script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def copy_package_runtime(project: Path, tools: Path) -> None:
    shutil.copy2(TOOLS / "_bootstrap.py", tools / "_bootstrap.py")
    shutil.copytree(SRC / "paradigma", project / "src" / "paradigma")


class ToolInventoryTests(unittest.TestCase):
    def test_expected_tool_inventory(self) -> None:
        actual = {
            path.name for path in TOOLS.glob("*.py") if not path.name.startswith("_")
        }
        self.assertEqual(EXPECTED_TOOLS, actual)

    def test_every_tool_exposes_help(self) -> None:
        for script in sorted(EXPECTED_TOOLS):
            with self.subTest(script=script):
                result = run_tool(script, "--help")
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn("usage:", result.stdout.lower())


class RepositoryCliBaselineTests(unittest.TestCase):
    def assert_tool_passes(self, script: str, *args: str) -> str:
        result = run_tool(script, *args)
        self.assertEqual(
            0,
            result.returncode,
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        return result.stdout

    def test_strict_lint_passes(self) -> None:
        output = self.assert_tool_passes("pd-lint-okf.py", "--strict")
        self.assertIn("errors=0, warnings=0, mode=strict", output)

    def test_link_check_passes(self) -> None:
        output = self.assert_tool_passes("pd-check-links.py", "--allow-warnings")
        self.assertIn("errors=0, warnings=0", output)

    def test_indexes_are_current(self) -> None:
        output = self.assert_tool_passes("pd-index.py", "verify")
        self.assertIn("Verified derived indexes; stale=0", output)

    def test_legacy_index_entrypoint_remains_compatible(self) -> None:
        output = self.assert_tool_passes("pd-sync-index.py", "--check")
        self.assertIn("Checked indexes; stale=0", output)

    def test_hot_size_check_passes(self) -> None:
        output = self.assert_tool_passes("pd-check-hot-size.py")
        self.assertIn("errors=0, warnings=0", output)

    def test_check_all_passes(self) -> None:
        output = self.assert_tool_passes("pd-check-all.py", "--keep-going")
        self.assertIn("All 6 checks passed", output)

    def test_version_report_is_consistent(self) -> None:
        output = self.assert_tool_passes("pd-version.py", "--verbose", "--check")
        self.assertIn("distribution_version: 0.7.0", output)
        self.assertIn("installed_distribution_version: 0.7.0", output)
        self.assertIn("config_schema_version: 0.4", output)
        self.assertIn("okf_version: 0.1", output)
        self.assertIn("document_schema_version: 0.2", output)

    def test_compact_progress_dry_run_does_not_write(self) -> None:
        summary = ROOT / "memory-bank" / "logs" / "progress" / "summary.md"
        before = summary.read_bytes() if summary.exists() else None
        output = self.assert_tool_passes("pd-compact-progress.py")
        after = summary.read_bytes() if summary.exists() else None
        self.assertEqual(before, after)
        self.assertIn("# Progress Summary", output)

    def test_compact_progress_forces_utf8_under_cp1252_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "兼容 workspace"
            tools = root / ".paradigma" / "tools"
            tools.mkdir(parents=True)
            shutil.copy2(TOOLS / "pd-compact-progress.py", tools)
            copy_package_runtime(root, tools)
            progress = root / "memory-bank" / "logs" / "progress"
            progress.mkdir(parents=True)
            (progress / "session.md").write_text(
                """---
title: 中文会话
---

# Session

- 已完成编码回归
""",
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment["PYTHONIOENCODING"] = "cp1252"
            result = subprocess.run(
                [sys.executable, str(tools / "pd-compact-progress.py")],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("中文会话", result.stdout)
            self.assertIn("已完成编码回归", result.stdout)

    def test_self_diagnose_reports_current_harness_baseline(self) -> None:
        output = self.assert_tool_passes(
            "pd-diagnose.py",
            "--project",
            str(ROOT),
            "--upstream",
            str(ROOT),
            "--json",
        )
        report = json.loads(output)
        self.assertEqual("0.7.0", report["detected_version"])
        self.assertEqual("0.7.0", report["upstream_version"])
        self.assertTrue(report["version_match"])
        self.assertEqual([], report["gaps"])


class IsolatedMutationBaselineTests(unittest.TestCase):
    def make_archive_repository(self, root: Path) -> Path:
        tools = root / ".paradigma" / "tools"
        tools.mkdir(parents=True)
        shutil.copy2(TOOLS / "pd-archive-task.py", tools)
        shutil.copy2(TOOLS / "_paradigma_yaml.py", tools)
        shutil.copy2(TOOLS / "_task_state.py", tools)
        copy_package_runtime(root, tools)

        runtime = root / "memory-bank" / "runtime"
        runtime.mkdir(parents=True)
        (runtime / "active-task.md").write_text(
            """# Active Task

## Task ID

TASK-001

## Current Status

completed

## Checklist

- [x] characterized
""",
            encoding="utf-8",
        )

        template = root / "memory-bank-template" / "runtime"
        template.mkdir(parents=True)
        (template / "active-task.template.md").write_text(
            """---
timestamp: YYYY-MM-DDTHH:mm:ssZ
---

# Active Task

## Task ID

## Current Status

pending

## Checklist

- [ ] Step 1

## Notes
""",
            encoding="utf-8",
        )
        return tools

    def test_archive_dry_run_is_non_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tools = self.make_archive_repository(root)
            active = root / "memory-bank" / "runtime" / "active-task.md"
            before = active.read_bytes()

            result = run_tool(
                "pd-archive-task.py",
                "--dry-run",
                cwd=root,
                tools_root=tools,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("Dry run only", result.stdout)
            self.assertIn("Mutation plan:", result.stdout)
            self.assertEqual(before, active.read_bytes())
            progress = root / "memory-bank" / "logs" / "progress"
            self.assertFalse(progress.exists())

    def test_archive_write_creates_log_and_resets_active_task(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tools = self.make_archive_repository(root)

            result = run_tool(
                "pd-archive-task.py",
                "--write",
                cwd=root,
                tools_root=tools,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            logs = list((root / "memory-bank" / "logs" / "progress").glob("*.md"))
            self.assertEqual(1, len(logs))
            self.assertIn("TASK-001", logs[0].read_text(encoding="utf-8"))
            active = (root / "memory-bank" / "runtime" / "active-task.md").read_text(
                encoding="utf-8"
            )
            self.assertNotIn("TASK-001", active)
            self.assertNotIn("YYYY-MM-DDTHH:mm:ssZ", active)
            self.assertIn("\n\npending\n", active)
            self.assertIn("Last archive ID:", active)

            repeated = run_tool(
                "pd-archive-task.py",
                "--write",
                cwd=root,
                tools_root=tools,
            )
            self.assertEqual(0, repeated.returncode, repeated.stderr)
            self.assertIn("Already archived", repeated.stdout)
            repeated_logs = list(
                (root / "memory-bank" / "logs" / "progress").glob("*.md")
            )
            self.assertEqual(1, len(repeated_logs))

    def test_archive_interruption_is_recoverable_without_duplicate_log(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_archive_repository(root)
            active = root / "memory-bank" / "runtime" / "active-task.md"
            progress = root / "memory-bank" / "logs" / "progress"
            active_text = active.read_text(encoding="utf-8")
            plan = task_service.build_archive_plan(
                root, task_service.datetime.now().astimezone(), force=False
            )
            injected = AtomicWriteFailure(active, "atomic replace", OSError("injected"))
            with mock.patch.object(
                task_service, "atomic_replace_text", side_effect=injected
            ):
                with self.assertRaises(task_service.ArchiveFailure) as raised:
                    task_service.execute_archive_plan(plan)
            self.assertEqual("PD_ARCHIVE_IO_ERROR", raised.exception.code)
            self.assertEqual(active_text, active.read_text(encoding="utf-8"))
            self.assertTrue(plan.target.exists())

            recovery = task_service.build_archive_plan(
                root, task_service.datetime.now().astimezone(), force=False
            )
            self.assertFalse(recovery.create_archive)
            self.assertEqual(plan.target, recovery.target)
            task_service.execute_archive_plan(recovery)

            self.assertIn("\n\npending\n", active.read_text(encoding="utf-8"))
            self.assertEqual(1, len(list(progress.glob("*.md"))))

    def test_archive_cli_rejects_unknown_status_with_stable_code(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tools = self.make_archive_repository(root)
            active = root / "memory-bank" / "runtime" / "active-task.md"
            active.write_text(
                active.read_text(encoding="utf-8").replace("completed", "未完成"),
                encoding="utf-8",
            )

            result = run_tool(
                "pd-archive-task.py",
                "--write",
                cwd=root,
                tools_root=tools,
            )

            self.assertEqual(1, result.returncode)
            self.assertIn("PD_ARCHIVE_INVALID_STATUS", result.stderr)
            self.assertFalse((root / "memory-bank" / "logs" / "progress").exists())

    def test_archive_plan_rejects_source_change_before_any_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_archive_repository(root)
            active = root / "memory-bank" / "runtime" / "active-task.md"
            progress = root / "memory-bank" / "logs" / "progress"
            plan = task_service.build_archive_plan(
                root, task_service.datetime.now().astimezone(), force=False
            )
            active.write_text(
                active.read_text(encoding="utf-8") + "\nuser edit\n",
                encoding="utf-8",
            )
            with self.assertRaises(task_service.ArchiveFailure) as raised:
                task_service.execute_archive_plan(plan)

            self.assertEqual("PD_ARCHIVE_SOURCE_CHANGED", raised.exception.code)
            self.assertFalse(progress.exists())

    def test_compact_write_preserves_source_logs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tools = root / ".paradigma" / "tools"
            tools.mkdir(parents=True)
            shutil.copy2(TOOLS / "pd-compact-progress.py", tools)
            shutil.copy2(TOOLS / "_paradigma_yaml.py", tools)
            copy_package_runtime(root, tools)
            progress = root / "memory-bank" / "logs" / "progress"
            progress.mkdir(parents=True)
            source = progress / "2026-07-22-session.md"
            source.write_text(
                """---
title: Characterization Session
---

# Session

- Preserved signal
""",
                encoding="utf-8",
            )
            before = source.read_bytes()

            result = run_tool(
                "pd-compact-progress.py",
                "--write",
                cwd=root,
                tools_root=tools,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(before, source.read_bytes())
            summary = (progress / "summary.md").read_text(encoding="utf-8")
            self.assertIn("Characterization Session", summary)
            self.assertIn("Preserved signal", summary)


class ParserAndFunctionBaselineTests(unittest.TestCase):
    def test_shared_parser_flattens_supported_nested_lists(self) -> None:
        source = """knowledge_roots:
  - memory-bank/knowledge
  - docs/rfc
paradigma:
  temperature: warm
"""
        parser = load_tool("_paradigma_yaml.py")
        parsed = parser.flatten_mapping(parser.load_yaml_text(source))
        self.assertEqual(
            ["memory-bank/knowledge", "docs/rfc"], parsed["knowledge_roots"]
        )
        self.assertEqual("warm", parsed["paradigma.temperature"])

    def test_diagnose_upstream_version_uses_root_distribution_version(self) -> None:
        diagnose = load_tool("pd-diagnose.py")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / ".paradigma"
            config.mkdir()
            (config / "config.yaml").write_text(
                'paradigma_harness_version: "0.4.2"\n', encoding="utf-8"
            )
            (root / "VERSION").write_text("0.5.0\n", encoding="utf-8")
            self.assertEqual("0.5.0", diagnose._read_upstream_version(root))

    def test_diagnose_reads_legacy_harness_version_for_migration(self) -> None:
        diagnose = load_tool("pd-diagnose.py")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / ".paradigma"
            config.mkdir()
            (config / "config.yaml").write_text(
                'paradigma_harness_version: "0.4.2"\n', encoding="utf-8"
            )
            self.assertEqual("0.4.2", diagnose._detect_version(root))
            report = diagnose_outcome(root, ROOT)
            self.assertTrue(
                any(gap["kind"] == "deprecated" for gap in report.data["gaps"]),
                report.data["gaps"],
            )

    def test_version_check_rejects_distribution_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tools = root / ".paradigma" / "tools"
            schemas = root / ".paradigma" / "schemas"
            tools.mkdir(parents=True)
            schemas.mkdir(parents=True)
            shutil.copy2(TOOLS / "_paradigma_yaml.py", tools)
            shutil.copy2(TOOLS / "_version.py", tools)
            shutil.copy2(TOOLS / "pd-version.py", tools)
            copy_package_runtime(root, tools)
            (root / "VERSION").write_text("0.5.0\n", encoding="utf-8")
            (root / ".paradigma" / "config.yaml").write_text(
                """config_schema_version: "0.2"
okf_version: "0.1"
installed_distribution_version: "0.4.2"
""",
                encoding="utf-8",
            )
            (schemas / "paradigma-types.schema.yaml").write_text(
                'document_schema_version: "0.2"\n', encoding="utf-8"
            )

            result = run_tool(
                "pd-version.py", "--check", cwd=root, tools_root=tools
            )

            self.assertEqual(1, result.returncode)
            self.assertIn("does not match root VERSION", result.stdout)

    def test_version_model_rejects_legacy_field_names(self) -> None:
        versioning = load_tool("_version.py")
        info = versioning.VersionInfo(
            distribution_version="0.5.0",
            installed_distribution_version="0.5.0",
            config_schema_version="0.2",
            okf_version="0.1",
            document_schema_version="0.2",
            legacy_harness_version="0.4.2",
            legacy_config_schema_version="0.1",
            legacy_document_schema_version="0.1",
        )
        errors = versioning.validate_version_info(info)
        self.assertEqual(3, len(errors))
        self.assertTrue(any("paradigma_harness_version" in error for error in errors))
        self.assertTrue(any("config schema_version" in error for error in errors))
        self.assertTrue(any("registry schema_version" in error for error in errors))

    def test_archive_completion_baseline(self) -> None:
        archive = load_tool("pd-archive-task.py")
        completed = "## Current Status\n\ncompleted\n\n## Checklist\n\n- [x] done\n"
        active = "## Current Status\n\nactive\n\n## Checklist\n\n- [ ] pending\n"
        checklist_only = "## Current Status\n\nactive\n\n## Checklist\n\n- [x] done\n"
        self.assertTrue(archive.is_completed(completed))
        self.assertFalse(archive.is_completed(active))
        self.assertFalse(archive.is_completed(checklist_only))

    def test_archive_rejects_unknown_natural_language_status(self) -> None:
        archive = load_tool("pd-archive-task.py")
        source = "## Current Status\n\n未完成\n"
        with self.assertRaises(archive.ArchiveFailure) as raised:
            archive.parse_status(source)
        self.assertEqual("PD_ARCHIVE_INVALID_STATUS", raised.exception.code)
        with self.assertRaises(archive.ArchiveFailure):
            archive.parse_status("## Current Status\n\nCompleted.\n")

    def test_hot_size_gate_rejects_unknown_active_task_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / ".paradigma"
            config.mkdir()
            (config / "config.yaml").write_text(
                """config_schema_version: "0.3"
okf_version: "0.1"
installed_distribution_version: "0.5.1"
knowledge_roots: [memory-bank/knowledge]
reserved_filenames: [index.md, log.md]
machine_index_path: .paradigma/cache/knowledge-index.json
""",
                encoding="utf-8",
            )
            active = root / "memory-bank" / "runtime" / "active-task.md"
            active.parent.mkdir(parents=True)
            active.write_text(
                "## Current Status\n\nIn progress.\n", encoding="utf-8"
            )
            outcome = hot_size_outcome(root)
            self.assertEqual("PD_TASK_INVALID_STATUS", outcome.diagnostics[0].code)

    def test_link_checker_strips_code_regions(self) -> None:
        source = """Visible [link](missing.md).

```markdown
[ignored](inside-fence.md)
```

Inline `[ignored](inline.md)`.
"""
        stripped = _strip_code_content(source)
        self.assertIn("[link](missing.md)", stripped)
        self.assertNotIn("inside-fence.md", stripped)
        self.assertNotIn("inline.md", stripped)


class SharedYamlParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.parser = load_tool("_paradigma_yaml.py")

    def assert_parse_code(self, expected: str, callback) -> None:
        with self.assertRaises(self.parser.ParseFailure) as raised:
            callback()
        self.assertEqual(expected, raised.exception.diagnostic.code)

    def test_frontmatter_accepts_bom_crlf_and_chinese(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "中文.md"
            path.write_bytes(
                b"\xef\xbb\xbf---\r\ntitle: \xe4\xb8\xad\xe6\x96\x87\xe6\xa0\x87\xe9\xa2\x98\r\ntimestamp: 2026-07-22T23:59:14+08:00\r\n---\r\n\r\n# Body\r\n"
            )
            parsed = self.parser.parse_markdown_file(path)
            self.assertEqual("中文标题", parsed.metadata["title"])
            self.assertEqual(
                "2026-07-22T23:59:14+08:00", parsed.metadata["timestamp"]
            )
            self.assertIn("# Body", parsed.body)

    def test_invalid_yaml_has_syntax_diagnostic_and_source_line(self) -> None:
        def parse() -> None:
            self.parser.parse_markdown_text(
                "---\ntags: [one, two\n---\n# Body\n", source="broken.md"
            )

        with self.assertRaises(self.parser.ParseFailure) as raised:
            parse()
        diagnostic = raised.exception.diagnostic
        self.assertEqual("YAML_SYNTAX_ERROR", diagnostic.code)
        self.assertEqual("broken.md", diagnostic.source)
        self.assertEqual(2, diagnostic.line)

    def test_duplicate_keys_are_rejected(self) -> None:
        self.assert_parse_code(
            "YAML_DUPLICATE_KEY",
            lambda: self.parser.load_yaml_text("title: one\ntitle: two\n"),
        )

    def test_non_mapping_yaml_root_is_rejected(self) -> None:
        self.assert_parse_code(
            "YAML_ROOT_TYPE_ERROR",
            lambda: self.parser.load_yaml_text("- one\n- two\n"),
        )

    def test_missing_and_unclosed_frontmatter_are_distinct(self) -> None:
        self.assert_parse_code(
            "FRONTMATTER_MISSING",
            lambda: self.parser.parse_markdown_text("# Body\n"),
        )
        self.assert_parse_code(
            "FRONTMATTER_UNCLOSED",
            lambda: self.parser.parse_markdown_text("---\ntitle: Test\n"),
        )

    def test_invalid_utf8_has_encoding_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "invalid.md"
            path.write_bytes(b"---\ntitle: \xff\n---\n")
            self.assert_parse_code(
                "ENCODING_ERROR", lambda: self.parser.parse_markdown_file(path)
            )

    def test_linter_preserves_parser_diagnostic_from_schema_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "broken.md"
            path.write_text("---\ntitle: [broken\n---\n", encoding="utf-8")
            with self.assertRaises(ParseFailure) as raised:
                parse_flat_frontmatter(path)
            self.assertEqual("YAML_SYNTAX_ERROR", raised.exception.diagnostic.code)

    def test_every_yaml_consumer_routes_through_shared_parser(self) -> None:
        consumers = {
            "_version.py",
            "_index.py",
            "pd-archive-task.py",
            "pd-check-hot-size.py",
            "pd-check-links.py",
            "pd-compact-progress.py",
            "pd-diagnose.py",
            "pd-lint-okf.py",
        }
        for script in sorted(consumers):
            with self.subTest(script=script):
                source = (TOOLS / script).read_text(encoding="utf-8")
                self.assertTrue(
                    "from paradigma" in source or "from _paradigma_yaml import" in source
                )
                self.assertNotIn("import yaml", source)
                self.assertNotIn("def parse_yaml_subset", source)


class DerivedIndexBoundaryTests(unittest.TestCase):
    def make_index_repository(self, root: Path) -> None:
        config = root / ".paradigma"
        config.mkdir(parents=True)
        (config / "config.yaml").write_text(
            """config_schema_version: "0.3"
okf_version: "0.1"
installed_distribution_version: "0.5.1"
knowledge_roots:
  - memory-bank/knowledge
reserved_filenames:
  - index.md
  - log.md
machine_index_path: .paradigma/cache/knowledge-index.json
""",
            encoding="utf-8",
        )
        knowledge = root / "memory-bank" / "knowledge"
        nested = knowledge / "domains" / "nested"
        nested.mkdir(parents=True)
        (knowledge / "index.md").write_text(
            "# Knowledge Navigation\n\n* [Domains](domains/)\n",
            encoding="utf-8",
        )
        self.write_concept(knowledge / "root-concept.md", "Root Concept")
        self.write_concept(knowledge / "domains" / "direct.md", "Direct Concept")
        self.write_concept(nested / "deep.md", "Deep Concept")

    @staticmethod
    def write_concept(path: Path, title: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"""---
type: test-concept
title: {title}
description: Test concept.
tags: [test]
timestamp: 2026-07-23T21:30:22+08:00
paradigma:
  retrieval_hints:
    en: [test]
---

# {title}
""",
            encoding="utf-8",
        )

    def test_root_navigation_is_constant_and_local_indexes_are_non_recursive(self) -> None:
        index = load_tool("_index.py")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_index_repository(root)
            settings = index.load_settings(root)
            root_index = root / "memory-bank" / "knowledge" / "index.md"
            navigation_text = index.normalize_newlines(
                root_index.read_text(encoding="utf-8")
            )
            root_index.write_text(
                root_index.read_text(encoding="utf-8")
                + f"\n{index.BEGIN_MARKER}\nlegacy recursive rows\n{index.END_MARKER}\n",
                encoding="utf-8",
            )

            first = index.rebuild_indexes(settings)
            self.assertEqual(3, first.concept_count)
            self.assertEqual(navigation_text, root_index.read_text(encoding="utf-8"))
            self.assertNotIn(index.BEGIN_MARKER, root_index.read_text(encoding="utf-8"))
            navigation = root_index.read_bytes()

            domain_index = root / "memory-bank" / "knowledge" / "domains" / "index.md"
            domain_text = domain_index.read_text(encoding="utf-8")
            self.assertIn("direct.md", domain_text)
            self.assertNotIn("deep.md", domain_text)
            nested_text = (
                root
                / "memory-bank"
                / "knowledge"
                / "domains"
                / "nested"
                / "index.md"
            ).read_text(encoding="utf-8")
            self.assertIn("deep.md", nested_text)

            for number in range(20):
                self.write_concept(
                    root / "memory-bank" / "knowledge" / f"extra-{number}.md",
                    f"Extra {number}",
                )
            second = index.rebuild_indexes(settings)
            self.assertEqual(23, second.concept_count)
            self.assertEqual(navigation, root_index.read_bytes())

    def test_machine_cache_corruption_does_not_change_canonical_knowledge(self) -> None:
        index = load_tool("_index.py")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_index_repository(root)
            settings = index.load_settings(root)
            canonical = {
                path.relative_to(root): path.read_bytes()
                for path in (root / "memory-bank" / "knowledge").rglob("*.md")
                if path.name != "index.md"
            }
            index.rebuild_indexes(settings)
            settings.cache_path.write_text("{broken", encoding="utf-8")

            checks = index.verify_indexes(settings)
            machine = [item for item in checks if item.label == "machine cache"]
            self.assertEqual(1, len(machine))
            self.assertFalse(machine[0].current)
            self.assertEqual(
                canonical,
                {
                    path.relative_to(root): path.read_bytes()
                    for path in (root / "memory-bank" / "knowledge").rglob("*.md")
                    if path.name != "index.md"
                },
            )

            index.rebuild_indexes(settings)
            self.assertTrue(all(item.current for item in index.verify_indexes(settings)))


if __name__ == "__main__":
    unittest.main()
