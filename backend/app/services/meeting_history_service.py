from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.schemas.analysis import MeetingAnalysis
from app.schemas.meeting_history import (
    MeetingHistoryListItem,
    MeetingHistoryStatus,
    MeetingHistoryTranscriptItem,
    MeetingProcessingStage,
    MeetingRecord,
    MeetingSourceType,
)
from app.schemas.summary import MeetingSummary
from app.schemas.transcript import TranscriptItem
from app.schemas.translation import TranscriptTranslation


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class MeetingHistoryService:
    INTERRUPTED_UPLOAD_ERROR = "Upload processing was interrupted before completion."

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self.reconcile_processing_uploads()

    def create_meeting(
        self,
        *,
        meeting_id: str,
        scene: str,
        target_lang: str | None,
        provider: str,
        status: MeetingHistoryStatus = MeetingHistoryStatus.DRAFT,
        source_type: MeetingSourceType = MeetingSourceType.LIVE,
        processing_stage: MeetingProcessingStage | None = None,
        error_message: str | None = None,
        source_name: str | None = None,
    ) -> str:
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO meetings (
                    meeting_id,
                    status,
                    source_type,
                    scene,
                    target_lang,
                    provider,
                    created_at,
                    updated_at,
                    transcript_count,
                    preview_text,
                    processing_stage,
                    error_message,
                    source_name,
                    summary_json,
                    analysis_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, '', ?, ?, ?, NULL, NULL)
                """,
                (
                    meeting_id,
                    status.value,
                    source_type.value,
                    scene,
                    target_lang,
                    provider,
                    timestamp,
                    timestamp,
                    processing_stage.value if processing_stage else None,
                    error_message,
                    source_name,
                ),
            )
        return timestamp

    def upsert_transcript(self, meeting_id: str, transcript: TranscriptItem) -> None:
        preview_text = self._build_preview_text(transcript.text)
        updated_at = _utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO meeting_transcripts (
                    meeting_id,
                    transcript_index,
                    speaker,
                    speaker_is_final,
                    transcript_is_final,
                    text,
                    start,
                    end,
                    translated_text,
                    translated_target_lang
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
                ON CONFLICT(meeting_id, transcript_index) DO UPDATE SET
                    speaker = excluded.speaker,
                    speaker_is_final = excluded.speaker_is_final,
                    transcript_is_final = excluded.transcript_is_final,
                    text = excluded.text,
                    start = excluded.start,
                    end = excluded.end
                """,
                (
                    meeting_id,
                    transcript.transcript_index,
                    transcript.speaker,
                    int(transcript.speaker_is_final),
                    int(transcript.transcript_is_final),
                    transcript.text,
                    transcript.start,
                    transcript.end,
                ),
            )
            connection.execute(
                """
                UPDATE meetings
                SET
                    transcript_count = CASE
                        WHEN transcript_count < ? THEN ?
                        ELSE transcript_count
                    END,
                    preview_text = ?,
                    updated_at = ?
                WHERE meeting_id = ?
                """,
                (
                    transcript.transcript_index + 1,
                    transcript.transcript_index + 1,
                    preview_text,
                    updated_at,
                    meeting_id,
                ),
            )

    def update_translation(self, meeting_id: str, translation: TranscriptTranslation) -> None:
        updated_at = _utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO meeting_transcripts (
                    meeting_id,
                    transcript_index,
                    speaker,
                    speaker_is_final,
                    transcript_is_final,
                    text,
                    start,
                    end,
                    translated_text,
                    translated_target_lang
                ) VALUES (?, ?, 'Unknown', 0, 1, '', 0, 0, ?, ?)
                ON CONFLICT(meeting_id, transcript_index) DO UPDATE SET
                    translated_text = excluded.translated_text,
                    translated_target_lang = excluded.translated_target_lang
                """,
                (
                    meeting_id,
                    translation.transcript_index,
                    translation.text,
                    translation.target_lang,
                ),
            )
            connection.execute(
                "UPDATE meetings SET updated_at = ? WHERE meeting_id = ?",
                (updated_at, meeting_id),
            )

    def update_analysis(self, meeting_id: str, analysis: MeetingAnalysis) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE meetings
                SET analysis_json = ?, updated_at = ?
                WHERE meeting_id = ?
                """,
                (json.dumps(analysis.model_dump()), _utc_now_iso(), meeting_id),
            )

    def update_summary(self, meeting_id: str, summary: MeetingSummary) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE meetings
                SET
                    summary_json = ?,
                    status = ?,
                    processing_stage = NULL,
                    error_message = NULL,
                    updated_at = ?
                WHERE meeting_id = ?
                """,
                (
                    json.dumps(summary.model_dump()),
                    MeetingHistoryStatus.FINALIZED.value,
                    _utc_now_iso(),
                    meeting_id,
                ),
            )

    def mark_processing(self, meeting_id: str, stage: MeetingProcessingStage) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE meetings
                SET
                    status = ?,
                    processing_stage = ?,
                    error_message = NULL,
                    updated_at = ?
                WHERE meeting_id = ?
                """,
                (
                    MeetingHistoryStatus.PROCESSING.value,
                    stage.value,
                    _utc_now_iso(),
                    meeting_id,
                ),
            )

    def mark_failed(self, meeting_id: str, error_message: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE meetings
                SET
                    status = ?,
                    processing_stage = NULL,
                    error_message = ?,
                    updated_at = ?
                WHERE meeting_id = ?
                """,
                (
                    MeetingHistoryStatus.FAILED.value,
                    error_message,
                    _utc_now_iso(),
                    meeting_id,
                ),
            )

    def mark_finalized(self, meeting_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE meetings
                SET
                    status = ?,
                    processing_stage = NULL,
                    error_message = NULL,
                    updated_at = ?
                WHERE meeting_id = ?
                """,
                (MeetingHistoryStatus.FINALIZED.value, _utc_now_iso(), meeting_id),
            )

    def update_provider(self, meeting_id: str, provider: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE meetings
                SET provider = ?, updated_at = ?
                WHERE meeting_id = ?
                """,
                (provider, _utc_now_iso(), meeting_id),
            )

    def list_meetings(self) -> list[MeetingHistoryListItem]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    meeting_id,
                    status,
                    source_type,
                    scene,
                    target_lang,
                    provider,
                    created_at,
                    updated_at,
                    transcript_count,
                    preview_text,
                    processing_stage,
                    error_message,
                    source_name
                FROM meetings
                ORDER BY updated_at DESC, created_at DESC
                """
            ).fetchall()
        return [MeetingHistoryListItem.model_validate(dict(row)) for row in rows]

    def get_meeting(self, meeting_id: str) -> MeetingRecord | None:
        with self._connect() as connection:
            meeting_row = connection.execute(
                """
                SELECT
                    meeting_id,
                    status,
                    source_type,
                    scene,
                    target_lang,
                    provider,
                    created_at,
                    updated_at,
                    transcript_count,
                    preview_text,
                    processing_stage,
                    error_message,
                    source_name,
                    summary_json,
                    analysis_json
                FROM meetings
                WHERE meeting_id = ?
                """,
                (meeting_id,),
            ).fetchone()
            if meeting_row is None:
                return None

            transcript_rows = connection.execute(
                """
                SELECT
                    transcript_index,
                    speaker,
                    speaker_is_final,
                    transcript_is_final,
                    text,
                    start,
                    end,
                    translated_text,
                    translated_target_lang
                FROM meeting_transcripts
                WHERE meeting_id = ?
                ORDER BY transcript_index ASC
                """,
                (meeting_id,),
            ).fetchall()

        summary_json = meeting_row["summary_json"]
        analysis_json = meeting_row["analysis_json"]
        return MeetingRecord(
            meeting_id=meeting_row["meeting_id"],
            status=meeting_row["status"],
            source_type=meeting_row["source_type"],
            scene=meeting_row["scene"],
            target_lang=meeting_row["target_lang"],
            provider=meeting_row["provider"],
            created_at=meeting_row["created_at"],
            updated_at=meeting_row["updated_at"],
            transcript_count=meeting_row["transcript_count"],
            preview_text=meeting_row["preview_text"],
            processing_stage=meeting_row["processing_stage"],
            error_message=meeting_row["error_message"],
            source_name=meeting_row["source_name"],
            transcripts=[
                MeetingHistoryTranscriptItem(
                    transcript_index=row["transcript_index"],
                    speaker=row["speaker"],
                    speaker_is_final=bool(row["speaker_is_final"]),
                    transcript_is_final=bool(row["transcript_is_final"]),
                    text=row["text"],
                    start=row["start"],
                    end=row["end"],
                    translated_text=row["translated_text"],
                    translated_target_lang=row["translated_target_lang"],
                )
                for row in transcript_rows
            ],
            summary=MeetingSummary.model_validate_json(summary_json) if summary_json else None,
            analysis=MeetingAnalysis.model_validate_json(analysis_json) if analysis_json else None,
        )

    def delete_meeting(self, meeting_id: str) -> bool:
        with self._connect() as connection:
            deleted = connection.execute("DELETE FROM meetings WHERE meeting_id = ?", (meeting_id,)).rowcount
        return deleted > 0

    def reconcile_processing_uploads(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE meetings
                SET
                    status = ?,
                    processing_stage = NULL,
                    error_message = ?,
                    updated_at = ?
                WHERE source_type = ? AND status = ?
                """,
                (
                    MeetingHistoryStatus.FAILED.value,
                    self.INTERRUPTED_UPLOAD_ERROR,
                    _utc_now_iso(),
                    MeetingSourceType.UPLOAD.value,
                    MeetingHistoryStatus.PROCESSING.value,
                ),
            )

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS meetings (
                    meeting_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    source_type TEXT NOT NULL DEFAULT 'live',
                    scene TEXT NOT NULL,
                    target_lang TEXT,
                    provider TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    transcript_count INTEGER NOT NULL DEFAULT 0,
                    preview_text TEXT NOT NULL DEFAULT '',
                    processing_stage TEXT,
                    error_message TEXT,
                    source_name TEXT,
                    summary_json TEXT,
                    analysis_json TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS meeting_transcripts (
                    meeting_id TEXT NOT NULL,
                    transcript_index INTEGER NOT NULL,
                    speaker TEXT NOT NULL,
                    speaker_is_final INTEGER NOT NULL,
                    transcript_is_final INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    start REAL NOT NULL,
                    end REAL NOT NULL,
                    translated_text TEXT,
                    translated_target_lang TEXT,
                    PRIMARY KEY (meeting_id, transcript_index),
                    FOREIGN KEY (meeting_id) REFERENCES meetings(meeting_id) ON DELETE CASCADE
                )
                """
            )
            self._migrate_meetings_table(connection)

    def _migrate_meetings_table(self, connection: sqlite3.Connection) -> None:
        columns = self._get_table_columns(connection, "meetings")
        if "source_type" not in columns:
            connection.execute(
                "ALTER TABLE meetings ADD COLUMN source_type TEXT NOT NULL DEFAULT 'live'"
            )
        if "processing_stage" not in columns:
            connection.execute("ALTER TABLE meetings ADD COLUMN processing_stage TEXT")
        if "error_message" not in columns:
            connection.execute("ALTER TABLE meetings ADD COLUMN error_message TEXT")
        if "source_name" not in columns:
            connection.execute("ALTER TABLE meetings ADD COLUMN source_name TEXT")

        connection.execute(
            """
            UPDATE meetings
            SET source_type = ?
            WHERE source_type IS NULL OR source_type = ''
            """,
            (MeetingSourceType.LIVE.value,),
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @staticmethod
    def _get_table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {row["name"] for row in rows}

    @staticmethod
    def _build_preview_text(text: str) -> str:
        normalized = " ".join(text.split())
        return normalized[:160]
