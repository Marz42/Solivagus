from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paradigma.integrations.coding import (
    BuildEvidence,
    CodingCheckpoint,
    CodingSession,
    CodingTask,
    EvidenceStatus,
    GitEvidence,
    RepositoryScope,
    SessionStatus,
    TaskStatus,
    TaskAction,
    TaskTransitionError,
    TestEvidence,
    transition_task,
)


NOW = datetime(2026, 7, 24, 2, 0, tzinfo=timezone.utc)
DIGEST = "sha256:" + "a" * 64


def repository() -> RepositoryScope:
    return RepositoryScope(
        workspace_id="workspace-1",
        repository_id="paradigma",
        repository_path="repos/paradigma",
        remote_url="https://example.test/paradigma.git",
    )


class RepositoryScopeTests(unittest.TestCase):
    def test_scope_projects_coding_identity_into_generic_memory_scope(self) -> None:
        scope = repository().memory_scope(
            task_id="TASK-001",
            session_id="SESSION-001",
            entity_ids=("src/paradigma",),
        )

        self.assertEqual("coding", scope.namespace)
        self.assertEqual("workspace-1", scope.workspace_id)
        self.assertEqual("paradigma", scope.project_id)
        self.assertEqual("TASK-001", scope.task_id)
        self.assertEqual("SESSION-001", scope.session_id)

    def test_repository_and_memory_scope_reject_ambiguous_paths_and_ids(self) -> None:
        with self.assertRaisesRegex(ValueError, "POSIX"):
            RepositoryScope("workspace-1", "repo", "src\\repo")
        with self.assertRaisesRegex(ValueError, "TASK"):
            repository().memory_scope(task_id="task-1")
        with self.assertRaisesRegex(ValueError, "duplicates"):
            repository().memory_scope(entity_ids=("symbol:A", "symbol:A"))


class CodingTaskAndSessionTests(unittest.TestCase):
    def test_task_is_immutable_and_accepts_string_status(self) -> None:
        task = CodingTask(
            task_id="TASK-001",
            repository=repository(),
            title="Coding domain",
            goal="Define deterministic domain values.",
            status="active",
            created_at=NOW,
            updated_at=NOW,
        )

        self.assertIs(TaskStatus.ACTIVE, task.status)
        with self.assertRaises(FrozenInstanceError):
            task.status = TaskStatus.COMPLETED  # type: ignore[misc]

    def test_blocked_and_suspended_tasks_require_a_reason(self) -> None:
        for status in (TaskStatus.BLOCKED, TaskStatus.SUSPENDED):
            with self.subTest(status=status):
                with self.assertRaisesRegex(ValueError, "status_reason"):
                    CodingTask(
                        "TASK-001",
                        repository(),
                        "Task",
                        "Goal",
                        status,
                        NOW,
                        NOW,
                    )

    def test_task_rejects_invalid_identity_parent_and_time(self) -> None:
        with self.assertRaisesRegex(ValueError, "TASK"):
            CodingTask("bad", repository(), "Task", "Goal", "active", NOW, NOW)
        with self.assertRaisesRegex(ValueError, "differ"):
            CodingTask(
                "TASK-001",
                repository(),
                "Task",
                "Goal",
                "active",
                NOW,
                NOW,
                parent_task_id="TASK-001",
            )
        with self.assertRaisesRegex(ValueError, "before"):
            CodingTask(
                "TASK-001",
                repository(),
                "Task",
                "Goal",
                "active",
                NOW,
                NOW - timedelta(seconds=1),
            )

    def test_session_requires_consistent_terminal_time(self) -> None:
        active = CodingSession(
            "SESSION-001",
            "TASK-001",
            repository(),
            "active",
            NOW,
            NOW,
            agent_id="codex",
        )
        self.assertIs(SessionStatus.ACTIVE, active.status)

        with self.assertRaisesRegex(ValueError, "requires ended_at"):
            CodingSession(
                "SESSION-001",
                "TASK-001",
                repository(),
                "ended",
                NOW,
                NOW,
            )
        with self.assertRaisesRegex(ValueError, "must not have ended_at"):
            CodingSession(
                "SESSION-001",
                "TASK-001",
                repository(),
                "active",
                NOW,
                NOW + timedelta(seconds=1),
                ended_at=NOW + timedelta(seconds=1),
            )


