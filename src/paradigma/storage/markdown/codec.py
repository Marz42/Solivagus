"""Deterministic codec for one-MemoryRecord-per-Markdown documents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any

import yaml

from paradigma.kernel.models.memory import MemoryRecord
from paradigma.kernel.models.provenance import ProvenanceRef
from paradigma.kernel.models.relation import MemoryRelation
from paradigma.kernel.models.scope import MemoryScope
from paradigma.parser import parse_markdown_text
from paradigma.storage.errors import MemoryDocumentError, MemoryIntegrityError


MEMORY_DOCUMENT_TYPE = "paradigma-memory"
MEMORY_DOCUMENT_SCHEMA_VERSION = "0.1"
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_TOP_LEVEL_KEYS = {
    "type",
    "memory_schema_version",
    "memory_id",
    "memory_type",
    "title",
    "status",
    "revision",
    "scope",
    "provenance",
    "validity",
    "confidence",
    "sensitivity",
    "tags",
    "relations",
    "created_at",
    "updated_at",
    "content_hash",
}
_SCOPE_KEYS = {
    "namespace",
    "workspace_id",
    "project_id",
    "task_id",
    "session_id",
    "entity_ids",
}
_PROVENANCE_KEYS = {
    "source_type",
    "source_uri",
    "source_id",
    "observed_at",
    "excerpt_hash",
    "actor",
}
_VALIDITY_KEYS = {"from", "until"}
_RELATION_KEYS = {"relation_type", "target_memory_id"}


@dataclass(frozen=True)
class DecodedMemoryDocument:
    record: MemoryRecord
    content_hash: str
    source_hash: str
    canonical: bool


class MemoryMarkdownCodec:
    """Encode and validate the canonical Markdown representation."""

    def encode(self, record: MemoryRecord) -> str:
        if not isinstance(record, MemoryRecord):
            raise MemoryDocumentError("record must be a MemoryRecord")
        if "\r" in record.content:
            raise MemoryDocumentError("record content must use LF line endings")
        metadata = self._metadata(record)
        dumped = yaml.safe_dump(
            metadata,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )
        return f"---\n{dumped}---\n\n{record.content}\n"

    def decode(self, text: str, *, source: str = "<string>") -> MemoryRecord:
        return self.inspect(text, source=source).record

    def inspect(
        self, text: str, *, source: str = "<string>"
    ) -> DecodedMemoryDocument:
        if not isinstance(text, str):
            raise MemoryDocumentError("Markdown document must be text")
        parsed = parse_markdown_text(text, source=source)
        metadata = parsed.metadata
        self._require_exact_keys(metadata, _TOP_LEVEL_KEYS, "frontmatter")
        if metadata["type"] != MEMORY_DOCUMENT_TYPE:
            raise MemoryDocumentError(
                f"type must be {MEMORY_DOCUMENT_TYPE!r}"
            )
        if metadata["memory_schema_version"] != MEMORY_DOCUMENT_SCHEMA_VERSION:
            raise MemoryDocumentError(
                "unsupported memory_schema_version "
                f"{metadata['memory_schema_version']!r}"
            )
        declared_hash = self._require_hash(
            metadata["content_hash"], "content_hash"
        )
        if not parsed.body.startswith("\n"):
            raise MemoryDocumentError(
                "frontmatter and memory content must be separated by one blank line"
            )
        content = parsed.body[1:]
        try:
            record = self._record(metadata, content)
        except ValueError as error:
            if isinstance(error, MemoryDocumentError):
                raise
            raise MemoryDocumentError(f"invalid MemoryRecord: {error}") from error
        actual_hash = self.content_hash(record)
        if declared_hash != actual_hash:
            raise MemoryIntegrityError(
                "content_hash does not match the decoded MemoryRecord"
            )
        return DecodedMemoryDocument(
            record=record,
            content_hash=actual_hash,
            source_hash=self.source_hash(text),
            canonical=text == self.encode(record),
        )

    def content_hash(self, record: MemoryRecord) -> str:
        if not isinstance(record, MemoryRecord):
            raise MemoryDocumentError("record must be a MemoryRecord")
        payload = json.dumps(
            self._record_payload(record),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(payload).hexdigest()

    @staticmethod
    def source_hash(text: str) -> str:
        if not isinstance(text, str):
            raise MemoryDocumentError("Markdown document must be text")
        return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def source_hash_bytes(raw: bytes) -> str:
        if not isinstance(raw, bytes):
            raise MemoryDocumentError("Markdown source must be bytes")
        return "sha256:" + hashlib.sha256(raw).hexdigest()

    def _metadata(self, record: MemoryRecord) -> dict[str, Any]:
        payload = self._record_payload(record)
        return {
            "type": MEMORY_DOCUMENT_TYPE,
            "memory_schema_version": MEMORY_DOCUMENT_SCHEMA_VERSION,
            "memory_id": payload["memory_id"],
            "memory_type": payload["memory_type"],
            "title": payload["title"],
            "status": payload["status"],
            "revision": payload["revision"],
            "scope": payload["scope"],
            "provenance": payload["provenance"],
            "validity": payload["validity"],
            "confidence": payload["confidence"],
            "sensitivity": payload["sensitivity"],
            "tags": payload["tags"],
            "relations": payload["relations"],
            "created_at": payload["created_at"],
            "updated_at": payload["updated_at"],
            "content_hash": self.content_hash(record),
        }

    @staticmethod
    def _record_payload(record: MemoryRecord) -> dict[str, Any]:
        return {
            "memory_id": record.memory_id,
            "memory_type": record.memory_type.value,
            "title": record.title,
            "content": record.content,
            "scope": {
                "namespace": record.scope.namespace,
                "workspace_id": record.scope.workspace_id,
                "project_id": record.scope.project_id,
                "task_id": record.scope.task_id,
                "session_id": record.scope.session_id,
                "entity_ids": list(record.scope.entity_ids),
            },
            "provenance": [
                {
                    "source_type": item.source_type.value,
                    "source_uri": item.source_uri,
                    "source_id": item.source_id,
                    "observed_at": _format_datetime(item.observed_at),
                    "excerpt_hash": item.excerpt_hash,
                    "actor": item.actor,
                }
                for item in record.provenance
            ],
            "status": record.status.value,
            "revision": record.revision,
            "validity": {
                "from": _format_datetime(record.valid_from),
                "until": _format_datetime(record.valid_until),
            },
            "confidence": (
                None if record.confidence is None else float(record.confidence)
            ),
            "sensitivity": record.sensitivity,
            "tags": list(record.tags),
            "relations": [
                {
                    "relation_type": item.relation_type,
                    "target_memory_id": item.target_memory_id,
                }
                for item in record.relations
            ],
            "created_at": _format_datetime(record.created_at),
            "updated_at": _format_datetime(record.updated_at),
        }

    def _record(self, metadata: dict[str, Any], content: str) -> MemoryRecord:
        scope = self._mapping(metadata["scope"], "scope")
        self._require_exact_keys(scope, _SCOPE_KEYS, "scope")
        validity = self._mapping(metadata["validity"], "validity")
        self._require_exact_keys(validity, _VALIDITY_KEYS, "validity")
        provenance_values = self._list(metadata["provenance"], "provenance")
        relation_values = self._list(metadata["relations"], "relations")
        tags = self._string_list(metadata["tags"], "tags")

        provenance: list[ProvenanceRef] = []
        for index, value in enumerate(provenance_values):
            item = self._mapping(value, f"provenance[{index}]")
            self._require_exact_keys(
                item, _PROVENANCE_KEYS, f"provenance[{index}]"
            )
            provenance.append(
                ProvenanceRef(
                    source_type=self._string(
                        item["source_type"], f"provenance[{index}].source_type"
                    ),
                    source_uri=self._optional_string(
                        item["source_uri"], f"provenance[{index}].source_uri"
                    ),
                    source_id=self._optional_string(
                        item["source_id"], f"provenance[{index}].source_id"
                    ),
                    observed_at=self._optional_datetime(
                        item["observed_at"], f"provenance[{index}].observed_at"
                    ),
                    excerpt_hash=self._optional_string(
                        item["excerpt_hash"], f"provenance[{index}].excerpt_hash"
                    ),
                    actor=self._optional_string(
                        item["actor"], f"provenance[{index}].actor"
                    ),
                )
            )

        relations: list[MemoryRelation] = []
        for index, value in enumerate(relation_values):
            item = self._mapping(value, f"relations[{index}]")
            self._require_exact_keys(item, _RELATION_KEYS, f"relations[{index}]")
            relations.append(
                MemoryRelation(
                    relation_type=self._string(
                        item["relation_type"], f"relations[{index}].relation_type"
                    ),
                    target_memory_id=self._string(
                        item["target_memory_id"],
                        f"relations[{index}].target_memory_id",
                    ),
                )
            )

        try:
            return MemoryRecord(
                memory_id=self._string(metadata["memory_id"], "memory_id"),
                memory_type=self._string(metadata["memory_type"], "memory_type"),
                title=self._string(metadata["title"], "title"),
                content=content,
                scope=MemoryScope(
                    namespace=self._string(scope["namespace"], "scope.namespace"),
                    workspace_id=self._optional_string(
                        scope["workspace_id"], "scope.workspace_id"
                    ),
                    project_id=self._optional_string(
                        scope["project_id"], "scope.project_id"
                    ),
                    task_id=self._optional_string(scope["task_id"], "scope.task_id"),
                    session_id=self._optional_string(
                        scope["session_id"], "scope.session_id"
                    ),
                    entity_ids=tuple(
                        self._string_list(scope["entity_ids"], "scope.entity_ids")
                    ),
                ),
                provenance=tuple(provenance),
                status=self._string(metadata["status"], "status"),
                revision=metadata["revision"],
                valid_from=self._optional_datetime(validity["from"], "validity.from"),
                valid_until=self._optional_datetime(
                    validity["until"], "validity.until"
                ),
                confidence=metadata["confidence"],
                sensitivity=self._string(metadata["sensitivity"], "sensitivity"),
                tags=tuple(tags),
                relations=tuple(relations),
                created_at=self._datetime(metadata["created_at"], "created_at"),
                updated_at=self._datetime(metadata["updated_at"], "updated_at"),
            )
        except ValueError as error:
            if isinstance(error, MemoryDocumentError):
                raise
            raise MemoryDocumentError(f"invalid MemoryRecord: {error}") from error

    @staticmethod
    def _require_exact_keys(
        value: dict[str, Any], expected: set[str], field: str
    ) -> None:
        if not all(isinstance(key, str) for key in value):
            raise MemoryDocumentError(f"{field} fields must have string names")
        actual = set(value)
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        if missing or unknown:
            details = []
            if missing:
                details.append(f"missing {', '.join(missing)}")
            if unknown:
                details.append(f"unknown {', '.join(unknown)}")
            raise MemoryDocumentError(f"{field} fields invalid: {'; '.join(details)}")

    @staticmethod
    def _mapping(value: Any, field: str) -> dict[str, Any]:
        if not isinstance(value, dict) or not all(
            isinstance(key, str) for key in value
        ):
            raise MemoryDocumentError(f"{field} must be a mapping with string keys")
        return value

    @staticmethod
    def _list(value: Any, field: str) -> list[Any]:
        if not isinstance(value, list):
            raise MemoryDocumentError(f"{field} must be a list")
        return value

    @classmethod
    def _string_list(cls, value: Any, field: str) -> list[str]:
        return [
            cls._string(item, f"{field}[{index}]")
            for index, item in enumerate(cls._list(value, field))
        ]

    @staticmethod
    def _string(value: Any, field: str) -> str:
        if not isinstance(value, str):
            raise MemoryDocumentError(f"{field} must be a string")
        return value

    @classmethod
    def _optional_string(cls, value: Any, field: str) -> str | None:
        if value is None:
            return None
        return cls._string(value, field)

    @classmethod
    def _datetime(cls, value: Any, field: str) -> datetime:
        text = cls._string(value, field)
        try:
            return datetime.fromisoformat(text)
        except ValueError as error:
            raise MemoryDocumentError(
                f"{field} must be an ISO 8601 datetime"
            ) from error

    @classmethod
    def _optional_datetime(cls, value: Any, field: str) -> datetime | None:
        if value is None:
            return None
        return cls._datetime(value, field)

    @staticmethod
    def _require_hash(value: Any, field: str) -> str:
        if not isinstance(value, str) or not _HASH_PATTERN.fullmatch(value):
            raise MemoryDocumentError(
                f"{field} must use sha256: followed by 64 lowercase hex digits"
            )
        return value


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")
