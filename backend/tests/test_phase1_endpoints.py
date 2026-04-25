from __future__ import annotations

import asyncio
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.meetings import router as meetings_router
from app.api.transcribe import router as transcribe_router
from app.api.websocket import router as websocket_router
from app.clients.volcengine_asr_client import VolcengineTranscriptSegment
from app.services.asr_provider_service import ASRProviderService
from app.core.config import Settings
from app.schemas.analysis import MeetingAnalysis
from app.schemas.summary import MeetingSummary
from app.schemas.transcript import TranscriptSegment
from app.services.diarization_service import DiarizationResult, DiarizationService, DiarizationTurn
from app.services.meeting_history_service import MeetingHistoryService
from app.services.session_manager import SessionManager
from app.services.speaker_service import SpeakerService
from app.services.upload_meeting_service import UploadMeetingService


class StubAudioCodecService:
    async def convert_upload_to_wav(self, audio_data: bytes, *, filename: str | None, content_type: str | None) -> bytes:
        return audio_data


class FailingAudioCodecService:
    async def convert_upload_to_wav(self, audio_data: bytes, *, filename: str | None, content_type: str | None) -> bytes:
        raise RuntimeError("Audio conversion failed in test")


class StubASRClient:
    def __init__(self, provider_name: str, segments: list[TranscriptSegment], *, is_configured: bool = True) -> None:
        self.provider_name = provider_name
        self._segments = segments
        self.is_configured = is_configured

    async def aclose(self) -> None:
        return

    async def transcribe_wav(self, audio_data: bytes) -> list[TranscriptSegment]:
        return list(self._segments)

    def create_pcm_stream(self, *, on_segment, on_error):
        return StubASRStream(self._segments, on_segment)


class StubASRStream:
    def __init__(self, segments: list[TranscriptSegment], on_segment) -> None:
        self._segments = segments
        self._on_segment = on_segment
        self._sent_count = 0

    async def start(self) -> None:
        return

    async def send_audio(self, audio_chunk: bytes) -> None:
        if self._sent_count >= len(self._segments):
            return
        segment = self._segments[self._sent_count]
        self._sent_count += 1
        await self._on_segment(segment)

    async def finish(self) -> list[TranscriptSegment]:
        return list(self._segments[: self._sent_count])

    async def aclose(self) -> None:
        return


class FailingASRClient(StubASRClient):
    async def transcribe_wav(self, audio_data: bytes) -> list[TranscriptSegment]:
        raise RuntimeError("ASR failed in test")


class StubTranslationService:
    is_configured = False

    def normalize_target_lang(self, target_lang: str | None) -> str | None:
        return None

    async def translate_text(self, *, text: str, target_lang: str) -> str:
        raise AssertionError("Translation should not be called in these tests")


class StubConfiguredTranslationService:
    is_configured = True

    def normalize_target_lang(self, target_lang: str | None) -> str | None:
        if target_lang is None:
            return None
        return target_lang.strip().lower() or None

    async def translate_text(self, *, text: str, target_lang: str) -> str:
        return f"[{target_lang}] {text}"


class StubSummaryService:
    is_configured = True

    async def generate_summary(self, transcripts, scene: str) -> MeetingSummary:
        return MeetingSummary(
            overview="The team reviewed the meeting plan and wrapped with a final follow-up action.",
            key_topics=["Meeting plan", "Follow-up"],
            action_items=[
                {
                    "task": f"Follow up with {transcripts[0].speaker}",
                    "assignee": transcripts[0].speaker,
                    "deadline": "Not specified",
                    "status": "pending",
                    "source_excerpt": transcripts[0].text,
                    "transcript_index": transcripts[0].transcript_index,
                    "is_actionable": True,
                    "confidence": 0.82,
                    "owner_explicit": True,
                    "deadline_explicit": False,
                }
            ]
            if transcripts
            else [],
            decisions=["Finalize diarization"],
            risks=[],
        )


class StubSentimentAnalysisService:
    is_configured = True

    async def analyze_meeting(self, transcripts, scene: str) -> MeetingAnalysis:
        return MeetingAnalysis.empty()


class IncrementingSentimentAnalysisService:
    is_configured = True

    def __init__(self) -> None:
        self.call_count = 0

    async def analyze_meeting(self, transcripts, scene: str) -> MeetingAnalysis:
        self.call_count += 1
        return MeetingAnalysis(
            overall_sentiment="neutral",
            engagement_level="medium",
            engagement_summary=f"Analysis #{self.call_count}",
        )


