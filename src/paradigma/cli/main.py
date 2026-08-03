"""Unified Paradigma command-line interface."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

from ..application.configuration import config_validate_outcome
from ..application.catalog import (
    catalog_rebuild_outcome,
    catalog_stats_outcome,
    catalog_verify_outcome,
)
from ..application.coding_tasks import (
    start_task_outcome,
    task_status_outcome,
    transition_task_outcome,
)
from ..application.coding_sessions import (
    checkpoint_session_outcome,
    end_session_outcome,
    handoff_build_outcome,
    session_status_outcome,
    start_session_outcome,
)
from ..application.coding_context import (
    CodingContextError,
    context_build_outcome,
    context_verify_outcome,
)
from ..application.diagnosis import diagnose_outcome
from ..application.indexing import index_rebuild_outcome, index_verify_outcome
from ..application.memory import memory_explain_outcome, memory_query_outcome
from ..application.mutations import (
    commit_memory,
    forget_memory,
    mutation_outcome,
    propose_memory,
    revise_memory,
    supersede_memory,
    validate_memory,
    validation_outcome,
    MemoryInputError,
)
from ..application.tasks import archive_outcome
from ..application.validation import check_outcome
from ..application.versioning import version_outcome
from ..diagnostics import Diagnostic
from ..errors import DiagnosticError, ParadigmaError
from ..kernel import MemoryQuery, MemoryScope, MemoryStatus
from ..integrations.coding import ContextRequest
from ..parser import ParseFailure, load_yaml_file
from ..storage.catalog import CatalogQuery, CatalogTextMode
from ..application.outcomes import CommandOutcome
from ..application.runtime import (
    coding_runtime_init_outcome,
    coding_runtime_rebuild_outcome,
    coding_runtime_verify_outcome,
)
from .output import configure_utf8_stdio, render
from .evidence import collect_git, run_build, run_test


def _leaf_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format", choices=("text", "json"), default="text", dest="output_format"
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--project", type=Path, default=Path.cwd())


def _aware_datetime(value: str) -> datetime:
    try:
        instant = datetime.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an ISO 8601 datetime") from error
    if instant.tzinfo is None:
        raise argparse.ArgumentTypeError("must include a timezone offset")
    return instant


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pd", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    version = commands.add_parser("version", help="report version dimensions")
    _leaf_options(version)

    config = commands.add_parser("config", help="configuration commands")
    config_commands = config.add_subparsers(dest="config_command", required=True)
    config_validate = config_commands.add_parser("validate", help="validate config")
    _leaf_options(config_validate)

    check = commands.add_parser("check", help="run repository quality gates")
    _leaf_options(check)

    diagnose = commands.add_parser("diagnose", help="compare project with upstream")
    diagnose.add_argument("--upstream", type=Path, required=True)
    _leaf_options(diagnose)

    index = commands.add_parser("index", help="derived index commands")
    index_commands = index.add_subparsers(dest="index_command", required=True)
    index_rebuild = index_commands.add_parser("rebuild", help="rebuild indexes")
    _leaf_options(index_rebuild)
    index_verify = index_commands.add_parser("verify", help="verify indexes")
    _leaf_options(index_verify)

    runtime = commands.add_parser("runtime", help="Coding YAML runtime commands")
    runtime_commands = runtime.add_subparsers(dest="runtime_command", required=True)
    runtime_rebuild = runtime_commands.add_parser(
        "rebuild", help="rebuild Markdown projections from YAML facts"
    )
    _leaf_options(runtime_rebuild)
    runtime_verify = runtime_commands.add_parser(
        "verify", help="verify Markdown projections against YAML facts"
    )
    _leaf_options(runtime_verify)
    runtime_init = runtime_commands.add_parser(
        "init", help="initialize null Coding runtime pointers"
    )
    runtime_init.add_argument("--write", action="store_true")
    _leaf_options(runtime_init)

    catalog = commands.add_parser("catalog", help="derived memory catalog commands")
    catalog_commands = catalog.add_subparsers(dest="catalog_command", required=True)
    catalog_rebuild = catalog_commands.add_parser(
        "rebuild", help="rebuild the catalog from canonical Markdown"
    )
    _leaf_options(catalog_rebuild)
    catalog_verify = catalog_commands.add_parser(
        "verify", help="verify the catalog against canonical Markdown"
    )
    _leaf_options(catalog_verify)
    catalog_stats = catalog_commands.add_parser(
        "stats", help="report catalog statistics"
    )
    _leaf_options(catalog_stats)

    memory = commands.add_parser("memory", help="canonical memory lifecycle commands")
    memory_commands = memory.add_subparsers(dest="memory_command", required=True)
    memory_propose = memory_commands.add_parser(
        "propose", help="create a canonical candidate from a YAML payload"
    )
    memory_propose.add_argument("--input", type=Path, required=True)
    memory_propose.add_argument("--memory-id")
    memory_propose.add_argument("--write", action="store_true")
    _leaf_options(memory_propose)
    memory_validate = memory_commands.add_parser(
        "validate", help="validate a canonical memory and report its source hash"
    )
    memory_validate.add_argument("memory_id")
    _leaf_options(memory_validate)
    for name, help_text in (
        ("commit", "activate a canonical candidate"),
        ("forget", "tombstone a canonical memory"),
    ):
        command = memory_commands.add_parser(name, help=help_text)
        command.add_argument("memory_id")
        command.add_argument("--expected-source-hash", required=True)
        command.add_argument("--write", action="store_true")
        _leaf_options(command)
    memory_revise = memory_commands.add_parser(
        "revise", help="create the next revision from a YAML patch"
    )
    memory_revise.add_argument("memory_id")
    memory_revise.add_argument("--input", type=Path, required=True)
    memory_revise.add_argument("--expected-source-hash", required=True)
    memory_revise.add_argument("--write", action="store_true")
    _leaf_options(memory_revise)
    memory_supersede = memory_commands.add_parser(
        "supersede", help="mark an active memory as replaced by another active memory"
    )
    memory_supersede.add_argument("memory_id")
    memory_supersede.add_argument("--replacement-id", required=True)
    memory_supersede.add_argument("--expected-source-hash", required=True)
    memory_supersede.add_argument("--write", action="store_true")
    _leaf_options(memory_supersede)
    memory_query = memory_commands.add_parser(
        "query", help="query current canonical memories through the derived catalog"
    )
    memory_query.add_argument("text", nargs="?")
    memory_query.add_argument(
        "--text-mode",
        choices=tuple(item.value for item in CatalogTextMode),
        default=CatalogTextMode.FTS.value,
    )
    memory_query.add_argument("--memory-id", action="append", default=[])
    memory_query.add_argument("--path", action="append", default=[])
    memory_query.add_argument("--tag", action="append", default=[])
    memory_query.add_argument("--scope-namespace")
    memory_query.add_argument("--workspace-id")
    memory_query.add_argument("--project-id")
    memory_query.add_argument("--task-id")
    memory_query.add_argument("--session-id")
    memory_query.add_argument("--entity-id", action="append", default=[])
    memory_query.add_argument(
        "--status",
        action="append",
        choices=tuple(item.value for item in MemoryStatus),
    )
    memory_query.add_argument("--valid-at", type=_aware_datetime)
    memory_query.add_argument("--include-related", action="store_true")
    memory_query.add_argument("--relation-type", action="append", default=[])
    memory_query.add_argument("--limit", type=int, default=50)
    _leaf_options(memory_query)
    memory_explain = memory_commands.add_parser(
        "explain", help="explain canonical state and ordinary-query eligibility"
    )
    memory_explain.add_argument("memory_id")
    memory_explain.add_argument("--at", type=_aware_datetime)
    _leaf_options(memory_explain)

    task = commands.add_parser("task", help="task lifecycle commands")
    task_commands = task.add_subparsers(dest="task_command", required=True)
    task_status = task_commands.add_parser("status", help="show the active YAML task")
    _leaf_options(task_status)
    task_start = task_commands.add_parser("start", help="start a new CodingTask")
    task_start.add_argument("--task-id", required=True)
    task_start.add_argument("--title", required=True)
    task_start.add_argument("--goal", required=True)
    task_start.add_argument("--workspace-id", required=True)
    task_start.add_argument("--repository-id", required=True)
    task_start.add_argument("--repository-path", default=".")
    task_start.add_argument("--remote-url")
    task_start.add_argument("--parent-task-id")
    task_start.add_argument("--write", action="store_true")
    _leaf_options(task_start)
    for name in ("block", "unblock", "suspend", "resume", "complete", "abort"):
        command = task_commands.add_parser(name, help=f"{name} the active CodingTask")
        if name in ("block", "suspend", "abort"):
            command.add_argument("--reason", required=True)
        command.add_argument("--write", action="store_true")
        _leaf_options(command)
    task_archive = task_commands.add_parser("archive", help="archive active task")
    task_archive.add_argument("--write", action="store_true")
    task_archive.add_argument("--force", action="store_true")
    _leaf_options(task_archive)

    session = commands.add_parser("session", help="CodingSession lifecycle commands")
    session_commands = session.add_subparsers(dest="session_command", required=True)
    session_start = session_commands.add_parser("start", help="start a CodingSession")
    session_start.add_argument("--session-id", required=True)
    session_start.add_argument("--agent-id")
    session_start.add_argument("--write", action="store_true")
    _leaf_options(session_start)
    session_status = session_commands.add_parser("status", help="show active session")
    _leaf_options(session_status)
    session_checkpoint = session_commands.add_parser(
        "checkpoint", help="capture deterministic facts and Agent narrative"
    )
    session_checkpoint.add_argument("--checkpoint-id", required=True)
    session_checkpoint.add_argument("--input", type=Path)
    session_checkpoint.add_argument("--test-command")
    session_checkpoint.add_argument("--build-command")
    session_checkpoint.add_argument("--write", action="store_true")
    _leaf_options(session_checkpoint)
    session_end = session_commands.add_parser("end", help="end active session")
    session_end.add_argument("--write", action="store_true")
    _leaf_options(session_end)

    handoff = commands.add_parser("handoff", help="Coding handoff projection")
    handoff_commands = handoff.add_subparsers(dest="handoff_command", required=True)
    handoff_build = handoff_commands.add_parser("build", help="rebuild handoff from YAML")
    _leaf_options(handoff_build)

    context = commands.add_parser("context", help="deterministic Coding context assembly")
    context_commands = context.add_subparsers(dest="context_command", required=True)
    context_build = context_commands.add_parser("build", help="build an explainable context manifest")
    context_build.add_argument("--intent", required=True)
    context_build.add_argument("--task-id", required=True)
    context_build.add_argument("--path", action="append", default=[])
    context_build.add_argument("--symbol", action="append", default=[])
    context_build.add_argument("--keyword", action="append", default=[])
    context_build.add_argument("--budget", type=int, default=12000)
    context_build.add_argument("--write", action="store_true")
    _leaf_options(context_build)
    context_verify = context_commands.add_parser("verify", help="verify the current context manifest")
    _leaf_options(context_verify)
    return parser


def _dispatch(args: argparse.Namespace) -> CommandOutcome:
    root = args.project.resolve()
    if args.command == "version":
        return version_outcome(root, dry_run=args.dry_run)
    if args.command == "config" and args.config_command == "validate":
        return config_validate_outcome(root, dry_run=args.dry_run)
    if args.command == "check":
        return check_outcome(root, dry_run=args.dry_run)
    if args.command == "diagnose":
        return diagnose_outcome(root, args.upstream, dry_run=args.dry_run)
    if args.command == "index" and args.index_command == "rebuild":
        return index_rebuild_outcome(root, dry_run=args.dry_run)
    if args.command == "index" and args.index_command == "verify":
        return index_verify_outcome(root, dry_run=args.dry_run)
    if args.command == "runtime" and args.runtime_command == "rebuild":
        return coding_runtime_rebuild_outcome(root, dry_run=args.dry_run)
    if args.command == "runtime" and args.runtime_command == "verify":
        return coding_runtime_verify_outcome(root, dry_run=args.dry_run)
    if args.command == "runtime" and args.runtime_command == "init":
        return coding_runtime_init_outcome(
            root, write=bool(args.write and not args.dry_run)
        )
    if args.command == "catalog" and args.catalog_command == "rebuild":
        return catalog_rebuild_outcome(root, dry_run=args.dry_run)
    if args.command == "catalog" and args.catalog_command == "verify":
        return catalog_verify_outcome(root, dry_run=args.dry_run)
    if args.command == "catalog" and args.catalog_command == "stats":
        return catalog_stats_outcome(root, dry_run=args.dry_run)
    if args.command == "memory":
        write = bool(getattr(args, "write", False) and not args.dry_run)
        command = f"memory {args.memory_command}"
        if args.memory_command == "propose":
            result = propose_memory(
                root,
                load_yaml_file(args.input),
                write=write,
                memory_id=args.memory_id,
            )
            return mutation_outcome(command, result, repository_root=root)
        if args.memory_command == "validate":
            return validation_outcome(
                root,
                validate_memory(root, args.memory_id),
                dry_run=args.dry_run,
            )
        if args.memory_command == "commit":
            result = commit_memory(
                root,
                args.memory_id,
                expected_source_hash=args.expected_source_hash,
                write=write,
            )
            return mutation_outcome(command, result, repository_root=root)
        if args.memory_command == "revise":
            result = revise_memory(
                root,
                args.memory_id,
                load_yaml_file(args.input),
                expected_source_hash=args.expected_source_hash,
                write=write,
            )
            return mutation_outcome(command, result, repository_root=root)
        if args.memory_command == "supersede":
            result = supersede_memory(
                root,
                args.memory_id,
                args.replacement_id,
                expected_source_hash=args.expected_source_hash,
                write=write,
            )
            return mutation_outcome(command, result, repository_root=root)
        if args.memory_command == "forget":
            result = forget_memory(
                root,
                args.memory_id,
                expected_source_hash=args.expected_source_hash,
                write=write,
            )
            return mutation_outcome(command, result, repository_root=root)
        if args.memory_command == "query":
            return memory_query_outcome(
                root,
                _catalog_query(args),
                dry_run=args.dry_run,
            )
        if args.memory_command == "explain":
            return memory_explain_outcome(
                root,
                args.memory_id,
                at=args.at,
                dry_run=args.dry_run,
            )
    if args.command == "task" and args.task_command == "archive":
        return archive_outcome(
            root,
            dry_run=args.dry_run or not args.write,
            force=args.force,
        )
    if args.command == "task" and args.task_command == "status":
        return task_status_outcome(root, dry_run=args.dry_run)
    if args.command == "task" and args.task_command == "start":
        return start_task_outcome(
            root,
            task_id=args.task_id,
            title=args.title,
            goal=args.goal,
            workspace_id=args.workspace_id,
            repository_id=args.repository_id,
            repository_path=args.repository_path,
            remote_url=args.remote_url,
            parent_task_id=args.parent_task_id,
            write=bool(args.write and not args.dry_run),
        )
    if args.command == "task" and args.task_command in (
        "block",
        "unblock",
        "suspend",
        "resume",
        "complete",
        "abort",
    ):
        return transition_task_outcome(
            root,
            args.task_command,
            reason=getattr(args, "reason", None),
            write=bool(args.write and not args.dry_run),
        )
    if args.command == "session" and args.session_command == "status":
        return session_status_outcome(root, dry_run=args.dry_run)
    if args.command == "session" and args.session_command == "start":
        return start_session_outcome(
            root,
            session_id=args.session_id,
            agent_id=args.agent_id,
            write=bool(args.write and not args.dry_run),
        )
    if args.command == "session" and args.session_command == "checkpoint":
        write = bool(args.write and not args.dry_run)
        instant = datetime.now().astimezone()
        status = task_status_outcome(root).data
        if not status["active"]:
            return checkpoint_session_outcome(
                root,
                checkpoint_id=args.checkpoint_id,
                write=write,
                at=instant,
            )
        task = status["task"]
        git = collect_git(root, task["repository_id"], instant)
        tests = (run_test(args.test_command, root, instant),) if write and args.test_command else ()
        builds = (run_build(args.build_command, root, instant),) if write and args.build_command else ()
        narrative = load_yaml_file(args.input) if args.input else {}
        return checkpoint_session_outcome(
            root,
            checkpoint_id=args.checkpoint_id,
            git=git,
            tests=tests,
            builds=builds,
            narrative=narrative,
            write=write,
            at=instant,
        )
    if args.command == "session" and args.session_command == "end":
        return end_session_outcome(
            root, write=bool(args.write and not args.dry_run)
        )
    if args.command == "handoff" and args.handoff_command == "build":
        return handoff_build_outcome(root, dry_run=args.dry_run)
    if args.command == "context" and args.context_command == "build":
        try:
            request = ContextRequest(
                intent=args.intent,
                task_id=args.task_id,
                explicit_paths=tuple(args.path),
                explicit_symbols=tuple(args.symbol),
                keywords=tuple(args.keyword),
                budget_tokens=args.budget,
            )
        except ValueError as error:
            raise CodingContextError(str(error), code="PD_CONTEXT_INPUT_ERROR") from error
        return context_build_outcome(
            root,
            request,
            write=bool(args.write and not args.dry_run),
        )
    if args.command == "context" and args.context_command == "verify":
        return context_verify_outcome(root, dry_run=args.dry_run)
    raise AssertionError("unreachable command")


def _catalog_query(args: argparse.Namespace) -> CatalogQuery:
    scope_values = (
        args.workspace_id,
        args.project_id,
        args.task_id,
        args.session_id,
        *args.entity_id,
    )
    if any(value is not None for value in scope_values) and not args.scope_namespace:
        raise MemoryInputError(
            "--scope-namespace is required when another scope filter is used"
        )
    try:
        scope = (
            None
            if args.scope_namespace is None
            else MemoryScope(
                namespace=args.scope_namespace,
                workspace_id=args.workspace_id,
                project_id=args.project_id,
                task_id=args.task_id,
                session_id=args.session_id,
                entity_ids=tuple(args.entity_id),
            )
        )
        query_values = {
            "text": args.text,
            "memory_ids": tuple(args.memory_id),
            "tags": tuple(args.tag),
            "scope": scope,
            "valid_at": args.valid_at,
            "relation_types": tuple(args.relation_type),
            "include_related": args.include_related,
            "limit": args.limit,
        }
        if args.status:
            query_values["statuses"] = tuple(args.status)
        return CatalogQuery(
            MemoryQuery(**query_values),
            paths=tuple(args.path),
            text_mode=args.text_mode,
        )
    except ValueError as error:
        raise MemoryInputError(str(error)) from error


def _error_outcome(command: str, error: Exception) -> CommandOutcome:
    if isinstance(error, DiagnosticError):
        diagnostic = error.diagnostic
        exit_code = error.exit_code
    elif isinstance(error, ParadigmaError):
        diagnostic = Diagnostic(error.code, str(error), command)
        exit_code = error.exit_code
    else:
        diagnostic = Diagnostic("PD_UNEXPECTED_ERROR", str(error), command)
        exit_code = 1
    return CommandOutcome(
        command=command,
        diagnostics=(diagnostic,),
        exit_code_override=exit_code,
    )


def main(argv: list[str] | None = None) -> int:
    configure_utf8_stdio()
    args = build_parser().parse_args(argv)
    command = " ".join(
        str(value)
        for value in (
            args.command,
            getattr(args, "config_command", None),
            getattr(args, "index_command", None),
            getattr(args, "catalog_command", None),
            getattr(args, "memory_command", None),
            getattr(args, "task_command", None),
            getattr(args, "session_command", None),
            getattr(args, "handoff_command", None),
            getattr(args, "context_command", None),
        )
        if value
    )
    try:
        outcome = _dispatch(args)
    except (OSError, UnicodeError, ParadigmaError, ParseFailure) as error:
        outcome = _error_outcome(command, error)
    print(render(outcome, args.output_format))
    return outcome.exit_code


if __name__ == "__main__":
    sys.exit(main())
