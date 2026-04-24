from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import uuid4

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, WebSocketException

from app.clients.asr_base import (
    ASRClient,
    ASRStream,
    ErrorHandler,
    SegmentHandler,
    noop_error_handler,
    noop_segment_handler,
)
from app.core.config import Settings
from app.schemas.transcript import TranscriptSegment

logger = logging.getLogger(__name__)


def _format_exception_message(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message


class DashScopeASRStream(ASRStream):
    def __init__(
        self,
        *,
        settings: Settings,
        audio_format: str,
        sample_rate: int,
        on_segment: SegmentHandler = noop_segment_handler,
        on_error: ErrorHandler = noop_error_handler,
    ) -> None:
        self._settings = settings
        self._audio_format = audio_format
        self._sample_rate = sample_rate
        self._on_segment = on_segment
        self._on_error = on_error
        self._task_id = uuid4().hex
        self._connection: ClientConnection | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._started = asyncio.Event()
        self._finished = asyncio.Event()
        self._send_lock = asyncio.Lock()
        self._segments: list[TranscriptSegment] = []
        self._seen_segments: set[tuple[float, float, str]] = set()
        self._error_message: str | None = None
        self._finish_requested = False
        self._closed_by_client = False

    async def start(self) -> None:
        if not self._settings.asr_configured:
            raise RuntimeError("DashScope ASR is not configured.")

        headers = {
            "Authorization": f"Bearer {self._settings.dashscope_api_key}",
            "user-agent": "smart-meeting-assistant/2.0.0",
        }
        if self._settings.dashscope_workspace_id:
            headers["X-DashScope-WorkSpace"] = self._settings.dashscope_workspace_id

        try:
            self._connection = await connect(
                self._settings.dashscope_asr_ws_url,
                additional_headers=headers,
                open_timeout=10,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=10,
                max_size=2**20,
            )
        except Exception as exc:  # pragma: no cover - network-dependent
            raise RuntimeError(
                f"DashScope ASR WebSocket connection failed: {_format_exception_message(exc)}"
            ) from exc

        self._reader_task = asyncio.create_task(self._read_events())
        await self._send_json(
            {
                "header": {
                    "action": "run-task",
                    "task_id": self._task_id,
                    "streaming": "duplex",
                },
                "payload": {
                    "task_group": "audio",
                    "task": "asr",
                    "function": "recognition",
                    "model": self._settings.dashscope_asr_model,
                    "parameters": {
                        "format": self._audio_format,
                        "sample_rate": self._sample_rate,
                        "disfluency_removal_enabled": False,
                    },
                    "input": {},
                },
            }
        )
        try:
            await asyncio.wait_for(self._started.wait(), timeout=10)
        except asyncio.TimeoutError as exc:
            await self.aclose()
            raise RuntimeError("DashScope ASR did not acknowledge run-task in time.") from exc

        if self._error_message:
            raise RuntimeError(self._error_message)

    async def send_audio(self, audio_chunk: bytes) -> None:
        if not audio_chunk:
            return
        if self._error_message:
            raise RuntimeError(self._error_message)
        if self._connection is None:
            raise RuntimeError("DashScope ASR stream is not started.")
        await self._started.wait()
        async with self._send_lock:
            await self._connection.send(audio_chunk)

    async def finish(self) -> list[TranscriptSegment]:
        if self._connection is None:
            return list(self._segments)

        self._finish_requested = True
        await self._send_json(
            {
                "header": {
                    "action": "finish-task",
                    "task_id": self._task_id,
                    "streaming": "duplex",
                },
                "payload": {"input": {}},
            }
        )
        try:
            await asyncio.wait_for(self._finished.wait(), timeout=20)
        except asyncio.TimeoutError as exc:
            raise RuntimeError("DashScope ASR did not finish in time.") from exc

        if self._connection is not None:
            self._closed_by_client = True
            await self._connection.close()
            self._connection = None
        if self._reader_task is not None:
            await self._reader_task

        if self._error_message:
            raise RuntimeError(self._error_message)
        return list(self._segments)

    async def aclose(self) -> None:
        if self._connection is not None:
            self._closed_by_client = True
            await self._connection.close()
            self._connection = None
        if self._reader_task is not None and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

    async def _send_json(self, payload: dict[str, Any]) -> None:
        if self._connection is None:
            raise RuntimeError("DashScope ASR stream is not connected.")
        async with self._send_lock:
            await self._connection.send(json.dumps(payload))

    async def _read_events(self) -> None:
        if self._connection is None:
            return

        try:
            async for raw_message in self._connection:
                if isinstance(raw_message, bytes):
                    continue
                try:
                    message = json.loads(raw_message)
                except json.JSONDecodeError:
                    logger.warning("DashScope ASR returned non-JSON message: %r", raw_message)
                    continue
                await self._handle_event(message)
        except ConnectionClosed as exc:
            if (
                not self._finished.is_set()
                and not self._error_message
                and not self._finish_requested
                and not self._closed_by_client
            ):
                self._error_message = f"DashScope ASR connection closed unexpectedly: {exc}"
                await self._on_error(self._error_message)
            else:
                logger.info("DashScope ASR connection closed for %s: %s", self._task_id, exc)
        except WebSocketException as exc:
            if not self._error_message:
                self._error_message = f"DashScope ASR WebSocket failed: {_format_exception_message(exc)}"
                await self._on_error(self._error_message)
        finally:
            self._finished.set()

    async def _handle_event(self, message: dict[str, Any]) -> None:
        header = message.get("header") or {}
        event = header.get("event")
        if event == "task-started":
            self._started.set()
            logger.info("DashScope ASR task started for %s", self._task_id)
            return

        if event == "result-generated":
            sentence = (
                (message.get("payload") or {})
                .get("output", {})
                .get("sentence", {})
            )
            if not sentence or sentence.get("heartbeat"):
                return

            end_time_raw = sentence.get("end_time")
            if end_time_raw is None:
                return

            text = str(sentence.get("text", "")).strip()
            if not text:
                return

            begin_time = float(sentence.get("begin_time") or 0) / 1000.0
            end_time = float(end_time_raw or 0) / 1000.0
            segment_key = (begin_time, end_time, text)
            if segment_key in self._seen_segments:
                return

            self._seen_segments.add(segment_key)
            segment = TranscriptSegment(
                text=text,
                start=begin_time,
                end=end_time,
            )
            self._segments.append(segment)
            await self._on_segment(segment)
            return

        if event == "task-finished":
            logger.info("DashScope ASR task finished for %s", self._task_id)
            self._finished.set()
            return

        if event == "task-failed":
            error_code = header.get("error_code") or "TASK_FAILED"
            error_message = header.get("error_message") or "DashScope ASR task failed."
            self._error_message = f"{error_code}: {error_message}"
            self._finished.set()
            await self._on_error(self._error_message)


class DashScopeASRClient(ASRClient):
    provider_name = "dashscope"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def is_configured(self) -> bool:
        return self._settings.asr_configured

    async def aclose(self) -> None:
        return

    def create_pcm_stream(
        self,
        *,
        on_segment: SegmentHandler = noop_segment_handler,
        on_error: ErrorHandler = noop_error_handler,
    ) -> DashScopeASRStream:
        return DashScopeASRStream(
            settings=self._settings,
            audio_format="pcm",
            sample_rate=self._settings.sample_rate,
            on_segment=on_segment,
            on_error=on_error,
        )

    async def transcribe_wav(self, audio_data: bytes) -> list[TranscriptSegment]:
        collected_segments: list[TranscriptSegment] = []
        error_messages: list[str] = []

        async def on_segment(segment: TranscriptSegment) -> None:
            collected_segments.append(segment)

        async def on_error(message: str) -> None:
            error_messages.append(message)

        stream = DashScopeASRStream(
            settings=self._settings,
            audio_format="wav",
            sample_rate=self._settings.sample_rate,
            on_segment=on_segment,
            on_error=on_error,
        )
        try:
            await stream.start()
            for start_index in range(0, len(audio_data), 8192):
                await stream.send_audio(audio_data[start_index : start_index + 8192])
            segments = await stream.finish()
        finally:
            await stream.aclose()

        if error_messages:
            raise RuntimeError(error_messages[-1])
        return segments
