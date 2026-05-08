from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BackgroundJob:
    job_id: str
    handler: Callable[[], Awaitable[None]]


class BackgroundTaskWorker:
    def __init__(self, *, name: str, concurrency: int = 1) -> None:
        self._name = name
        self._concurrency = max(1, concurrency)
        self._queue: asyncio.Queue[BackgroundJob | None] = asyncio.Queue()
        self._workers: list[asyncio.Task[None]] = []
        self._active_job_ids: set[str] = set()

    def start(self) -> None:
        if self._workers:
            return
        for index in range(self._concurrency):
            self._workers.append(asyncio.create_task(self._run(index)))

    async def enqueue(self, job: BackgroundJob) -> None:
        self.start()
        await self._queue.put(job)

    async def shutdown(self) -> None:
        if not self._workers:
            return
        for _ in self._workers:
            await self._queue.put(None)
        for worker in self._workers:
            try:
                await worker
            except asyncio.CancelledError:
                pass
        self._workers.clear()
        self._active_job_ids.clear()

    async def _run(self, worker_index: int) -> None:
        while True:
            job = await self._queue.get()
            if job is None:
                self._queue.task_done()
                break

            self._active_job_ids.add(job.job_id)
            try:
                await job.handler()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Background worker %s/%s failed while running job %s.",
                    self._name,
                    worker_index,
                    job.job_id,
                )
            finally:
                self._active_job_ids.discard(job.job_id)
                self._queue.task_done()
