#!/usr/bin/env python3
"""Soak / pre-run gate checks for Solivagus workspaces.

Usage:
  python scripts/soak_verify.py --workspace D:\\Repos\\Solivagus
  python scripts/soak_verify.py --workspace ... --snapshot-attempts .solivagus/soak-attempts.json
  python scripts/soak_verify.py --workspace ... --compare-attempts .solivagus/soak-attempts.json
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Allow `python scripts/soak_verify.py` without install when repo is on PYTHONPATH.
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from solivagus.style.capsule import StyleCapsule  # noqa: E402
from solivagus.workspace import state_db_path  # noqa: E402

SUCCESS_DOC = frozenset(
    {
        "qa_complete",
        "translation_complete",
        "translation_complete_with_warnings",
    }
)
FAILED_DOC = frozenset({"failed", "cancelled"})
TERMINAL_DOC_OK = SUCCESS_DOC | FAILED_DOC
RESIDUAL_RUNNING = frozenset({"running"})
RESIDUAL_PENDING = frozenset({"pending"})
RESIDUAL_UNIT = RESIDUAL_RUNNING | RESIDUAL_PENDING  # legacy alias for mid-run messaging
COMPLETE_PARTITION_STATUS = frozenset({"ready", "ready_low_cache", "degraded"})
REQUIRED_ARTIFACTS = (
    "source.md",
    "translated.zh.md",
    "translated.bilingual.md",
    "qa-report.md",
    "usage-report.json",
    "manifest.json",
)
QA_FAILED_RE = re.compile(r"-\s*未通过：\s*(\d+)")


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""
    severity: str = "error"  # error | warn


@dataclass
class DocumentReport:
    document_id: int
    source_path: str
    status: str
    checks: list[CheckResult] = field(default_factory=list)
    unit_status: dict[str, int] = field(default_factory=dict)
    attempt_count: int = 0

    @property
    def ok(self) -> bool:
        return all(c.ok or c.severity == "warn" for c in self.checks) and all(
            c.ok for c in self.checks if c.severity == "error"
        )


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def _count_attempts(conn: sqlite3.Connection, document_id: int) -> int:
    cur = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM translation_attempts a
        JOIN translation_units u ON u.id = a.unit_id
        WHERE u.document_id = ?
        """,
        (document_id,),
    )
    return int(cur.fetchone()["n"])


def _attempt_snapshot(conn: sqlite3.Connection, *, workspace: Path) -> dict[str, Any]:
    docs = conn.execute("SELECT id, source_path, status FROM documents").fetchall()
    by_doc: dict[str, Any] = {}
    for doc in docs:
        did = int(doc["id"])
        units = conn.execute(
            """
            SELECT id, unit_key, status, attempt_count
            FROM translation_units WHERE document_id = ?
            """,
            (did,),
        ).fetchall()
        attempts = conn.execute(
            """
            SELECT a.id, a.unit_id, a.attempt_number, a.http_status, a.error_type
            FROM translation_attempts a
            JOIN translation_units u ON u.id = a.unit_id
            WHERE u.document_id = ?
            ORDER BY a.id
            """,
            (did,),
        ).fetchall()
        by_doc[str(did)] = {
            "source_path": doc["source_path"],
            "status": doc["status"],
            "attempt_rows": len(attempts),
            "units": {
                str(u["id"]): {
                    "unit_key": u["unit_key"],
                    "status": u["status"],
                    "attempt_count": int(u["attempt_count"] or 0),
                }
                for u in units
            },
            "attempt_ids": [int(a["id"]) for a in attempts],
        }
    from solivagus.providers.request_log import count_provider_log_lines
    from solivagus.workspace import workspace_root

    log_path = workspace_root(workspace) / "provider-requests.jsonl"
    return {
        "documents": by_doc,
        "provider_log_path": str(log_path),
        "provider_log_lines": count_provider_log_lines(log_path),
        "note": (
            "translation_attempts excludes warm-up/probe/repair unless also logged; "
            "prefer provider_log_lines for zero-API proof"
        ),
    }


