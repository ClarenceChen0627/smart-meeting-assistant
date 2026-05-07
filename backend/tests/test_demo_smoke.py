from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.health import router as health_router
from app.api.meetings import router as meetings_router
from app.api.websocket import router as websocket_router
from app.clients.demo_asr_client import DemoASRClient
from app.clients.demo_dashscope_client import DemoDashScopeClient
from app.core.config import Settings
from app.schemas.transcript import TranscriptSegment
from app.services.asr_provider_service import ASRProviderService
from app.services.diarization_service import DiarizationResult, DiarizationService
from app.services.meeting_analysis_service import MeetingAnalysisService
from app.services.meeting_history_service import MeetingHistoryService
from app.services.session_manager import SessionManager
from app.services.speaker_service import SpeakerService
from app.services.summary_service import SummaryService
from app.services.translation_service import TranslationService
from app.services.upload_meeting_service import UploadMeetingService


pytestmark = pytest.mark.smoke


class FailingAudioCodecService:
    async def convert_upload_to_wav(self, audio_data: bytes, *, filename: str | None, content_type: str | None) -> bytes:
        raise RuntimeError("Audio conversion should not run in demo smoke tests")


class StubASRClient:
    def __init__(self, provider_name: str, *, is_configured: bool = True) -> None:
        self.provider_name = provider_name
        self.is_configured = is_configured

    async def aclose(self) -> None:
        return

    async def transcribe_wav(self, audio_data: bytes) -> list[TranscriptSegment]:
        return []

    def create_pcm_stream(self, *, on_segment, on_error):
        raise AssertionError("Real ASR stream should not be used by demo smoke tests")


class StubDiarizationService(DiarizationService):
    def __init__(self, speaker_service: SpeakerService, settings: Settings) -> None:
        super().__init__(settings, speaker_service)

    async def diarize_audio_bytes(self, audio_data: bytes, *, suffix: str = ".wav") -> DiarizationResult:
        return DiarizationResult(succeeded=True, turns=[])

    async def diarize_audio_file(self, audio_path) -> DiarizationResult:
        return DiarizationResult(succeeded=True, turns=[])


class StubRealtimeDiarizationService:
    def create_session(self, session_id: str):
        raise AssertionError("Realtime diarization should not run for the demo provider")


def build_settings(tmp_path, **overrides) -> Settings:
    values = {
        "meeting_history_db_path": str(tmp_path / "meeting_history.sqlite3"),
        "demo_mode": True,
        "default_asr_provider": "demo",
        "diarization_mode": "disabled",
    }
    values.update(overrides)
    return Settings(**values)


def build_demo_services(tmp_path):
    settings = build_settings(tmp_path)
    demo_asr_client = DemoASRClient(settings)
    demo_llm_client = DemoDashScopeClient(settings)
    speaker_service = SpeakerService()
    asr_provider_service = ASRProviderService(
        settings=settings,
        dashscope_client=StubASRClient("dashscope", is_configured=False),
        volcengine_client=StubASRClient("volcengine", is_configured=False),
        demo_client=demo_asr_client,
    )
    meeting_history_service = MeetingHistoryService(settings.resolved_meeting_history_db_path)
    translation_service = TranslationService(demo_llm_client)
    summary_service = SummaryService(demo_llm_client)
    meeting_analysis_service = MeetingAnalysisService(demo_llm_client)
    return (
        settings,
        speaker_service,
        asr_provider_service,
        translation_service,
        summary_service,
        meeting_analysis_service,
        meeting_history_service,
    )


def receive_until(websocket, predicate, *, limit: int = 20) -> list[dict]:
    messages = []
    for _ in range(limit):
        message = websocket.receive_json()
        messages.append(message)
        if predicate(messages):
            return messages
    raise AssertionError(f"Timed out waiting for demo smoke websocket messages: {messages}")


def wait_for_meeting_status(
    client: TestClient,
    meeting_id: str,
    expected_status: str,
    *,
    attempts: int = 80,
    delay_seconds: float = 0.02,
):
    latest_payload = None
    for _ in range(attempts):
        response = client.get(f"/api/meetings/{meeting_id}")
        assert response.status_code == 200
        latest_payload = response.json()
        if latest_payload["status"] == expected_status:
            return latest_payload
        time.sleep(delay_seconds)
    raise AssertionError(f"Timed out waiting for meeting {meeting_id} to reach {expected_status!r}: {latest_payload}")


def test_demo_health_reports_demo_mode_and_provider(tmp_path) -> None:
    (
        settings,
        _speaker_service,
        asr_provider_service,
        _translation_service,
        _summary_service,
        _meeting_analysis_service,
        _meeting_history_service,
    ) = build_demo_services(tmp_path)
    app = FastAPI()
    app.include_router(health_router)
    app.state.settings = settings
    app.state.asr_provider_service = asr_provider_service

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["demoMode"] is True
    assert "demo" in payload["providers"]["availableAsrProviders"]
    assert any(
        item["provider"] == "demo" and item["configured"] is True
        for item in payload["providers"]["asrProviderStatuses"]
    )


