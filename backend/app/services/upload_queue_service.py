from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.schemas.glossary import GlossaryTerm

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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


class UploadQueueStore:
    def __init__(self, *, db_path: Path | str, queue_dir: Path | str) -> None:
        self._db_path = Path(db_path)
        self._queue_dir = Path(queue_dir)
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
                    error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
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
                ),
            )
        job = self.get_job(meeting_id)
        if job is None:
            raise RuntimeError("Upload job was not created.")
        return job

    def claim_next(self) -> UploadJob | None:
        timestamp = _utc_now_iso()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT meeting_id
                FROM upload_jobs
                WHERE status = ?
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (UploadJobStatus.QUEUED,),
            ).fetchone()
            if row is None:
                connection.commit()
                return None

            meeting_id = row["meeting_id"]
            updated = connection.execute(
                """
                UPDATE upload_jobs
                SET status = ?, claimed_at = ?, updated_at = ?, error_message = NULL
                WHERE meeting_id = ? AND status = ?
                """,
                (
                    UploadJobStatus.PROCESSING,
                    timestamp,
                    timestamp,
                    meeting_id,
                    UploadJobStatus.QUEUED,
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

    def release_processing_jobs(self) -> int:
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            return connection.execute(
                """
                UPDATE upload_jobs
                SET status = ?, claimed_at = NULL, updated_at = ?
                WHERE status = ?
                """,
                (UploadJobStatus.QUEUED, timestamp, UploadJobStatus.PROCESSING),
            ).rowcount

    def mark_completed(self, meeting_id: str) -> None:
        timestamp = _utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE upload_jobs
                SET status = ?, completed_at = ?, updated_at = ?, error_message = NULL
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
                SET status = ?, completed_at = ?, updated_at = ?, error_message = ?
                WHERE meeting_id = ?
                """,
                (UploadJobStatus.FAILED, timestamp, timestamp, error_message, meeting_id),
            )

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
                    error_message TEXT
                )
                """
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
                error_message
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


class UploadQueueWorker:
    def __init__(
        self,
        *,
        name: str,
        store: UploadQueueStore,
        handler: Callable[[UploadJob], Awaitable[str | None]],
        concurrency: int = 1,
        poll_interval_seconds: float = 0.1,
    ) -> None:
        self._name = name
        self._store = store
        self._handler = handler
        self._concurrency = max(1, concurrency)
        self._poll_interval_seconds = max(0.01, poll_interval_seconds)
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
            job = self._store.claim_next()
            if job is None:
                return processed_count
            processed_count += 1
            await self._process_job(job)

    async def _run(self, worker_index: int) -> None:
        while not self._stopping.is_set():
            job = self._store.claim_next()
            if job is None:
                await asyncio.sleep(self._poll_interval_seconds)
                continue
            logger.info("Upload queue worker %s/%s claimed job %s.", self._name, worker_index, job.meeting_id)
            await self._process_job(job)

    async def _process_job(self, job: UploadJob) -> None:
        try:
            error_message = await self._handler(job)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Upload queue worker %s failed while running job %s.", self._name, job.meeting_id)
            error_message = str(exc).strip() or exc.__class__.__name__

        if error_message:
            self._store.mark_failed(job.meeting_id, error_message)
        else:
            self._store.mark_completed(job.meeting_id)
        self._store.cleanup_payload(job)
