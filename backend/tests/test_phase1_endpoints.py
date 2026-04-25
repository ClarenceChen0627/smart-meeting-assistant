from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.transcribe import router as transcribe_router
from app.api.websocket import router as websocket_router
from app.clients.volcengine_asr_client import VolcengineTranscriptSegment
from app.services.asr_provider_service import ASRProviderService
from app.core.config import Settings
from app.schemas.analysis import MeetingAnalysis
from app.schemas.summary import MeetingSummary
from app.schemas.transcript import TranscriptSegment
from app.services.diarization_service import DiarizationResult, DiarizationService, DiarizationTurn
from app.services.session_manager import SessionManager
from app.services.speaker_service import SpeakerService


class StubAudioCodecService:
    async def convert_upload_to_wav(self, audio_data: bytes, *, filename: str | None, content_type: str | None) -> bytes:
        return audio_data


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


class StubTranslationService:
    is_configured = False

    def normalize_target_lang(self, target_lang: str | None) -> str | None:
        return None

    async def translate_text(self, *, text: str, target_lang: str) -> str:
        raise AssertionError("Translation should not be called in these tests")


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


def test_websocket_finalize_emits_transcripts_then_speaker_updates_then_final_outputs() -> None:
    speaker_service = SpeakerService()
    dashscope_client = StubASRClient("dashscope", build_segments())
    volcengine_client = StubASRClient("volcengine", build_segments(), is_configured=False)
    diarization_service = StubDiarizationService(
        speaker_service,
        DiarizationResult(succeeded=True, turns=build_turns()),
    )
    app = FastAPI()
    app.include_router(websocket_router)
    app.state.session_manager = SessionManager(
        settings=Settings(default_asr_provider="dashscope", diarization_mode="offline"),
        asr_provider_service=ASRProviderService(
            settings=Settings(default_asr_provider="dashscope", diarization_mode="offline"),
            dashscope_client=dashscope_client,
            volcengine_client=volcengine_client,
        ),
        audio_codec_service=StubAudioCodecService(),
        speaker_service=speaker_service,
        diarization_service=diarization_service,
        summary_service=StubSummaryService(),
        sentiment_analysis_service=StubSentimentAnalysisService(),
        translation_service=StubTranslationService(),
    )

    with TestClient(app) as client:
        with client.websocket_connect("/ws/meeting?scene=general") as websocket:
            websocket.send_bytes(b"\x00\x00" * 160)
            first = websocket.receive_json()
            websocket.send_bytes(b"\x00\x00" * 160)
            second = websocket.receive_json()

            websocket.send_json({"type": "finalize"})
            third = websocket.receive_json()
            fourth = websocket.receive_json()
            fifth = websocket.receive_json()
            sixth = websocket.receive_json()

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


def test_websocket_volcengine_partial_transcript_is_updated_in_place() -> None:
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
    app.state.session_manager = SessionManager(
        settings=Settings(default_asr_provider="volcengine", diarization_mode="disabled"),
        asr_provider_service=ASRProviderService(
            settings=Settings(default_asr_provider="volcengine", diarization_mode="disabled"),
            dashscope_client=dashscope_client,
            volcengine_client=volcengine_client,
        ),
        audio_codec_service=StubAudioCodecService(),
        speaker_service=speaker_service,
        diarization_service=StubDiarizationService(
            speaker_service,
            DiarizationResult(succeeded=False, turns=[]),
        ),
        summary_service=StubSummaryService(),
        sentiment_analysis_service=StubSentimentAnalysisService(),
        translation_service=StubTranslationService(),
    )

    with TestClient(app) as client:
        with client.websocket_connect("/ws/meeting?scene=general&provider=volcengine") as websocket:
            websocket.send_bytes(b"\x00\x00" * 160)
            first = websocket.receive_json()
            websocket.send_bytes(b"\x00\x00" * 160)
            second = websocket.receive_json()

            websocket.send_json({"type": "finalize"})
            third = websocket.receive_json()
            fourth = websocket.receive_json()

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