def test_demo_websocket_emits_outputs_and_writes_history(tmp_path) -> None:
    (
        settings,
        speaker_service,
        asr_provider_service,
        translation_service,
        summary_service,
        meeting_analysis_service,
        meeting_history_service,
    ) = build_demo_services(tmp_path)
    app = FastAPI()
    app.include_router(websocket_router)
    app.include_router(meetings_router)
    app.state.session_manager = SessionManager(
        settings=settings,
        asr_provider_service=asr_provider_service,
        audio_codec_service=FailingAudioCodecService(),
        speaker_service=speaker_service,
        diarization_service=StubDiarizationService(speaker_service, settings),
        realtime_diarization_service=StubRealtimeDiarizationService(),
        summary_service=summary_service,
        meeting_analysis_service=meeting_analysis_service,
        translation_service=translation_service,
        meeting_history_service=meeting_history_service,
    )
    app.state.meeting_history_service = meeting_history_service

    with TestClient(app) as client:
        with client.websocket_connect("/ws/meeting?scene=general&target_lang=ja&provider=demo") as websocket:
            session_started = websocket.receive_json()
            websocket.send_bytes(b"demo-audio-1")
            websocket.send_bytes(b"demo-audio-2")
            websocket.send_bytes(b"demo-audio-3")
            live_messages = receive_until(
                websocket,
                lambda items: (
                    sum(1 for item in items if item["type"] == "transcript") == 3
                    and any(item["type"] == "translation" for item in items)
                ),
            )
            websocket.send_json({"type": "finalize"})
            final_messages = receive_until(
                websocket,
                lambda items: (
                    any(item["type"] == "analysis" for item in items)
                    and any(item["type"] == "summary" for item in items)
                ),
            )

        detail_response = client.get(f"/api/meetings/{session_started['data']['meeting_id']}")

    assert session_started["type"] == "session_started"
    assert session_started["data"]["provider"] == "demo"
    assert any(message["type"] == "translation" for message in live_messages)
    assert any(message["type"] == "analysis" for message in final_messages)
    assert any(message["type"] == "summary" for message in final_messages)
    detail_payload = detail_response.json()
    assert detail_payload["provider"] == "demo"
    assert detail_payload["source_type"] == "live"
    assert detail_payload["status"] == "finalized"
    assert detail_payload["transcript_count"] == 3
    assert detail_payload["summary"]["title"] == "Demo Launch Checklist Review"


def test_demo_upload_finalizes_without_ffmpeg_or_external_keys(tmp_path) -> None:
    (
        settings,
        speaker_service,
        asr_provider_service,
        translation_service,
        summary_service,
        meeting_analysis_service,
        meeting_history_service,
    ) = build_demo_services(tmp_path)
    upload_meeting_service = UploadMeetingService(
        asr_provider_service=asr_provider_service,
        audio_codec_service=FailingAudioCodecService(),
        speaker_service=speaker_service,
        diarization_service=StubDiarizationService(speaker_service, settings),
        summary_service=summary_service,
        meeting_analysis_service=meeting_analysis_service,
        translation_service=translation_service,
        meeting_history_service=meeting_history_service,
    )
    app = FastAPI()
    app.include_router(meetings_router)
    app.state.meeting_history_service = meeting_history_service
    app.state.upload_meeting_service = upload_meeting_service

    with TestClient(app) as client:
        response = client.post(
            "/api/meetings/upload",
            data={"scene": "general", "target_lang": "es", "provider": "demo"},
            files={"file": ("demo.wav", b"demo-audio", "audio/wav")},
        )
        assert response.status_code == 202
        payload = response.json()
        finalized_payload = wait_for_meeting_status(client, payload["meeting_id"], "finalized")

    assert finalized_payload["provider"] == "demo"
    assert finalized_payload["source_type"] == "upload"
    assert finalized_payload["transcript_count"] == 3
    assert finalized_payload["transcripts"][0]["translated_target_lang"] == "es"
    assert finalized_payload["summary"]["title"] == "Demo Launch Checklist Review"
    assert finalized_payload["analysis"]["overall_sentiment"] == "mixed"


def test_demo_provider_disabled_does_not_fallback_to_real_provider(tmp_path) -> None:
    settings = build_settings(tmp_path, demo_mode=False, default_asr_provider="volcengine")
    provider_service = ASRProviderService(
        settings=settings,
        dashscope_client=StubASRClient("dashscope", is_configured=True),
        volcengine_client=StubASRClient("volcengine", is_configured=True),
        demo_client=DemoASRClient(settings),
    )

    selection = provider_service.resolve_provider("demo")

    assert selection.provider_name == "demo"
    assert selection.client.is_configured is False
