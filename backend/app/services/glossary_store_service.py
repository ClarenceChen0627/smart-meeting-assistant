from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.schemas.glossary import GlossaryTermCreate, GlossaryTermRecord, GlossaryTermUpdate


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class GlossaryTermAlreadyExists(ValueError):
    pass


class GlossaryTermNotFound(ValueError):
    pass


class GlossaryStoreService:
    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def list_terms(self) -> list[GlossaryTermRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, term, replacement, note, created_at, updated_at
                FROM glossary_terms
                ORDER BY lower(term) ASC, created_at ASC
                """
            ).fetchall()
        return [GlossaryTermRecord.model_validate(dict(row)) for row in rows]

    def get_term(self, term_id: str) -> GlossaryTermRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, term, replacement, note, created_at, updated_at
                FROM glossary_terms
                WHERE id = ?
                """,
                (term_id,),
            ).fetchone()
        return GlossaryTermRecord.model_validate(dict(row)) if row is not None else None

    def create_term(self, payload: GlossaryTermCreate) -> GlossaryTermRecord:
        term_key = self._term_key(payload.term)
        timestamp = _utc_now_iso()
        term_id = uuid4().hex
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO glossary_terms (
                        id,
                        term,
                        term_key,
                        replacement,
                        note,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        term_id,
                        payload.term,
                        term_key,
                        payload.replacement,
                        payload.note,
                        timestamp,
                        timestamp,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise GlossaryTermAlreadyExists(f"Glossary term already exists: {payload.term}") from exc
        return self._get_required(term_id)

    def update_term(self, term_id: str, payload: GlossaryTermUpdate) -> GlossaryTermRecord:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, term, replacement, note
                FROM glossary_terms
                WHERE id = ?
                """,
                (term_id,),
            ).fetchone()
            if row is None:
                raise GlossaryTermNotFound("Glossary term not found.")

            fields_set = payload.model_fields_set
            next_term = payload.term if "term" in fields_set else row["term"]
            if not next_term:
                raise ValueError("Glossary term cannot be empty.")
            next_replacement = payload.replacement if "replacement" in fields_set else row["replacement"]
            next_note = payload.note if "note" in fields_set else row["note"]

            try:
                connection.execute(
                    """
                    UPDATE glossary_terms
                    SET
                        term = ?,
                        term_key = ?,
                        replacement = ?,
                        note = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        next_term,
                        self._term_key(next_term),
                        next_replacement,
                        next_note,
                        _utc_now_iso(),
                        term_id,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise GlossaryTermAlreadyExists(f"Glossary term already exists: {next_term}") from exc

        return self._get_required(term_id)

    def delete_term(self, term_id: str) -> bool:
        with self._connect() as connection:
            deleted = connection.execute(
                "DELETE FROM glossary_terms WHERE id = ?",
                (term_id,),
            ).rowcount
        return deleted > 0

    def _get_required(self, term_id: str) -> GlossaryTermRecord:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, term, replacement, note, created_at, updated_at
                FROM glossary_terms
                WHERE id = ?
                """,
                (term_id,),
            ).fetchone()
        if row is None:
            raise GlossaryTermNotFound("Glossary term not found.")
        return GlossaryTermRecord.model_validate(dict(row))

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS glossary_terms (
                    id TEXT PRIMARY KEY,
                    term TEXT NOT NULL,
                    term_key TEXT NOT NULL UNIQUE,
                    replacement TEXT,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @staticmethod
    def _term_key(term: str) -> str:
        return term.casefold()
