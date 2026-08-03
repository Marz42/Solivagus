"""Deterministic YAML codec and projection store for ContextManifest."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
import hashlib
import json

import yaml

from ..atomic import atomic_replace_text
from ..errors import AtomicWriteFailure
from ..integrations.coding import (
    ContextDocument,
    ContextExclusion,
    ContextManifest,
    ContextPriority,
    ContextRequest,
    ContextSourceKind,
)
from ..parser import load_yaml_text, read_utf8_source
from .coding import (
    CodingRuntimeNotFoundError,
    CodingRuntimeSchemaError,
    CodingRuntimeStorageError,
)


CONTEXT_MANIFEST_VERSION = "0.1"
_EMPTY_DIGEST = "sha256:" + "0" * 64


@dataclass(frozen=True)
class StoredContextManifest:
    manifest: ContextManifest
    source_hash: str
    path: Path
    canonical: bool


def _exact(data: dict[str, Any], keys: tuple[str, ...], field: str) -> None:
    missing = [key for key in keys if key not in data]
    unknown = [key for key in data if key not in keys]
    if missing or unknown:
        raise CodingRuntimeSchemaError(
            f"{field} fields do not match schema (missing={missing}; unknown={unknown})"
        )


def _mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CodingRuntimeSchemaError(f"{field} must be a string-keyed mapping")
    return value


def _string(value: object, field: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str):
        raise CodingRuntimeSchemaError(f"{field} must be a string")
    return value


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CodingRuntimeSchemaError(f"{field} must be an integer")
    return value


def _strings(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CodingRuntimeSchemaError(f"{field} must be a list of strings")
    return tuple(value)


class CodingContextManifestCodec:
    """Strict codec whose checksum covers every field except the checksum itself."""

    def create(
        self,
        *,
        request: ContextRequest,
        session_id: str | None,
        checkpoint_id: str | None,
        source_digest: str,
        documents: tuple[ContextDocument, ...],
        excluded: tuple[ContextExclusion, ...],
        warnings: tuple[str, ...],
    ) -> ContextManifest:
        draft = ContextManifest(
            request=request,
            session_id=session_id,
            checkpoint_id=checkpoint_id,
            source_digest=source_digest,
            estimated_tokens=sum(item.estimated_tokens for item in documents),
            documents=documents,
            excluded=excluded,
            warnings=warnings,
            checksum=_EMPTY_DIGEST,
        )
        return replace(draft, checksum=self.checksum(draft))

    def checksum(self, manifest: ContextManifest) -> str:
        payload = json.dumps(
            self._data(manifest, include_checksum=False),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(payload).hexdigest()

    def encode(self, manifest: ContextManifest) -> str:
        if manifest.checksum != self.checksum(manifest):
            raise CodingRuntimeSchemaError("context manifest checksum does not match payload")
        return yaml.safe_dump(
            self._data(manifest, include_checksum=True),
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=100,
        )

    def decode(self, text: str, *, source: str = "<string>") -> ContextManifest:
        data = load_yaml_text(text, source=source)
        _exact(
            data,
            (
                "manifest_version", "profile", "request", "session_id",
                "checkpoint_id", "source_digest", "estimated_tokens", "documents",
                "excluded", "warnings", "checksum",
            ),
            "context manifest",
        )
        if data["manifest_version"] != CONTEXT_MANIFEST_VERSION:
            raise CodingRuntimeSchemaError("unsupported context manifest version")
        if data["profile"] != "coding":
            raise CodingRuntimeSchemaError("context manifest profile must be coding")
        request_data = _mapping(data["request"], "request")
        _exact(
            request_data,
            (
                "intent", "task_id", "explicit_paths", "explicit_symbols",
                "keywords", "budget_tokens",
            ),
            "context request",
        )
        try:
            request = ContextRequest(
                intent=_string(request_data["intent"], "request.intent"),
                task_id=_string(request_data["task_id"], "request.task_id"),
                explicit_paths=_strings(request_data["explicit_paths"], "request.explicit_paths"),
                explicit_symbols=_strings(
                    request_data["explicit_symbols"], "request.explicit_symbols"
                ),
                keywords=_strings(request_data["keywords"], "request.keywords"),
                budget_tokens=_integer(request_data["budget_tokens"], "request.budget_tokens"),
            )
            manifest = ContextManifest(
                request=request,
                session_id=_string(data["session_id"], "session_id", optional=True),
                checkpoint_id=_string(
                    data["checkpoint_id"], "checkpoint_id", optional=True
                ),
                source_digest=_string(data["source_digest"], "source_digest"),
                estimated_tokens=_integer(data["estimated_tokens"], "estimated_tokens"),
                documents=self._documents(data["documents"]),
                excluded=self._excluded(data["excluded"]),
                warnings=_strings(data["warnings"], "warnings"),
                checksum=_string(data["checksum"], "checksum"),
            )
        except ValueError as error:
            raise CodingRuntimeSchemaError(str(error)) from error
        if manifest.checksum != self.checksum(manifest):
            raise CodingRuntimeSchemaError("context manifest checksum does not match payload")
        return manifest

    @staticmethod
    def _documents(raw: object) -> tuple[ContextDocument, ...]:
        if not isinstance(raw, list):
            raise CodingRuntimeSchemaError("documents must be a list")
        result = []
        keys = (
            "document_id", "path", "source_kind", "title", "priority",
            "estimated_tokens", "reasons",
        )
        for index, item in enumerate(raw):
            value = _mapping(item, f"documents[{index}]")
            _exact(value, keys, f"documents[{index}]")
            result.append(ContextDocument(
                document_id=_string(value["document_id"], "document_id"),
                path=_string(value["path"], "path"),
                source_kind=_string(value["source_kind"], "source_kind"),
                title=_string(value["title"], "title"),
                priority=_string(value["priority"], "priority"),
                estimated_tokens=_integer(value["estimated_tokens"], "estimated_tokens"),
                reasons=_strings(value["reasons"], "reasons"),
            ))
        return tuple(result)

    @staticmethod
    def _excluded(raw: object) -> tuple[ContextExclusion, ...]:
        if not isinstance(raw, list):
            raise CodingRuntimeSchemaError("excluded must be a list")
        result = []
        keys = ("document_id", "path", "reason", "estimated_tokens")
        for index, item in enumerate(raw):
            value = _mapping(item, f"excluded[{index}]")
            _exact(value, keys, f"excluded[{index}]")
            result.append(ContextExclusion(
                document_id=_string(value["document_id"], "document_id"),
                path=_string(value["path"], "path"),
                reason=_string(value["reason"], "reason"),
                estimated_tokens=_integer(value["estimated_tokens"], "estimated_tokens"),
            ))
        return tuple(result)

    @staticmethod
    def _data(manifest: ContextManifest, *, include_checksum: bool) -> dict[str, object]:
        data: dict[str, object] = {
            "manifest_version": manifest.manifest_version,
            "profile": manifest.profile,
            "request": {
                "intent": manifest.request.intent,
                "task_id": manifest.request.task_id,
                "explicit_paths": list(manifest.request.explicit_paths),
                "explicit_symbols": list(manifest.request.explicit_symbols),
                "keywords": list(manifest.request.keywords),
                "budget_tokens": manifest.request.budget_tokens,
            },
            "session_id": manifest.session_id,
            "checkpoint_id": manifest.checkpoint_id,
            "source_digest": manifest.source_digest,
            "estimated_tokens": manifest.estimated_tokens,
            "documents": [
                {
                    "document_id": item.document_id,
                    "path": item.path,
                    "source_kind": item.source_kind.value,
                    "title": item.title,
                    "priority": item.priority.value,
                    "estimated_tokens": item.estimated_tokens,
                    "reasons": list(item.reasons),
                }
                for item in manifest.documents
            ],
            "excluded": [
                {
                    "document_id": item.document_id,
                    "path": item.path,
                    "reason": item.reason,
                    "estimated_tokens": item.estimated_tokens,
                }
                for item in manifest.excluded
            ],
            "warnings": list(manifest.warnings),
        }
        if include_checksum:
            data["checksum"] = manifest.checksum
        return data


class CodingContextManifestStore:
    """Atomic store for the current derived context manifest."""

    def __init__(self, runtime_root: Path, *, codec: CodingContextManifestCodec | None = None):
        self.root = Path(runtime_root).resolve()
        self.codec = codec or CodingContextManifestCodec()

    @property
    def path(self) -> Path:
        return self.root / "context-manifest.yaml"

    def write(self, manifest: ContextManifest) -> StoredContextManifest:
        if self.path.is_symlink():
            raise CodingRuntimeStorageError(f"context manifest must not be symlink: {self.path}")
        try:
            atomic_replace_text(self.path, self.codec.encode(manifest))
        except AtomicWriteFailure as error:
            raise CodingRuntimeStorageError(str(error)) from error
        return self.read()

    def read(self) -> StoredContextManifest:
        if not self.path.exists():
            raise CodingRuntimeNotFoundError(f"context manifest does not exist: {self.path}")
        if self.path.is_symlink():
            raise CodingRuntimeStorageError(f"context manifest must not be symlink: {self.path}")
        source = read_utf8_source(self.path)
        manifest = self.codec.decode(source.text, source=str(self.path))
        canonical = source.raw == self.codec.encode(manifest).encode("utf-8")
        return StoredContextManifest(
            manifest=manifest,
            source_hash="sha256:" + hashlib.sha256(source.raw).hexdigest(),
            path=self.path,
            canonical=canonical,
        )