def _verify_capsule_pair(
    *,
    capsule_dir: Path,
    row: sqlite3.Row,
) -> list[CheckResult]:
    checks: list[CheckResult] = []
    version = int(row["version"])
    part_id = row["source_partition_id"]
    db_hash = str(row["content_hash"] or "")
    capsule = StyleCapsule.from_db_row(row)
    recomputed = capsule.content_hash()
    if recomputed != db_hash:
        checks.append(
            CheckResult(
                "capsule_db_hash_self",
                False,
                f"v{version} DB content_hash != recomputed ({db_hash[:12]}... vs {recomputed[:12]}...)",
            )
        )
    else:
        checks.append(
            CheckResult(
                "capsule_db_hash_self",
                True,
                f"v{version} DB hash matches StyleCapsule.content_hash()",
            )
        )

    path = capsule_dir / f"v{version}.json"
    if not path.is_file():
        checks.append(
            CheckResult(
                "capsule_json_exists",
                False,
                f"missing {path.name} for partition={part_id}",
            )
        )
        return checks

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError) as exc:
        checks.append(
            CheckResult("capsule_json_parse", False, f"{path.name}: {exc}")
        )
        return checks

    if not isinstance(raw, dict):
        checks.append(CheckResult("capsule_db_json_bind", False, f"v{version} JSON not an object"))
        return checks

    try:
        json_ver = int(raw["version"])
        json_part = int(raw["source_partition_id"])
        rebuilt = StyleCapsule(
            version=json_ver,
            style_rules=list(raw["style_rules"]),
            terminology=dict(raw["terminology"]),
            examples=list(raw["examples"]),
            boundary_context=dict(raw["boundary_context"]),
        )
        json_recomputed = rebuilt.content_hash()
        declared = str(raw.get("content_hash") or "")
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        checks.append(
            CheckResult(
                "capsule_db_json_bind",
                False,
                f"v{version} JSON field/type error: {exc}",
            )
        )
        return checks

    ok = (
        declared == json_recomputed
        and json_recomputed == db_hash
        and json_ver == version
        and (part_id is None or json_part == int(part_id))
        and rebuilt.style_rules == capsule.style_rules
        and rebuilt.terminology == capsule.terminology
        and rebuilt.examples == capsule.examples
        and rebuilt.boundary_context == capsule.boundary_context
    )
    checks.append(
        CheckResult(
            "capsule_db_json_bind",
            ok,
            (
                f"v{version} DB<->JSON payload OK (partition={part_id})"
                if ok
                else (
                    f"v{version} payload mismatch "
                    f"db_hash={db_hash[:12]}... json_recomputed={json_recomputed[:12]}... "
                    f"declared={declared[:12]}... ver/part=({json_ver},{json_part})"
                )
            ),
        )
    )
    return checks


