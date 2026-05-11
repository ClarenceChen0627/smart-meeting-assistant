from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from collections.abc import Awaitable, Callable
from typing import TypeVar, cast
from uuid import uuid4

from app.core.logging import correlation_context
from app.schemas.glossary import GlossaryTerm
from app.schemas.meeting_history import (
    MeetingProcessingStage,
    MeetingRecord,
    MeetingSourceType,
    MeetingHistoryStatus,
)
from app.schemas.transcript import TranscriptItem
from app.schemas.translation import TranscriptTranslation
from app.services.asr_provider_service import ASR_PROVIDER_DEMO, ASRProviderService
from app.services.audio_codec_service import AudioCodecService
from app.services.diarization_service import DiarizationService
from app.services.glossary_service import GlossaryService
from app.services.meeting_history_service import MeetingHistoryService
from app.services.meeting_analysis_service import MeetingAnalysisService
from app.services.raw_audio_retention_service import RawAudioRetentionService
from app.services.observability_service import ObservabilityService
from app.services.speaker_service import SpeakerService
from app.services.summary_service import SummaryService
from app.services.translation_service import TranslationService
from app.services.upload_queue_service import UploadJob, UploadQueueStore, UploadQueueWorker

logger = logging.getLogger(__name__)
T = TypeVar("T")


