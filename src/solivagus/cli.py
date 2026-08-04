from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from solivagus import __version__
from solivagus.config import clear_settings_cache, get_settings
from solivagus.database import Database
from solivagus.migrate.mvp import MvpImportError, import_mvp_translation_dir
from solivagus.models import Stage
from solivagus.pipeline.translate import run_translate_stage
from solivagus.util.text import sha256_file
from solivagus.workspace import ensure_workspace, state_db_path

app = typer.Typer(
    name="solivagus",
    help="Solivagus — local technical PDF translation CLI",
    no_args_is_help=True,
    add_completion=False,
)


def _open_db(workspace: Path) -> Database:
    ensure_workspace(workspace)
    return Database(state_db_path(workspace))


def _resolve_document(db: Database, pdf: Optional[Path]) -> tuple[int, object]:
    if pdf is None:
        rows = db.list_documents()
        if not rows:
            raise typer.BadParameter("workspace has no documents; import or run first")
        row = rows[0]
        return int(row["id"]), row
    pdf = pdf.expanduser().resolve()
    sha = sha256_file(pdf) if pdf.is_file() else None
    row = db.get_document_by_path_or_sha(path=pdf, sha256=sha)
    if row is None:
        raise typer.BadParameter(
            f"document not registered: {pdf}. Use `solivagus import-mvp` first "
            "or wait for OCR registration in a later phase."
        )
    return int(row["id"]), row


@app.callback()
def main_callback(
    ctx: typer.Context,
    env_file: Optional[Path] = typer.Option(
        None, "--env-file", help="Path to .env (default: ./.env or SOLIVAGUS_ENV_FILE)"
    ),
    config: Optional[Path] = typer.Option(
        None, "--config", help="YAML config profile (reproducible settings entry)"
    ),
    workspace: Optional[Path] = typer.Option(
        None, "--workspace", help="Workspace root containing .solivagus/"
    ),
) -> None:
    clear_settings_cache()
    if config is not None:
        from solivagus.config_loader import ConfigLoadError, load_settings_from_config

        try:
            settings = load_settings_from_config(
                config, env_file=str(env_file) if env_file else None
            )
        except ConfigLoadError as exc:
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2) from exc
    else:
        settings = get_settings(str(env_file) if env_file else None)
    if workspace is not None:
        settings.workspace = workspace.expanduser().resolve()
    ctx.ensure_object(dict)
    ctx.obj["settings"] = settings
    ctx.obj["env_file"] = env_file
    ctx.obj["config"] = config


@app.command("version")
def version_cmd() -> None:
    """Show Solivagus application version."""
    typer.echo(f"solivagus {__version__}")


@app.command("status")
def status_cmd(
    ctx: typer.Context,
    pdf: Optional[Path] = typer.Argument(None, help="Optional PDF to filter"),
) -> None:
    """Show workspace or single-document status from SQLite."""
    settings = ctx.obj["settings"]
    with _open_db(settings.workspace) as db:
        if pdf is None:
            rows = db.list_documents()
            if not rows:
                typer.echo(f"workspace: {settings.workspace}")
                typer.echo("documents: 0")
                return
            typer.echo(f"workspace: {settings.workspace}")
            typer.echo(f"state_db: {state_db_path(settings.workspace)}")
            typer.echo(f"documents: {len(rows)}")
            for row in rows:
                units = db.list_units(int(row["id"]))
                done = sum(1 for unit in units if unit["status"] == "done")
                typer.echo(
                    f"- [{row['id']}] {row['display_name']}  status={row['status']}  "
                    f"units={done}/{len(units)}  artifact={row['artifact_dir']}"
                )
            return
        _doc_id, row = _resolve_document(db, pdf)
        units = db.list_units(int(row["id"]))
        done = sum(1 for unit in units if unit["status"] == "done")
        fallback = sum(1 for unit in units if unit["status"] == "fallback")
        pending = sum(1 for unit in units if unit["status"] == "pending")
        typer.echo(f"document_id: {row['id']}")
        typer.echo(f"name: {row['display_name']}")
        typer.echo(f"sha256: {row['source_sha256']}")
        typer.echo(f"status: {row['status']}")
        typer.echo(f"translation_status: {row['translation_status']}")
        typer.echo(f"artifact_dir: {row['artifact_dir']}")
        typer.echo(f"units: total={len(units)} done={done} pending={pending} fallback={fallback}")


