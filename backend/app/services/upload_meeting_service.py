from __future__ import annotations

import asyncio
import logging
from typing import cast
from uuid import uuid4

from app.schemas.meeting_history import (
    MeetingProcessingStage,
    MeetingRecord,
    MeetingSourceType,
    MeetingHistoryStatus,
)
from app.schemas.transcript import TranscriptItem
from app.schemas.translation import TranscriptTranslation
from app.services.asr_provider_service import ASRProviderService
from app.services.audio_codec_service import AudioCodecService
from app.services.diarization_service import DiarizationService
from app.services.meeting_history_service import MeetingHistoryService
from app.services.sentiment_analysis_service import SentimentAnalysisService
from app.services.speaker_service import SpeakerService
from app.services.summary_service import SummaryService
from app.services.translation_service import TranslationService

logger = logging.getLogger(__name__)


class UploadMeetingService:
    def __init__(
        self,
        *,
        asr_provider_service: ASRProviderService,
        audio_codec_service: AudioCodecService,
        speaker_service: SpeakerService,
        diarization_service: DiarizationService,
        summary_service: SummaryService,
        sentiment_analysis_service: SentimentAnalysisService,
        translation_service: TranslationService,
        meeting_history_service: MeetingHistoryService,
    ) -> None:
        self._asr_provider_service = asr_provider_service
        self._audio_codec_service = audio_codec_service
        self._speaker_service = speaker_service
        self._diarization_service = diarization_service
        self._summary_service = summary_service
        self._sentiment_analysis_service = sentiment_analysis_service
        self._translation_service = translation_service
        self._meeting_history_service = meeting_history_service
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def start_upload(
        self,
        *,
        audio_data: bytes,
        filename: str | None,
        content_type: str | None,
        scene: str,
        target_lang: str | None,
        preferred_provider: str | None,
    ) -> MeetingRecord:
        if not audio_data:
            raise ValueError("Audio upload is empty.")

        normalized_target_lang = self._translation_service.normalize_target_lang(target_lang)
        selection = self._asr_provider_service.resolve_provider(preferred_provider)
        meeting_id = uuid4().hex
        self._meeting_history_service.create_meeting(
            meeting_id=meeting_id,
            scene=scene,
            target_lang=normalized_target_lang,
            provider=selection.provider_name,
            status=MeetingHistoryStatus.PROCESSING,
            source_type=MeetingSourceType.UPLOAD,
            processing_stage=MeetingProcessingStage.TRANSCRIBING,
            source_name=filename,
        )

        self._tasks[meeting_id] = asyncio.create_task(
            self._process_upload(
                meeting_id=meeting_id,
                audio_data=audio_data,
                filename=filename,
                content_type=content_type,
                scene=scene,
                target_lang=normalized_target_lang,
                initial_provider=selection.provider_name,
            )
        )

        meeting = self._meeting_history_service.get_meeting(meeting_id)
        if meeting is None:
            raise RuntimeError("Upload meeting record was not created.")
        return meeting

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()

    async def _process_upload(
        self,
        *,
        meeting_id: str,
        audio_data: bytes,
        filename: str | None,
        content_type: str | None,
        scene: str,
        target_lang: str | None,
        initial_provider: str,
    ) -> None:
        try:
            wav_audio = await self._audio_codec_service.convert_upload_to_wav(
                audio_data,
                filename=filename,
                content_type=content_type,
            )
            transcripts, resolved_provider = await self._transcribe_audio(
                wav_audio,
                preferred_provider=initial_provider,
            )
            if resolved_provider != initial_provider:
                self._meeting_history_service.update_provider(meeting_id, resolved_provider)

            for transcript in transcripts:
                self._meeting_history_service.upsert_transcript(meeting_id, transcript)

            if not transcripts:
                self._meeting_history_service.mark_finalized(meeting_id)
                return

            if target_lang and self._translation_service.is_configured:
                self._meeting_history_service.mark_processing(meeting_id, MeetingProcessingStage.TRANSLATING)
                await self._translate_transcripts(
                    meeting_id=meeting_id,
                    transcripts=transcripts,
                    target_lang=target_lang,
                )

            self._meeting_history_service.mark_processing(meeting_id, MeetingProcessingStage.ANALYZING)
            analysis = await self._sentiment_analysis_service.analyze_meeting(transcripts, scene)
            self._meeting_history_service.update_analysis(meeting_id, analysis)

            self._meeting_history_service.mark_processing(meeting_id, MeetingProcessingStage.SUMMARIZING)
            summary = await self._summary_service.generate_summary(transcripts, scene)
            self._meeting_history_service.update_summary(meeting_id, summary)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Upload meeting processing failed for %s", meeting_id)
            message = str(exc).strip() or exc.__class__.__name__
            self._meeting_history_service.mark_failed(meeting_id, message)
        finally:
            self._tasks.pop(meeting_id, None)

    async def _transcribe_audio(
        self,
        wav_audio: bytes,
        *,
        preferred_provider: str | None,
    ) -> tuple[list[TranscriptItem], str]:
        selection = self._asr_provider_service.resolve_provider(preferred_provider)
        try:
            segments = await selection.client.transcribe_wav(wav_audio)
        except RuntimeError as exc:
            fallback = self._asr_provider_service.resolve_fallback(selection.provider_name)
            if fallback is None:
                raise RuntimeError(str(exc)) from exc
            segments = await fallback.client.transcribe_wav(wav_audio)
            selection = fallback

        transcripts = [
            self._speaker_service.assign_speaker(
                segment,
                transcript_index=index,
                speaker=getattr(segment, "speaker", None),
                speaker_is_final=getattr(segment, "speaker_is_final", selection.provider_name == "volcengine"),
            )
            for index, segment in enumerate(segments)
        ]
        if selection.should_run_diarization:
            diarization_result = await self._diarization_service.diarize_audio_bytes(wav_audio)
            transcripts = self._diarization_service.assign_speakers(
                transcripts,
                diarization_result.turns,
                speaker_is_final=diarization_result.succeeded,
            )
        return transcripts, selection.provider_name

    async def _translate_transcripts(
        self,
        *,
        meeting_id: str,
        transcripts: list[TranscriptItem],
        target_lang: str,
    ) -> None:
        for transcript in transcripts:
            try:
                translated_text = await self._translation_service.translate_text(
                    text=transcript.text,
                    target_lang=target_lang,
                )
            except (RuntimeError, ValueError) as exc:
                logger.warning(
                    "Upload translation failed for %s transcript %s (%s): %s",
                    meeting_id,
                    transcript.transcript_index,
                    target_lang,
                    exc,
                )
                continue

            if not translated_text:
                continue

            self._meeting_history_service.update_translation(
                meeting_id,
                cast(
                    TranscriptTranslation,
                    TranscriptTranslation(
                        transcript_index=transcript.transcript_index,
                        target_lang=target_lang,
                        text=translated_text,
                    ),
                ),
            )
