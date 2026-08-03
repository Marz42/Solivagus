"""Rebuildable SQLite + FTS5 catalog derived from canonical Markdown."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import tempfile
from typing import Any, Iterable

from paradigma.errors import ParadigmaError
from paradigma.kernel import MemoryResult
from paradigma.kernel.identifiers import is_memory_id
from paradigma.kernel.models.memory import MemoryRecord
from paradigma.storage.contract import StoredMemory
from paradigma.storage.markdown.store import MarkdownMemoryStore

from .query import CatalogQuery, CatalogTextMode


CATALOG_SCHEMA_VERSION = "0.1"
_MEMORY_COLUMNS = (
    "memory_id",
    "path",
    "title",
    "description",
    "content",
    "memory_type",
    "tags_json",
    "status",
    "scope_json",
    "scope_namespace",
    "workspace_id",
    "project_id",
    "task_id",
    "session_id",
    "entity_ids_json",
    "valid_from",
    "valid_until",
    "confidence",
    "sensitivity",
    "provenance_json",
    "provenance_summary",
    "relations_json",
    "content_hash",
    "source_hash",
    "revision",
    "created_at",
    "updated_at",
)


class CatalogFailure(ParadigmaError):
    code = "PD_CATALOG_ERROR"


class CatalogWriteFailure(CatalogFailure, OSError):
    code = "PD_CATALOG_WRITE_ERROR"
    exit_code = 2


class CatalogQueryFailure(CatalogFailure):
    code = "PD_CATALOG_QUERY_ERROR"
    exit_code = 2


@dataclass(frozen=True)
class CatalogEntry:
    values: tuple[Any, ...]
    tags: tuple[str, ...]
    relations: tuple[tuple[str, str], ...]

    @property
    def memory_id(self) -> str:
        return str(self.values[0])

    def digest_payload(self) -> dict[str, Any]:
        return dict(zip(_MEMORY_COLUMNS, self.values))


@dataclass(frozen=True)
class _QueryMatch:
    memory_id: str
    score: float
    matched_fields: tuple[str, ...]
    match_reasons: tuple[str, ...]


@dataclass(frozen=True)
class CatalogRebuildResult:
    catalog_path: Path
    record_count: int
    source_digest: str
    written: bool


@dataclass(frozen=True)
class CatalogVerification:
    catalog_path: Path
    current: bool
    source_count: int
    catalog_count: int
    source_digest: str
    issues: tuple[str, ...]


@dataclass(frozen=True)
class CatalogStats:
    catalog_path: Path
    record_count: int
    tag_count: int
    relation_count: int
    status_counts: tuple[tuple[str, int], ...]
    type_counts: tuple[tuple[str, int], ...]


class SQLiteMemoryCatalog:
    def __init__(
        self,
        path: Path,
        memory_store: MarkdownMemoryStore,
        *,
        path_base: Path,
    ):
        self.path = Path(path).resolve()
        self.memory_store = memory_store
        self.path_base = Path(path_base).resolve()

    def rebuild(self, *, dry_run: bool = False) -> CatalogRebuildResult:
        entries = self._source_entries()
        digest = _entries_digest(entries)
        if dry_run:
            return CatalogRebuildResult(self.path, len(entries), digest, False)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        os.close(descriptor)
        temporary = Path(name)
        try:
            connection = sqlite3.connect(temporary)
            try:
                connection.executescript(_schema_sql())
                with connection:
                    self._insert_entries(connection, entries)
                    connection.executemany(
                        "INSERT INTO catalog_meta(key, value) VALUES (?, ?)",
                        (
                            ("catalog_schema_version", CATALOG_SCHEMA_VERSION),
                            ("source_digest", digest),
                            ("record_count", str(len(entries))),
                        ),
                    )
                integrity = connection.execute("PRAGMA integrity_check").fetchone()
                if integrity != ("ok",):
                    raise CatalogFailure(
                        f"rebuilt catalog failed integrity check: {integrity!r}"
                    )
            finally:
                connection.close()
            with temporary.open("r+b") as handle:
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except CatalogFailure:
            raise
        except (OSError, sqlite3.Error) as error:
            raise CatalogWriteFailure(
                f"failed to rebuild catalog {self.path}: {error}"
            ) from error
        finally:
            _remove_sqlite_artifacts(temporary)
        return CatalogRebuildResult(self.path, len(entries), digest, True)

    def verify(self) -> CatalogVerification:
        entries = self._source_entries()
        digest = _entries_digest(entries)
        issues: list[str] = []
        if not self.path.exists():
            return CatalogVerification(
                self.path,
                False,
                len(entries),
                0,
                digest,
                ("catalog file is missing",),
            )
        if self.path.is_symlink():
            return CatalogVerification(
                self.path,
                False,
                len(entries),
                0,
                digest,
                ("catalog file must not be a symlink",),
            )

        catalog_count = 0
        try:
            connection = _connect_read_only(self.path)
            try:
                integrity = connection.execute("PRAGMA integrity_check").fetchone()
                if integrity != ("ok",):
                    issues.append(f"SQLite integrity check failed: {integrity!r}")
                meta = dict(connection.execute("SELECT key, value FROM catalog_meta"))
                if meta.get("catalog_schema_version") != CATALOG_SCHEMA_VERSION:
                    issues.append("catalog schema version does not match")
                if meta.get("source_digest") != digest:
                    issues.append("catalog source digest does not match Markdown")
                if meta.get("record_count") != str(len(entries)):
                    issues.append("catalog metadata record count does not match")

                rows = tuple(
                    connection.execute(
                        f"SELECT {', '.join(_MEMORY_COLUMNS)} "
                        "FROM memories ORDER BY memory_id"
                    )
                )
                catalog_count = len(rows)
                expected_rows = tuple(entry.values for entry in entries)
                if rows != expected_rows:
                    issues.append("memory rows do not match canonical Markdown")

                expected_tags = tuple(
                    (entry.memory_id, position, tag)
                    for entry in entries
                    for position, tag in enumerate(entry.tags)
                )
                actual_tags = tuple(
                    connection.execute(
                        "SELECT memory_id, position, tag FROM memory_tags "
                        "ORDER BY memory_id, position"
                    )
                )
                if actual_tags != expected_tags:
                    issues.append("normalized tags do not match memory rows")

                expected_relations = tuple(
                    (entry.memory_id, position, relation_type, target)
                    for entry in entries
                    for position, (relation_type, target) in enumerate(entry.relations)
                )
                actual_relations = tuple(
                    connection.execute(
                        "SELECT memory_id, position, relation_type, target_memory_id "
                        "FROM memory_relations ORDER BY memory_id, position"
                    )
                )
                if actual_relations != expected_relations:
                    issues.append("normalized relations do not match memory rows")

                expected_fts = tuple(
                    (
                        entry.values[0],
                        entry.values[2],
                        entry.values[3],
                        entry.values[4],
                        " ".join(entry.tags),
                    )
                    for entry in entries
                )
                actual_fts = tuple(
                    connection.execute(
                        "SELECT memory_id, title, description, content, tags "
                        "FROM memory_fts ORDER BY memory_id"
                    )
                )
                if actual_fts != expected_fts:
                    issues.append("FTS rows do not match memory rows")
            finally:
                connection.close()
        except sqlite3.Error as error:
            issues.append(f"catalog cannot be read: {error}")
        return CatalogVerification(
            self.path,
            not issues,
            len(entries),
            catalog_count,
            digest,
            tuple(issues),
        )

    def stats(self) -> CatalogStats:
        if not self.path.exists():
            raise CatalogFailure(f"catalog file is missing: {self.path}")
        try:
            connection = _connect_read_only(self.path)
            try:
                record_count = int(
                    connection.execute("SELECT count(*) FROM memories").fetchone()[0]
                )
                tag_count = int(
                    connection.execute("SELECT count(*) FROM memory_tags").fetchone()[0]
                )
                relation_count = int(
                    connection.execute(
                        "SELECT count(*) FROM memory_relations"
                    ).fetchone()[0]
                )
                statuses = tuple(
                    (str(value), int(count))
                    for value, count in connection.execute(
                        "SELECT status, count(*) FROM memories "
                        "GROUP BY status ORDER BY status"
                    )
                )
                types = tuple(
                    (str(value), int(count))
                    for value, count in connection.execute(
                        "SELECT memory_type, count(*) FROM memories "
                        "GROUP BY memory_type ORDER BY memory_type"
                    )
                )
            finally:
                connection.close()
        except sqlite3.Error as error:
            raise CatalogFailure(f"catalog cannot be read: {error}") from error
        return CatalogStats(
            self.path,
            record_count,
            tag_count,
            relation_count,
            statuses,
            types,
        )

    def query(self, request: CatalogQuery) -> tuple[MemoryResult, ...]:
        """Return deterministic direct matches followed by optional one-hop targets."""

        if not isinstance(request, CatalogQuery):
            raise ValueError("request must be a CatalogQuery")
        verification = self.verify()
        if not verification.current:
            detail = "; ".join(verification.issues) or "unknown catalog drift"
            raise CatalogQueryFailure(
                f"catalog must be rebuilt before querying: {detail}"
            )

        try:
            connection = _connect_read_only(self.path)
            try:
                direct_matches = self._direct_matches(connection, request)
                direct_results = tuple(
                    self._direct_result(match, request)
                    for match in direct_matches
                )
                if not request.memory.include_related:
                    return direct_results[: request.memory.limit]
                related_results = self._related_results(
                    connection,
                    request,
                    direct_results,
                )
            finally:
                connection.close()
        except CatalogQueryFailure:
            raise
        except sqlite3.Error as error:
            raise CatalogQueryFailure(f"catalog query failed: {error}") from error
        return (direct_results + related_results)[: request.memory.limit]

    def _direct_matches(
        self, connection: sqlite3.Connection, request: CatalogQuery
    ) -> tuple[_QueryMatch, ...]:
        query = request.memory
        conditions: list[str] = []
        parameters: list[Any] = []

        def values_condition(column: str, values: tuple[Any, ...]) -> None:
            if values:
                conditions.append(
                    f"{column} IN ({', '.join('?' for _ in values)})"
                )
                parameters.extend(values)

        values_condition("m.memory_id", query.memory_ids)
        values_condition("m.path", request.paths)
        values_condition("m.status", tuple(item.value for item in query.statuses))
        for tag in query.tags:
            conditions.append(
                "EXISTS (SELECT 1 FROM memory_tags t "
                "WHERE t.memory_id = m.memory_id AND t.tag = ?)"
            )
            parameters.append(tag)
        if query.scope is not None:
            conditions.append("m.scope_namespace = ?")
            parameters.append(query.scope.namespace)
            for column, value in (
                ("workspace_id", query.scope.workspace_id),
                ("project_id", query.scope.project_id),
                ("task_id", query.scope.task_id),
                ("session_id", query.scope.session_id),
            ):
                if value is not None:
                    conditions.append(f"m.{column} = ?")
                    parameters.append(value)

        text = query.text
        use_fts = text is not None and request.text_mode is CatalogTextMode.FTS
        if use_fts:
            conditions.append("memory_fts MATCH ?")
            parameters.append(text)
        select = (
            "SELECT m.memory_id, m.path, m.title, m.description, m.content, "
            "m.tags_json, m.entity_ids_json, m.status"
        )
        join = ""
        if use_fts:
            select += (
                ", bm25(memory_fts), "
                "highlight(memory_fts, 1, char(1), char(2)), "
                "highlight(memory_fts, 2, char(1), char(2)), "
                "highlight(memory_fts, 3, char(1), char(2)), "
                "highlight(memory_fts, 4, char(1), char(2))"
            )
            join = " JOIN memory_fts ON memory_fts.memory_id = m.memory_id"
        statement = select + " FROM memories m" + join
        if conditions:
            statement += " WHERE " + " AND ".join(conditions)

        try:
            rows = tuple(connection.execute(statement, parameters))
        except sqlite3.Error as error:
            if use_fts:
                raise CatalogQueryFailure(f"invalid FTS query: {error}") from error
            raise

        matches = []
        for row in rows:
            (
                memory_id,
                path,
                title,
                description,
                content,
                tags_json,
                entities_json,
                status,
            ) = row[:8]
            entities = tuple(json.loads(entities_json))
            if query.scope is not None and not set(query.scope.entity_ids).issubset(
                entities
            ):
                continue
            fields: list[str] = []
            reasons: list[str] = []
            score = 0.0
            if query.memory_ids:
                fields.append("memory_id")
                reasons.append(f"memory_id:{memory_id}")
            if request.paths:
                fields.append("path")
                reasons.append(f"path:{path}")
            if query.tags:
                fields.append("tags")
                reasons.extend(f"tag:{tag}" for tag in query.tags)
            if query.scope is not None:
                fields.append("scope")
                reasons.append(f"scope:{query.scope.namespace}")
            fields.append("status")
            reasons.append(f"status:{status}")
            if query.valid_at is not None:
                fields.append("validity")
                reasons.append(f"valid_at:{_instant(query.valid_at)}")

            if text is not None and request.text_mode is CatalogTextMode.KEYWORD:
                keyword_fields = _keyword_fields(
                    text, title, description, content, tuple(json.loads(tags_json))
                )
                if not keyword_fields:
                    continue
                fields.extend(keyword_fields)
                reasons.append(f"keyword:{text}")
                score = float(len(keyword_fields))
            elif use_fts:
                highlighted = row[9:13]
                text_fields = ("title", "description", "content", "tags")
                fts_fields = tuple(
                    field
                    for field, value in zip(text_fields, highlighted)
                    if "\x01" in value
                )
                fields.extend(fts_fields)
                reasons.append(f"fts:{text}")
                score = max(0.0, -float(row[8]))

            record = self.memory_store.read(str(memory_id)).record
            if query.valid_at is not None and not record.is_valid_at(query.valid_at):
                continue
            matches.append(
                _QueryMatch(
                    str(memory_id),
                    score,
                    tuple(dict.fromkeys(fields)),
                    tuple(dict.fromkeys(reasons)),
                )
            )
        return tuple(sorted(matches, key=lambda item: (-item.score, item.memory_id)))

    def _direct_result(
        self, match: _QueryMatch, request: CatalogQuery
    ) -> MemoryResult:
        record = self.memory_store.read(match.memory_id).record
        return MemoryResult(
            record=record,
            score=match.score if request.memory.text is not None else None,
            matched_fields=match.matched_fields,
            match_reasons=match.match_reasons,
            warnings=_query_warnings(record, request),
        )

    def _related_results(
        self,
        connection: sqlite3.Connection,
        request: CatalogQuery,
        direct_results: tuple[MemoryResult, ...],
    ) -> tuple[MemoryResult, ...]:
        if not direct_results:
            return ()
        direct_ids = tuple(result.record.memory_id for result in direct_results)
        placeholders = ", ".join("?" for _ in direct_ids)
        conditions = [f"memory_id IN ({placeholders})"]
        parameters: list[Any] = list(direct_ids)
        if request.memory.relation_types:
            relation_placeholders = ", ".join(
                "?" for _ in request.memory.relation_types
            )
            conditions.append(f"relation_type IN ({relation_placeholders})")
            parameters.extend(request.memory.relation_types)
        rows = tuple(
            connection.execute(
                "SELECT memory_id, relation_type, target_memory_id "
                "FROM memory_relations WHERE "
                + " AND ".join(conditions),
                parameters,
            )
        )
        direct_order = {memory_id: index for index, memory_id in enumerate(direct_ids)}
        rows = tuple(
            sorted(
                rows,
                key=lambda row: (direct_order[str(row[0])], str(row[2]), str(row[1])),
            )
        )
        seen = set(direct_ids)
        results = []
        for source_id, relation_type, target_id in rows:
            target_id = str(target_id)
            if target_id in seen:
                continue
            try:
                record = self.memory_store.read(target_id).record
            except ParadigmaError:
                continue
            if record.status not in request.memory.statuses:
                continue
            if request.memory.valid_at is not None and not record.is_valid_at(
                request.memory.valid_at
            ):
                continue
            if not _scope_matches(record, request):
                continue
            seen.add(target_id)
            results.append(
                MemoryResult(
                    record=record,
                    matched_fields=("relations",),
                    match_reasons=(f"relation:{relation_type}",),
                    relation_source_id=str(source_id),
                    warnings=_query_warnings(record, request),
                )
            )
        return tuple(results)

    def _source_entries(self) -> tuple[CatalogEntry, ...]:
        if self.memory_store.root.exists():
            for path in sorted(self.memory_store.root.glob("MEM-*.md")):
                if path.is_symlink() or not is_memory_id(path.stem):
                    raise CatalogFailure(
                        f"invalid managed memory document path: {path}"
                    )
        return tuple(
            self._entry(self.memory_store.read(path.stem))
            for path in self.memory_store.paths()
        )

    def _entry(self, stored: StoredMemory) -> CatalogEntry:
        record = stored.record
        try:
            relative_path = stored.path.resolve().relative_to(self.path_base).as_posix()
        except ValueError as error:
            raise CatalogFailure(
                f"memory path is outside catalog path base: {stored.path}"
            ) from error
        scope = {
            "namespace": record.scope.namespace,
            "workspace_id": record.scope.workspace_id,
            "project_id": record.scope.project_id,
            "task_id": record.scope.task_id,
            "session_id": record.scope.session_id,
            "entity_ids": list(record.scope.entity_ids),
        }
        provenance = [
            {
                "source_type": item.source_type.value,
                "source_uri": item.source_uri,
                "source_id": item.source_id,
                "observed_at": _instant(item.observed_at),
                "excerpt_hash": item.excerpt_hash,
                "actor": item.actor,
            }
            for item in record.provenance
        ]
        relations = [
            {
                "relation_type": item.relation_type,
                "target_memory_id": item.target_memory_id,
            }
            for item in record.relations
        ]
        values = (
            record.memory_id,
            relative_path,
            record.title,
            _description(record.content),
            record.content,
            record.memory_type.value,
            _json(list(record.tags)),
            record.status.value,
            _json(scope),
            record.scope.namespace,
            record.scope.workspace_id,
            record.scope.project_id,
            record.scope.task_id,
            record.scope.session_id,
            _json(list(record.scope.entity_ids)),
            _instant(record.valid_from),
            _instant(record.valid_until),
            None if record.confidence is None else float(record.confidence),
            record.sensitivity,
            _json(provenance),
            _provenance_summary(record),
            _json(relations),
            stored.content_hash,
            stored.source_hash,
            record.revision,
            _instant(record.created_at),
            _instant(record.updated_at),
        )
        return CatalogEntry(
            values=values,
            tags=record.tags,
            relations=tuple(
                (item.relation_type, item.target_memory_id)
                for item in record.relations
            ),
        )

    @staticmethod
    def _insert_entries(
        connection: sqlite3.Connection, entries: Iterable[CatalogEntry]
    ) -> None:
        placeholders = ", ".join("?" for _ in _MEMORY_COLUMNS)
        for entry in entries:
            connection.execute(
                f"INSERT INTO memories({', '.join(_MEMORY_COLUMNS)}) "
                f"VALUES ({placeholders})",
                entry.values,
            )
            connection.executemany(
                "INSERT INTO memory_tags(memory_id, position, tag) VALUES (?, ?, ?)",
                (
                    (entry.memory_id, position, tag)
                    for position, tag in enumerate(entry.tags)
                ),
            )
            connection.executemany(
                "INSERT INTO memory_relations"
                "(memory_id, position, relation_type, target_memory_id) "
                "VALUES (?, ?, ?, ?)",
                (
                    (entry.memory_id, position, relation_type, target)
                    for position, (relation_type, target) in enumerate(entry.relations)
                ),
            )
            connection.execute(
                "INSERT INTO memory_fts(memory_id, title, description, content, tags) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    entry.values[0],
                    entry.values[2],
                    entry.values[3],
                    entry.values[4],
                    " ".join(entry.tags),
                ),
            )


def _schema_sql() -> str:
    return files("paradigma.storage.catalog").joinpath("schema.sql").read_text(
        encoding="utf-8"
    )


def _connect_read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _instant(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat(timespec="microseconds")


def _description(content: str, limit: int = 280) -> str:
    for block in content.split("\n\n"):
        lines = [
            line.strip()
            for line in block.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        value = " ".join(line for line in lines if line)
        if value:
            return value[:limit]
    fallback = " ".join(
        line.strip().lstrip("#").strip()
        for line in content.splitlines()
        if line.strip()
    )
    return fallback[:limit]


def _provenance_summary(record: MemoryRecord) -> str:
    values = []
    for item in record.provenance:
        locator = item.source_uri or item.source_id or item.actor or "unknown"
        values.append(f"{item.source_type.value}:{locator}")
    return " | ".join(values)


def _keyword_fields(
    keyword: str,
    title: str,
    description: str,
    content: str,
    tags: tuple[str, ...],
) -> tuple[str, ...]:
    needle = keyword.casefold()
    values = (
        ("title", title),
        ("description", description),
        ("content", content),
        ("tags", " ".join(tags)),
    )
    return tuple(field for field, value in values if needle in value.casefold())


def _scope_matches(record: MemoryRecord, request: CatalogQuery) -> bool:
    expected = request.memory.scope
    if expected is None:
        return True
    actual = record.scope
    if actual.namespace != expected.namespace:
        return False
    for field in ("workspace_id", "project_id", "task_id", "session_id"):
        value = getattr(expected, field)
        if value is not None and getattr(actual, field) != value:
            return False
    return set(expected.entity_ids).issubset(actual.entity_ids)


def _query_warnings(
    record: MemoryRecord, request: CatalogQuery
) -> tuple[str, ...]:
    warnings = []
    if record.status.value != "active":
        warnings.append(
            f"excluded from ordinary queries: status {record.status.value}"
        )
    if request.memory.valid_at is None and (
        record.valid_from is not None or record.valid_until is not None
    ):
        warnings.append("validity not evaluated")
    return tuple(warnings)


def _entries_digest(entries: Iterable[CatalogEntry]) -> str:
    payload = _json([entry.digest_payload() for entry in entries]).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _remove_sqlite_artifacts(path: Path) -> None:
    for candidate in (
        path,
        Path(f"{path}-journal"),
        Path(f"{path}-wal"),
        Path(f"{path}-shm"),
    ):
        try:
            candidate.unlink(missing_ok=True)
        except OSError:
            pass
