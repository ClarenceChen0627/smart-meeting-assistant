from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from uuid import uuid4

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from app.clients.aliyun_asr_client import AliyunASRClient
from app.core.config import Settings
from app.schemas.transcript import TranscriptItem
from app.schemas.ws_message import WebSocketMessage, WebSocketMessageType
from app.services.audio_codec_service import AudioCodecService
from app.services.speaker_service import SpeakerService
from app.services.summary_service import SummaryService

logger = logging.getLogger(__name__)


@dataclass
class MeetingSession:
    session_id: str
    scene: str
    websocket: WebSocket
    audio_queue: asyncio.Queue[bytes | None] = field(default_factory=asyncio.Queue)
    transcripts: list[TranscriptItem] = field(default_factory=list)
    transcript_count: int = 0
    finalizing: bool = False
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    worker_task: asyncio.Task[None] | None = None


class SessionManager:
    def __init__(
        self,
        *,
        settings: Settings,
        asr_client: AliyunASRClient,
        audio_codec_service: AudioCodecService,
        speaker_service: SpeakerService,
        summary_service: SummaryService,
    ) -> None:
        self._settings = settings
        self._asr_client = asr_client
        self._audio_codec_service = audio_codec_service
        self._speaker_service = speaker_service
        self._summary_service = summary_service
        self._sessions: dict[str, MeetingSession] = {}

    async def create_session(self, websocket: WebSocket, scene: str) -> MeetingSession:
        session = MeetingSession(
            session_id=uuid4().hex,
            scene=scene,
            websocket=websocket,
        )
        session.worker_task = asyncio.create_task(self._consume_audio(session))
        self._sessions[session.session_id] = session
        return session

    async def enqueue_audio(self, session: MeetingSession, payload: bytes) -> None:
        if session.finalizing:
            await self._send_error(session, "Session is finalizing; audio chunk ignored.")
            return
        await session.audio_queue.put(payload)

    async def finalize(self, session: MeetingSession) -> None:
        if session.finalizing:
            return
        session.finalizing = True
        await session.audio_queue.put(None)
        if session.worker_task is not None:
            await session.worker_task

    async def cleanup(self, session: MeetingSession) -> None:
        self._sessions.pop(session.session_id, None)
        if session.worker_task is not None and not session.worker_task.done():
            session.worker_task.cancel()
            try:
                await session.worker_task
            except asyncio.CancelledError:
                pass

    async def send_error(self, session: MeetingSession, message: str) -> None:
        await self._send_error(session, message)

    async def _consume_audio(self, session: MeetingSession) -> None:
        try:
            while True:
                payload = await session.audio_queue.get()
                if payload is None:
                    break

                try:
                    wav_audio = await self._audio_codec_service.convert_browser_chunk_to_wav(payload)
                    segments = await self._asr_client.transcribe_wav(wav_audio)
                except (RuntimeError, ValueError) as exc:
                    logger.error("Audio processing failed for %s: %s", session.session_id, exc)
                    await self._send_error(session, str(exc))
                    continue

                for segment in segments:
                    transcript = self._speaker_service.assign_speaker(
                        segment,
                        transcript_index=session.transcript_count,
                    )
                    session.transcripts.append(transcript)
                    session.transcript_count += 1
                    await self._send_transcript(session, transcript)
                    if session.transcript_count % self._settings.summary_interval == 0:
                        await self._send_summary(session)

            if session.finalizing:
                await self._send_summary(session)
                await self._close_socket(session, code=1000, reason="finalized")
        except asyncio.CancelledError:
            raise

    async def _send_transcript(
        self,
        session: MeetingSession,
        transcript: TranscriptItem,
    ) -> None:
        await self._send_message(
            session,
            WebSocketMessage(
                type=WebSocketMessageType.TRANSCRIPT,
                data=transcript.model_dump(),
            ),
        )

    async def _send_summary(self, session: MeetingSession) -> None:
        if not self._summary_service.is_configured:
            await self._send_error(session, "DashScope is not configured; summary is empty.")
        summary = await self._summary_service.generate_summary(session.transcripts, session.scene)
        await self._send_message(
            session,
            WebSocketMessage(
                type=WebSocketMessageType.SUMMARY,
                data=summary.model_dump(),
            ),
        )

    async def _send_error(self, session: MeetingSession, message: str) -> None:
        await self._send_message(
            session,
            WebSocketMessage(type=WebSocketMessageType.ERROR, data=message),
        )

    async def _send_message(
        self,
        session: MeetingSession,
        message: WebSocketMessage,
    ) -> None:
        if session.websocket.application_state == WebSocketState.DISCONNECTED:
            return
        async with session.send_lock:
            if session.websocket.application_state == WebSocketState.DISCONNECTED:
                return
            try:
                await session.websocket.send_json(message.model_dump())
            except RuntimeError:
                logger.warning("WebSocket send skipped because the connection is already closed.")

    async def _close_socket(
        self,
        session: MeetingSession,
        *,
        code: int,
        reason: str,
    ) -> None:
        if session.websocket.application_state != WebSocketState.DISCONNECTED:
            try:
                await session.websocket.close(code=code, reason=reason)
            except RuntimeError:
                logger.warning("WebSocket close skipped because the connection is already closed.")
