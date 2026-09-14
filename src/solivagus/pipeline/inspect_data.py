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
    sends_ocr_text_only: bool = False
    unit_count: int = 0
    sample_units: list[dict[str, Any]] = field(default_factory=list)
    partitions: list[dict[str, Any]] = field(default_factory=list)
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
            "partitions": self.partitions,
            "sample_units": self.sample_units,
            "notes": self.notes,
        }


def _message_manifest(
    messages: list[dict[str, str]],
    *,
    include_content: bool,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in messages:
        content = str(msg.get("content") or "")
        entry: dict[str, Any] = {
            "role": msg.get("role"),
            "chars": len(content),
            "sha256": sha256_text(content)[:16],
        }
        if include_content:
            entry["content"] = content
        out.append(entry)
    return out


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
    include_content: bool = False,
) -> InspectDataReport:
    if sample_limit < 0:
        raise ValueError("--sample must be >= 0")
    doc = db.fetchone("SELECT * FROM documents WHERE id = ?", (document_id,))
    if doc is None:
        raise ValueError(f"document not found: {document_id}")
    units = db.list_units(document_id)
    partitions = db.list_partitions(document_id)
    source_sha = str(doc["source_sha256"] or "")
    user_id = document_user_id(source_sha) if source_sha else "(unset)"
    document_title = Path(str(doc["display_name"])).stem

    capsule = empty_capsule()
    latest = db.get_latest_style_capsule(document_id)
    if latest is not None:
        capsule = StyleCapsule.from_db_row(latest)
    capsule_text = capsule.to_prompt_text()
    has_style_payload = bool(
        capsule.terminology
        or capsule.examples
        or (capsule.boundary_context or {}).get("source_tail")
        or (capsule.boundary_context or {}).get("translation_tail")
    )

    units_by_partition: dict[int | None, list[Any]] = {}
    for unit in units:
        pid = unit["partition_id"]
        units_by_partition.setdefault(int(pid) if pid is not None else None, []).append(unit)

    partition_manifests: list[dict[str, Any]] = []
    preview_budget = sample_limit
    samples: list[dict[str, Any]] = []

    def _emit_partition(
        *,
        sequence_index: int | None,
        partition_id: int | None,
        part_units: list[Any],
        part_user_id: str,
    ) -> None:
        nonlocal preview_budget
        unit_dicts = [
            {"unit_key": u["unit_key"], "source_text": u["source_text"] or ""} for u in part_units
        ]
        system, stable_user, prefix_hash = build_stable_prefix(
            document_title=document_title,
            target_language=settings.target_language,
            units=unit_dicts or [{"unit_key": "u00000", "source_text": ""}],
            style_capsule=capsule_text,
            prompt_version=settings.prompt_version or PROMPT_VERSION,
        )
        unit_requests: list[dict[str, Any]] = []
        for unit in part_units:
            protected, _ph = protect_markdown(str(unit["source_text"] or ""))
            messages = build_unit_messages(
                stable_system=system,
                stable_user=stable_user,
                warmup_assistant="PARTITION_READY",
                unit_key=str(unit["unit_key"]),
                source_text=protected,
                target_mode=settings.target_mode,  # type: ignore[arg-type]
            )
            unit_entry: dict[str, Any] = {
                "unit_key": str(unit["unit_key"]),
                "message_count": len(messages),
                "message_roles": [m.get("role") for m in messages],
                "messages": _message_manifest(messages, include_content=include_content),
                "sources": {
                    "stable_prefix": "partition OCR/markdown + style capsule",
                    "warmup_assistant": "placeholder PARTITION_READY (real run uses warm-up reply)",
                    "dynamic_user": "protected OCR/markdown for this unit",
                },
            }
            unit_requests.append(unit_entry)
            if preview_budget > 0:
                sample = _preview_unit(unit)
                sample["partition_sequence"] = sequence_index
                sample["message_roles"] = unit_entry["message_roles"]
                sample["dynamic_user_chars"] = unit_entry["messages"][-1]["chars"]
                samples.append(sample)
                preview_budget -= 1

        partition_manifests.append(
            {
                "partition_id": partition_id,
                "sequence_index": sequence_index,
                "user_id": part_user_id,
                "unit_count": len(part_units),
                "stable_prefix_chars": len(stable_user),
                "stable_prefix_hash": prefix_hash,
                "stable_system_chars": len(system),
                "style_capsule_version": capsule.version_label(),
                "style_capsule_chars": len(capsule_text),
                "includes_prior_translations": has_style_payload,
                "warmup_request": {
                    "message_roles": ["system", "user"],
                    "messages": _message_manifest(
                        [
                            {"role": "system", "content": system},
                            {"role": "user", "content": stable_user},
                        ],
                        include_content=include_content,
                    ),
                },
                "unit_requests": unit_requests,
            }
        )

    if partitions:
        for partition in partitions:
            part_id = int(partition["id"])
            part_units = units_by_partition.get(part_id, [])
            part_user = str(partition["user_id"] or user_id)
            _emit_partition(
                sequence_index=int(partition["sequence_index"]),
                partition_id=part_id,
                part_units=part_units,
                part_user_id=part_user,
            )
    elif units:
        _emit_partition(
            sequence_index=None,
            partition_id=None,
            part_units=list(units),
            part_user_id=user_id,
        )

    first_prefix_chars = (
        int(partition_manifests[0]["stable_prefix_chars"]) if partition_manifests else 0
    )
    first_prefix_hash = (
        str(partition_manifests[0]["stable_prefix_hash"]) if partition_manifests else ""
    )

    notes = [
        "PDF and images stay local; API payloads are text messages only.",
        "Stable prefix is built per partition from that partition's units, not the whole document.",
        "Style capsule may include prior translations and boundary context — not OCR-only.",
        "user_id is derived from document SHA-256, not filename or author.",
        "This command does not call the network.",
        "Use --include-content to print full message bodies (may contain sensitive text).",
    ]
    if not units:
        notes.append("No translation units yet — run plan/OCR first for a full unit inventory.")
    if sample_limit == 0:
        notes.append("sample=0: unit previews omitted; partition request manifests still included.")

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
        sends_ocr_text_only=not has_style_payload,
        unit_count=len(units),
        sample_units=samples,
        partitions=partition_manifests,
        stable_prefix_chars=first_prefix_chars,
        stable_prefix_hash=first_prefix_hash,
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
        f"- stable_prefix_chars (first partition): {report.stable_prefix_chars}",
        f"- stable_prefix_hash (first partition): {report.stable_prefix_hash}",
        "",
        f"## Partitions ({len(report.partitions)})",
    ]
    for part in report.partitions:
        lines.append(
            f"- seq={part.get('sequence_index')} id={part.get('partition_id')} "
            f"units={part['unit_count']} prefix_chars={part['stable_prefix_chars']} "
            f"prefix_hash={part['stable_prefix_hash']} "
            f"style={part['style_capsule_version']} "
            f"includes_prior_translations={part['includes_prior_translations']}"
        )
        warmup = part.get("warmup_request") or {}
        lines.append(f"  warmup_roles={warmup.get('message_roles')}")
        for req in part.get("unit_requests") or []:
            lines.append(
                f"  unit {req['unit_key']}: roles={req['message_roles']} "
                f"msgs={req['message_count']}"
            )
            for idx, msg in enumerate(req.get("messages") or []):
                lines.append(
                    f"    [{idx}] role={msg['role']} chars={msg['chars']} sha={msg['sha256']}"
                )
                if "content" in msg:
                    preview = msg["content"]
                    if len(preview) > 200:
                        preview = preview[:200] + "…"
                    lines.append(f"        content_preview: {preview!r}")
    lines.extend(["", f"## Sample units ({len(report.sample_units)} / {report.unit_count})"])
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
    if report.unit_count > len(report.sample_units) and report.sample_units:
        lines.append(f"  ... {report.unit_count - len(report.sample_units)} more units not shown")
    lines.extend(["", "## Notes"])
    for note in report.notes:
        lines.append(f"- {note}")
    return "\n".join(lines) + "\n"
