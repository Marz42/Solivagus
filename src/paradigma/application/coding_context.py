"""Deterministic Coding Context Builder over OKF knowledge and canonical Memory."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote
import hashlib
import json

from ..config import ParadigmaConfig, require_valid_config
from ..diagnostics import Diagnostic
from ..errors import ParadigmaError
from ..integrations.coding import (
    ContextDocument,
    ContextExclusion,
    ContextManifest,
    ContextPriority,
    ContextRequest,
    ContextSourceKind,
)
from ..kernel import MemoryQuery, MemoryStatus
from ..parser import FlatValue, parse_flat_frontmatter, read_utf8_source
from ..runtime import (
    ActiveSessionPointer,
    ActiveTaskPointer,
    CodingContextManifestCodec,
    CodingContextManifestStore,
    CodingRuntimeStore,
)
from ..storage.catalog import CatalogQuery, SQLiteMemoryCatalog
from ..storage.markdown import MarkdownMemoryStore
from .indexing import all_concepts
from .outcomes import CommandOutcome


class CodingContextError(ParadigmaError):
    code = "PD_CONTEXT_ERROR"


@dataclass
class _Candidate:
    document_id: str
    path: str
    source_kind: ContextSourceKind
    title: str
    text: str
    estimated_tokens: int
    source_hash: str
    symbols: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    relation_targets: tuple[tuple[str, str], ...] = ()
    filter_reason: str | None = None
    reasons: set[str] = field(default_factory=set)


def build_context_manifest(repository_root: Path, request: ContextRequest) -> ContextManifest:
    if not isinstance(request, ContextRequest):
        raise CodingContextError("request must be ContextRequest", code="PD_CONTEXT_INPUT_ERROR")
    config = require_valid_config(repository_root)
    runtime = CodingRuntimeStore(config.repository_root / config.runtime_root_name)
    task_pointer_stored = runtime.read_active_task()
    task_pointer = task_pointer_stored.pointer
    assert isinstance(task_pointer, ActiveTaskPointer)
    if task_pointer.task_id not in (None, request.task_id):
        raise CodingContextError(
            "ContextRequest task_id must identify the active task when one exists",
            code="PD_CONTEXT_TASK_MISMATCH",
            exit_code=3,
        )
    task_stored = runtime.read_task(request.task_id)
    session_pointer_stored = runtime.read_active_session()
    session_pointer = session_pointer_stored.pointer
    assert isinstance(session_pointer, ActiveSessionPointer)
    session_id = session_pointer.session_id
    if (
        session_id is None
        and task_pointer.task_id is None
        and session_pointer.last_session_id is not None
    ):
        last = runtime.read_session(session_pointer.last_session_id)
        if last.session.task_id == request.task_id:
            session_id = last.session.session_id
            session_stored = last
        else:
            session_stored = None
    else:
        session_stored = runtime.read_session(session_id) if session_id is not None else None
    if session_stored is not None and session_stored.session.task_id != request.task_id:
        raise CodingContextError(
            "active Session belongs to another task",
            code="PD_CONTEXT_SESSION_MISMATCH",
            exit_code=3,
        )
    checkpoint_id = (
        session_stored.session.current_checkpoint_id if session_stored else None
    )
    checkpoint_hash = None
    if checkpoint_id is not None:
        from ..runtime import CodingCheckpointStore

        checkpoint_hash = CodingCheckpointStore(runtime.root).read(checkpoint_id).source_hash

    candidates, catalog_digest = _load_candidates(
        config,
        task_stored.task.repository.workspace_id,
        task_stored.task.repository.repository_id,
        request.task_id,
        session_id,
        task_stored.task.updated_at,
    )
    _match_direct(candidates, request)
    _expand_relations(candidates)
    documents, excluded, warnings = _select_with_budget(candidates, request.budget_tokens)
    source_digest = _source_digest(
        candidates,
        catalog_digest,
        task_stored.source_hash,
        session_pointer_stored.source_hash,
        session_stored.source_hash if session_stored else None,
        checkpoint_hash,
    )
    return CodingContextManifestCodec().create(
        request=request,
        session_id=session_id,
        checkpoint_id=checkpoint_id,
        source_digest=source_digest,
        documents=documents,
        excluded=excluded,
        warnings=warnings,
    )


def context_build_outcome(
    repository_root: Path,
    request: ContextRequest,
    *,
    write: bool = False,
) -> CommandOutcome:
    config = require_valid_config(repository_root)
    manifest = build_context_manifest(config.repository_root, request)
    store = CodingContextManifestStore(
        config.repository_root / config.runtime_root_name
    )
    encoded = store.codec.encode(manifest)
    would_change = (
        store.path.is_symlink()
        or not store.path.exists()
        or store.path.read_bytes() != encoded.encode("utf-8")
    )
    stored = None
    if write:
        stored = store.write(manifest) if would_change else store.read()
    data = _manifest_data(manifest)
    data.update(
        {
            "written": write,
            "would_change": would_change,
            "path": (
                str(stored.path.relative_to(config.repository_root).as_posix())
                if stored is not None
                else f"{config.runtime_root_name}/context-manifest.yaml"
            ),
            "source_hash": stored.source_hash if stored is not None else None,
        }
    )
    return CommandOutcome(
        command="context build",
        data=data,
        messages=(
            f"Context manifest selected {len(manifest.documents)} document(s); "
            f"estimated_tokens={manifest.estimated_tokens}."
        ,),
        changed=write and would_change,
        dry_run=not write,
    )


def context_verify_outcome(
    repository_root: Path, *, dry_run: bool = False
) -> CommandOutcome:
    config = require_valid_config(repository_root)
    store = CodingContextManifestStore(
        config.repository_root / config.runtime_root_name
    )
    stored = store.read()
    expected = build_context_manifest(config.repository_root, stored.manifest.request)
    current = store.codec.encode(stored.manifest) == store.codec.encode(expected)
    diagnostics = () if current else (
        Diagnostic(
            "PD_CONTEXT_MANIFEST_STALE",
            "context manifest does not match its request and current repository state; run `pd context build --write`",
            f"{config.runtime_root_name}/context-manifest.yaml",
        ),
    )
    return CommandOutcome(
        command="context verify",
        data={
            "current": current,
            "checksum": stored.manifest.checksum,
            "expected_checksum": expected.checksum,
            "source_digest": stored.manifest.source_digest,
            "expected_source_digest": expected.source_digest,
        },
        messages=(
            "Context manifest matches its request and current repository state."
            if current
            else "Context manifest is stale."
        ,),
        diagnostics=diagnostics,
        dry_run=dry_run,
    )


def _load_candidates(
    config: ParadigmaConfig,
    workspace_id: str,
    repository_id: str,
    task_id: str,
    session_id: str | None,
    valid_at,
) -> tuple[dict[str, _Candidate], str]:
    candidates: dict[str, _Candidate] = {}
    knowledge_paths: dict[Path, str] = {}
    pending_relations: dict[str, tuple[tuple[str, str], ...]] = {}
    for knowledge_root, concept in all_concepts(config):
        metadata, body = parse_flat_frontmatter(concept.path)
        source = read_utf8_source(concept.path)
        path = concept.path.relative_to(config.repository_root).as_posix()
        identifier = path
        knowledge_paths[concept.path.resolve()] = identifier
        epistemic = _scalar(metadata, "paradigma.epistemic_status")
        lifecycle = _scalar(metadata, "paradigma.lifecycle")
        filter_reason = None
        if epistemic in ("deprecated", "rejected"):
            filter_reason = f"epistemic_status_filtered:{epistemic}"
        elif lifecycle in ("deprecated", "rejected"):
            filter_reason = f"lifecycle_filtered:{lifecycle}"
        candidate = _Candidate(
            document_id=identifier,
            path=path,
            source_kind=ContextSourceKind.KNOWLEDGE,
            title=concept.title,
            text="\n".join(
                (concept.title, concept.description, *concept.hints, *concept.symbols, body)
            ),
            estimated_tokens=_tokens(source.raw),
            source_hash="sha256:" + hashlib.sha256(source.raw).hexdigest(),
            symbols=concept.symbols,
            filter_reason=filter_reason,
        )
        if _scalar(metadata, "paradigma.temperature") == "hot":
            candidate.reasons.add("mandatory_hot_document")
        candidates[identifier] = candidate
        pending_relations[identifier] = tuple(
            _split_relation(item) for item in concept.relations
        )
    for identifier, relations in pending_relations.items():
        source = (config.repository_root / candidates[identifier].path).resolve()
        resolved = []
        for kind, target in relations:
            path = _resolve_knowledge_target(source, target, config.knowledge_roots)
            target_id = knowledge_paths.get(path) if path is not None else None
            if target_id is not None:
                resolved.append((kind, target_id))
        candidates[identifier].relation_targets = tuple(resolved)

    memory_store = MarkdownMemoryStore(config.memory_root)
    catalog = SQLiteMemoryCatalog(
        config.catalog_path,
        memory_store,
        path_base=config.repository_root,
    )
    verification = catalog.verify()
    if not verification.current:
        raise CodingContextError(
            "memory catalog must be current before context retrieval: "
            + "; ".join(verification.issues),
            code="PD_CONTEXT_CATALOG_STALE",
            exit_code=2,
        )
    if verification.source_count > 1000:
        raise CodingContextError(
            "context retrieval currently supports at most 1000 canonical Memory records",
            code="PD_CONTEXT_CATALOG_LIMIT",
            exit_code=2,
        )
    query_results = catalog.query(
        CatalogQuery(MemoryQuery(valid_at=valid_at, limit=1000))
    )
    query_eligible_ids = {item.record.memory_id for item in query_results}
    for memory_path in memory_store.paths():
        stored = memory_store.read(memory_path.stem)
        record = stored.record
        if record.status is not MemoryStatus.ACTIVE:
            filter_reason = f"status_filtered:{record.status.value}"
        elif not record.is_valid_at(valid_at):
            filter_reason = f"validity_filtered:{valid_at.isoformat()}"
        elif record.memory_id not in query_eligible_ids:
            filter_reason = "catalog_query_filtered"
        else:
            filter_reason = _memory_scope_filter(
                record.scope,
                workspace_id,
                repository_id,
                task_id,
                session_id,
            )
        path = stored.path.relative_to(config.repository_root).as_posix()
        candidate = _Candidate(
            document_id=record.memory_id,
            path=path,
            source_kind=ContextSourceKind.MEMORY,
            title=record.title,
            text="\n".join((record.title, record.content, *record.tags)),
            estimated_tokens=_tokens(stored.path.read_bytes()),
            source_hash=stored.source_hash,
            tags=record.tags,
            relation_targets=tuple(
                (item.relation_type, item.target_memory_id)
                for item in record.relations
            ),
            filter_reason=filter_reason,
        )
        if "mandatory" in record.tags:
            candidate.reasons.add("mandatory_memory")
        candidates[record.memory_id] = candidate
    return candidates, verification.source_digest


def _match_direct(candidates: dict[str, _Candidate], request: ContextRequest) -> None:
    for candidate in candidates.values():
        for signal in request.explicit_paths:
            if _matches_path(signal, candidate):
                candidate.reasons.add(f"path_match:{signal}")
        symbols = {item.casefold() for item in candidate.symbols}
        symbols.update(
            item[len("symbol:") :].casefold()
            for item in candidate.tags
            if item.startswith("symbol:")
        )
        for signal in request.explicit_symbols:
            if signal.casefold() in symbols:
                candidate.reasons.add(f"symbol_match:{signal}")
        haystack = candidate.text.casefold()
        for keyword in request.keywords:
            if keyword.casefold() in haystack:
                candidate.reasons.add(f"keyword_match:{keyword}")


def _expand_relations(candidates: dict[str, _Candidate]) -> None:
    direct = tuple(
        candidate
        for candidate in candidates.values()
        if candidate.reasons and candidate.filter_reason is None
    )
    for source in sorted(direct, key=lambda item: item.document_id):
        for kind, target_id in source.relation_targets:
            target = candidates.get(target_id)
            if target is not None:
                target.reasons.add(f"relation_from:{source.document_id}:{kind}")


def _select_with_budget(
    candidates: dict[str, _Candidate], budget: int
) -> tuple[
    tuple[ContextDocument, ...],
    tuple[ContextExclusion, ...],
    tuple[str, ...],
]:
    matched = [candidate for candidate in candidates.values() if candidate.reasons]
    filtered = [candidate for candidate in matched if candidate.filter_reason is not None]
    eligible = [candidate for candidate in matched if candidate.filter_reason is None]
    eligible.sort(key=_candidate_key)
    selected: list[ContextDocument] = []
    excluded: list[ContextExclusion] = [
        ContextExclusion(
            item.document_id,
            item.path,
            item.filter_reason or "filtered",
            item.estimated_tokens,
        )
        for item in sorted(filtered, key=lambda value: value.path)
    ]
    used = 0
    for candidate in eligible:
        priority = _priority(candidate)
        if priority is not ContextPriority.REQUIRED and used + candidate.estimated_tokens > budget:
            excluded.append(ContextExclusion(
                candidate.document_id,
                candidate.path,
                "budget_trimmed",
                candidate.estimated_tokens,
            ))
            continue
        selected.append(ContextDocument(
            candidate.document_id,
            candidate.path,
            candidate.source_kind,
            candidate.title,
            priority,
            candidate.estimated_tokens,
            tuple(sorted(candidate.reasons, key=_reason_key)),
        ))
        used += candidate.estimated_tokens
    warnings = []
    required_tokens = sum(
        item.estimated_tokens
        for item in selected
        if item.priority is ContextPriority.REQUIRED
    )
    if required_tokens > budget:
        warnings.append(
            f"required context exceeds budget by {required_tokens - budget} token(s)"
        )
    if not selected:
        warnings.append("no eligible context documents matched the request")
    return tuple(selected), tuple(excluded), tuple(warnings)


def _candidate_key(candidate: _Candidate) -> tuple[int, str, str]:
    return (
        min(_reason_key(item)[0] for item in candidate.reasons),
        candidate.path,
        candidate.document_id,
    )


def _priority(candidate: _Candidate) -> ContextPriority:
    if any(
        reason.startswith(("mandatory_", "path_match:", "symbol_match:"))
        for reason in candidate.reasons
    ):
        return ContextPriority.REQUIRED
    if any(reason.startswith("keyword_match:") for reason in candidate.reasons):
        return ContextPriority.RELEVANT
    return ContextPriority.RELATED


def _reason_key(reason: str) -> tuple[int, str]:
    prefixes = (
        "mandatory_", "path_match:", "symbol_match:", "keyword_match:",
        "relation_from:",
    )
    return (next((index for index, prefix in enumerate(prefixes) if reason.startswith(prefix)), 99), reason)


def _matches_path(signal: str, candidate: _Candidate) -> bool:
    expected = signal.rstrip("/")
    if candidate.path == expected or candidate.path.startswith(expected + "/"):
        return True
    values = [
        item.rstrip("/")
        for item in candidate.symbols
        if "/" in item or item.startswith(".")
    ]
    values.extend(
        item[len("path:") :].rstrip("/")
        for item in candidate.tags
        if item.startswith("path:")
    )
    return any(
        expected == value
        or expected.startswith(value + "/")
        or value.startswith(expected + "/")
        for value in values
    )


def _memory_scope_filter(
    scope,
    workspace_id: str,
    repository_id: str,
    task_id: str,
    session_id: str | None,
) -> str | None:
    if scope.namespace != "coding":
        return f"scope_filtered:namespace:{scope.namespace}"
    expected = {
        "workspace_id": workspace_id,
        "project_id": repository_id,
        "task_id": task_id,
        "session_id": session_id,
    }
    for field_name, actual in (
        ("workspace_id", scope.workspace_id),
        ("project_id", scope.project_id),
        ("task_id", scope.task_id),
        ("session_id", scope.session_id),
    ):
        if actual is not None and actual != expected[field_name]:
            return f"scope_filtered:{field_name}:{actual}"
    return None


def _resolve_knowledge_target(
    source: Path, target: str, roots: tuple[Path, ...]
) -> Path | None:
    clean = unquote(target.split("#", 1)[0].strip())
    if not clean or clean.lower().startswith(("http://", "https://", "mailto:", "tel:")):
        return None
    if clean.startswith("/"):
        for root in roots:
            try:
                source.relative_to(root)
                return (root / clean.lstrip("/")).resolve()
            except ValueError:
                continue
        return None
    return (source.parent / clean).resolve()


def _split_relation(value: str) -> tuple[str, str]:
    kind, separator, target = value.partition(":")
    return (kind, target) if separator else ("related_to", value)


def _scalar(metadata: dict[str, FlatValue], key: str) -> str:
    value = metadata.get(key, "")
    return "" if isinstance(value, list) else str(value).strip()


def _tokens(raw: bytes) -> int:
    return max(1, (len(raw) + 3) // 4)


def _source_digest(
    candidates: dict[str, _Candidate],
    catalog_digest: str,
    *runtime_hashes: str | None,
) -> str:
    payload = {
        "catalog": catalog_digest,
        "documents": [
            (item.document_id, item.source_hash)
            for item in sorted(candidates.values(), key=lambda value: value.document_id)
        ],
        "runtime": [item for item in runtime_hashes if item is not None],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _manifest_data(manifest: ContextManifest) -> dict[str, Any]:
    return {
        "manifest_version": manifest.manifest_version,
        "profile": manifest.profile,
        "task_id": manifest.request.task_id,
        "session_id": manifest.session_id,
        "checkpoint_id": manifest.checkpoint_id,
        "budget_tokens": manifest.request.budget_tokens,
        "estimated_tokens": manifest.estimated_tokens,
        "source_digest": manifest.source_digest,
        "checksum": manifest.checksum,
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