class CodingTaskTransitionTests(unittest.TestCase):
    def make_task(self, status: TaskStatus | str = "pending", reason=None) -> CodingTask:
        return CodingTask(
            "TASK-001",
            repository(),
            "Task",
            "Goal",
            status,
            NOW,
            NOW,
            status_reason=reason,
        )

    def test_valid_transition_chain_is_pure_and_clears_transient_reason(self) -> None:
        pending = self.make_task()
        active = transition_task(pending, "start", at=NOW + timedelta(seconds=1))
        blocked = transition_task(
            active,
            TaskAction.BLOCK,
            at=NOW + timedelta(seconds=2),
            reason="Waiting for CI",
        )
        unblocked = transition_task(
            blocked, "unblock", at=NOW + timedelta(seconds=3)
        )
        completed = transition_task(
            unblocked, "complete", at=NOW + timedelta(seconds=4)
        )

        self.assertIs(TaskStatus.PENDING, pending.status)
        self.assertIs(TaskStatus.ACTIVE, active.status)
        self.assertEqual("Waiting for CI", blocked.status_reason)
        self.assertIsNone(unblocked.status_reason)
        self.assertIs(TaskStatus.COMPLETED, completed.status)

    def test_suspend_resume_and_abort_require_explicit_legal_actions(self) -> None:
        active = self.make_task("active")
        suspended = transition_task(
            active,
            "suspend",
            at=NOW + timedelta(seconds=1),
            reason="Switching priority",
        )
        resumed = transition_task(
            suspended, "resume", at=NOW + timedelta(seconds=2)
        )
        aborted = transition_task(
            resumed,
            "abort",
            at=NOW + timedelta(seconds=3),
            reason="No longer needed",
        )
        self.assertIs(TaskStatus.SUSPENDED, suspended.status)
        self.assertIs(TaskStatus.ACTIVE, resumed.status)
        self.assertIs(TaskStatus.ABORTED, aborted.status)

    def test_illegal_transition_reason_and_time_are_rejected(self) -> None:
        with self.assertRaisesRegex(TaskTransitionError, "cannot complete"):
            transition_task(self.make_task(), "complete", at=NOW)
        with self.assertRaisesRegex(TaskTransitionError, "requires a reason"):
            transition_task(self.make_task("active"), "block", at=NOW)
        with self.assertRaisesRegex(TaskTransitionError, "does not accept"):
            transition_task(
                self.make_task("active"), "complete", at=NOW, reason="done"
            )
        with self.assertRaisesRegex(TaskTransitionError, "before"):
            transition_task(
                self.make_task("active"),
                "complete",
                at=NOW - timedelta(seconds=1),
            )
        with self.assertRaisesRegex(TaskTransitionError, "cannot start"):
            transition_task(self.make_task("completed"), "start", at=NOW)


class CodingEvidenceTests(unittest.TestCase):
    def test_git_evidence_supports_clean_dirty_detached_and_unborn_states(self) -> None:
        clean = GitEvidence("paradigma", NOW, "a" * 40, "main", False)
        dirty = GitEvidence(
            "paradigma",
            NOW,
            None,
            None,
            True,
            ("src/paradigma/new.py",),
        )
        self.assertFalse(clean.dirty)
        self.assertIsNone(dirty.head_commit)

        with self.assertRaisesRegex(ValueError, "clean"):
            GitEvidence("paradigma", NOW, "a" * 40, "main", False, ("README.md",))
        with self.assertRaisesRegex(ValueError, "lowercase hex"):
            GitEvidence("paradigma", NOW, "NOT-A-COMMIT", "main", False)

    def test_test_evidence_preserves_counts_duration_report_and_digest(self) -> None:
        evidence = TestEvidence(
            command="python -m unittest",
            status="passed",
            observed_at=NOW,
            exit_code=0,
            passed_count=136,
            failed_count=0,
            skipped_count=0,
            duration_seconds=20.7,
            report_path="artifacts/test-report.xml",
            output_hash=DIGEST,
        )
        self.assertIs(EvidenceStatus.PASSED, evidence.status)
        self.assertEqual(136, evidence.passed_count)

        with self.assertRaisesRegex(ValueError, "cannot report failure"):
            TestEvidence("pytest", "passed", NOW, exit_code=1)
        with self.assertRaisesRegex(ValueError, "non-negative"):
            TestEvidence("pytest", "failed", NOW, failed_count=-1)

    def test_build_evidence_validates_artifacts_and_result(self) -> None:
        evidence = BuildEvidence(
            command="python -m build",
            status="passed",
            observed_at=NOW,
            exit_code=0,
            artifact_paths=("dist/paradigma-0.6.0.whl",),
            output_hash=DIGEST,
        )
        self.assertEqual(("dist/paradigma-0.6.0.whl",), evidence.artifact_paths)

        with self.assertRaisesRegex(ValueError, "non-zero"):
            BuildEvidence("build", "passed", NOW, exit_code=2)
        with self.assertRaisesRegex(ValueError, "inside"):
            BuildEvidence("build", "failed", NOW, artifact_paths=("../secret",))


class CodingCheckpointTests(unittest.TestCase):
    def test_checkpoint_separates_tool_evidence_from_agent_narrative(self) -> None:
        git = GitEvidence("paradigma", NOW, "b" * 40, "main", True, ("src/a.py",))
        tests = (TestEvidence("python -m unittest", "passed", NOW, exit_code=0),)
        builds = (BuildEvidence("python -m build", "passed", NOW, exit_code=0),)
        checkpoint = CodingCheckpoint(
            checkpoint_id="CHECKPOINT-001",
            task_id="TASK-001",
            session_id="SESSION-001",
            created_at=NOW,
            task_status="active",
            git=git,
            tests=tests,
            builds=builds,
            touched_paths=("src/a.py", "tests/test_a.py"),
            summary="Domain values implemented.",
            completed_work=("Added immutable values",),
            remaining_work=("Add YAML codec",),
            next_steps=("Start Batch 3.2",),
        )

        self.assertIs(TaskStatus.ACTIVE, checkpoint.task_status)
        self.assertEqual(git, checkpoint.git)
        self.assertEqual(tests, checkpoint.tests)

    def test_checkpoint_rejects_wrong_evidence_and_unexplained_block(self) -> None:
        with self.assertRaisesRegex(ValueError, "TestEvidence"):
            CodingCheckpoint(
                "CHECKPOINT-001",
                "TASK-001",
                "SESSION-001",
                NOW,
                "active",
                tests=("not evidence",),  # type: ignore[arg-type]
            )
        with self.assertRaisesRegex(ValueError, "blocker"):
            CodingCheckpoint(
                "CHECKPOINT-001",
                "TASK-001",
                "SESSION-001",
                NOW,
                "blocked",
            )


if __name__ == "__main__":
    unittest.main()
