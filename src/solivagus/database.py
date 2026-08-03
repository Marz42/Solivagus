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
                  document_id, unit_key, sequence_index, source_text, source_hash,
                  status, translation_text, translation_hash, provider, model,
                  prompt_version, attempt_count, warning_flags, source_file,
                  translated_file
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    unit["unit_key"],
                    unit["sequence_index"],
                    unit["source_text"],
                    unit["source_hash"],
                    unit["status"],
                    unit.get("translation_text"),
                    unit.get("translation_hash"),
                    unit.get("provider"),
                    unit.get("model"),
                    unit.get("prompt_version"),
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
              warning_flags = COALESCE(?, warning_flags)
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
                unit_id,
            ),
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
