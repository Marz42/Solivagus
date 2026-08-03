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
    workspace: Optional[Path] = typer.Option(
        None, "--workspace", help="Workspace root containing .solivagus/"
    ),
) -> None:
    clear_settings_cache()
    settings = get_settings(str(env_file) if env_file else None)
    if workspace is not None:
        settings.workspace = workspace.expanduser().resolve()
    ctx.ensure_object(dict)
    ctx.obj["settings"] = settings
    ctx.obj["env_file"] = env_file


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


@app.command("run")
def run_cmd(
    ctx: typer.Context,
    pdf: Path = typer.Argument(..., help="Input PDF (must already be registered)"),
    stage: Stage = typer.Option(Stage.ALL, "--stage", help="Pipeline stage"),
    force_translate: bool = typer.Option(False, "--force-translate"),
    strict: bool = typer.Option(False, "--strict"),
) -> None:
    """Run pipeline stages. Phase 1 supports --stage translate against SQLite units."""
    settings = ctx.obj["settings"]
    if stage == Stage.OCR:
        typer.echo("OCR stage is scheduled for Phase 2; use legacy script or import-mvp for now.")
        raise typer.Exit(code=2)
    if stage not in {Stage.ALL, Stage.TRANSLATE}:
        raise typer.BadParameter(f"unsupported stage: {stage}")

    with _open_db(settings.workspace) as db:
        doc_id, _row = _resolve_document(db, pdf)
        if stage in {Stage.ALL, Stage.TRANSLATE}:
            # Phase 1: ALL means translate-only until OCR lands.
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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