@app.command("inspect")
def inspect_cmd(
    ctx: typer.Context,
    pdf: Optional[Path] = typer.Argument(None, help="PDF path or omit for latest document"),
    unit: Optional[str] = typer.Option(None, "--unit", help="Unit key, e.g. b00001"),
) -> None:
    """Inspect document / unit records stored in SQLite."""
    settings = ctx.obj["settings"]
    with _open_db(settings.workspace) as db:
        doc_id, row = _resolve_document(db, pdf)
        typer.echo(f"document_id: {doc_id}")
        typer.echo(f"source_path: {row['source_path']}")
        typer.echo(f"source_sha256: {row['source_sha256']}")
        typer.echo(f"status: {row['status']}")
        typer.echo(f"artifact_dir: {row['artifact_dir']}")
        units = db.list_units(doc_id)
        if unit:
            match = [item for item in units if item["unit_key"] == unit]
            if not match:
                raise typer.BadParameter(f"unit not found: {unit}")
            item = match[0]
            typer.echo(f"unit_key: {item['unit_key']}")
            typer.echo(f"status: {item['status']}")
            typer.echo(f"source_hash: {item['source_hash']}")
            typer.echo(f"model: {item['model']}")
            preview = (item["translation_text"] or "")[:500]
            typer.echo(f"translation_preview:\n{preview}")
            return
        typer.echo(f"units: {len(units)}")
        for item in units[:30]:
            typ = "zh" if item["translation_text"] else "-"
            typer.echo(
                f"  {item['unit_key']:>8}  status={item['status']:<10}  "
                f"chars={len(item['source_text'])}  translation={typ}"
            )
        if len(units) > 30:
            typer.echo(f"  ... {len(units) - 30} more")


@app.command("import-mvp")
def import_mvp_cmd(
    ctx: typer.Context,
    translation_dir: Path = typer.Argument(..., help="MVP *.translation directory"),
    pdf: Optional[Path] = typer.Option(None, "--pdf", help="Source PDF for hash verification"),
) -> None:
    """Import an MVP translation workspace into SQLite."""
    settings = ctx.obj["settings"]
    with _open_db(settings.workspace) as db:
        try:
            result = import_mvp_translation_dir(
                db, translation_dir=translation_dir, pdf_path=pdf
            )
        except MvpImportError as exc:
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2) from exc
    typer.echo("import ok")
    for key, value in result.items():
        typer.echo(f"{key}: {value}")


@app.command("plan")
def plan_cmd(
    ctx: typer.Context,
    pdf: Path = typer.Argument(..., help="Input PDF already registered / OCR'd"),
    force: bool = typer.Option(False, "--force-plan", help="Recompute even if plan hash matches"),
) -> None:
    """Build structure tree, translation units, and cache partitions (no API calls)."""
    from solivagus.pipeline.plan import PlanStageError, run_plan_stage

    settings = ctx.obj["settings"]
    pdf = pdf.expanduser().resolve()
    with _open_db(settings.workspace) as db:
        doc_id, _row = _resolve_document(db, pdf)
        try:
            result = run_plan_stage(
                db, document_id=doc_id, settings=settings, force=force
            )
        except PlanStageError as exc:
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2) from exc
    typer.echo("plan stage complete")
    for key, value in result.items():
        typer.echo(f"{key}: {value}")


