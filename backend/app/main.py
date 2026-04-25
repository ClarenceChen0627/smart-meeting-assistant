from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api.health import router as health_router
from app.api.meetings import router as meetings_router
from app.api.transcribe import router as transcribe_router
from app.api.websocket import router as websocket_router
from app.clients.dashscope_asr_client import DashScopeASRClient
from app.clients.dashscope_client import DashScopeClient
from app.clients.volcengine_asr_client import VolcengineASRClient
from app.core.config import settings
from app.core.logging import configure_logging
from app.services.audio_codec_service import AudioCodecService
from app.services.asr_provider_service import ASRProviderService
from app.services.diarization_service import DiarizationService
from app.services.meeting_history_service import MeetingHistoryService
from app.services.sentiment_analysis_service import SentimentAnalysisService
from app.services.session_manager import SessionManager
from app.services.speaker_service import SpeakerService
from app.services.summary_service import SummaryService
from app.services.translation_service import TranslationService

configure_logging(settings.log_level)
logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    dashscope_asr_client = DashScopeASRClient(settings)
    volcengine_asr_client = VolcengineASRClient(settings)
    dashscope_client = DashScopeClient(settings)
    audio_codec_service = AudioCodecService(settings)
    speaker_service = SpeakerService()
    diarization_service = DiarizationService(settings, speaker_service)
    asr_provider_service = ASRProviderService(
        settings=settings,
        dashscope_client=dashscope_asr_client,
        volcengine_client=volcengine_asr_client,
    )
    summary_service = SummaryService(dashscope_client)
    sentiment_analysis_service = SentimentAnalysisService(dashscope_client)
    translation_service = TranslationService(dashscope_client)
    meeting_history_service = MeetingHistoryService(settings.resolved_meeting_history_db_path)
    session_manager = SessionManager(
        settings=settings,
        asr_provider_service=asr_provider_service,
        audio_codec_service=audio_codec_service,
        speaker_service=speaker_service,
        diarization_service=diarization_service,
        summary_service=summary_service,
        sentiment_analysis_service=sentiment_analysis_service,
        translation_service=translation_service,
        meeting_history_service=meeting_history_service,
    )

    app.state.settings = settings
    app.state.asr_client = dashscope_asr_client
    app.state.dashscope_asr_client = dashscope_asr_client
    app.state.volcengine_asr_client = volcengine_asr_client
    app.state.asr_provider_service = asr_provider_service
    app.state.dashscope_client = dashscope_client
    app.state.audio_codec_service = audio_codec_service
    app.state.speaker_service = speaker_service
    app.state.diarization_service = diarization_service
    app.state.summary_service = summary_service
    app.state.sentiment_analysis_service = sentiment_analysis_service
    app.state.translation_service = translation_service
    app.state.meeting_history_service = meeting_history_service
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
    if translation_service.is_configured:
        logger.info("Using DashScope translation model: %s", settings.dashscope_translation_model)
    if settings.diarization_enabled:
        logger.info("Speaker diarization is enabled with model: %s", settings.diarization_model)
    else:
        logger.info("Speaker diarization is disabled.")

    logger.info("Starting %s %s", settings.service_name, settings.service_version)
    yield
    await dashscope_asr_client.aclose()
    await volcengine_asr_client.aclose()
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

app.include_router(health_router)
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
