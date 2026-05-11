from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api.diagnostics import router as diagnostics_router
from app.api.health import router as health_router
from app.api.glossary import router as glossary_router
from app.api.meetings import router as meetings_router
from app.api.transcribe import router as transcribe_router
from app.api.websocket import router as websocket_router
from app.clients.dashscope_asr_client import DashScopeASRClient
from app.clients.dashscope_client import DashScopeClient
from app.clients.demo_asr_client import DemoASRClient
from app.clients.demo_dashscope_client import DemoDashScopeClient
from app.clients.volcengine_asr_client import VolcengineASRClient
from app.core.config import settings
from app.core.logging import configure_logging
from app.middleware.observability import observability_middleware
from app.services.audio_codec_service import AudioCodecService
from app.services.asr_provider_service import ASRProviderService
from app.services.diarization_service import DiarizationService
from app.services.glossary_service import GlossaryService
from app.services.glossary_store_service import GlossaryStoreService
from app.services.meeting_history_service import MeetingHistoryService
from app.services.realtime_diarization_service import RealtimeDiarizationService
from app.services.meeting_analysis_service import MeetingAnalysisService
from app.services.raw_audio_retention_service import RawAudioRetentionService
from app.services.observability_service import ObservabilityService
from app.services.session_manager import SessionManager
from app.services.speaker_service import SpeakerService
from app.services.summary_service import SummaryService
from app.services.translation_service import TranslationService
from app.services.upload_meeting_service import UploadMeetingService
from app.services.upload_queue_service import UploadQueueStore