@app.command("run")
def run_cmd(
    ctx: typer.Context,
    pdf: Path = typer.Argument(..., help="Input PDF"),
    stage: Stage = typer.Option(Stage.ALL, "--stage", help="Pipeline stage"),
    force_ocr: bool = typer.Option(False, "--force-ocr"),
    force_plan: bool = typer.Option(False, "--force-plan"),
    force_translate: bool = typer.Option(False, "--force-translate"),
    force_qa: bool = typer.Option(False, "--force-qa"),
    strict: bool = typer.Option(False, "--strict"),
    prevent_sleep: bool = typer.Option(False, "--prevent-sleep"),
    device: Optional[str] = typer.Option(None, "--device", help="OCR device, e.g. gpu:0"),
    drop_footnotes: bool = typer.Option(
        False, "--drop-footnotes", help="OCR: drop footnote regions (default: keep)"
    ),
    drop_aside_text: bool = typer.Option(
        False, "--drop-aside-text", help="OCR: drop aside_text regions (default: keep)"
    ),
) -> None:
    """Run pipeline stages against SQLite-backed workspace state."""
    from solivagus.ocr.checkpoints import OcrConfig
    from solivagus.ocr.runner import OcrStageError, run_ocr_stage
    from solivagus.pipeline.plan import PlanStageError, run_plan_stage
    from solivagus.qa import QAStageError, run_qa_stage

    settings = ctx.obj["settings"]
    if strict:
        settings.qa_strict = True
    pdf = pdf.expanduser().resolve()
    if not pdf.is_file():
        raise typer.BadParameter(f"PDF not found: {pdf}")

    ocr_config = OcrConfig(
        pipeline_version=settings.ocr_pipeline_version,
        device=device or settings.ocr_device,
        use_orientation=settings.ocr_use_orientation,
        use_unwarping=settings.ocr_use_unwarping,
        use_chart_recognition=settings.ocr_use_chart_recognition,
        batch_pages=settings.ocr_batch_pages,
        drop_footnotes=drop_footnotes or settings.ocr_drop_footnotes,
        drop_aside_text=drop_aside_text or settings.ocr_drop_aside_text,
    )

    with _open_db(settings.workspace) as db:
        if stage in {Stage.ALL, Stage.OCR}:
            try:
                ocr_result = run_ocr_stage(
                    db,
                    pdf_path=pdf,
                    workspace=settings.workspace,
                    config=ocr_config,
                    chunk_chars=settings.chunk_chars,
                    force=force_ocr,
                    prevent_sleep=prevent_sleep,
                )
            except OcrStageError as exc:
                typer.secho(str(exc), fg=typer.colors.RED, err=True)
                raise typer.Exit(code=2) from exc
            typer.echo("ocr stage complete")
            for key, value in ocr_result.items():
                typer.echo(f"{key}: {value}")

        if stage in {Stage.ALL, Stage.PLAN}:
            doc_id, _row = _resolve_document(db, pdf)
            try:
                plan_result = run_plan_stage(
                    db,
                    document_id=doc_id,
                    settings=settings,
                    force=force_plan,
                )
            except PlanStageError as exc:
                typer.secho(str(exc), fg=typer.colors.RED, err=True)
                raise typer.Exit(code=2) from exc
            typer.echo("plan stage complete")
            for key, value in plan_result.items():
                typer.echo(f"{key}: {value}")

        if stage in {Stage.ALL, Stage.TRANSLATE}:
            doc_id, _row = _resolve_document(db, pdf)
            result = run_translate_stage(
                db,
                document_id=doc_id,
                settings=settings,
                force=force_translate,
                strict=strict,
            )
            typer.echo("translate stage complete")
            for key, value in result.items():
                typer.echo(f"{key}: {value}")

        if stage in {Stage.ALL, Stage.QA}:
            doc_id, _row = _resolve_document(db, pdf)
            try:
                qa_result = run_qa_stage(
                    db,
                    document_id=doc_id,
                    settings=settings,
                    force=force_qa or stage == Stage.QA,
                )
            except QAStageError as exc:
                typer.secho(str(exc), fg=typer.colors.RED, err=True)
                raise typer.Exit(code=2) from exc
            typer.echo("qa stage complete")
            for key, value in qa_result.items():
                typer.echo(f"{key}: {value}")