class SlowSummaryService(StubSummaryService):
    async def generate_summary(self, transcripts, scene: str) -> MeetingSummary:
        await asyncio.sleep(0.05)
        return await super().generate_summary(transcripts, scene)


class SlowSentimentAnalysisService(IncrementingSentimentAnalysisService):
    async def analyze_meeting(self, transcripts, scene: str) -> MeetingAnalysis:
        await asyncio.sleep(0.05)
        return await super().analyze_meeting(transcripts, scene)


class StubDiarizationService(DiarizationService):
    def __init__(self, speaker_service: SpeakerService, result: DiarizationResult) -> None:
        super().__init__(Settings(), speaker_service)
        self._result = result

    async def diarize_audio_bytes(self, audio_data: bytes, *, suffix: str = ".wav") -> DiarizationResult:
        return self._result

    async def diarize_audio_file(self, audio_path) -> DiarizationResult:
        return self._result


def build_turns() -> list[DiarizationTurn]:
    return [
        DiarizationTurn(start=0.0, end=1.2, speaker_label="SPEAKER_00"),
        DiarizationTurn(start=1.2, end=2.5, speaker_label="SPEAKER_01"),
    ]


def build_segments() -> list[TranscriptSegment]:
    return [
        TranscriptSegment(text="Hello team", start=0.0, end=1.0),
        TranscriptSegment(text="Let's finalize the plan", start=1.2, end=2.4),
    ]


def build_three_segments() -> list[TranscriptSegment]:
    return [
        TranscriptSegment(text="Hello team", start=0.0, end=1.0),
        TranscriptSegment(text="Let's finalize the plan", start=1.2, end=2.4),
        TranscriptSegment(text="I will send the update today", start=2.5, end=3.6),
    ]


def build_settings(tmp_path, **overrides) -> Settings:
    return Settings(
        meeting_history_db_path=str(tmp_path / "meeting_history.sqlite3"),
        **overrides,
    )


def build_session_manager(
    tmp_path,
    *,
    speaker_service: SpeakerService,
    dashscope_client: StubASRClient,
    volcengine_client: StubASRClient,
    diarization_service: DiarizationService,
    default_asr_provider: str,
    diarization_mode: str,
    summary_service=None,
    sentiment_analysis_service=None,
    translation_service=None,
) -> tuple[Settings, SessionManager]:
    settings = build_settings(
        tmp_path,
        default_asr_provider=default_asr_provider,
        diarization_mode=diarization_mode,
    )
    return settings, SessionManager(
        settings=settings,
        asr_provider_service=ASRProviderService(
            settings=settings,
            dashscope_client=dashscope_client,
            volcengine_client=volcengine_client,
        ),
        audio_codec_service=StubAudioCodecService(),
        speaker_service=speaker_service,
        diarization_service=diarization_service,
        summary_service=summary_service or StubSummaryService(),
        sentiment_analysis_service=sentiment_analysis_service or StubSentimentAnalysisService(),
        translation_service=translation_service or StubTranslationService(),
        meeting_history_service=MeetingHistoryService(settings.resolved_meeting_history_db_path),
    )


def build_upload_service(
    tmp_path,
    *,
    speaker_service: SpeakerService,
    dashscope_client: StubASRClient,
    volcengine_client: StubASRClient,
    diarization_service: DiarizationService,
    default_asr_provider: str,
    diarization_mode: str,
    audio_codec_service=None,
    summary_service=None,
    sentiment_analysis_service=None,
    translation_service=None,
) -> tuple[Settings, MeetingHistoryService, UploadMeetingService]:
    settings = build_settings(
        tmp_path,
        default_asr_provider=default_asr_provider,
        diarization_mode=diarization_mode,
    )
    meeting_history_service = MeetingHistoryService(settings.resolved_meeting_history_db_path)
    return settings, meeting_history_service, UploadMeetingService(
        asr_provider_service=ASRProviderService(
            settings=settings,
            dashscope_client=dashscope_client,
            volcengine_client=volcengine_client,
        ),
        audio_codec_service=audio_codec_service or StubAudioCodecService(),
        speaker_service=speaker_service,
        diarization_service=diarization_service,
        summary_service=summary_service or StubSummaryService(),
        sentiment_analysis_service=sentiment_analysis_service or StubSentimentAnalysisService(),
        translation_service=translation_service or StubTranslationService(),
        meeting_history_service=meeting_history_service,
    )


