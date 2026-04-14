from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.transcribe import router as transcribe_router
from app.api.websocket import router as websocket_router
from app.clients.aliyun_asr_client import AliyunASRClient
from app.clients.dashscope_client import DashScopeClient
from app.core.config import settings
from app.core.logging import configure_logging
from app.services.audio_codec_service import AudioCodecService
from app.services.session_manager import SessionManager
from app.services.speaker_service import SpeakerService
from app.services.summary_service import SummaryService

configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    asr_client = AliyunASRClient(settings)
    dashscope_client = DashScopeClient(settings)
    audio_codec_service = AudioCodecService(settings)
    speaker_service = SpeakerService()
    summary_service = SummaryService(dashscope_client)
    session_manager = SessionManager(
        settings=settings,
        asr_client=asr_client,
        audio_codec_service=audio_codec_service,
        speaker_service=speaker_service,
        summary_service=summary_service,
    )

    app.state.settings = settings
    app.state.asr_client = asr_client
    app.state.dashscope_client = dashscope_client
    app.state.audio_codec_service = audio_codec_service
    app.state.speaker_service = speaker_service
    app.state.summary_service = summary_service
    app.state.session_manager = session_manager

    logger.info("Starting %s %s", settings.service_name, settings.service_version)
    yield
    await asr_client.aclose()
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
app.include_router(transcribe_router)
app.include_router(websocket_router)


@app.get("/")
async def root() -> dict:
    return {
        "service": settings.service_name,
        "version": settings.service_version,
        "status": "running",
    }