class UploadMeetingService:
    RUNTIME_RETRY_COUNT = 1

    def __init__(
        self,
        *,
        asr_provider_service: ASRProviderService,
        audio_codec_service: AudioCodecService,
        speaker_service: SpeakerService,
        diarization_service: DiarizationService,
        summary_service: SummaryService,
        meeting_analysis_service: MeetingAnalysisService,
        translation_service: TranslationService,
        meeting_history_service: MeetingHistoryService,
        glossary_service: GlossaryService,
        raw_audio_retention_service: RawAudioRetentionService,
        upload_queue_store: UploadQueueStore,
        embedded_worker_enabled: bool = True,
        upload_queue_processing_timeout_seconds: float = 1800.0,
        observability_service: ObservabilityService | None = None,
        upload_queue_worker: UploadQueueWorker | None = None,
    ) -> None:
        self._asr_provider_service = asr_provider_service
        self._audio_codec_service = audio_codec_service
        self._speaker_service = speaker_service
        self._diarization_service = diarization_service
        self._summary_service = summary_service
        self._meeting_analysis_service = meeting_analysis_service
        self._translation_service = translation_service
        self._meeting_history_service = meeting_history_service
        self._glossary_service = glossary_service
        self._raw_audio_retention_service = raw_audio_retention_service
        self._upload_queue_store = upload_queue_store
        self._embedded_worker_enabled = embedded_worker_enabled
        self._upload_queue_processing_timeout_seconds = upload_queue_processing_timeout_seconds
        self._observability_service = observability_service
        self._upload_queue_worker = upload_queue_worker or UploadQueueWorker(
            name="upload-meetings",
            store=upload_queue_store,
            handler=self.process_upload_job,
            on_terminal_failure=self._mark_job_terminal_failed,
        )
        self.reconcile_upload_queue()

    async def start_upload(
        self,
        *,
        audio_data: bytes,
        filename: str | None,
        content_type: str | None,
        scene: str,
        target_lang: str | None,
        preferred_provider: str | None,
        retain_raw_audio: bool = False,
        glossary_terms: str | None = None,
    ) -> MeetingRecord:
        if not audio_data:
            raise ValueError("Audio upload is empty.")

        normalized_target_lang = self._translation_service.normalize_target_lang(target_lang)
        selection = self._asr_provider_service.resolve_provider(preferred_provider)
        resolved_glossary_terms = self._glossary_service.resolve_terms(glossary_terms)
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
            glossary_terms=resolved_glossary_terms,
        )
        raw_audio_metadata = self._raw_audio_retention_service.retain_upload(
            meeting_id=meeting_id,
            audio_data=audio_data,
            filename=filename,
            content_type=content_type,
            requested=retain_raw_audio,
        )
        if raw_audio_metadata is not None:
            self._meeting_history_service.update_raw_audio_metadata(meeting_id, raw_audio_metadata)

        self._upload_queue_store.enqueue_upload(
            meeting_id=meeting_id,
            audio_data=audio_data,
            filename=filename,
            content_type=content_type,
            scene=scene,
            target_lang=normalized_target_lang,
            provider=selection.provider_name,
            glossary_terms=resolved_glossary_terms,
        )
        self.start_embedded_worker()

        meeting = self._meeting_history_service.get_meeting(meeting_id)
        if meeting is None:
            raise RuntimeError("Upload meeting record was not created.")
        return meeting

    def start_embedded_worker(self) -> None:
        if self._embedded_worker_enabled:
            self._upload_queue_worker.start()

    def reconcile_upload_queue(self) -> None:
        self._upload_queue_store.release_stale_processing_jobs(
            timeout_seconds=self._upload_queue_processing_timeout_seconds
        )
        for meeting_id, error_message in self._upload_queue_store.fail_jobs_with_missing_payloads().items():
            self._meeting_history_service.mark_failed(meeting_id, error_message)
        for meeting_id, error_message in self._upload_queue_store.terminal_failed_job_errors().items():
            meeting = self._meeting_history_service.get_meeting(meeting_id)
            if meeting is not None and meeting.status == MeetingHistoryStatus.PROCESSING:
                self._meeting_history_service.mark_failed(meeting_id, error_message)
        self._meeting_history_service.reconcile_processing_uploads(
            self._upload_queue_store.active_job_meeting_ids()
        )

    async def process_available_jobs(self) -> int:
        return await self._upload_queue_worker.process_available_jobs()

    async def process_upload_job(self, job: UploadJob) -> str | None:
        with correlation_context(meeting_id=job.meeting_id, job_id=job.meeting_id, provider=job.provider):
            try:
                audio_data = job.payload_path.read_bytes()
                self._meeting_history_service.mark_processing(job.meeting_id, MeetingProcessingStage.TRANSCRIBING)
                await self._process_upload(
                    meeting_id=job.meeting_id,
                    audio_data=audio_data,
                    filename=job.filename,
                    content_type=job.content_type,
                    scene=job.scene,
                    target_lang=job.target_lang,
                    initial_provider=job.provider,
                    glossary_terms=job.glossary_terms,
                )
                return None
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Upload meeting processing failed.")
                message = str(exc).strip() or exc.__class__.__name__
                return message

    async def shutdown(self) -> None:
        await self._upload_queue_worker.shutdown()

    def _mark_job_terminal_failed(self, job: UploadJob, error_message: str) -> None:
        self._meeting_history_service.mark_failed(job.meeting_id, error_message)

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
        glossary_terms: list[GlossaryTerm],
    ) -> None:
        if initial_provider == ASR_PROVIDER_DEMO:
            wav_audio = audio_data
        else:
            wav_audio = await self._audio_codec_service.convert_upload_to_wav(
                audio_data,
                filename=filename,
                content_type=content_type,
            )
        transcripts, resolved_provider = await self._run_with_runtime_retries(
            "upload transcription",
            lambda: self._transcribe_audio(
                wav_audio,
                preferred_provider=initial_provider,
            ),
        )
        transcripts = self._glossary_service.apply_to_transcripts(transcripts, glossary_terms)
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
        analysis = await self._run_with_runtime_retries(
            "upload analysis",
            lambda: self._recorded_operation(
                operation_name="upload_analysis",
                provider="dashscope",
                call=lambda: self._meeting_analysis_service.analyze_meeting(
                    transcripts,
                    scene,
                    glossary_terms=glossary_terms,
                ),
            ),
        )
        self._meeting_history_service.update_analysis(meeting_id, analysis)

        self._meeting_history_service.mark_processing(meeting_id, MeetingProcessingStage.SUMMARIZING)
        summary = await self._run_with_runtime_retries(
            "upload summary",
            lambda: self._recorded_operation(
                operation_name="upload_summary",
                provider="dashscope",
                call=lambda: self._summary_service.generate_summary(
                    transcripts,
                    scene,
                    glossary_terms=glossary_terms,
                ),
            ),
        )
        self._meeting_history_service.update_summary(meeting_id, summary)

    async def _transcribe_audio(
        self,
        wav_audio: bytes,
        *,
        preferred_provider: str | None,
    ) -> tuple[list[TranscriptItem], str]:
        selection = self._asr_provider_service.resolve_provider(preferred_provider)
        started_at = perf_counter()
        try:
            segments = await selection.client.transcribe_wav(wav_audio)
            self._record_provider_operation(
                operation="upload_asr",
                provider=selection.provider_name,
                latency_seconds=perf_counter() - started_at,
                success=True,
            )
        except RuntimeError as exc:
            self._record_provider_operation(
                operation="upload_asr",
                provider=selection.provider_name,
                latency_seconds=perf_counter() - started_at,
                success=False,
            )
            fallback = self._asr_provider_service.resolve_fallback(selection.provider_name)
            if fallback is None:
                raise RuntimeError(str(exc)) from exc
            fallback_started_at = perf_counter()
            try:
                segments = await fallback.client.transcribe_wav(wav_audio)
            except RuntimeError:
                self._record_provider_operation(
                    operation="upload_asr",
                    provider=fallback.provider_name,
                    latency_seconds=perf_counter() - fallback_started_at,
                    success=False,
                )
                raise
            self._record_provider_operation(
                operation="upload_asr",
                provider=fallback.provider_name,
                latency_seconds=perf_counter() - fallback_started_at,
                success=True,
            )
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

    async def _run_with_runtime_retries(
        self,
        operation_name: str,
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        for attempt in range(self.RUNTIME_RETRY_COUNT + 1):
            try:
                return await operation()
            except RuntimeError:
                if attempt >= self.RUNTIME_RETRY_COUNT:
                    raise
                logger.warning(
                    "%s failed with a runtime error; retrying once.",
                    operation_name,
                    exc_info=True,
                )

        raise RuntimeError(f"{operation_name} failed after retry.")

    async def _recorded_operation(
        self,
        *,
        operation_name: str,
        provider: str,
        call: Callable[[], Awaitable[T]],
    ) -> T:
        started_at = perf_counter()
        try:
            result = await call()
        except Exception:
            self._record_provider_operation(
                operation=operation_name,
                provider=provider,
                latency_seconds=perf_counter() - started_at,
                success=False,
            )
            raise
        self._record_provider_operation(
            operation=operation_name,
            provider=provider,
            latency_seconds=perf_counter() - started_at,
            success=True,
        )
        return result

    def _record_provider_operation(
        self,
        *,
        operation: str,
        provider: str,
        latency_seconds: float,
        success: bool,
    ) -> None:
        if self._observability_service is None:
            return
        self._observability_service.record_provider_operation(
            operation=operation,
            provider=provider,
            latency_seconds=latency_seconds,
            success=success,
        )

    async def _translate_transcripts(
        self,
        *,
        meeting_id: str,
        transcripts: list[TranscriptItem],
        target_lang: str,
    ) -> None:
        for transcript in transcripts:
            try:
                translated_text = await self._recorded_operation(
                    operation_name="upload_translation",
                    provider="dashscope",
                    call=lambda: self._translation_service.translate_text(
                        text=transcript.text,
                        target_lang=target_lang,
                    ),
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