def receive_until(websocket, predicate, *, limit: int = 20) -> list[dict]:
    messages = []
    for _ in range(limit):
        message = websocket.receive_json()
        messages.append(message)
        if predicate(messages):
            return messages
    raise AssertionError("Timed out waiting for expected websocket messages")


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


def test_transcribe_batch_returns_final_diarized_speakers() -> None:
    speaker_service = SpeakerService()
    dashscope_client = StubASRClient("dashscope", build_segments())
    volcengine_client = StubASRClient("volcengine", build_segments(), is_configured=False)
    diarization_service = StubDiarizationService(
        speaker_service,
        DiarizationResult(succeeded=True, turns=build_turns()),
    )
    app = FastAPI()
    app.include_router(transcribe_router)
    app.state.audio_codec_service = StubAudioCodecService()
    app.state.asr_provider_service = ASRProviderService(
        settings=Settings(default_asr_provider="dashscope", diarization_mode="offline"),
        dashscope_client=dashscope_client,
        volcengine_client=volcengine_client,
    )
    app.state.speaker_service = speaker_service
    app.state.diarization_service = diarization_service

    with TestClient(app) as client:
        response = client.post(
            "/api/transcribe/batch",
            files={"file": ("meeting.wav", b"fake-audio", "audio/wav")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert [item["transcript_index"] for item in payload] == [0, 1]
    assert [item["speaker"] for item in payload] == ["Speaker 1", "Speaker 2"]
    assert all(item["speaker_is_final"] is True for item in payload)


def test_websocket_finalize_emits_transcripts_then_speaker_updates_then_final_outputs(tmp_path) -> None:
    speaker_service = SpeakerService()
    dashscope_client = StubASRClient("dashscope", build_segments())
    volcengine_client = StubASRClient("volcengine", build_segments(), is_configured=False)
    diarization_service = StubDiarizationService(
        speaker_service,
        DiarizationResult(succeeded=True, turns=build_turns()),
    )
    app = FastAPI()
    app.include_router(meetings_router)
    app.include_router(websocket_router)
    _, session_manager = build_session_manager(
        tmp_path,
        speaker_service=speaker_service,
        dashscope_client=dashscope_client,
        volcengine_client=volcengine_client,
        diarization_service=diarization_service,
        default_asr_provider="dashscope",
        diarization_mode="offline",
    )
    app.state.session_manager = session_manager
    app.state.meeting_history_service = session_manager._meeting_history_service

    with TestClient(app) as client:
        with client.websocket_connect("/ws/meeting?scene=general") as websocket:
            session_started = websocket.receive_json()
            websocket.send_bytes(b"\x00\x00" * 160)
            first = websocket.receive_json()
            websocket.send_bytes(b"\x00\x00" * 160)
            second = websocket.receive_json()

            websocket.send_json({"type": "finalize"})
            third = websocket.receive_json()
            fourth = websocket.receive_json()
            fifth = websocket.receive_json()
            sixth = websocket.receive_json()

        detail_response = client.get(f"/api/meetings/{session_started['data']['meeting_id']}")

    assert session_started["type"] == "session_started"
    assert session_started["data"]["status"] == "draft"
    assert first["type"] == "transcript"
    assert first["data"]["speaker"] == "Unknown"
    assert first["data"]["speaker_is_final"] is False
    assert first["data"]["transcript_index"] == 0

    assert second["type"] == "transcript"
    assert second["data"]["speaker"] == "Unknown"
    assert second["data"]["speaker_is_final"] is False
    assert second["data"]["transcript_index"] == 1

    assert third["type"] == "speaker_update"
    assert third["data"] == {
        "transcript_index": 0,
        "speaker": "Speaker 1",
        "speaker_is_final": True,
    }
    assert fourth["type"] == "speaker_update"
    assert fourth["data"] == {
        "transcript_index": 1,
        "speaker": "Speaker 2",
        "speaker_is_final": True,
    }
    assert fifth["type"] == "analysis"
    assert sixth["type"] == "summary"
    assert sixth["data"]["overview"].startswith("The team reviewed")
    assert sixth["data"]["key_topics"] == ["Meeting plan", "Follow-up"]
    assert sixth["data"]["action_items"][0]["assignee"] == "Speaker 1"
    assert sixth["data"]["action_items"][0]["confidence"] == 0.82
    assert sixth["data"]["action_items"][0]["is_actionable"] is True

    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["status"] == "finalized"
    assert detail_payload["transcript_count"] == 2
    assert detail_payload["summary"]["overview"].startswith("The team reviewed")
    assert [item["speaker"] for item in detail_payload["transcripts"]] == ["Speaker 1", "Speaker 2"]


def test_transcribe_batch_uses_native_volcengine_speaker_info_without_diarization() -> None:
    speaker_service = SpeakerService()
    native_segments = [
        VolcengineTranscriptSegment(
            text="Hello team",
            start=0.0,
            end=1.0,
            speaker="Speaker 1",
            speaker_is_final=True,
        ),
        VolcengineTranscriptSegment(
            text="Let's finalize the plan",
            start=1.2,
            end=2.4,
            speaker="Speaker 2",
            speaker_is_final=True,
        ),
    ]
    dashscope_client = StubASRClient("dashscope", build_segments(), is_configured=False)
    volcengine_client = StubASRClient("volcengine", native_segments)
    diarization_service = StubDiarizationService(
        speaker_service,
        DiarizationResult(succeeded=True, turns=[]),
    )
    app = FastAPI()
    app.include_router(transcribe_router)
    app.state.audio_codec_service = StubAudioCodecService()
    app.state.asr_provider_service = ASRProviderService(
        settings=Settings(default_asr_provider="volcengine", diarization_mode="offline"),
        dashscope_client=dashscope_client,
        volcengine_client=volcengine_client,
    )
    app.state.speaker_service = speaker_service
    app.state.diarization_service = diarization_service

    with TestClient(app) as client:
        response = client.post(
            "/api/transcribe/batch?provider=volcengine",
            files={"file": ("meeting.wav", b"fake-audio", "audio/wav")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert [item["speaker"] for item in payload] == ["Speaker 1", "Speaker 2"]
    assert all(item["speaker_is_final"] is True for item in payload)


def test_websocket_volcengine_partial_transcript_is_updated_in_place(tmp_path) -> None:
    speaker_service = SpeakerService()
    partial_then_final_segments = [
        VolcengineTranscriptSegment(
            text="Hello",
            start=0.0,
            end=0.4,
            speaker="Speaker 1",
            speaker_is_final=False,
            transcript_is_final=False,
        ),
        VolcengineTranscriptSegment(
            text="Hello team",
            start=0.0,
            end=1.0,
            speaker="Speaker 1",
            speaker_is_final=True,
            transcript_is_final=True,
        ),
    ]
    dashscope_client = StubASRClient("dashscope", build_segments(), is_configured=False)
    volcengine_client = StubASRClient("volcengine", partial_then_final_segments)
    app = FastAPI()
    app.include_router(websocket_router)
    _, session_manager = build_session_manager(
        tmp_path,
        speaker_service=speaker_service,
        dashscope_client=dashscope_client,
        volcengine_client=volcengine_client,
        diarization_service=StubDiarizationService(
            speaker_service,
            DiarizationResult(succeeded=False, turns=[]),
        ),
        default_asr_provider="volcengine",
        diarization_mode="disabled",
    )
    app.state.session_manager = session_manager

    with TestClient(app) as client:
        with client.websocket_connect("/ws/meeting?scene=general&provider=volcengine") as websocket:
            session_started = websocket.receive_json()
            websocket.send_bytes(b"\x00\x00" * 160)
            first = websocket.receive_json()
            websocket.send_bytes(b"\x00\x00" * 160)
            second = websocket.receive_json()

            websocket.send_json({"type": "finalize"})
            third = websocket.receive_json()
            fourth = websocket.receive_json()

    assert session_started["type"] == "session_started"
    assert first["type"] == "transcript"
    assert first["data"]["transcript_index"] == 0
    assert first["data"]["text"] == "Hello"
    assert first["data"]["speaker"] == "Speaker 1"
    assert first["data"]["speaker_is_final"] is False
    assert first["data"]["transcript_is_final"] is False

    assert second["type"] == "transcript_update"
    assert second["data"]["transcript_index"] == 0
    assert second["data"]["text"] == "Hello team"
    assert second["data"]["speaker"] == "Speaker 1"
    assert second["data"]["speaker_is_final"] is True
    assert second["data"]["transcript_is_final"] is True

    assert third["type"] == "analysis"
    assert fourth["type"] == "summary"
    assert fourth["data"]["overview"].startswith("The team reviewed")
    assert fourth["data"]["key_topics"] == ["Meeting plan", "Follow-up"]
    assert fourth["data"]["action_items"][0]["is_actionable"] is True


def test_meeting_history_keeps_draft_after_disconnect(tmp_path) -> None:
    speaker_service = SpeakerService()
    dashscope_client = StubASRClient("dashscope", build_segments())
    volcengine_client = StubASRClient("volcengine", build_segments(), is_configured=False)
    app = FastAPI()
    app.include_router(meetings_router)
    app.include_router(websocket_router)
    _, session_manager = build_session_manager(
        tmp_path,
        speaker_service=speaker_service,
        dashscope_client=dashscope_client,
        volcengine_client=volcengine_client,
        diarization_service=StubDiarizationService(
            speaker_service,
            DiarizationResult(succeeded=False, turns=[]),
        ),
        default_asr_provider="dashscope",
        diarization_mode="disabled",
    )
    app.state.session_manager = session_manager
    app.state.meeting_history_service = session_manager._meeting_history_service

    with TestClient(app) as client:
        with client.websocket_connect("/ws/meeting?scene=general") as websocket:
            session_started = websocket.receive_json()
            websocket.send_bytes(b"\x00\x00" * 160)
            first = websocket.receive_json()

        list_response = client.get("/api/meetings")
        detail_response = client.get(f"/api/meetings/{session_started['data']['meeting_id']}")

    assert session_started["type"] == "session_started"
    assert first["type"] == "transcript"
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert len(list_payload) == 1
    assert list_payload[0]["meeting_id"] == session_started["data"]["meeting_id"]
    assert list_payload[0]["status"] == "draft"
    assert list_payload[0]["transcript_count"] == 1
    assert detail_response.status_code == 200
    assert detail_response.json()["status"] == "draft"


def test_meeting_history_persists_translation_latest_analysis_and_delete(tmp_path) -> None:
    speaker_service = SpeakerService()
    dashscope_client = StubASRClient("dashscope", build_three_segments())
    volcengine_client = StubASRClient("volcengine", build_three_segments(), is_configured=False)
    app = FastAPI()
    app.include_router(meetings_router)
    app.include_router(websocket_router)
    _, session_manager = build_session_manager(
        tmp_path,
        speaker_service=speaker_service,
        dashscope_client=dashscope_client,
        volcengine_client=volcengine_client,
        diarization_service=StubDiarizationService(
            speaker_service,
            DiarizationResult(succeeded=False, turns=[]),
        ),
        default_asr_provider="dashscope",
        diarization_mode="disabled",
        translation_service=StubConfiguredTranslationService(),
        sentiment_analysis_service=IncrementingSentimentAnalysisService(),
    )
    app.state.session_manager = session_manager
    app.state.meeting_history_service = session_manager._meeting_history_service

    with TestClient(app) as client:
        with client.websocket_connect("/ws/meeting?scene=general&target_lang=ja") as websocket:
            session_started = websocket.receive_json()

            websocket.send_bytes(b"\x00\x00" * 160)
            websocket.send_bytes(b"\x00\x00" * 160)
            websocket.send_bytes(b"\x00\x00" * 160)

            pre_finalize_messages = receive_until(
                websocket,
                lambda messages: (
                    sum(1 for message in messages if message["type"] == "transcript") == 3
                    and sum(1 for message in messages if message["type"] == "translation") == 3
                    and sum(1 for message in messages if message["type"] == "analysis") >= 1
                ),
            )

            websocket.send_json({"type": "finalize"})
            post_finalize_messages = receive_until(
                websocket,
                lambda messages: any(message["type"] == "summary" for message in messages),
            )

        detail_response = client.get(f"/api/meetings/{session_started['data']['meeting_id']}")
        list_response = client.get("/api/meetings")
        delete_response = client.delete(f"/api/meetings/{session_started['data']['meeting_id']}")
        missing_detail_response = client.get(f"/api/meetings/{session_started['data']['meeting_id']}")

    assert session_started["type"] == "session_started"
    assert sum(1 for message in pre_finalize_messages if message["type"] == "translation") == 3
    assert any(message["type"] == "analysis" for message in pre_finalize_messages)
    assert any(message["type"] == "summary" for message in post_finalize_messages)
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["status"] == "finalized"
    assert detail_payload["analysis"]["engagement_summary"] == "Analysis #2"
    assert detail_payload["transcripts"][0]["translated_text"] == "[ja] Hello team"
    assert detail_payload["transcripts"][0]["translated_target_lang"] == "ja"
    assert list_response.status_code == 200
    assert list_response.json()[0]["preview_text"] == "I will send the update today"
    assert delete_response.status_code == 204
    assert missing_detail_response.status_code == 404


def test_upload_endpoint_creates_processing_record_and_finalizes_with_results(tmp_path) -> None:
    speaker_service = SpeakerService()
    dashscope_client = StubASRClient("dashscope", build_three_segments())
    volcengine_client = StubASRClient("volcengine", build_three_segments(), is_configured=False)
    app = FastAPI()
    app.include_router(meetings_router)
    _, meeting_history_service, upload_meeting_service = build_upload_service(
        tmp_path,
        speaker_service=speaker_service,
        dashscope_client=dashscope_client,
        volcengine_client=volcengine_client,
        diarization_service=StubDiarizationService(
            speaker_service,
            DiarizationResult(succeeded=False, turns=[]),
        ),
        default_asr_provider="dashscope",
        diarization_mode="disabled",
        translation_service=StubConfiguredTranslationService(),
        sentiment_analysis_service=IncrementingSentimentAnalysisService(),
    )
    app.state.meeting_history_service = meeting_history_service
    app.state.upload_meeting_service = upload_meeting_service

    with TestClient(app) as client:
        response = client.post(
            "/api/meetings/upload",
            files={
                "file": ("meeting.wav", b"fake-audio", "audio/wav"),
                "scene": (None, "general"),
                "target_lang": (None, "ja"),
                "provider": (None, "dashscope"),
            },
        )

        assert response.status_code == 202
        initial_payload = response.json()
        assert initial_payload["status"] == "processing"
        assert initial_payload["source_type"] == "upload"
        assert initial_payload["processing_stage"] == "transcribing"
        assert initial_payload["source_name"] == "meeting.wav"

        finalized_payload = wait_for_meeting_status(client, initial_payload["meeting_id"], "finalized")
        list_response = client.get("/api/meetings")

    assert finalized_payload["source_type"] == "upload"
    assert finalized_payload["processing_stage"] is None
    assert finalized_payload["error_message"] is None
    assert finalized_payload["transcript_count"] == 3
    assert finalized_payload["summary"]["overview"].startswith("The team reviewed")
    assert finalized_payload["analysis"]["engagement_summary"] == "Analysis #1"
    assert finalized_payload["transcripts"][0]["translated_text"] == "[ja] Hello team"
    assert finalized_payload["transcripts"][0]["translated_target_lang"] == "ja"
    assert list_response.status_code == 200
    assert list_response.json()[0]["source_type"] == "upload"


def test_upload_detail_polling_returns_partial_results_before_summary(tmp_path) -> None:
    speaker_service = SpeakerService()
    dashscope_client = StubASRClient("dashscope", build_three_segments())
    volcengine_client = StubASRClient("volcengine", build_three_segments(), is_configured=False)
    app = FastAPI()
    app.include_router(meetings_router)
    _, meeting_history_service, upload_meeting_service = build_upload_service(
        tmp_path,
        speaker_service=speaker_service,
        dashscope_client=dashscope_client,
        volcengine_client=volcengine_client,
        diarization_service=StubDiarizationService(
            speaker_service,
            DiarizationResult(succeeded=False, turns=[]),
        ),
        default_asr_provider="dashscope",
        diarization_mode="disabled",
        translation_service=StubConfiguredTranslationService(),
        sentiment_analysis_service=SlowSentimentAnalysisService(),
        summary_service=SlowSummaryService(),
    )
    app.state.meeting_history_service = meeting_history_service
    app.state.upload_meeting_service = upload_meeting_service

    with TestClient(app) as client:
        response = client.post(
            "/api/meetings/upload",
            files={
                "file": ("meeting.wav", b"fake-audio", "audio/wav"),
                "scene": (None, "general"),
                "target_lang": (None, "ja"),
                "provider": (None, "dashscope"),
            },
        )

        assert response.status_code == 202
        meeting_id = response.json()["meeting_id"]

        partial_payload = None
        for _ in range(80):
            detail_response = client.get(f"/api/meetings/{meeting_id}")
            assert detail_response.status_code == 200
            payload = detail_response.json()
            if payload["transcript_count"] > 0 and payload["summary"] is None:
                partial_payload = payload
                break
            time.sleep(0.02)

        finalized_payload = wait_for_meeting_status(client, meeting_id, "finalized")

    assert partial_payload is not None
    assert partial_payload["status"] == "processing"
    assert partial_payload["processing_stage"] in {"translating", "analyzing", "summarizing"}
    assert partial_payload["transcript_count"] == 3
    assert partial_payload["summary"] is None
    assert finalized_payload["summary"] is not None


def test_upload_failure_marks_record_failed_and_keeps_error_message(tmp_path) -> None:
    speaker_service = SpeakerService()
    dashscope_client = FailingASRClient("dashscope", build_segments())
    volcengine_client = StubASRClient("volcengine", build_segments(), is_configured=False)
    app = FastAPI()
    app.include_router(meetings_router)
    _, meeting_history_service, upload_meeting_service = build_upload_service(
        tmp_path,
        speaker_service=speaker_service,
        dashscope_client=dashscope_client,
        volcengine_client=volcengine_client,
        diarization_service=StubDiarizationService(
            speaker_service,
            DiarizationResult(succeeded=False, turns=[]),
        ),
        default_asr_provider="dashscope",
        diarization_mode="disabled",
    )
    app.state.meeting_history_service = meeting_history_service
    app.state.upload_meeting_service = upload_meeting_service

    with TestClient(app) as client:
        response = client.post(
            "/api/meetings/upload",
            files={
                "file": ("meeting.wav", b"fake-audio", "audio/wav"),
                "scene": (None, "general"),
                "target_lang": (None, "en"),
                "provider": (None, "dashscope"),
            },
        )

        assert response.status_code == 202
        failed_payload = wait_for_meeting_status(client, response.json()["meeting_id"], "failed")

    assert failed_payload["source_type"] == "upload"
    assert failed_payload["processing_stage"] is None
    assert failed_payload["summary"] is None
    assert failed_payload["analysis"] is None
    assert failed_payload["error_message"] == "ASR failed in test"


def test_meeting_history_service_migrates_old_schema_and_reconciles_processing_uploads(tmp_path) -> None:
    db_path = tmp_path / "meeting_history.sqlite3"
    connection = MeetingHistoryService(db_path)._connect()
    connection.execute("DROP TABLE meeting_transcripts")
    connection.execute("DROP TABLE meetings")
    connection.execute(
        """
        CREATE TABLE meetings (
            meeting_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            scene TEXT NOT NULL,
            target_lang TEXT,
            provider TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            transcript_count INTEGER NOT NULL DEFAULT 0,
            preview_text TEXT NOT NULL DEFAULT '',
            summary_json TEXT,
            analysis_json TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE meeting_transcripts (
            meeting_id TEXT NOT NULL,
            transcript_index INTEGER NOT NULL,
            speaker TEXT NOT NULL,
            speaker_is_final INTEGER NOT NULL,
            transcript_is_final INTEGER NOT NULL,
            text TEXT NOT NULL,
            start REAL NOT NULL,
            end REAL NOT NULL,
            translated_text TEXT,
            translated_target_lang TEXT,
            PRIMARY KEY (meeting_id, transcript_index)
        )
        """
    )
    connection.execute(
        """
        INSERT INTO meetings (
            meeting_id,
            status,
            scene,
            target_lang,
            provider,
            created_at,
            updated_at,
            transcript_count,
            preview_text,
            summary_json,
            analysis_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
        """,
        (
            "legacy-upload",
            "processing",
            "general",
            "en",
            "dashscope",
            "2026-04-25T00:00:00Z",
            "2026-04-25T00:00:00Z",
            0,
            "",
        ),
    )
    connection.execute(
        "ALTER TABLE meetings ADD COLUMN source_type TEXT NOT NULL DEFAULT 'upload'"
    )
    connection.commit()
    connection.close()

    service = MeetingHistoryService(db_path)
    meeting = service.get_meeting("legacy-upload")
    assert meeting is not None
    assert meeting.status.value == "failed"
    assert meeting.source_type.value == "upload"
    assert meeting.processing_stage is None
    assert meeting.error_message == MeetingHistoryService.INTERRUPTED_UPLOAD_ERROR

    migrated_connection = service._connect()
    migrated_columns = service._get_table_columns(migrated_connection, "meetings")
    migrated_connection.close()
    assert {"source_type", "processing_stage", "error_message", "source_name"}.issubset(migrated_columns)