@app.command("batch")
def batch_cmd(
    ctx: typer.Context,
    directory: Optional[Path] = typer.Argument(
        None,
        help="PDF directory (else SOLIVAGUS_BATCH_DIR / config batch_dir)",
    ),
    recursive: bool = typer.Option(False, "--recursive"),
    continue_on_error: bool = typer.Option(
        True, "--continue-on-error/--fail-fast", help="Isolate document failures"
    ),
    prevent_sleep: bool = typer.Option(True, "--prevent-sleep/--allow-sleep"),
    profile: str = typer.Option(
        "balanced", "--profile", help="conservative | balanced | throughput"
    ),
    device: Optional[str] = typer.Option(None, "--device", help="OCR device, e.g. gpu:0"),
) -> None:
    """Batch-process PDFs with OCR + translate dual queues."""
    from solivagus.batch import BatchDirError, BatchSupervisorError, run_batch

    settings = ctx.obj["settings"]
    if device:
        settings.ocr_device = device
    try:
        result = run_batch(
            settings=settings,
            batch_dir=directory,
            recursive=recursive,
            continue_on_error=continue_on_error,
            prevent_sleep=prevent_sleep,
            profile=profile,
        )
    except (BatchDirError, BatchSupervisorError, ValueError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc
    typer.echo("batch complete")
    for key in (
        "batch_dir",
        "profile",
        "total",
        "completed",
        "failed",
        "manifest",
        "global_usage",
        "nightly_md",
    ):
        if key in result:
            typer.echo(f"{key}: {result[key]}")
    if result.get("failed"):
        raise typer.Exit(code=1)


@app.command("retry")
def retry_cmd(
    ctx: typer.Context,
    pdf: Optional[Path] = typer.Argument(None, help="Failed PDF to retry"),
    all_failed: bool = typer.Option(False, "--all-failed", help="Retry all failed docs"),
    profile: str = typer.Option("balanced", "--profile"),
) -> None:
    """Retry failed document(s) without clearing successful checkpoints."""
    from solivagus.batch import BatchSupervisorError, retry_failed_documents

    settings = ctx.obj["settings"]
    if pdf is None and not all_failed:
        raise typer.BadParameter("pass a PDF path or --all-failed")
    try:
        result = retry_failed_documents(
            settings=settings,
            pdf=pdf,
            all_failed=all_failed,
            profile=profile,
        )
    except BatchSupervisorError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc
    typer.echo("retry complete")
    for key, value in result.items():
        if key == "documents":
            continue
        typer.echo(f"{key}: {value}")
    if result.get("failed"):
        raise typer.Exit(code=1)


@app.command("report")
def report_cmd(
    ctx: typer.Context,
    output_dir: Optional[Path] = typer.Option(
        None, "--output-dir", help="Where to write nightly-*.md/json"
    ),
) -> None:
    """Write nightly summary and optional global usage rollup."""
    from solivagus.batch.usage import aggregate_usage_reports
    from solivagus.ocr.report import write_nightly_report

    settings = ctx.obj["settings"]
    out = (output_dir or (settings.workspace / ".solivagus" / "reports")).expanduser()
    with _open_db(settings.workspace) as db:
        rows = []
        for doc in db.list_documents():
            batches = db.fetchall(
                "SELECT status FROM ocr_batches WHERE document_id = ?",
                (int(doc["id"]),),
            )
            ok = sum(
                1
                for item in batches
                if str(item["status"]).startswith("done") or item["status"] == "skipped_done"
            )
            rows.append(
                {
                    "display_name": doc["display_name"],
                    "status": doc["status"],
                    "ocr_batches_ok": ok,
                    "failed_pages": None,
                    "artifact_dir": doc["artifact_dir"],
                }
            )
        md_path, json_path = write_nightly_report(out, documents=rows)
        usage_path, _usage = aggregate_usage_reports(rows, output_dir=out)
    typer.echo(f"wrote {md_path}")
    typer.echo(f"wrote {json_path}")
    typer.echo(f"wrote {usage_path}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