def _verify_document(
    conn: sqlite3.Connection,
    doc: sqlite3.Row,
    *,
    require_ok_terminal: bool,
) -> DocumentReport:
    did = int(doc["id"])
    report = DocumentReport(
        document_id=did,
        source_path=str(doc["source_path"] or ""),
        status=str(doc["status"] or ""),
    )
    artifact = Path(str(doc["artifact_dir"] or ""))
    units = conn.execute(
        """
        SELECT * FROM translation_units
        WHERE document_id = ?
        ORDER BY sequence_index, id
        """,
        (did,),
    ).fetchall()
    partitions = conn.execute(
        """
        SELECT * FROM cache_partitions
        WHERE document_id = ?
        ORDER BY sequence_index, id
        """,
        (did,),
    ).fetchall()
    capsules = conn.execute(
        """
        SELECT * FROM style_capsules
        WHERE document_id = ?
        ORDER BY version, id
        """,
        (did,),
    ).fetchall()

    report.unit_status = dict(Counter(str(u["status"]) for u in units))
    report.attempt_count = _count_attempts(conn, did)

    # 1) Terminal document status
    if report.status in TERMINAL_DOC_OK:
        report.checks.append(
            CheckResult("doc_terminal", True, f"status={report.status}")
        )
    elif require_ok_terminal:
        report.checks.append(
            CheckResult(
                "doc_terminal",
                False,
                f"non-terminal status={report.status} "
                f"(want qa_complete|translation_complete[_with_warnings]|failed)",
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "doc_terminal",
                True,
                f"status={report.status} (mid-run allowed)",
                severity="warn",
            )
        )

    # 2) Unit residuals by document outcome
    # - success: no pending, no running
    # - explicit failed/cancelled (recoverable): pending OK; orphan running NOT OK
    # - mid-run: warn only
    running = [
        f"{u['unit_key']}=running"
        for u in units
        if str(u["status"]) in RESIDUAL_RUNNING
    ]
    pending = [
        f"{u['unit_key']}=pending"
        for u in units
        if str(u["status"]) in RESIDUAL_PENDING
    ]
    if report.status in SUCCESS_DOC:
        residual = running + pending
        report.checks.append(
            CheckResult(
                "no_residual_units",
                not residual,
                "ok" if not residual else f"residual: {', '.join(residual[:12])}",
            )
        )
    elif report.status in FAILED_DOC:
        report.checks.append(
            CheckResult(
                "no_orphan_running_units",
                not running,
                (
                    "ok (pending allowed on failed/recoverable docs)"
                    if not running
                    else f"orphan running: {', '.join(running[:12])}"
                ),
            )
        )
        if pending:
            report.checks.append(
                CheckResult(
                    "pending_on_failed_ok",
                    True,
                    f"pending={len(pending)} (allowed until recovery)",
                    severity="warn",
                )
            )
    elif running or pending:
        report.checks.append(
            CheckResult(
                "no_residual_units",
                True,
                f"in-flight residual running={len(running)} pending={len(pending)}",
                severity="warn",
            )
        )
    else:
        report.checks.append(CheckResult("no_residual_units", True, "no residual"))

    # Incomplete must never look like success (status already gated above).
    if report.status in {"translation_running", "ocr_running", "planning"} and require_ok_terminal:
        report.checks.append(
            CheckResult(
                "incomplete_not_success",
                False,
                f"status={report.status} left mid-pipeline (batch should mark failed or resume)",
            )
        )

    # 3) Artifacts for successful docs
    if report.status in SUCCESS_DOC:
        if not artifact.is_dir():
            report.checks.append(
                CheckResult("artifacts_dir", False, f"missing artifact_dir={artifact}")
            )
        else:
            required = list(REQUIRED_ARTIFACTS)
            if report.status != "qa_complete":
                required = [n for n in required if n != "qa-report.md"]
            missing = [name for name in required if not (artifact / name).is_file()]
            report.checks.append(
                CheckResult(
                    "artifacts_files",
                    not missing,
                    "ok" if not missing else f"missing: {', '.join(missing)}",
                )
            )
            qa_path = artifact / "qa-report.md"
            if report.status == "qa_complete" and qa_path.is_file():
                text = qa_path.read_text(encoding="utf-8", errors="replace")
                m = QA_FAILED_RE.search(text)
                failed_n = int(m.group(1)) if m else -1
                report.checks.append(
                    CheckResult(
                        "qa_no_unexplained_fail",
                        failed_n == 0,
                        (
                            "qa failed_units=0"
                            if failed_n == 0
                            else f"qa failed_units={failed_n} (review HIGH findings)"
                        ),
                    )
                )
            elif report.status == "qa_complete":
                report.checks.append(
                    CheckResult("qa_no_unexplained_fail", False, "missing qa-report.md")
                )
    else:
        report.checks.append(
            CheckResult(
                "artifacts_files",
                True,
                f"skipped (status={report.status})",
                severity="warn",
            )
        )

    # 4) Completed partitions <-> capsules
    capsule_dir = artifact / "style_capsules" if artifact else Path()
    capsules_by_part = {
        int(c["source_partition_id"]): c
        for c in capsules
        if c["source_partition_id"] is not None
    }
    units_by_part: dict[int, list[sqlite3.Row]] = {}
    for u in units:
        if u["partition_id"] is None:
            continue
        units_by_part.setdefault(int(u["partition_id"]), []).append(u)

    for part in partitions:
        part_id = int(part["id"])
        part_status = str(part["status"] or "")
        part_units = units_by_part.get(part_id, [])
        doneish = [
            u
            for u in part_units
            if str(u["status"]) in {"done", "fallback"} and u["translation_text"]
        ]
        is_complete = part_status in COMPLETE_PARTITION_STATUS or (
            part_units
            and all(str(u["status"]) in {"done", "fallback"} for u in part_units)
            and any(str(u["status"]) == "done" for u in part_units)
        )
        if not is_complete or not doneish:
            continue
        if part_id not in capsules_by_part:
            report.checks.append(
                CheckResult(
                    f"partition_{part_id}_capsule_db",
                    False,
                    f"partition {part_id} complete ({part_status}) but no style_capsules row",
                )
            )
            continue
        report.checks.extend(
            _verify_capsule_pair(capsule_dir=capsule_dir, row=capsules_by_part[part_id])
        )

    # Also verify every stored capsule has JSON even if partition incomplete
    for cap in capsules:
        if cap["source_partition_id"] is None:
            continue
        # Avoid duplicate names: only add if not already covered above
        already = any(
            c.name == "capsule_db_json_bind" and f"v{int(cap['version'])}" in c.detail
            for c in report.checks
        )
        if already:
            continue
        report.checks.extend(_verify_capsule_pair(capsule_dir=capsule_dir, row=cap))

    return report


