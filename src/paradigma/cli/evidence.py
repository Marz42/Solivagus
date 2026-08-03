"""Deterministic local evidence collection used by checkpoint CLI adapters."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import hashlib
import os
import shlex
import subprocess
import time

from ..errors import ParadigmaError
from ..integrations.coding import BuildEvidence, GitEvidence, TestEvidence


class EvidenceCollectionError(ParadigmaError):
    code = "PD_EVIDENCE_COLLECTION_ERROR"
    exit_code = 2


def collect_git(root: Path, repository_id: str, at: datetime) -> GitEvidence:
    head = _git(root, "rev-parse", "HEAD", allow_failure=True)
    branch = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD", allow_failure=True)
    status = _git(
        root,
        "-c",
        "core.quotepath=false",
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    paths = []
    for line in status.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        path = path.strip('"').replace("\\", "/")
        if path and path not in paths:
            paths.append(path)
    return GitEvidence(
        repository_id=repository_id,
        observed_at=at,
        head_commit=head or None,
        branch=branch or None,
        dirty=bool(paths),
        worktree_paths=tuple(paths),
    )


def run_test(command: str, root: Path, at: datetime) -> TestEvidence:
    result, duration, digest = _run(command, root)
    return TestEvidence(
        command=command,
        status="passed" if result.returncode == 0 else "failed",
        observed_at=at,
        exit_code=result.returncode,
        duration_seconds=duration,
        output_hash=digest,
    )


def run_build(command: str, root: Path, at: datetime) -> BuildEvidence:
    result, duration, digest = _run(command, root)
    return BuildEvidence(
        command=command,
        status="passed" if result.returncode == 0 else "failed",
        observed_at=at,
        exit_code=result.returncode,
        duration_seconds=duration,
        output_hash=digest,
    )


def _git(root: Path, *arguments: str, allow_failure: bool = False) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode and not allow_failure:
        raise EvidenceCollectionError(result.stderr.strip() or "git evidence collection failed")
    return result.stdout.rstrip("\r\n") if result.returncode == 0 else ""


def _run(command: str, root: Path):
    if not isinstance(command, str) or not command.strip():
        raise EvidenceCollectionError("evidence command must be non-empty")
    arguments = shlex.split(command, posix=os.name != "nt")
    if os.name == "nt":
        arguments = [
            item[1:-1]
            if len(item) >= 2 and item[0] == item[-1] and item[0] in ('"', "'")
            else item
            for item in arguments
        ]
    started = time.monotonic()
    try:
        result = subprocess.run(
            arguments,
            cwd=root,
            capture_output=True,
            check=False,
        )
    except OSError as error:
        raise EvidenceCollectionError(str(error)) from error
    duration = time.monotonic() - started
    digest = "sha256:" + hashlib.sha256(
        result.stdout + b"\n--- stderr ---\n" + result.stderr
    ).hexdigest()
    return result, duration, digest
