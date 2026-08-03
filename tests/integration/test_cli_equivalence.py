from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
TOOLS = ROOT / ".paradigma" / "tools"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paradigma.cli.main import main


def run_new(*args: str) -> tuple[int, str]:
    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(list(args))
    return exit_code, output.getvalue()


def run_legacy(script: str, *args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(cwd / ".paradigma" / "tools" / script), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


class CliEquivalenceTests(unittest.TestCase):
    def test_unified_cli_forces_utf8_for_structured_non_ascii_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "缺失版本"
            project.mkdir()
            environment = os.environ.copy()
            environment["PYTHONIOENCODING"] = "cp1252"
            environment["PYTHONPATH"] = os.pathsep.join(
                value
                for value in (str(SRC), environment.get("PYTHONPATH"))
                if value
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "paradigma.cli.main",
                    "version",
                    "--project",
                    str(project),
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(1, result.returncode, result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("缺失版本", payload["diagnostics"][0]["source"])

    def test_version_and_diagnose_json_preserve_legacy_data(self) -> None:
        legacy_version = run_legacy("pd-version.py", "--json")
        new_version_exit, new_version_text = run_new(
            "version", "--project", str(ROOT), "--format", "json"
        )
        self.assertEqual(legacy_version.returncode, new_version_exit)
        legacy_version_data = json.loads(legacy_version.stdout)
        new_version_data = json.loads(new_version_text)["data"]
        legacy_version_data.pop("errors")
        self.assertEqual(legacy_version_data, new_version_data)

        legacy_diagnose = run_legacy(
            "pd-diagnose.py",
            "--project",
            str(ROOT),
            "--upstream",
            str(ROOT),
            "--json",
        )
        new_diagnose_exit, new_diagnose_text = run_new(
            "diagnose",
            "--project",
            str(ROOT),
            "--upstream",
            str(ROOT),
            "--format",
            "json",
        )
        self.assertEqual(legacy_diagnose.returncode, new_diagnose_exit)
        self.assertEqual(
            json.loads(legacy_diagnose.stdout),
            json.loads(new_diagnose_text)["data"],
        )

    def test_quality_and_index_exit_semantics_are_equivalent(self) -> None:
        legacy_check = run_legacy("pd-check-all.py", "--keep-going")
        new_check_exit, new_check_text = run_new(
            "check", "--project", str(ROOT), "--format", "json", "--dry-run"
        )
        self.assertEqual(legacy_check.returncode, new_check_exit)
        self.assertEqual(6, json.loads(new_check_text)["data"]["passed"])

        legacy_index = run_legacy("pd-index.py", "verify")
        new_index_exit, new_index_text = run_new(
            "index", "verify", "--project", str(ROOT), "--format", "json"
        )
        self.assertEqual(legacy_index.returncode, new_index_exit)
        self.assertIn("stale=0", legacy_index.stdout)
        self.assertEqual(0, json.loads(new_index_text)["data"]["stale"])

    def test_relocated_unicode_path_works_for_old_and_new_entrypoints(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "derived project 项目"
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

            legacy = run_legacy("pd-index.py", "rebuild", cwd=project)
            self.assertEqual(0, legacy.returncode, legacy.stderr)
            new_exit, output = run_new(
                "check", "--project", str(project), "--format", "json", "--dry-run"
            )
            self.assertEqual(0, new_exit, output)
            self.assertEqual(6, json.loads(output)["data"]["passed"])


if __name__ == "__main__":
    unittest.main()