def _safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(text.encode(enc, errors="replace").decode(enc, errors="replace"))


def _print_report(
    reports: list[DocumentReport],
    *,
    compare: dict[str, Any] | None,
    workspace: Path,
) -> int:
    from solivagus.providers.request_log import count_provider_log_lines
    from solivagus.workspace import workspace_root

    errors = 0
    for r in reports:
        _safe_print(f"\n=== document {r.document_id} ===")
        _safe_print(f"path: {r.source_path}")
        _safe_print(f"status: {r.status}")
        _safe_print(f"units: {r.unit_status}")
        _safe_print(f"translation_attempts: {r.attempt_count}")
        for c in r.checks:
            mark = "PASS" if c.ok else ("WARN" if c.severity == "warn" else "FAIL")
            if not c.ok and c.severity == "error":
                errors += 1
            _safe_print(f"  [{mark}] {c.name}: {c.detail}")
        if compare is not None:
            prev = compare.get("documents", {}).get(str(r.document_id))
            if prev is None:
                _safe_print("  [WARN] compare: no prior snapshot for this document_id")
            else:
                delta = r.attempt_count - int(prev.get("attempt_rows", 0))
                # Strict: any growth is new unit traffic; shrink means rows were rebuilt
                # (attempts table alone still misses warm-up — see provider_log check).
                if delta > 0:
                    errors += 1
                    _safe_print(
                        f"  [FAIL] translation_attempts_delta: {delta} "
                        f"(new unit attempt rows)"
                    )
                elif delta < 0:
                    errors += 1
                    _safe_print(
                        f"  [FAIL] translation_attempts_delta: {delta} "
                        f"(rows shrunk; table rebuilt — not proof of zero API)"
                    )
                else:
                    _safe_print(
                        "  [PASS] translation_attempts_delta: 0 "
                        "(unit attempts only; warm-up not covered here)"
                    )
                _safe_print(
                    f"  [info] prior_attempts={prev.get('attempt_rows')} "
                    f"prior_status={prev.get('status')}"
                )

    if compare is not None:
        log_path = workspace_root(workspace) / "provider-requests.jsonl"
        prior_lines = int(compare.get("provider_log_lines") or 0)
        now_lines = count_provider_log_lines(log_path)
        log_delta = now_lines - prior_lines
        if not log_path.is_file() and prior_lines == 0:
            errors += 1
            _safe_print(
                "\n  [FAIL] provider_log: missing "
                f"{log_path} — cannot prove zero API "
                "(warm-up/probe/repair are not in translation_attempts)"
            )
        elif log_delta != 0:
            errors += 1
            _safe_print(
                f"\n  [FAIL] provider_log_delta: {log_delta} "
                f"(prior={prior_lines} now={now_lines}; want 0)"
            )
        else:
            _safe_print(
                f"\n  [PASS] provider_log_delta: 0 "
                f"(lines={now_lines} at {log_path})"
            )

    _safe_print(f"\n=== summary: {len(reports)} docs, {errors} error(s) ===")
    return 1 if errors else 0


