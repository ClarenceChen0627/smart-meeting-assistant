from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.schemas.audit import AuditEventRecord


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class AuditLogService:
    SCOPE_MEETING = "meeting"
    SCOPE_GLOBAL = "global"

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def record_event(
        self,
        *,
        scope: str,
        entity_type: str,
        action: str,
        meeting_id: str | None = None,
        entity_id: str | None = None,
        field_path: str | None = None,
        before: Any = None,
        after: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEventRecord:
        if scope not in {self.SCOPE_MEETING, self.SCOPE_GLOBAL}:
            raise ValueError("Audit event scope must be meeting or global.")
        if scope == self.SCOPE_MEETING and not meeting_id:
            raise ValueError("Meeting audit events require meeting_id.")

        event_id = uuid4().hex
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO audit_events (
                    id,
                    scope,
                    meeting_id,
                    entity_type,
                    entity_id,
                    action,
                    field_path,
                    before_json,
                    after_json,
                    metadata_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    scope,
                    meeting_id,
                    entity_type,
                    entity_id,
                    action,
                    field_path,
                    self._dump_json(before),
                    self._dump_json(after),
                    self._dump_json(metadata or {}),
                    timestamp,
                ),
            )
        return self._get_required(event_id)

    def list_meeting_events(self, meeting_id: str, *, limit: int = 100) -> list[AuditEventRecord]:
        return self.list_events(scope=self.SCOPE_MEETING, meeting_id=meeting_id, limit=limit)

    def list_events(
        self,
        *,
        scope: str | None = None,
        meeting_id: str | None = None,
        entity_type: str | None = None,
        limit: int = 100,
    ) -> list[AuditEventRecord]:
        conditions: list[str] = []
        parameters: list[Any] = []
        if scope:
            conditions.append("scope = ?")
            parameters.append(scope)
        if meeting_id:
            conditions.append("meeting_id = ?")
            parameters.append(meeting_id)
        if entity_type:
            conditions.append("entity_type = ?")
            parameters.append(entity_type)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        parameters.append(max(1, min(limit, 500)))
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    id,
                    scope,
                    meeting_id,
                    entity_type,
                    entity_id,
                    action,
                    field_path,
                    before_json,
                    after_json,
                    metadata_json,
                    created_at
                FROM audit_events
                {where_clause}
                ORDER BY created_at DESC, rowid DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def _get_required(self, event_id: str) -> AuditEventRecord:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    scope,
                    meeting_id,
                    entity_type,
                    entity_id,
                    action,
                    field_path,
                    before_json,
                    after_json,
                    metadata_json,
                    created_at
                FROM audit_events
                WHERE id = ?
                """,
                (event_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Audit event was not created.")
        return self._row_to_event(row)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    id TEXT PRIMARY KEY,
                    scope TEXT NOT NULL,
                    meeting_id TEXT,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT,
                    action TEXT NOT NULL,
                    field_path TEXT,
                    before_json TEXT,
                    after_json TEXT,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_events_meeting_created
                ON audit_events(meeting_id, created_at)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_events_scope_entity_created
                ON audit_events(scope, entity_type, created_at)
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @classmethod
    def _row_to_event(cls, row: sqlite3.Row) -> AuditEventRecord:
        return AuditEventRecord(
            id=row["id"],
            scope=row["scope"],
            meeting_id=row["meeting_id"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            action=row["action"],
            field_path=row["field_path"],
            before=cls._load_json(row["before_json"]),
            after=cls._load_json(row["after_json"]),
            metadata=cls._load_json(row["metadata_json"]) or {},
            created_at=row["created_at"],
        )

    @staticmethod
    def _dump_json(value: Any) -> str | None:
        if value is None:
            return None
        return json.dumps(value)

    @staticmethod
    def _load_json(value: str | None) -> Any:
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
