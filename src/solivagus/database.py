from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "1"

_SCHEMA_SQL = (Path(__file__).with_name("schema.sql")).read_text(encoding="utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA busy_timeout = 5000")
        self.initialize()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    def initialize(self) -> None:
        self._conn.executescript(_SCHEMA_SQL)
        row = self._conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO schema_meta(key, value) VALUES ('schema_version', ?)",
                (SCHEMA_VERSION,),
            )
        self._conn.commit()

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, tuple(params))

    def commit(self) -> None:
        self._conn.commit()

    def fetchone(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        return self.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        return list(self.execute(sql, params).fetchall())

    def upsert_document(
        self,
        *,
        source_path: str,
        source_sha256: str,
        display_name: str,
        artifact_dir: str,
        status: str,
        page_count: int | None = None,
        ocr_status: str | None = None,
        translation_status: str | None = None,
        active_config_hash: str | None = None,
    ) -> int:
        now = utc_now()
        existing = self.fetchone(
            "SELECT id FROM documents WHERE source_sha256 = ?",
            (source_sha256,),
        )
        if existing is None:
            cur = self.execute(
                """
                INSERT INTO documents(
                  source_path, source_sha256, display_name, page_count, status,
                  ocr_status, translation_status, artifact_dir, active_config_hash,
                  created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_path,
                    source_sha256,
                    display_name,
                    page_count,
                    status,
                    ocr_status,
                    translation_status,
                    artifact_dir,
                    active_config_hash,
                    now,
                    now,
                ),
            )
            self.commit()
            return int(cur.lastrowid)
        self.execute(
            """
            UPDATE documents SET
              source_path = ?, display_name = ?, page_count = COALESCE(?, page_count),
              status = ?, ocr_status = COALESCE(?, ocr_status),
              translation_status = COALESCE(?, translation_status),
              artifact_dir = ?, active_config_hash = COALESCE(?, active_config_hash),
              updated_at = ?
            WHERE id = ?
            """,
            (
                source_path,
                display_name,
                page_count,
                status,
                ocr_status,
                translation_status,
                artifact_dir,
                active_config_hash,
                now,
                int(existing["id"]),
            ),
        )
        self.commit()
        return int(existing["id"])

    def list_documents(self) -> list[sqlite3.Row]:
        return self.fetchall("SELECT * FROM documents ORDER BY updated_at DESC, id DESC")

    def get_document_by_path_or_sha(
        self, *, path: Path | None = None, sha256: str | None = None
    ) -> sqlite3.Row | None:
        if sha256:
            row = self.fetchone(
                "SELECT * FROM documents WHERE source_sha256 = ?", (sha256,)
            )
            if row is not None:
                return row
        if path is not None:
            resolved = str(path.expanduser().resolve())
            return self.fetchone(
                "SELECT * FROM documents WHERE source_path = ?", (resolved,)
            )
        return None

    def replace_structural_nodes(
        self,
        document_id: int,
        nodes: list[dict[str, Any]],
    ) -> list[int]:
        self.execute(
            "DELETE FROM structural_nodes WHERE document_id = ?", (document_id,)
        )
        temp_to_id: dict[int, int] = {}
        ordered = sorted(nodes, key=lambda item: int(item["sequence_index"]))
        # First pass: insert without parents.
        for node in ordered:
            cur = self.execute(
                """
                INSERT INTO structural_nodes(
                  document_id, parent_id, node_type, sequence_index, heading_level,
                  heading_path, source_pages, source_text, source_hash, token_count,
                  metadata_json
                ) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    node["node_type"],
                    node["sequence_index"],
                    node.get("heading_level"),
                    node.get("heading_path"),
                    node.get("source_pages"),
                    node.get("source_text"),
                    node.get("source_hash"),
                    node.get("token_count"),
                    node.get("metadata_json"),
                ),
            )
            db_id = int(cur.lastrowid)
            temp_id = node.get("temp_id")
            if temp_id is not None:
                temp_to_id[int(temp_id)] = db_id
        # Second pass: wire parent_id.
        for node in ordered:
            parent_temp = node.get("parent_temp_id")
            temp_id = node.get("temp_id")
            if parent_temp is None or temp_id is None:
                continue
            child_id = temp_to_id.get(int(temp_id))
            parent_id = temp_to_id.get(int(parent_temp))
            if child_id is None or parent_id is None:
                continue
            self.execute(
                "UPDATE structural_nodes SET parent_id = ? WHERE id = ?",
                (parent_id, child_id),
            )
        self.commit()
        return [temp_to_id[int(n["temp_id"])] for n in ordered if n.get("temp_id") is not None]

    def list_structural_nodes(self, document_id: int) -> list[sqlite3.Row]:
        return self.fetchall(
            """
            SELECT * FROM structural_nodes
            WHERE document_id = ?
            ORDER BY sequence_index ASC, id ASC
            """,
            (document_id,),
        )

    def replace_partitions(
        self,
        document_id: int,
        partitions: list[dict[str, Any]],
    ) -> list[int]:
        # Units reference partitions; clear units' partition_id then partitions.
        self.execute(
            "UPDATE translation_units SET partition_id = NULL WHERE document_id = ?",
            (document_id,),
        )
        self.execute(
            "DELETE FROM cache_partitions WHERE document_id = ?", (document_id,)
        )
        ids: list[int] = []
        for part in partitions:
            cur = self.execute(
                """
                INSERT INTO cache_partitions(
                  document_id, sequence_index, source_tokens, context_tokens,
                  unit_count, prefix_hash, user_id, warmup_status,
                  expected_cache_tokens, actual_probe_hit_tokens, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    part["sequence_index"],
                    part.get("source_tokens"),
                    part.get("context_tokens"),
                    part.get("unit_count"),
                    part.get("prefix_hash"),
                    part.get("user_id"),
                    part.get("warmup_status"),
                    part.get("expected_cache_tokens"),
                    part.get("actual_probe_hit_tokens"),
                    part.get("status", "pending"),
                ),
            )
            ids.append(int(cur.lastrowid))
        self.commit()
        return ids

    def list_partitions(self, document_id: int) -> list[sqlite3.Row]:
        return self.fetchall(
            """
            SELECT * FROM cache_partitions
            WHERE document_id = ?
            ORDER BY sequence_index ASC, id ASC
            """,
            (document_id,),
        )

    def replace_units(
        self,
        document_id: int,
        units: list[dict[str, Any]],
    ) -> None:
        self.execute(
            "DELETE FROM translation_units WHERE document_id = ?", (document_id,)
        )
        for unit in units:
            self.execute(
                """
                INSERT INTO translation_units(
                  document_id, partition_id, unit_key, sequence_index, heading_path,
                  source_pages, source_text, source_hash, source_tokens,
                  estimated_output_tokens, status, translation_text, translation_hash,
                  provider, model, prompt_version, style_capsule_version, attempt_count,
                  warning_flags, source_file, translated_file
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    unit.get("partition_id"),
                    unit["unit_key"],
                    unit["sequence_index"],
                    unit.get("heading_path"),
                    unit.get("source_pages"),
                    unit["source_text"],
                    unit["source_hash"],
                    unit.get("source_tokens"),
                    unit.get("estimated_output_tokens"),
                    unit["status"],
                    unit.get("translation_text"),
                    unit.get("translation_hash"),
                    unit.get("provider"),
                    unit.get("model"),
                    unit.get("prompt_version"),
                    unit.get("style_capsule_version"),
                    unit.get("attempt_count", 0),
                    unit.get("warning_flags"),
                    unit.get("source_file"),
                    unit.get("translated_file"),
                ),
            )
        self.commit()

    def list_units(self, document_id: int) -> list[sqlite3.Row]:
        return self.fetchall(
            """
            SELECT * FROM translation_units
            WHERE document_id = ?
            ORDER BY sequence_index ASC, id ASC
            """,
            (document_id,),
        )

    def update_partition(
        self,
        partition_id: int,
        *,
        warmup_status: str | None = None,
        prefix_hash: str | None = None,
        user_id: str | None = None,
        actual_probe_hit_tokens: int | None = None,
        status: str | None = None,
        expected_cache_tokens: int | None = None,
    ) -> None:
        self.execute(
            """
            UPDATE cache_partitions SET
              warmup_status = COALESCE(?, warmup_status),
              prefix_hash = COALESCE(?, prefix_hash),
              user_id = COALESCE(?, user_id),
              actual_probe_hit_tokens = COALESCE(?, actual_probe_hit_tokens),
              status = COALESCE(?, status),
              expected_cache_tokens = COALESCE(?, expected_cache_tokens)
            WHERE id = ?
            """,
            (
                warmup_status,
                prefix_hash,
                user_id,
                actual_probe_hit_tokens,
                status,
                expected_cache_tokens,
                partition_id,
            ),
        )

    def insert_translation_attempt(
        self,
        unit_id: int,
        attempt_number: int,
        *,
        request_hash: str | None = None,
        usage: Any = None,
        finish_reason: str | None = None,
        http_status: int | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        latency_ms: int | None = None,
    ) -> None:
        from solivagus.providers.usage import UsageRecord

        record = usage if isinstance(usage, UsageRecord) else UsageRecord.from_api(usage or {})
        now = utc_now()
        self.execute(
            """
            INSERT INTO translation_attempts(
              unit_id, attempt_number, request_hash, started_at, finished_at,
              latency_ms, http_status, finish_reason, prompt_tokens,
              cache_hit_tokens, cache_miss_tokens, completion_tokens,
              error_type, error_message, raw_response_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                unit_id,
                attempt_number,
                request_hash,
                now,
                now,
                latency_ms,
                http_status if http_status is not None else record.http_status,
                finish_reason,
                record.prompt_tokens,
                record.cache_hit_tokens,
                record.cache_miss_tokens,
                record.completion_tokens,
                error_type,
                error_message,
            ),
        )

    def list_units_for_partition(self, partition_id: int) -> list[sqlite3.Row]:
        return self.fetchall(
            """
            SELECT * FROM translation_units
            WHERE partition_id = ?
            ORDER BY sequence_index ASC, id ASC
            """,
            (partition_id,),
        )

    def update_unit(
        self,
        unit_id: int,
        *,
        status: str,
        translation_text: str | None = None,
        translation_hash: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        attempt_count: int | None = None,
        warning_flags: str | None = None,
        prompt_version: str | None = None,
        style_capsule_version: str | None = None,
    ) -> None:
        self.execute(
            """
            UPDATE translation_units SET
              status = ?,
              translation_text = COALESCE(?, translation_text),
              translation_hash = COALESCE(?, translation_hash),
              provider = COALESCE(?, provider),
              model = COALESCE(?, model),
              attempt_count = COALESCE(?, attempt_count),
              warning_flags = COALESCE(?, warning_flags),
              prompt_version = COALESCE(?, prompt_version),
              style_capsule_version = COALESCE(?, style_capsule_version)
            WHERE id = ?
            """,
            (
                status,
                translation_text,
                translation_hash,
                provider,
                model,
                attempt_count,
                warning_flags,
                prompt_version,
                style_capsule_version,
                unit_id,
            ),
        )

    def insert_style_capsule(
        self,
        document_id: int,
        *,
        version: int,
        rules_json: str,
        terminology_json: str,
        examples_json: str,
        boundary_context_json: str,
        content_hash: str,
        source_partition_id: int | None = None,
    ) -> int:
        cur = self.execute(
            """
            INSERT INTO style_capsules(
              document_id, version, source_partition_id, rules_json, terminology_json,
              examples_json, boundary_context_json, content_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                version,
                source_partition_id,
                rules_json,
                terminology_json,
                examples_json,
                boundary_context_json,
                content_hash,
                utc_now(),
            ),
        )
        self.commit()
        return int(cur.lastrowid)

    def get_latest_style_capsule(self, document_id: int) -> sqlite3.Row | None:
        return self.fetchone(
            """
            SELECT * FROM style_capsules
            WHERE document_id = ?
            ORDER BY version DESC, id DESC
            LIMIT 1
            """,
            (document_id,),
        )

    def get_style_capsule(self, document_id: int, version: int) -> sqlite3.Row | None:
        return self.fetchone(
            """
            SELECT * FROM style_capsules
            WHERE document_id = ? AND version = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (document_id, version),
        )

    def list_style_capsules(self, document_id: int) -> list[sqlite3.Row]:
        return self.fetchall(
            """
            SELECT * FROM style_capsules
            WHERE document_id = ?
            ORDER BY version ASC, id ASC
            """,
            (document_id,),
        )

    def update_document_status(
        self,
        document_id: int,
        *,
        status: str,
        translation_status: str | None = None,
        ocr_status: str | None = None,
    ) -> None:
        self.execute(
            """
            UPDATE documents SET
              status = ?,
              translation_status = COALESCE(?, translation_status),
              ocr_status = COALESCE(?, ocr_status),
              updated_at = ?
            WHERE id = ?
            """,
            (status, translation_status, ocr_status, utc_now(), document_id),
        )
        self.commit()

    def record_artifact(
        self,
        document_id: int,
        artifact_type: str,
        path: str,
        content_hash: str | None = None,
    ) -> None:
        self.execute(
            """
            INSERT INTO artifacts(document_id, artifact_type, path, content_hash, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (document_id, artifact_type, path, content_hash, utc_now()),
        )
