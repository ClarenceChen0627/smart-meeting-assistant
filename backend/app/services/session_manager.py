from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from uuid import uuid4

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from app.clients.dashscope_asr_client import DashScopeASRClient, DashScopeASRStream
from app.core.config import Settings
from app.schemas.analysis import MeetingAnalysis
from app.schemas.translation import TranscriptTranslation
from app.schemas.transcript import TranscriptItem
from app.schemas.ws_message import WebSocketMessage, WebSocketMessageType
from app.services.audio_codec_service import AudioCodecService
from app.services.sentiment_analysis_service import SentimentAnalysisService
from app.services.speaker_service import SpeakerService
from app.services.summary_service import SummaryService
from app.services.translation_service import TranslationService

logger = logging.getLogger(__name__)


@dataclass
class MeetingSession:
    session_id: str
    scene: str
    target_lang: str | None
    websocket: WebSocket
    audio_queue: asyncio.Queue[bytes | None] = field(default_factory=asyncio.Queue)
    translation_queue: asyncio.Queue[tuple[int, str] | None] = field(default_factory=asyncio.Queue)
    transcripts: list[TranscriptItem] = field(default_factory=list)
    transcript_count: int = 0
    finalizing: bool = False
    transcription_blocked: bool = False
    last_error_message: str | None = None
    last_summary_transcript_count: int = 0
    last_analysis_transcript_count: int = 0
    latest_analysis: MeetingAnalysis = field(default_factory=MeetingAnalysis.empty)
    analysis_in_progress: bool = False
    translated_transcript_indices: set[int] = field(default_factory=set)
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    worker_task: asyncio.Task[None] | None = None
    asr_stream: DashScopeASRStream | None = None
    translation_worker_task: asyncio.Task[None] | None = None


