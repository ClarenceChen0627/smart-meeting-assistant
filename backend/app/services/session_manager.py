from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import wave
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from app.clients.asr_base import ASRClient, ASRStream
from app.core.config import Settings
from app.schemas.analysis import MeetingAnalysis
from app.schemas.translation import TranscriptTranslation
from app.schemas.transcript import TranscriptItem
from app.schemas.ws_message import SpeakerUpdate, WebSocketMessage, WebSocketMessageType
from app.services.asr_provider_service import ASRProviderSelection, ASRProviderService
from app.services.audio_codec_service import AudioCodecService
from app.services.diarization_service import DiarizationService
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
    active_provider: str
    asr_client: ASRClient
    should_run_diarization: bool
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
    analysis_task: asyncio.Task[None] | None = None
    translated_transcript_indices: set[int] = field(default_factory=set)
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    worker_task: asyncio.Task[None] | None = None
    asr_stream: ASRStream | None = None
    translation_worker_task: asyncio.Task[None] | None = None
    session_audio_path: Path | None = None
    session_audio_writer: wave.Wave_write | None = None
    active_partial_transcript_index: int | None = None


class SessionManager:
    def __init__(
        self,
        *,
        settings: Settings,
        asr_provider_service: ASRProviderService,
        audio_codec_service: AudioCodecService,
        speaker_service: SpeakerService,
        diarization_service: DiarizationService,
        summary_service: SummaryService,
        sentiment_analysis_service: SentimentAnalysisService,
        translation_service: TranslationService,
    ) -> None:
        self._settings = settings
        self._asr_provider_service = asr_provider_service
        self._audio_codec_service = audio_codec_service
        self._speaker_service = speaker_service
        self._diarization_service = diarization_service
        self._summary_service = summary_service
        self._sentiment_analysis_service = sentiment_analysis_service
        self._translation_service = translation_service
        self._sessions: dict[str, MeetingSession] = {}

    async def create_session(
        self,
        websocket: WebSocket,
        scene: str,
        target_lang: str | None,
        preferred_provider: str | None = None,
    ) -> MeetingSession:
        normalized_target_lang = self._translation_service.normalize_target_lang(target_lang)
        selection = self._asr_provider_service.resolve_provider(preferred_provider)
        session = MeetingSession(
            session_id=uuid4().hex,
            scene=scene,
            target_lang=normalized_target_lang,
            websocket=websocket,
            active_provider=selection.provider_name,
            asr_client=selection.client,
            should_run_diarization=selection.should_run_diarization,
        )
        self._open_session_audio_writer(session)
        session.worker_task = asyncio.create_task(self._consume_audio(session))
        if normalized_target_lang and self._translation_service.is_configured:
            session.translation_worker_task = asyncio.create_task(self._consume_translations(session))
        self._sessions[session.session_id] = session
        return session

    async def enqueue_audio(self, session: MeetingSession, payload: bytes) -> None:
        if session.finalizing:
            await self._send_error(session, "Session is finalizing; audio chunk ignored.")
            return
        self._persist_session_audio(session, payload)
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
        if session.analysis_task is not None and not session.analysis_task.done():
            session.analysis_task.cancel()
            try:
                await session.analysis_task
            except asyncio.CancelledError:
                pass
        if session.asr_stream is not None:
            await session.asr_stream.aclose()
            session.asr_stream = None
        self._close_session_audio_writer(session)
        if session.session_audio_path is not None:
            session.session_audio_path.unlink(missing_ok=True)
            session.session_audio_path = None

    async def send_error(self, session: MeetingSession, message: str) -> None:
        await self._send_error(session, message)

    async def _consume_audio(self, session: MeetingSession) -> None:
        if not session.asr_client.is_configured:
            await self._send_error_once(
                session,
                f"ASR provider '{session.active_provider}' is not configured.",
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
                    logger.exception("Streaming audio failed for %s via %s", session.session_id, session.active_provider)
                    await self._handle_asr_error(session, str(exc).strip() or exc.__class__.__name__)
                    continue

            if session.finalizing:
                if session.asr_stream is not None and not session.transcription_blocked:
                    try:
                        await session.asr_stream.finish()
                    except RuntimeError as exc:
                        logger.exception("Finalizing ASR stream failed for %s via %s", session.session_id, session.active_provider)
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
                await self._finalize_speakers(session)
                await self._send_analysis(session, force=True)
                await self._send_summary(session, force=True)
                await asyncio.sleep(0.05)
                await self._close_socket(session, code=1000, reason="finalized")
        except asyncio.CancelledError:
            raise

    async def _start_asr_stream(self, session: MeetingSession) -> None:
        try:
            session.asr_stream = session.asr_client.create_pcm_stream(
                on_segment=lambda segment: self._handle_segment(session, segment),
                on_error=lambda message: self._handle_asr_error(session, message),
            )
            await session.asr_stream.start()
        except RuntimeError as exc:
            fallback = self._asr_provider_service.resolve_fallback(session.active_provider)
            if fallback is None:
                logger.exception("Starting ASR stream failed for %s via %s", session.session_id, session.active_provider)
                await self._handle_asr_error(session, str(exc).strip() or exc.__class__.__name__)
                return
            logger.warning(
                "Starting ASR stream failed for %s via %s. Retrying with %s.",
                session.session_id,
                session.active_provider,
                fallback.provider_name,
            )
            self._apply_asr_selection(session, fallback)
            try:
                session.asr_stream = session.asr_client.create_pcm_stream(
                    on_segment=lambda segment: self._handle_segment(session, segment),
                    on_error=lambda message: self._handle_asr_error(session, message),
                )
                await session.asr_stream.start()
            except RuntimeError as fallback_exc:
                logger.exception(
                    "Starting fallback ASR stream failed for %s via %s",
                    session.session_id,
                    session.active_provider,
                )
                await self._handle_asr_error(session, str(fallback_exc).strip() or fallback_exc.__class__.__name__)

    async def _handle_segment(self, session: MeetingSession, segment: TranscriptSegment) -> None:
        transcript_is_final = getattr(segment, "transcript_is_final", True)
        speaker = getattr(segment, "speaker", None)
        speaker_is_final = getattr(
            segment,
            "speaker_is_final",
            session.active_provider == "volcengine" and transcript_is_final,
        )

        if not transcript_is_final:
            if session.active_partial_transcript_index is None:
                transcript = self._speaker_service.assign_speaker(
                    segment,
                    transcript_index=session.transcript_count,
                    speaker=speaker,
                    speaker_is_final=speaker_is_final,
                    transcript_is_final=False,
                )
                session.transcripts.append(transcript)
                session.active_partial_transcript_index = session.transcript_count
                session.transcript_count += 1
                await self._send_transcript(session, transcript)
                return

            transcript_index = session.active_partial_transcript_index
            updated = self._speaker_service.update_transcript(
                session.transcripts[transcript_index],
                text=segment.text,
                start=segment.start,
                end=segment.end,
                speaker=speaker or session.transcripts[transcript_index].speaker,
                speaker_is_final=speaker_is_final,
                transcript_is_final=False,
            )
            session.transcripts[transcript_index] = updated
            await self._send_transcript_update(session, updated)
            return

        if session.active_partial_transcript_index is not None:
            transcript_index = session.active_partial_transcript_index
            updated = self._speaker_service.update_transcript(
                session.transcripts[transcript_index],
                text=segment.text,
                start=segment.start,
                end=segment.end,
                speaker=speaker or session.transcripts[transcript_index].speaker,
                speaker_is_final=speaker_is_final,
                transcript_is_final=True,
            )
            session.transcripts[transcript_index] = updated
            session.active_partial_transcript_index = None
            await self._send_transcript_update(session, updated)
            await self._postprocess_final_transcript(session, updated)
            return

        transcript = self._speaker_service.assign_speaker(
            segment,
            transcript_index=session.transcript_count,
            speaker=speaker,
            speaker_is_final=speaker_is_final,
            transcript_is_final=True,
        )
        session.transcripts.append(transcript)
        session.transcript_count += 1
        await self._send_transcript(session, transcript)
        await self._postprocess_final_transcript(session, transcript)

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

    async def _send_transcript_update(
        self,
        session: MeetingSession,
        transcript: TranscriptItem,
    ) -> None:
        await self._send_message(
            session,
            WebSocketMessage(
                type=WebSocketMessageType.TRANSCRIPT_UPDATE,
                data=transcript.model_dump(),
            ),
        )

    async def _send_speaker_update(
        self,
        session: MeetingSession,
        update: SpeakerUpdate,
    ) -> None:
        await self._send_message(
            session,
            WebSocketMessage(
                type=WebSocketMessageType.SPEAKER_UPDATE,
                data=update.model_dump(),
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

    def _schedule_analysis(self, session: MeetingSession) -> None:
        if session.finalizing:
            return
        if session.analysis_in_progress:
            return
        if session.analysis_task is not None and not session.analysis_task.done():
            return
        if session.last_analysis_transcript_count == session.transcript_count:
            return

        async def run_analysis() -> None:
            try:
                await self._send_analysis(session)
            except Exception:
                logger.exception("Background analysis task failed for %s", session.session_id)
            finally:
                session.analysis_task = None

        session.analysis_task = asyncio.create_task(run_analysis())

    async def _postprocess_final_transcript(
        self,
        session: MeetingSession,
        transcript: TranscriptItem,
    ) -> None:
        if session.translation_worker_task is not None and session.target_lang:
            await session.translation_queue.put((transcript.transcript_index, transcript.text))
        if session.transcript_count % 3 == 0:
            self._schedule_analysis(session)

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

    async def _finalize_speakers(self, session: MeetingSession) -> None:
        if not session.should_run_diarization:
            self._close_session_audio_writer(session)
            return
        if not session.transcripts:
            self._close_session_audio_writer(session)
            return

        self._close_session_audio_writer(session)
        if session.session_audio_path is None:
            return

        diarization_result = await self._diarization_service.diarize_audio_file(session.session_audio_path)
        if not diarization_result.succeeded:
            return

        session.transcripts = self._diarization_service.assign_speakers(
            session.transcripts,
            diarization_result.turns,
            speaker_is_final=True,
        )
        for transcript in session.transcripts:
            await self._send_speaker_update(
                session,
                SpeakerUpdate(
                    transcript_index=transcript.transcript_index,
                    speaker=transcript.speaker,
                    speaker_is_final=transcript.speaker_is_final,
                ),
            )

    def _apply_asr_selection(self, session: MeetingSession, selection: ASRProviderSelection) -> None:
        session.active_provider = selection.provider_name
        session.asr_client = selection.client
        session.should_run_diarization = selection.should_run_diarization
        if session.should_run_diarization:
            self._open_session_audio_writer(session)
        else:
            self._close_session_audio_writer(session)
            if session.session_audio_path is not None:
                session.session_audio_path.unlink(missing_ok=True)
                session.session_audio_path = None

    def _open_session_audio_writer(self, session: MeetingSession) -> None:
        if not session.should_run_diarization or session.session_audio_writer is not None:
            return
        try:
            file_descriptor, file_path = tempfile.mkstemp(
                prefix=f"meeting-{session.session_id}-",
                suffix=".wav",
            )
            os.close(file_descriptor)
            audio_writer = wave.open(file_path, "wb")
            audio_writer.setnchannels(self._settings.audio_channels)
            audio_writer.setsampwidth(2)
            audio_writer.setframerate(self._settings.sample_rate)
            session.session_audio_path = Path(file_path)
            session.session_audio_writer = audio_writer
        except Exception as exc:
            logger.warning(
                "Failed to initialize session audio capture for diarization; continuing without it: %s",
                exc,
            )
            session.session_audio_path = None
            session.session_audio_writer = None

    def _persist_session_audio(self, session: MeetingSession, payload: bytes) -> None:
        if session.session_audio_writer is None or not payload:
            return
        try:
            session.session_audio_writer.writeframes(payload)
        except Exception as exc:
            logger.warning(
                "Failed to persist session audio for diarization; continuing without it: %s",
                exc,
            )
            self._close_session_audio_writer(session)

    def _close_session_audio_writer(self, session: MeetingSession) -> None:
        if session.session_audio_writer is None:
            return
        try:
            session.session_audio_writer.close()
        except Exception as exc:
            logger.warning("Closing session audio writer failed: %s", exc)
        finally:
            session.session_audio_writer = None
