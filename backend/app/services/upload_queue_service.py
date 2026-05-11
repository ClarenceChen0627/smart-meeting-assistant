from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from app.core.logging import correlation_context
from app.schemas.glossary import GlossaryTerm

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_utc_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class UploadJobStatus:
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class UploadJob:
    meeting_id: str
    status: str
    payload_path: Path
    filename: str | None
    content_type: str | None
    scene: str
    target_lang: str | None
    provider: str
    glossary_terms: list[GlossaryTerm]
    created_at: str
    updated_at: str
    claimed_at: str | None = None
    completed_at: str | None = None
    error_message: str | None = None
    attempt_count: int = 0
    max_attempts: int = 3
    next_run_at: str | None = None
    last_error: str | None = None
    last_attempted_at: str | None = None
    claimed_by: str | None = None


class UploadQueueStore:
    MISSING_PAYLOAD_ERROR = "Upload queue payload is missing and the job cannot be recovered."

    def __init__(
        self,
        *,
        db_path: Path | str,
        queue_dir: Path | str,
        max_attempts: int = 3,
        retry_base_seconds: float = 30.0,
        retry_max_seconds: float = 300.0,
    ) -> None:
        self._db_path = Path(db_path)
        self._queue_dir = Path(queue_dir)
        self._max_attempts = max(1, max_attempts)
        self._retry_base_seconds = max(0.0, retry_base_seconds)
        self._retry_max_seconds = max(self._retry_base_seconds, retry_max_seconds)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._queue_dir.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def enqueue_upload(
        self,
        *,
        meeting_id: str,
        audio_data: bytes,
        filename: str | None,
        content_type: str | None,
        scene: str,
        target_lang: str | None,
        provider: str,
        glossary_terms: list[GlossaryTerm],
    ) -> UploadJob:
        payload_path = self._write_payload(
            meeting_id=meeting_id,
            audio_data=audio_data,
            filename=filename,
        )
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO upload_jobs (
                    meeting_id,
                    status,
                    payload_path,
                    filename,
                    content_type,
                    scene,
                    target_lang,
                    provider,
                    glossary_terms_json,
                    created_at,
                    updated_at,
                    claimed_at,
                    completed_at,
                    error_message,
                    attempt_count,
                    max_attempts,
                    next_run_at,
                    last_error,
                    last_attempted_at,
                    claimed_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, 0, ?, NULL, NULL, NULL, NULL)
                """,
                (
                    meeting_id,
                    UploadJobStatus.QUEUED,
                    str(payload_path),
                    filename,
                    content_type,
                    scene,
                    target_lang,
                    provider,
                    self._dump_glossary_terms(glossary_terms),
                    timestamp,
                    timestamp,
                    self._max_attempts,
                ),
            )
        job = self.get_job(meeting_id)
        if job is None:
            raise RuntimeError("Upload job was not created.")
        return job

    def claim_next(self, *, claimed_by: str | None = None) -> UploadJob | None:
        timestamp = _utc_now_iso()
        worker_id = claimed_by or f"worker-{uuid4().hex[:12]}"
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT meeting_id
                FROM upload_jobs
                WHERE status = ?
                  AND (next_run_at IS NULL OR next_run_at <= ?)
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (UploadJobStatus.QUEUED, timestamp),
            ).fetchone()
            if row is None:
                connection.commit()
                return None

            meeting_id = row["meeting_id"]
            updated = connection.execute(
                """
                UPDATE upload_jobs
                SET
                    status = ?,
                    claimed_at = ?,
                    claimed_by = ?,
                    last_attempted_at = ?,
                    attempt_count = attempt_count + 1,
                    updated_at = ?,
                    error_message = NULL
                WHERE meeting_id = ? AND status = ?
                  AND (next_run_at IS NULL OR next_run_at <= ?)
                """,
                (
                    UploadJobStatus.PROCESSING,
                    timestamp,
                    worker_id,
                    timestamp,
                    timestamp,
                    meeting_id,
                    UploadJobStatus.QUEUED,
                    timestamp,
                ),
            ).rowcount
            if updated == 0:
                connection.commit()
                return None

            claimed_row = self._fetch_job_row(connection, meeting_id)
            connection.commit()
            return self._row_to_job(claimed_row) if claimed_row is not None else None
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_job(self, meeting_id: str) -> UploadJob | None:
        with self._connect() as connection:
            row = self._fetch_job_row(connection, meeting_id)
        return self._row_to_job(row) if row is not None else None

    def active_job_meeting_ids(self) -> set[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT meeting_id
                FROM upload_jobs
                WHERE status IN (?, ?)
                """,
                (UploadJobStatus.QUEUED, UploadJobStatus.PROCESSING),
            ).fetchall()
        return {row["meeting_id"] for row in rows}

    def terminal_failed_job_errors(self) -> dict[str, str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT meeting_id, error_message, last_error
                FROM upload_jobs
                WHERE status = ?
                """,
                (UploadJobStatus.FAILED,),
            ).fetchall()
        return {
            row["meeting_id"]: row["error_message"] or row["last_error"] or "Upload processing failed."
            for row in rows
        }

    def diagnostics_snapshot(self, *, processing_timeout_seconds: float) -> dict:
        timestamp = _utc_now_iso()
        stale_cutoff = (_utc_now() - timedelta(seconds=max(0.0, processing_timeout_seconds))).isoformat().replace("+00:00", "Z")
        with self._connect() as connection:
            status_rows = connection.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM upload_jobs
                GROUP BY status
                """
            ).fetchall()
            eligible_queued = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM upload_jobs
                WHERE status = ?
                  AND (next_run_at IS NULL OR next_run_at <= ?)
                """,
                (UploadJobStatus.QUEUED, timestamp),
            ).fetchone()["count"]
            delayed_retry = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM upload_jobs
                WHERE status = ?
                  AND next_run_at IS NOT NULL
                  AND next_run_at > ?
                """,
                (UploadJobStatus.QUEUED, timestamp),
            ).fetchone()["count"]
            processing_count = connection.execute(
                "SELECT COUNT(*) AS count FROM upload_jobs WHERE status = ?",
                (UploadJobStatus.PROCESSING,),
            ).fetchone()["count"]
            stale_processing = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM upload_jobs
                WHERE status = ?
                  AND (claimed_at IS NULL OR claimed_at <= ?)
                """,
                (UploadJobStatus.PROCESSING, stale_cutoff),
            ).fetchone()["count"]
            oldest_queued_row = connection.execute(
                """
                SELECT created_at
                FROM upload_jobs
                WHERE status = ?
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (UploadJobStatus.QUEUED,),
            ).fetchone()
            last_error_count = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM upload_jobs
                WHERE last_error IS NOT NULL AND TRIM(last_error) != ''
                """
            ).fetchone()["count"]

        oldest_queued_age_seconds = None
        if oldest_queued_row is not None:
            created_at = _parse_utc_iso(oldest_queued_row["created_at"])
            if created_at is not None:
                oldest_queued_age_seconds = round(max(0.0, (_utc_now() - created_at).total_seconds()), 3)
        return {
            "byStatus": {row["status"]: row["count"] for row in status_rows},
            "eligibleQueued": eligible_queued,
            "delayedRetry": delayed_retry,
            "processing": processing_count,
            "staleProcessing": stale_processing,
            "oldestQueuedAgeSeconds": oldest_queued_age_seconds,
            "lastErrorCount": last_error_count,
        }

    def fail_jobs_with_missing_payloads(self) -> dict[str, str]:
        failed: dict[str, str] = {}
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT meeting_id, payload_path
                FROM upload_jobs
                WHERE status IN (?, ?)
                """,
                (UploadJobStatus.QUEUED, UploadJobStatus.PROCESSING),
            ).fetchall()

        for row in rows:
            payload_path = Path(row["payload_path"])
            if payload_path.exists():
                continue
            self.mark_failed(row["meeting_id"], self.MISSING_PAYLOAD_ERROR)
            failed[row["meeting_id"]] = self.MISSING_PAYLOAD_ERROR
        return failed

    def release_processing_jobs(self) -> int:
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            return connection.execute(
                """
                UPDATE upload_jobs
                SET status = ?, claimed_at = NULL, claimed_by = NULL, updated_at = ?
                WHERE status = ?
                """,
                (UploadJobStatus.QUEUED, timestamp, UploadJobStatus.PROCESSING),
            ).rowcount

    def release_stale_processing_jobs(self, *, timeout_seconds: float) -> int:
        cutoff = (_utc_now() - timedelta(seconds=max(0.0, timeout_seconds))).isoformat().replace("+00:00", "Z")
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            return connection.execute(
                """
                UPDATE upload_jobs
                SET status = ?, claimed_at = NULL, claimed_by = NULL, updated_at = ?
                WHERE status = ?
                  AND (claimed_at IS NULL OR claimed_at <= ?)
                """,
                (UploadJobStatus.QUEUED, timestamp, UploadJobStatus.PROCESSING, cutoff),
            ).rowcount

    def mark_completed(self, meeting_id: str) -> None:
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE upload_jobs
                SET
                    status = ?,
                    completed_at = ?,
                    updated_at = ?,
                    error_message = NULL,
                    last_error = NULL,
                    next_run_at = NULL
                WHERE meeting_id = ?
                """,
                (UploadJobStatus.COMPLETED, timestamp, timestamp, meeting_id),
            )

    def mark_failed(self, meeting_id: str, error_message: str) -> None:
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE upload_jobs
                SET
                    status = ?,
                    completed_at = ?,
                    updated_at = ?,
                    error_message = ?,
                    last_error = ?,
                    next_run_at = NULL
                WHERE meeting_id = ?
                """,
                (UploadJobStatus.FAILED, timestamp, timestamp, error_message, error_message, meeting_id),
            )

    def mark_attempt_failed(self, job: UploadJob, error_message: str) -> bool:
        if job.attempt_count >= job.max_attempts:
            self.mark_failed(job.meeting_id, error_message)
            return True

        timestamp = _utc_now()
        retry_delay = self._retry_delay_seconds(job.attempt_count)
        next_run_at = (timestamp + timedelta(seconds=retry_delay)).isoformat().replace("+00:00", "Z")
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE upload_jobs
                SET
                    status = ?,
                    claimed_at = NULL,
                    claimed_by = NULL,
                    updated_at = ?,
                    next_run_at = ?,
                    last_error = ?,
                    error_message = NULL
                WHERE meeting_id = ?
                """,
                (
                    UploadJobStatus.QUEUED,
                    timestamp.isoformat().replace("+00:00", "Z"),
                    next_run_at,
                    error_message,
                    job.meeting_id,
                ),
            )
        return False

    def cleanup_payload(self, job: UploadJob) -> None:
        try:
            job.payload_path.unlink(missing_ok=True)
            parent = job.payload_path.parent
            if parent.exists() and parent != self._queue_dir and not any(parent.iterdir()):
                parent.rmdir()
        except OSError:
            logger.warning("Failed to clean upload queue payload for %s.", job.meeting_id, exc_info=True)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS upload_jobs (
                    meeting_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    payload_path TEXT NOT NULL,
                    filename TEXT,
                    content_type TEXT,
                    scene TEXT NOT NULL,
                    target_lang TEXT,
                    provider TEXT NOT NULL,
                    glossary_terms_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    claimed_at TEXT,
                    completed_at TEXT,
                    error_message TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    next_run_at TEXT,
                    last_error TEXT,
                    last_attempted_at TEXT,
                    claimed_by TEXT
                )
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(upload_jobs)").fetchall()
            }
            migrations = {
                "attempt_count": "ALTER TABLE upload_jobs ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0",
                "max_attempts": "ALTER TABLE upload_jobs ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 3",
                "next_run_at": "ALTER TABLE upload_jobs ADD COLUMN next_run_at TEXT",
                "last_error": "ALTER TABLE upload_jobs ADD COLUMN last_error TEXT",
                "last_attempted_at": "ALTER TABLE upload_jobs ADD COLUMN last_attempted_at TEXT",
                "claimed_by": "ALTER TABLE upload_jobs ADD COLUMN claimed_by TEXT",
            }
            for column, statement in migrations.items():
                if column not in columns:
                    connection.execute(statement)
            connection.execute(
                """
                UPDATE upload_jobs
                SET max_attempts = ?
                WHERE max_attempts IS NULL OR max_attempts < 1
                """,
                (self._max_attempts,),
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_upload_jobs_status_created
                ON upload_jobs(status, created_at)
                """
            )

    def _write_payload(self, *, meeting_id: str, audio_data: bytes, filename: str | None) -> Path:
        payload_dir = self._queue_dir / meeting_id
        payload_dir.mkdir(parents=True, exist_ok=True)
        payload_path = payload_dir / f"source{self._safe_suffix(filename)}"
        payload_path.write_bytes(audio_data)
        return payload_path

    @staticmethod
    def _safe_suffix(filename: str | None) -> str:
        suffix = Path(filename or "").suffix.lower()
        if not suffix or not re.fullmatch(r"\.[a-z0-9]{1,12}", suffix):
            return ".bin"
        return suffix

    @staticmethod
    def _fetch_job_row(connection: sqlite3.Connection, meeting_id: str) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT
                meeting_id,
                status,
                payload_path,
                filename,
                content_type,
                scene,
                target_lang,
                provider,
                glossary_terms_json,
                created_at,
                updated_at,
                claimed_at,
                completed_at,
                error_message,
                attempt_count,
                max_attempts,
                next_run_at,
                last_error,
                last_attempted_at,
                claimed_by
            FROM upload_jobs
            WHERE meeting_id = ?
            """,
            (meeting_id,),
        ).fetchone()

    @classmethod
    def _row_to_job(cls, row: sqlite3.Row) -> UploadJob:
        return UploadJob(
            meeting_id=row["meeting_id"],
            status=row["status"],
            payload_path=Path(row["payload_path"]),
            filename=row["filename"],
            content_type=row["content_type"],
            scene=row["scene"],
            target_lang=row["target_lang"],
            provider=row["provider"],
            glossary_terms=cls._load_glossary_terms(row["glossary_terms_json"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            claimed_at=row["claimed_at"],
            completed_at=row["completed_at"],
            error_message=row["error_message"],
            attempt_count=row["attempt_count"],
            max_attempts=row["max_attempts"],
            next_run_at=row["next_run_at"],
            last_error=row["last_error"],
            last_attempted_at=row["last_attempted_at"],
            claimed_by=row["claimed_by"],
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @staticmethod
    def _dump_glossary_terms(terms: list[GlossaryTerm]) -> str | None:
        if not terms:
            return None
        return json.dumps([term.model_dump() for term in terms])

    @staticmethod
    def _load_glossary_terms(value: str | None) -> list[GlossaryTerm]:
        if not value:
            return []
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []
        terms: list[GlossaryTerm] = []
        for item in payload:
            try:
                terms.append(GlossaryTerm.model_validate(item))
            except Exception:
                continue
        return terms

    def _retry_delay_seconds(self, attempt_count: int) -> float:
        if attempt_count <= 0:
            return self._retry_base_seconds
        delay = self._retry_base_seconds * (2 ** (attempt_count - 1))
        return min(delay, self._retry_max_seconds)


class UploadQueueWorker:
    def __init__(
        self,
        *,
        name: str,
        store: UploadQueueStore,
        handler: Callable[[UploadJob], Awaitable[str | None]],
        on_terminal_failure: Callable[[UploadJob, str], Awaitable[None] | None] | None = None,
        concurrency: int = 1,
        poll_interval_seconds: float = 0.1,
    ) -> None:
        self._name = name
        self._store = store
        self._handler = handler
        self._on_terminal_failure = on_terminal_failure
        self._concurrency = max(1, concurrency)
        self._poll_interval_seconds = max(0.01, poll_interval_seconds)
        self._worker_id = f"{name}-{uuid4().hex[:12]}"
        self._workers: list[asyncio.Task[None]] = []
        self._stopping = asyncio.Event()

    def start(self) -> None:
        if self._workers:
            return
        self._stopping.clear()
        for index in range(self._concurrency):
            self._workers.append(asyncio.create_task(self._run(index)))

    async def shutdown(self) -> None:
        if not self._workers:
            return
        self._stopping.set()
        for worker in self._workers:
            worker.cancel()
        for worker in self._workers:
            try:
                await worker
            except asyncio.CancelledError:
                pass
        self._workers.clear()

    async def run_forever(self) -> None:
        while not self._stopping.is_set():
            processed = await self.process_available_jobs()
            if processed == 0:
                await asyncio.sleep(self._poll_interval_seconds)

    async def process_available_jobs(self) -> int:
        processed_count = 0
        while True:
            job = self._store.claim_next(claimed_by=self._worker_id)
            if job is None:
                return processed_count
            processed_count += 1
            await self._process_job(job)

    async def _run(self, worker_index: int) -> None:
        while not self._stopping.is_set():
            job = self._store.claim_next(claimed_by=self._worker_id)
            if job is None:
                await asyncio.sleep(self._poll_interval_seconds)
                continue
            with correlation_context(meeting_id=job.meeting_id, job_id=job.meeting_id, provider=job.provider):
                logger.info("Upload queue worker %s/%s claimed job.", self._name, worker_index)
            await self._process_job(job)

    async def _process_job(self, job: UploadJob) -> None:
        with correlation_context(meeting_id=job.meeting_id, job_id=job.meeting_id, provider=job.provider):
            if not job.payload_path.exists():
                error_message = UploadQueueStore.MISSING_PAYLOAD_ERROR
                logger.error("Upload queue payload is missing.")
                self._store.mark_failed(job.meeting_id, error_message)
                await self._notify_terminal_failure(job, error_message)
                self._store.cleanup_payload(job)
                return

            try:
                error_message = await self._handler(job)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Upload queue worker %s failed while running job.", self._name)
                error_message = str(exc).strip() or exc.__class__.__name__

            if error_message:
                terminal = self._store.mark_attempt_failed(job, error_message)
                if terminal:
                    logger.error("Upload queue job exhausted retry attempts: %s", error_message)
                    await self._notify_terminal_failure(job, error_message)
                    self._store.cleanup_payload(job)
                else:
                    logger.warning("Upload queue job will retry after attempt failure: %s", error_message)
            else:
                self._store.mark_completed(job.meeting_id)
                logger.info("Upload queue job completed.")
                self._store.cleanup_payload(job)

    async def _notify_terminal_failure(self, job: UploadJob, error_message: str) -> None:
        if self._on_terminal_failure is None:
            return
        result = self._on_terminal_failure(job, error_message)
        if result is not None:
            await result
