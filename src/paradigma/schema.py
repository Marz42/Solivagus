"""OKF concept schema registry and pure validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import re

from .diagnostics import Diagnostic, Severity
from .errors import ParseFailure, SchemaFailure
from .parser import FlatValue, load_flat_yaml_file


TIMESTAMP_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(Z|[+-]\d{2}:\d{2})$"
)
HEADING_PATTERN = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
BEGIN_MARKER = "<!-- BEGIN PARADIGMA AUTO-INDEX -->"
END_MARKER = "<!-- END PARADIGMA AUTO-INDEX -->"
CHECKSUM_PATTERN = re.compile(r"<!-- checksum:\s*([0-9a-f]+)\s*-->")


def _get_list(data: dict[str, FlatValue], key: str) -> tuple[str, ...]:
    value = data.get(key, [])
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    return (str(value),) if value else ()


def _get_scalar(data: dict[str, FlatValue], key: str) -> str:
    value = data.get(key, "")
    return "" if isinstance(value, list) else str(value).strip()


@dataclass(frozen=True)
class DocumentType:
    name: str
    layer: str
    default_temperature: str
    required_sections: tuple[str, ...]


@dataclass(frozen=True)
class SchemaRegistry:
    source: Path
    document_schema_version: str
    required_frontmatter: tuple[str, ...]
    required_paradigma_fields: tuple[str, ...]
    allowed_update_policies: tuple[str, ...]
    allowed_epistemic_statuses: tuple[str, ...]
    allowed_temperatures: tuple[str, ...]
    allowed_lifecycles: tuple[str, ...]
    document_types: dict[str, DocumentType]


def load_schema_registry(path: Path) -> SchemaRegistry:
    try:
        raw = load_flat_yaml_file(path)
    except ParseFailure as error:
        raise SchemaFailure(error.diagnostic) from error
    type_names = sorted(
        {key.split(".")[1] for key in raw if key.startswith("types.")}
    )
    document_types = {
        name: DocumentType(
            name=name,
            layer=_get_scalar(raw, f"types.{name}.layer"),
            default_temperature=_get_scalar(
                raw, f"types.{name}.default_temperature"
            ),
            required_sections=_get_list(
                raw, f"types.{name}.required_sections"
            ),
        )
        for name in type_names
    }
    version = _get_scalar(raw, "document_schema_version")
    if not version:
        raise SchemaFailure(
            Diagnostic(
                "PD_SCHEMA_VERSION_MISSING",
                "missing document_schema_version",
                str(path),
            )
        )
    return SchemaRegistry(
        source=path,
        document_schema_version=version,
        required_frontmatter=_get_list(raw, "required_frontmatter"),
        required_paradigma_fields=_get_list(raw, "required_paradigma_fields"),
        allowed_update_policies=_get_list(raw, "allowed_update_policies"),
        allowed_epistemic_statuses=_get_list(raw, "allowed_epistemic_statuses"),
        allowed_temperatures=_get_list(raw, "allowed_temperatures"),
        allowed_lifecycles=_get_list(raw, "allowed_lifecycles"),
        document_types=document_types,
    )


def validate_concept(
    metadata: dict[str, FlatValue],
    body: str,
    registry: SchemaRegistry,
    *,
    source: str,
    strict: bool = True,
) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    document_type = _get_scalar(metadata, "type")
    if not document_type:
        return (
            Diagnostic(
                "PD_SCHEMA_TYPE_MISSING",
                "frontmatter must include a non-empty `type` field",
                source,
            ),
        )
    if document_type not in registry.document_types:
        diagnostics.append(
            Diagnostic(
                "PD_SCHEMA_TYPE_UNKNOWN",
                f"unknown type `{document_type}`",
                source,
            )
        )
    required = registry.required_frontmatter if strict else ("type",)
    for key in required:
        if not metadata.get(key):
            diagnostics.append(
                Diagnostic(
                    "PD_SCHEMA_FIELD_MISSING",
                    f"missing required frontmatter field `{key}`",
                    source,
                    details={"field": key},
                )
            )
    timestamp = _get_scalar(metadata, "timestamp")
    if timestamp and not TIMESTAMP_PATTERN.fullmatch(timestamp):
        diagnostics.append(
            Diagnostic(
                "PD_SCHEMA_TIMESTAMP_INVALID",
                f"timestamp `{timestamp}` is not ISO 8601",
                source,
            )
        )
    if strict:
        for key in registry.required_paradigma_fields:
            if not metadata.get(f"paradigma.{key}"):
                diagnostics.append(
                    Diagnostic(
                        "PD_SCHEMA_PARADIGMA_FIELD_MISSING",
                        f"missing required paradigma field `{key}`",
                        source,
                        details={"field": key},
                    )
                )
        enum_checks = (
            ("paradigma.update_policy", registry.allowed_update_policies),
            ("paradigma.epistemic_status", registry.allowed_epistemic_statuses),
            ("paradigma.temperature", registry.allowed_temperatures),
            ("paradigma.lifecycle", registry.allowed_lifecycles),
        )
        for field_name, allowed in enum_checks:
            value = _get_scalar(metadata, field_name)
            if value and allowed and value not in allowed:
                diagnostics.append(
                    Diagnostic(
                        "PD_SCHEMA_ENUM_INVALID",
                        f"invalid {field_name} `{value}`",
                        source,
                        details={"field": field_name, "allowed": list(allowed)},
                    )
                )
        definition = registry.document_types.get(document_type)
        if definition is not None:
            headings = {
                match.group(1).strip()
                for match in HEADING_PATTERN.finditer(body)
            }
            for section in definition.required_sections:
                if section not in headings:
                    diagnostics.append(
                        Diagnostic(
                            "PD_SCHEMA_SECTION_MISSING",
                            f"missing required section `# {section}`",
                            source,
                            details={"section": section},
                        )
                    )
        if not metadata.get("paradigma.retrieval_hints.zh") and not metadata.get(
            "paradigma.retrieval_hints.en"
        ):
            diagnostics.append(
                Diagnostic(
                    "PD_SCHEMA_RETRIEVAL_HINTS_MISSING",
                    "retrieval_hints are missing",
                    source,
                    severity=Severity.WARNING,
                )
            )
        has_relations = any(
            key.startswith("paradigma.relations.") for key in metadata
        )
        if not has_relations and "decision" not in document_type:
            diagnostics.append(
                Diagnostic(
                    "PD_SCHEMA_RELATIONS_MISSING",
                    "relations are missing",
                    source,
                    severity=Severity.WARNING,
                )
            )
    return tuple(diagnostics)


def validate_generated_index(
    text: str, *, source: str, strict: bool = True
) -> tuple[Diagnostic, ...]:
    begin_count = text.count(BEGIN_MARKER)
    end_count = text.count(END_MARKER)
    diagnostics: list[Diagnostic] = []
    if begin_count != end_count:
        diagnostics.append(
            Diagnostic(
                "PD_SCHEMA_INDEX_MARKERS_UNBALANCED",
                "generated block markers are unbalanced",
                source,
            )
        )
        return tuple(diagnostics)
    if strict and begin_count:
        between = text.split(BEGIN_MARKER, 1)[1].split(END_MARKER, 1)[0].strip(
            "\n"
        )
        checksum_match = CHECKSUM_PATTERN.search(between)
        if checksum_match is None:
            diagnostics.append(
                Diagnostic(
                    "PD_SCHEMA_INDEX_CHECKSUM_MISSING",
                    "generated block checksum is missing",
                    source,
                    severity=Severity.WARNING,
                )
            )
        else:
            inner_lines = [
                line
                for line in between.splitlines()
                if not CHECKSUM_PATTERN.match(line.strip())
            ]
            digest = hashlib.sha256(
                "\n".join(inner_lines).encode("utf-8")
            ).hexdigest()[:16]
            if digest != checksum_match.group(1):
                diagnostics.append(
                    Diagnostic(
                        "PD_SCHEMA_INDEX_CHECKSUM_STALE",
                        "generated block checksum is stale",
                        source,
                    )
                )
    return tuple(diagnostics)