def _compare_done_unit_attempts(
    conn: sqlite3.Connection,
    reports: list[DocumentReport],
    prior: dict[str, Any],
) -> list[CheckResult]:
    """Extra checks: done/fallback units must not gain attempt_count after re-run."""
    extra: list[CheckResult] = []
    for r in reports:
        prev_doc = prior.get("documents", {}).get(str(r.document_id))
        if not prev_doc:
            continue
        if prev_doc.get("status") not in SUCCESS_DOC:
            continue
        units_now = {
            str(u["id"]): u
            for u in conn.execute(
                "SELECT id, unit_key, status, attempt_count FROM translation_units WHERE document_id=?",
                (r.document_id,),
            )
        }
        grown = []
        for uid, meta in (prev_doc.get("units") or {}).items():
            if meta.get("status") not in {"done", "fallback"}:
                continue
            cur = units_now.get(uid)
            if cur is None:
                continue
            before = int(meta.get("attempt_count") or 0)
            after = int(cur["attempt_count"] or 0)
            if after > before:
                grown.append(f"{meta.get('unit_key')}:{before}->{after}")
        ok = not grown
        extra.append(
            CheckResult(
                f"doc_{r.document_id}_done_units_no_reattempt",
                ok,
                "ok" if ok else f"grown: {', '.join(grown[:20])}",
            )
        )
        r.checks.append(extra[-1])
    return extra


def main() -> int:
    parser = argparse.ArgumentParser(description="Solivagus soak / pre-run verifier")
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Workspace root containing .solivagus/state.db",
    )
    parser.add_argument("--document-id", type=int, action="append", default=None)
    parser.add_argument(
        "--allow-in-flight",
        action="store_true",
        help="Do not fail non-terminal document statuses (for mid-run probes)",
    )
    parser.add_argument(
        "--snapshot-attempts",
        type=Path,
        help="Write attempt snapshot JSON then exit 0",
    )
    parser.add_argument(
        "--compare-attempts",
        type=Path,
        help="Compare current attempt rows vs prior snapshot (expect delta 0)",
    )
    parser.add_argument("--json-out", type=Path, help="Write full report JSON")
    args = parser.parse_args()

    db_path = state_db_path(args.workspace)
    if not db_path.is_file():
        print(f"FAIL: state db not found: {db_path}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    if args.snapshot_attempts:
        snap = _attempt_snapshot(conn, workspace=args.workspace)
        args.snapshot_attempts.parent.mkdir(parents=True, exist_ok=True)
        args.snapshot_attempts.write_text(
            json.dumps(snap, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"wrote attempt snapshot: {args.snapshot_attempts}")
        conn.close()
        return 0

    docs = conn.execute(
        "SELECT * FROM documents ORDER BY id ASC"
    ).fetchall()
    if args.document_id:
        want = set(args.document_id)
        docs = [d for d in docs if int(d["id"]) in want]

    if not docs:
        print("FAIL: no documents in workspace", file=sys.stderr)
        conn.close()
        return 2

    require_terminal = not args.allow_in_flight
    reports = [
        _verify_document(conn, d, require_ok_terminal=require_terminal) for d in docs
    ]

    compare_payload = None
    if args.compare_attempts:
        compare_payload = json.loads(args.compare_attempts.read_text(encoding="utf-8"))
        _compare_done_unit_attempts(conn, reports, compare_payload)

    if args.json_out:
        payload = {
            "workspace": str(args.workspace.resolve()),
            "documents": [
                {
                    **{k: getattr(r, k) for k in ("document_id", "source_path", "status", "unit_status", "attempt_count")},
                    "ok": r.ok,
                    "checks": [asdict(c) for c in r.checks],
                }
                for r in reports
            ],
        }
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"wrote report: {args.json_out}")

    code = _print_report(reports, compare=compare_payload, workspace=args.workspace)
    conn.close()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