configure_logging(settings.log_level)
logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    dashscope_asr_client = DashScopeASRClient(settings)
    volcengine_asr_client = VolcengineASRClient(settings)
    demo_asr_client = DemoASRClient(settings)
    dashscope_client = DemoDashScopeClient(settings) if settings.demo_mode else DashScopeClient(settings)
    audio_codec_service = AudioCodecService(settings)
    speaker_service = SpeakerService()
    diarization_service = DiarizationService(settings, speaker_service)
    realtime_diarization_service = RealtimeDiarizationService(settings)
    asr_provider_service = ASRProviderService(
        settings=settings,
        dashscope_client=dashscope_asr_client,
        volcengine_client=volcengine_asr_client,
        demo_client=demo_asr_client,
    )
    summary_service = SummaryService(dashscope_client)
    meeting_analysis_service = MeetingAnalysisService(dashscope_client)
    translation_service = TranslationService(dashscope_client)
    raw_audio_retention_service = RawAudioRetentionService(settings)
    observability_service = ObservabilityService()
    meeting_history_service = MeetingHistoryService(settings.resolved_meeting_history_db_path)
    upload_queue_store = UploadQueueStore(
        db_path=settings.resolved_meeting_history_db_path,
        queue_dir=settings.resolved_upload_queue_dir,
        max_attempts=settings.upload_queue_max_attempts,
        retry_base_seconds=settings.upload_queue_retry_base_seconds,
        retry_max_seconds=settings.upload_queue_retry_max_seconds,
    )
    glossary_store_service = GlossaryStoreService(settings.resolved_meeting_history_db_path)
    glossary_service = GlossaryService(settings, glossary_store_service)
    upload_meeting_service = UploadMeetingService(
        asr_provider_service=asr_provider_service,
        audio_codec_service=audio_codec_service,
        speaker_service=speaker_service,
        diarization_service=diarization_service,
        summary_service=summary_service,
        meeting_analysis_service=meeting_analysis_service,
        translation_service=translation_service,
        meeting_history_service=meeting_history_service,
        glossary_service=glossary_service,
        raw_audio_retention_service=raw_audio_retention_service,
        upload_queue_store=upload_queue_store,
        embedded_worker_enabled=settings.upload_queue_embedded_worker_enabled,
        upload_queue_processing_timeout_seconds=settings.upload_queue_processing_timeout_seconds,
        observability_service=observability_service,
    )
    session_manager = SessionManager(
        settings=settings,
        asr_provider_service=asr_provider_service,
        audio_codec_service=audio_codec_service,
        speaker_service=speaker_service,
        diarization_service=diarization_service,
        realtime_diarization_service=realtime_diarization_service,
        summary_service=summary_service,
        meeting_analysis_service=meeting_analysis_service,
        translation_service=translation_service,
        meeting_history_service=meeting_history_service,
        glossary_service=glossary_service,
        observability_service=observability_service,
    )

    app.state.settings = settings
    app.state.asr_client = dashscope_asr_client
    app.state.dashscope_asr_client = dashscope_asr_client
    app.state.volcengine_asr_client = volcengine_asr_client
    app.state.demo_asr_client = demo_asr_client
    app.state.asr_provider_service = asr_provider_service
    app.state.dashscope_client = dashscope_client
    app.state.audio_codec_service = audio_codec_service
    app.state.speaker_service = speaker_service
    app.state.diarization_service = diarization_service
    app.state.realtime_diarization_service = realtime_diarization_service
    app.state.summary_service = summary_service
    app.state.meeting_analysis_service = meeting_analysis_service
    app.state.translation_service = translation_service
    app.state.glossary_service = glossary_service
    app.state.glossary_store_service = glossary_store_service
    app.state.raw_audio_retention_service = raw_audio_retention_service
    app.state.observability_service = observability_service
    app.state.upload_queue_store = upload_queue_store
    app.state.meeting_history_service = meeting_history_service
    app.state.upload_meeting_service = upload_meeting_service
    app.state.session_manager = session_manager

    try:
        ffmpeg_binary = audio_codec_service.resolve_ffmpeg_binary()
        logger.info("Using ffmpeg binary: %s", ffmpeg_binary)
    except RuntimeError as exc:
        logger.warning("%s", exc)
    if dashscope_asr_client.is_configured:
        logger.info("DashScope ASR is configured with model: %s", settings.dashscope_asr_model)
    else:
        logger.warning("DashScope ASR is not configured.")
    if volcengine_asr_client.is_configured:
        logger.info(
            "Volcengine ASR is configured with resource: %s (default provider=%s)",
            settings.volcengine_asr_resource_id,
            settings.default_asr_provider,
        )
    else:
        logger.warning("Volcengine ASR is not configured.")
    if settings.demo_mode:
        logger.info("Demo mode is enabled. Deterministic demo ASR, translation, summary, and analysis are available.")
    if translation_service.is_configured:
        logger.info("Using DashScope translation model: %s", settings.dashscope_translation_model)
    if settings.diarization_enabled:
        logger.info("Speaker diarization is enabled in %s mode with model: %s", settings.diarization_mode, settings.diarization_model)
        if settings.realtime_diarization_enabled:
            logger.info(
                "Realtime speaker diarization is enabled with duration=%ss step=%ss latency=%ss.",
                settings.realtime_diarization_duration_seconds,
                settings.realtime_diarization_step_seconds,
                settings.realtime_diarization_latency_seconds,
            )
    else:
        logger.info("Speaker diarization is disabled.")
    if settings.upload_queue_embedded_worker_enabled:
        upload_meeting_service.start_embedded_worker()
        logger.info("Embedded upload queue worker is enabled.")
    else:
        logger.info("Embedded upload queue worker is disabled. Run tools/run_upload_worker.py to process uploads.")

    logger.info("Starting %s %s", settings.service_name, settings.service_version)
    yield
    await upload_meeting_service.shutdown()
    await dashscope_asr_client.aclose()
    await volcengine_asr_client.aclose()
    await demo_asr_client.aclose()
    await dashscope_client.aclose()


app = FastAPI(
    title=settings.service_name,
    version=settings.service_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.middleware("http")(observability_middleware)

app.include_router(diagnostics_router)
app.include_router(health_router)
app.include_router(glossary_router)
app.include_router(meetings_router)
app.include_router(transcribe_router)
app.include_router(websocket_router)


@app.get("/")
async def root() -> dict:
    return {
        "service": settings.service_name,
        "version": settings.service_version,
        "status": "running",
    }


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    return FileResponse(STATIC_DIR / "favicon.ico")