class SessionManager:
    def __init__(
        self,
        *,
        settings: Settings,
        asr_client: DashScopeASRClient,
        audio_codec_service: AudioCodecService,
        speaker_service: SpeakerService,
        summary_service: SummaryService,
        sentiment_analysis_service: SentimentAnalysisService,
        translation_service: TranslationService,
    ) -> None:
        self._settings = settings
        self._asr_client = asr_client
        self._speaker_service = speaker_service
        self._summary_service = summary_service
        self._sentiment_analysis_service = sentiment_analysis_service
        self._translation_service = translation_service
        self._sessions: dict[str, MeetingSession] = {}

    async def create_session(
        self,
        websocket: WebSocket,
        scene: str,
        target_lang: str | None,
    ) -> MeetingSession:
        normalized_target_lang = self._translation_service.normalize_target_lang(target_lang)
        session = MeetingSession(
            session_id=uuid4().hex,
            scene=scene,
            target_lang=normalized_target_lang,
            websocket=websocket,
        )
        session.worker_task = asyncio.create_task(self._consume_audio(session))
        if normalized_target_lang and self._translation_service.is_configured:
            session.translation_worker_task = asyncio.create_task(self._consume_translations(session))
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
        if session.translation_worker_task is not None and not session.translation_worker_task.done():
            session.translation_worker_task.cancel()
            try:
                await session.translation_worker_task
            except asyncio.CancelledError:
                pass
        if session.asr_stream is not None:
            await session.asr_stream.aclose()
            session.asr_stream = None

    async def send_error(self, session: MeetingSession, message: str) -> None:
        await self._send_error(session, message)

    async def _consume_audio(self, session: MeetingSession) -> None:
        if not self._asr_client.is_configured:
            await self._send_error_once(
                session,
                "DashScope ASR is not configured. Set DASHSCOPE_API_KEY and DASHSCOPE_ASR_MODEL.",
            )
            session.transcription_blocked = True

        if not session.transcription_blocked:
            await self._start_asr_stream(session)

        try:
            while True:
                payload = await session.audio_queue.get()
                if payload is None:
                    break

                if session.transcription_blocked or session.asr_stream is None:
                    continue

                try:
                    await session.asr_stream.send_audio(payload)
                except RuntimeError as exc:
                    logger.exception("Streaming audio failed for %s", session.session_id)
                    await self._handle_asr_error(session, str(exc).strip() or exc.__class__.__name__)
                    continue

            if session.finalizing:
                if session.asr_stream is not None and not session.transcription_blocked:
                    try:
                        await session.asr_stream.finish()
                    except RuntimeError as exc:
                        logger.exception("Finalizing ASR stream failed for %s", session.session_id)
                        await self._handle_asr_error(
                            session,
                            str(exc).strip() or exc.__class__.__name__,
                        )
                if session.translation_worker_task is not None:
                    await session.translation_queue.put(None)
                    try:
                        await session.translation_worker_task
                    except RuntimeError as exc:
                        logger.exception("Waiting for translation worker failed for %s", session.session_id)
                        await self._send_error_once(
                            session,
                            str(exc).strip() or exc.__class__.__name__,
                        )
                    finally:
                        session.translation_worker_task = None
                await self._send_analysis(session, force=True)
                await self._send_summary(session)
                await asyncio.sleep(0.05)
                await self._close_socket(session, code=1000, reason="finalized")
        except asyncio.CancelledError:
            raise

    async def _start_asr_stream(self, session: MeetingSession) -> None:
        try:
            session.asr_stream = self._asr_client.create_pcm_stream(
                on_segment=lambda segment: self._handle_segment(session, segment),
                on_error=lambda message: self._handle_asr_error(session, message),
            )
            await session.asr_stream.start()
        except RuntimeError as exc:
            logger.exception("Starting ASR stream failed for %s", session.session_id)
            await self._handle_asr_error(session, str(exc).strip() or exc.__class__.__name__)

    async def _handle_segment(self, session: MeetingSession, segment) -> None:
        transcript = self._speaker_service.assign_speaker(
            segment,
            transcript_index=session.transcript_count,
        )
        session.transcripts.append(transcript)
        session.transcript_count += 1
        transcript_index = session.transcript_count - 1
        await self._send_transcript(session, transcript)
        if session.translation_worker_task is not None and session.target_lang:
            await session.translation_queue.put((transcript_index, transcript.text))
        if session.transcript_count % 3 == 0:
            await self._send_analysis(session)
        if session.transcript_count % self._settings.summary_interval == 0:
            await self._send_summary(session)

    async def _handle_asr_error(self, session: MeetingSession, message: str) -> None:
        session.transcription_blocked = True
        await self._send_error_once(session, message)

    async def _consume_translations(self, session: MeetingSession) -> None:
        while True:
            item = await session.translation_queue.get()
            if item is None:
                break

            transcript_index, text = item
            if transcript_index in session.translated_transcript_indices:
                continue
            if not session.target_lang:
                continue

            try:
                translated_text = await self._translation_service.translate_text(
                    text=text,
                    target_lang=session.target_lang,
                )
            except (RuntimeError, ValueError) as exc:
                logger.warning(
                    "Translation failed for %s transcript %s (%s): %s",
                    session.session_id,
                    transcript_index,
                    session.target_lang,
                    exc,
                )
                continue

            if not translated_text:
                continue

            session.translated_transcript_indices.add(transcript_index)
            await self._send_translation(
                session,
                TranscriptTranslation(
                    transcript_index=transcript_index,
                    target_lang=session.target_lang,
                    text=translated_text,
                ),
            )

    async def _send_error_once(self, session: MeetingSession, message: str) -> None:
        if session.last_error_message == message:
            return
        session.last_error_message = message
        await self._send_error(session, message)

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

    async def _send_translation(
        self,
        session: MeetingSession,
        translation: TranscriptTranslation,
    ) -> None:
        await self._send_message(
            session,
            WebSocketMessage(
                type=WebSocketMessageType.TRANSLATION,
                data=translation.model_dump(),
            ),
        )

    async def _send_summary(self, session: MeetingSession, *, force: bool = False) -> None:
        if not session.transcripts:
            return
        if not force and session.last_summary_transcript_count == session.transcript_count:
            return
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
        session.last_summary_transcript_count = session.transcript_count

    async def _send_analysis(self, session: MeetingSession, *, force: bool = False) -> None:
        if not session.transcripts:
            return
        if session.analysis_in_progress:
            return
        if not force and session.last_analysis_transcript_count == session.transcript_count:
            return
        if not self._sentiment_analysis_service.is_configured:
            return

        session.analysis_in_progress = True
        try:
            analysis = await self._sentiment_analysis_service.analyze_meeting(
                session.transcripts,
                session.scene,
            )
            session.latest_analysis = analysis
            await self._send_message(
                session,
                WebSocketMessage(
                    type=WebSocketMessageType.ANALYSIS,
                    data=analysis.model_dump(),
                ),
            )
            session.last_analysis_transcript_count = session.transcript_count
        finally:
            session.analysis_in_progress = False

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
