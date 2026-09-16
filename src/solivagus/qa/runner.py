"""QA stage orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from solivagus.assembly import assemble_outputs
from solivagus.config import Settings
from solivagus.database import Database
from solivagus.models import DocumentStatus, UnitStatus
from solivagus.providers.openai_compatible import FatalProviderError, call_chat_api
from solivagus.providers.request_log import provider_log_scope
from solivagus.qa.checks import check_unit
from solivagus.qa.models import QAFinding, QAReportSummary, Severity, UnitQAResult
from solivagus.qa.repair import repair_unit
from solivagus.qa.report import write_qa_report
from solivagus.structure.html_tables import translate_html_tables_in_markdown
from solivagus.structure.references import apply_references_mode
from solivagus.style.capsule import StyleCapsule
from solivagus.util.text import sha256_text
from solivagus.workspace import workspace_root


ChatFn = Callable[..., tuple[str, str | None, dict[str, Any]]]


class QAStageError(RuntimeError):
    pass


def run_qa_stage(
    db: Database,
    *,
    document_id: int,
    settings: Settings,
    chat_fn: ChatFn | None = None,
    force: bool = False,
) -> dict[str, Any]:
    log_path = workspace_root(settings.workspace) / "provider-requests.jsonl"
    with provider_log_scope(log_path):
        return _run_qa_stage_unguarded(
            db,
            document_id=document_id,
            settings=settings,
            chat_fn=chat_fn,
            force=force,
        )


def _run_qa_stage_unguarded(
    db: Database,
    *,
    document_id: int,
    settings: Settings,
    chat_fn: ChatFn | None = None,
    force: bool = False,
) -> dict[str, Any]:
    if not settings.qa_enabled and not force:
        return {"document_id": document_id, "skipped": True, "reason": "qa_disabled"}

    doc = db.fetchone("SELECT * FROM documents WHERE id = ?", (document_id,))
    if doc is None:
        raise QAStageError(f"document not found: {document_id}")

    artifact_dir = Path(doc["artifact_dir"])
    units = db.list_units(document_id)
    if not units:
        raise QAStageError("document has no units to QA")

    terminology: dict[str, str] = {}
    latest = db.get_latest_style_capsule(document_id)
    if latest is not None:
        terminology = StyleCapsule.from_db_row(latest).terminology

    chat = chat_fn or call_chat_api
    summary = QAReportSummary()
    summary.unit_count = len(units)
    assembled: list[dict[str, str]] = []
    any_high_remaining = False
    changed = False
    max_repairs = max(0, int(settings.qa_max_repair_attempts))

    for unit in units:
        unit_key = str(unit["unit_key"])
        source = str(unit["source_text"] or "")
        translation = str(unit["translation_text"] or "")
        status = str(unit["status"] or "")

        # Dedicated structure processors (default: keep / heading-only).
        if settings.html_table_mode == "translate_cells" and translation:
            try:
                new_tr = translate_html_tables_in_markdown(
                    translation,
                    mode="translate_cells",
                    chat_fn=chat,
                    api_base=settings.llm_api_base,
                    api_key=settings.llm_api_key,
                    model=settings.repair_model or settings.llm_model,
                    timeout=settings.timeout_seconds,
                    send_temperature=settings.send_temperature,
                )
                if new_tr != translation:
                    translation = new_tr
                    changed = True
            except Exception as exc:  # noqa: BLE001
                # Leave translation as-is; surface as medium finding below.
                table_err = str(exc)
            else:
                table_err = None
        else:
            table_err = None

        translation = apply_references_mode(translation, settings.references_mode)
        source_for_check = source
        if settings.references_mode == "keep":
            # Compare against heading-normalized source so keep-mode is not flagged.
            source_for_check = apply_references_mode(source, "keep")

        result = check_unit(
            unit_key=unit_key,
            source_text=source_for_check,
            translation_text=translation,
            unit_status=status,
            warning_flags=unit["warning_flags"],
            terminology=terminology,
            numerical_check=settings.qa_numerical_check,
            structure_check=settings.qa_structure_check,
            citation_check=settings.qa_citation_check,
            terminology_check=settings.qa_terminology_check,
        )
        if table_err:
            result.findings.append(
                QAFinding(
                    code="html_table_translate_failed",
                    message=f"HTML 表格单元格翻译失败：{table_err}",
                    severity=Severity.MEDIUM,
                )
            )
            if result.status == "pass":
                result.status = "warn"

        summary.html_tables_kept += result.html_tables_kept

        if (
            settings.qa_auto_repair
            and max_repairs >= 1
            and result.status in {"fail", "warn"}
            and result.findings
            and status != UnitStatus.FALLBACK.value
        ):
            high_or_medium = [
                f
                for f in result.findings
                if f.severity in {Severity.HIGH, Severity.MEDIUM}
            ]
            if high_or_medium:
                try:
                    fixed = repair_unit(
                        source=source,
                        translation=translation,
                        findings=high_or_medium,
                        unit_key=unit_key,
                        settings=settings,
                        chat_fn=chat,
                    )
                    fixed = apply_references_mode(fixed, settings.references_mode)
                    recheck = check_unit(
                        unit_key=unit_key,
                        source_text=source_for_check,
                        translation_text=fixed,
                        unit_status=UnitStatus.DONE.value,
                        terminology=terminology,
                        numerical_check=settings.qa_numerical_check,
                        structure_check=settings.qa_structure_check,
                        citation_check=settings.qa_citation_check,
                        terminology_check=settings.qa_terminology_check,
                    )
                    if recheck.high_count == 0:
                        for finding in result.findings:
                            finding.repaired = True
                        result = UnitQAResult(
                            unit_key=unit_key,
                            status="repaired",
                            findings=result.findings + [
                                f for f in recheck.findings if f.severity != Severity.HIGH
                            ],
                            source_text=source,
                            translation_text=fixed,
                            html_tables_kept=recheck.html_tables_kept,
                        )
                        db.update_unit(
                            int(unit["id"]),
                            status=UnitStatus.DONE.value,
                            translation_text=fixed,
                            translation_hash=sha256_text(fixed),
                            provider="openai-compatible",
                            model=settings.repair_model or settings.llm_model,
                            attempt_count=int(unit["attempt_count"] or 0) + 1,
                            warning_flags="qa_repaired",
                        )
                        translation = fixed
                        changed = True
                    else:
                        result = recheck
                        result.status = "fail" if recheck.high_count else "warn"
                except FatalProviderError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    result.findings.append(
                        QAFinding(
                            code="repair_failed",
                            message=f"定向修复失败：{exc}",
                            severity=Severity.MEDIUM,
                        )
                    )
                    if result.status == "pass":
                        result.status = "warn"

        if result.status == "pass":
            summary.passed += 1
        elif result.status == "repaired":
            summary.repaired += 1
        elif result.status == "fallback":
            summary.fallback += 1
        elif result.status == "fail":
            summary.failed += 1
            any_high_remaining = True
        else:
            summary.warned += 1

        if result.high_count and result.status not in {"repaired", "pass"}:
            any_high_remaining = True

        summary.units.append(result)
        assembled.append(
            {
                "unit_key": unit_key,
                "source_text": source,
                "translation_text": translation or source,
            }
        )

    if changed or summary.repaired:
        assemble_outputs(
            artifact_dir,
            assembled,
            document_title=Path(str(doc["display_name"])).stem,
            pdf_name=str(doc["display_name"]),
            model=settings.llm_model,
            make_bilingual=True,
        )

    report_path = write_qa_report(artifact_dir, summary)
    db.record_artifact(
        document_id,
        "qa_report",
        str(report_path),
        sha256_text(report_path.read_text(encoding="utf-8")),
    )

    if any_high_remaining and settings.qa_strict:
        qa_status = "failed"
        doc_status = DocumentStatus.FAILED.value
    elif summary.failed or summary.fallback or summary.warned or summary.repaired:
        qa_status = "warnings"
        doc_status = DocumentStatus.QA_COMPLETE.value
    else:
        qa_status = "pass"
        doc_status = DocumentStatus.QA_COMPLETE.value

    db.update_document_status(
        document_id,
        status=doc_status,
        translation_status=doc["translation_status"],
        qa_status=qa_status,
    )

    from solivagus.pipeline.manifest import write_document_manifest

    manifest_path = write_document_manifest(
        artifact_dir,
        document_id=document_id,
        display_name=str(doc["display_name"]),
        source_sha256=str(doc["source_sha256"]),
        status=doc_status,
        model=settings.llm_model,
        extra={"qa_status": qa_status, "unit_count": summary.unit_count},
    )
    db.record_artifact(
        document_id,
        "manifest",
        str(manifest_path),
        sha256_text(manifest_path.read_text(encoding="utf-8")),
    )
    db.commit()

    return {
        "document_id": document_id,
        "skipped": False,
        "qa_status": qa_status,
        "status": doc_status,
        "unit_count": summary.unit_count,
        "passed": summary.passed,
        "repaired": summary.repaired,
        "fallback": summary.fallback,
        "warned": summary.warned,
        "failed": summary.failed,
        "html_tables_kept": summary.html_tables_kept,
        "qa_report": str(report_path),
        "manifest": str(manifest_path),
    }
