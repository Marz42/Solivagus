"""Privacy audit: show what would be sent to the API (no network)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from solivagus.config import Settings
from solivagus.database import Database
from solivagus.providers.prompts import (
    PROMPT_VERSION,
    build_stable_prefix,
    build_unit_messages,
    document_user_id,
)
from solivagus.style.capsule import StyleCapsule, empty_capsule
from solivagus.util.markdown import protect_markdown, split_passthrough_segments
from solivagus.util.text import sha256_text


@dataclass
class InspectDataReport:
    document_id: int
    display_name: str
    source_sha256: str
    artifact_dir: str
    api_base: str
    model: str
    user_id: str
    prompt_version: str
    target_mode: str
    uploads_pdf: bool = False
    uploads_images: bool = False
    sends_ocr_text_only: bool = True
    unit_count: int = 0
    sample_units: list[dict[str, Any]] = field(default_factory=list)
    stable_prefix_chars: int = 0
    stable_prefix_hash: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "display_name": self.display_name,
            "source_sha256": self.source_sha256,
            "artifact_dir": self.artifact_dir,
            "provider": {
                "api_base": self.api_base,
                "model": self.model,
                "user_id": self.user_id,
                "prompt_version": self.prompt_version,
                "target_mode": self.target_mode,
            },
            "privacy": {
                "uploads_pdf": self.uploads_pdf,
                "uploads_images": self.uploads_images,
                "sends_ocr_text_only": self.sends_ocr_text_only,
            },
            "unit_count": self.unit_count,
            "stable_prefix_chars": self.stable_prefix_chars,
            "stable_prefix_hash": self.stable_prefix_hash,
            "sample_units": self.sample_units,
            "notes": self.notes,
        }


def _preview_unit(unit: Any, *, max_chars: int = 240) -> dict[str, Any]:
    source = str(unit["source_text"] or "")
    protected, placeholders = protect_markdown(source)
    segments = split_passthrough_segments(source)
    passthrough = [kind for kind, _ in segments if kind != "text"]
    return {
        "unit_key": str(unit["unit_key"]),
        "source_chars": len(source),
        "protected_chars": len(protected),
        "placeholder_count": len(placeholders),
        "passthrough_kinds": sorted(set(passthrough)),
        "source_preview": source[:max_chars] + ("…" if len(source) > max_chars else ""),
        "content_sha256": sha256_text(source)[:16],
    }


def build_inspect_data_report(
    db: Database,
    *,
    document_id: int,
    settings: Settings,
    sample_limit: int = 5,
) -> InspectDataReport:
    doc = db.fetchone("SELECT * FROM documents WHERE id = ?", (document_id,))
    if doc is None:
        raise ValueError(f"document not found: {document_id}")
    units = db.list_units(document_id)
    source_sha = str(doc["source_sha256"] or "")
    user_id = document_user_id(source_sha) if source_sha else "(unset)"

    capsule_text = empty_capsule().to_prompt_text()
    latest = db.get_latest_style_capsule(document_id)
    if latest is not None:
        capsule_text = StyleCapsule.from_db_row(latest).to_prompt_text()

    unit_dicts = [
        {"unit_key": u["unit_key"], "source_text": u["source_text"] or ""} for u in units[:20]
    ]
    _system, stable_user, prefix_hash = build_stable_prefix(
        document_title=Path(str(doc["display_name"])).stem,
        target_language=settings.target_language,
        units=unit_dicts or [{"unit_key": "u00000", "source_text": ""}],
        style_capsule=capsule_text,
        prompt_version=settings.prompt_version or PROMPT_VERSION,
    )

    samples = [_preview_unit(u) for u in units[: max(0, sample_limit)]]
    notes = [
        "PDF and images stay local; only OCR/markdown text is prepared for API.",
        "user_id is derived from document SHA-256, not filename or author.",
        "This command does not call the network.",
    ]
    if not units:
        notes.append("No translation units yet — run plan/OCR first for a full unit inventory.")

    # Show one synthetic message outline for the first unit (structure only).
    if units:
        first = units[0]
        protected, _ph = protect_markdown(str(first["source_text"] or ""))
        messages = build_unit_messages(
            stable_system=_system,
            stable_user=stable_user,
            warmup_assistant="READY",
            unit_key=str(first["unit_key"]),
            source_text=protected,
            target_mode=settings.target_mode,  # type: ignore[arg-type]
        )
        samples[0]["message_roles"] = [m.get("role") for m in messages]
        samples[0]["dynamic_user_chars"] = len(messages[-1].get("content") or "")

    return InspectDataReport(
        document_id=document_id,
        display_name=str(doc["display_name"]),
        source_sha256=source_sha,
        artifact_dir=str(doc["artifact_dir"]),
        api_base=settings.llm_api_base,
        model=settings.llm_model,
        user_id=user_id,
        prompt_version=settings.prompt_version,
        target_mode=settings.target_mode,
        unit_count=len(units),
        sample_units=samples,
        stable_prefix_chars=len(stable_user),
        stable_prefix_hash=prefix_hash,
        notes=notes,
    )


def format_inspect_data_report(report: InspectDataReport) -> str:
    lines = [
        f"document_id: {report.document_id}",
        f"display_name: {report.display_name}",
        f"source_sha256: {report.source_sha256}",
        f"artifact_dir: {report.artifact_dir}",
        "",
        "## Privacy defaults",
        f"- uploads_pdf: {report.uploads_pdf}",
        f"- uploads_images: {report.uploads_images}",
        f"- sends_ocr_text_only: {report.sends_ocr_text_only}",
        "",
        "## Provider target",
        f"- api_base: {report.api_base}",
        f"- model: {report.model}",
        f"- user_id: {report.user_id}",
        f"- prompt_version: {report.prompt_version}",
        f"- target_mode: {report.target_mode}",
        f"- stable_prefix_chars: {report.stable_prefix_chars}",
        f"- stable_prefix_hash: {report.stable_prefix_hash}",
        "",
        f"## Units ({report.unit_count})",
    ]
    for sample in report.sample_units:
        lines.append(
            f"- {sample['unit_key']}: chars={sample['source_chars']} "
            f"placeholders={sample['placeholder_count']} "
            f"passthrough={','.join(sample['passthrough_kinds']) or '-'} "
            f"sha={sample['content_sha256']}"
        )
        if sample.get("message_roles"):
            lines.append(
                f"  message_roles={sample['message_roles']} "
                f"dynamic_user_chars={sample.get('dynamic_user_chars')}"
            )
        lines.append(f"  preview: {sample['source_preview']!r}")
    if report.unit_count > len(report.sample_units):
        lines.append(f"  ... {report.unit_count - len(report.sample_units)} more units not shown")
    lines.extend(["", "## Notes"])
    for note in report.notes:
        lines.append(f"- {note}")
    return "\n".join(lines) + "\n"
