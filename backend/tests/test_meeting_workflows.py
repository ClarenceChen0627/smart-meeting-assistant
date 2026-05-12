from __future__ import annotations

import asyncio
import sqlite3
import time
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.audit import router as audit_router
from app.api.diagnostics import router as diagnostics_router
from app.api.health import router as health_router
from app.api.meetings import router as meetings_router
from app.api.transcribe import router as transcribe_router
from app.api.websocket import router as websocket_router
from app.clients.demo_asr_client import DemoASRClient
from app.clients.demo_dashscope_client import DemoDashScopeClient
from app.clients.volcengine_asr_client import VolcengineTranscriptSegment
from app.services.asr_provider_service import ASRProviderService
from app.services.audit_log_service import AuditLogService
from app.core.config import Settings
from app.schemas.analysis import MeetingAnalysis, MeetingAnalysisHighlight, MeetingSignalCounts, ParticipantAnalysis
from app.schemas.glossary import GlossaryTermCreate
from app.schemas.meeting_history import MeetingHistoryStatus, MeetingProcessingStage, MeetingSourceType
from app.schemas.summary import MeetingSummary
from app.schemas.transcript import TranscriptItem, TranscriptSegment
from app.services.diarization_service import DiarizationResult, DiarizationService, DiarizationTurn
from app.services.glossary_service import GlossaryService
from app.services.glossary_store_service import GlossaryStoreService
from app.services.meeting_history_service import MeetingHistoryService
from app.services.meeting_analysis_service import MeetingAnalysisService
from app.services.observability_service import ObservabilityService
from app.services.raw_audio_retention_service import RawAudioRetentionService
from app.services.session_manager import SessionManager
from app.services.speaker_service import SpeakerService
from app.services.summary_service import SummaryService
from app.services.translation_service import TranslationService
from app.services.upload_meeting_service import UploadMeetingService
from app.services.upload_queue_service import UploadJobStatus, UploadQueueStore, UploadQueueWorker
from app.middleware.observability import observability_middleware


class StubAudioCodecService:
    async def convert_upload_to_wav(self, audio_data: bytes, *, filename: str | None, content_type: str | None) -> bytes:
        return audio_data


class FailingAudioCodecService:
    async def convert_upload_to_wav(self, audio_data: bytes, *, filename: str | None, content_type: str | None) -> bytes:
        raise RuntimeError("Audio conversion failed in test")


class CountingFailingAudioCodecService(FailingAudioCodecService):
    def __init__(self) -> None:
        self.call_count = 0

    async def convert_upload_to_wav(self, audio_data: bytes, *, filename: str | None, content_type: str | None) -> bytes:
        self.call_count += 1
        return await super().convert_upload_to_wav(
            audio_data,
            filename=filename,
            content_type=content_type,
        )


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


class FailingStartASRClient(StubASRClient):
    def create_pcm_stream(self, *, on_segment, on_error):
        raise RuntimeError("ASR stream start failed in test")


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


class FlakyASRClient(StubASRClient):
    def __init__(
        self,
        provider_name: str,
        segments: list[TranscriptSegment],
        *,
        failures_before_success: int = 1,
        is_configured: bool = True,
    ) -> None:
        super().__init__(provider_name, segments, is_configured=is_configured)
        self.failures_before_success = failures_before_success
        self.call_count = 0

    async def transcribe_wav(self, audio_data: bytes) -> list[TranscriptSegment]:
        self.call_count += 1
        if self.call_count <= self.failures_before_success:
            raise RuntimeError("Transient ASR failure in test")
        return await super().transcribe_wav(audio_data)


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

    async def generate_summary(self, transcripts, scene: str, *, glossary_terms=None) -> MeetingSummary:
        return MeetingSummary(
            title="Meeting plan follow-up",
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


class CountingSummaryService(StubSummaryService):
    def __init__(self) -> None:
        self.call_count = 0
        self.transcript_counts: list[int] = []

    async def generate_summary(self, transcripts, scene: str, *, glossary_terms=None) -> MeetingSummary:
        self.call_count += 1
        self.transcript_counts.append(len(transcripts))
        summary = await super().generate_summary(transcripts, scene, glossary_terms=glossary_terms)
        return summary.model_copy(
            update={
                "overview": f"Summary #{self.call_count} over {len(transcripts)} transcripts.",
            }
        )


class StubMeetingAnalysisService:
    is_configured = True

    async def analyze_meeting(self, transcripts, scene: str, *, glossary_terms=None) -> MeetingAnalysis:
        return MeetingAnalysis.empty()


class IncrementingMeetingAnalysisService:
    is_configured = True

    def __init__(self) -> None:
        self.call_count = 0

    async def analyze_meeting(self, transcripts, scene: str, *, glossary_terms=None) -> MeetingAnalysis:
        self.call_count += 1
        return MeetingAnalysis(
            overall_sentiment="neutral",
            engagement_level="medium",
            engagement_summary=f"Analysis #{self.call_count}",
        )


class SlowSummaryService(StubSummaryService):
    async def generate_summary(self, transcripts, scene: str, *, glossary_terms=None) -> MeetingSummary:
        await asyncio.sleep(0.05)
        return await super().generate_summary(transcripts, scene, glossary_terms=glossary_terms)


class FlakySummaryService(StubSummaryService):
    def __init__(self, *, failures_before_success: int = 1) -> None:
        self.failures_before_success = failures_before_success
        self.call_count = 0

    async def generate_summary(self, transcripts, scene: str, *, glossary_terms=None) -> MeetingSummary:
        self.call_count += 1
        if self.call_count <= self.failures_before_success:
            raise RuntimeError("Transient summary failure in test")
        return await super().generate_summary(transcripts, scene, glossary_terms=glossary_terms)


class SlowMeetingAnalysisService(IncrementingMeetingAnalysisService):
    async def analyze_meeting(self, transcripts, scene: str, *, glossary_terms=None) -> MeetingAnalysis:
        await asyncio.sleep(0.05)
        return await super().analyze_meeting(transcripts, scene, glossary_terms=glossary_terms)


class FlakyMeetingAnalysisService(StubMeetingAnalysisService):
    def __init__(self, *, failures_before_success: int = 1) -> None:
        self.failures_before_success = failures_before_success
        self.call_count = 0

    async def analyze_meeting(self, transcripts, scene: str, *, glossary_terms=None) -> MeetingAnalysis:
        self.call_count += 1
        if self.call_count <= self.failures_before_success:
            raise RuntimeError("Transient analysis failure in test")
        return await super().analyze_meeting(transcripts, scene, glossary_terms=glossary_terms)


class StubDiarizationService(DiarizationService):
    def __init__(self, speaker_service: SpeakerService, result: DiarizationResult) -> None:
        super().__init__(Settings(), speaker_service)
        self._result = result

    async def diarize_audio_bytes(self, audio_data: bytes, *, suffix: str = ".wav") -> DiarizationResult:
        return self._result

    async def diarize_audio_file(self, audio_path) -> DiarizationResult:
        return self._result


class StubRealtimeDiarizationSession:
    def __init__(self, turn_batches: list[list[DiarizationTurn]]) -> None:
        self._turn_batches = turn_batches
        self._batch_index = 0
        self.closed = False

    async def process_audio(self, audio_chunk: bytes) -> list[DiarizationTurn]:
        if self._batch_index >= len(self._turn_batches):
            return []
        turns = self._turn_batches[self._batch_index]
        self._batch_index += 1
        return turns

    async def finish(self) -> list[DiarizationTurn]:
        return []

    async def aclose(self) -> None:
        self.closed = True


class StubRealtimeDiarizationService:
    def __init__(self, turn_batches: list[list[DiarizationTurn]] | None = None) -> None:
        self._turn_batches = turn_batches or []
        self.created_sessions: list[StubRealtimeDiarizationSession] = []

    def create_session(self, session_id: str) -> StubRealtimeDiarizationSession:
        session = StubRealtimeDiarizationSession(self._turn_batches)
        self.created_sessions.append(session)
        return session


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


def build_six_segments() -> list[TranscriptSegment]:
    return [
        TranscriptSegment(text=f"Agenda item {index}", start=float(index), end=float(index) + 0.8)
        for index in range(6)
    ]


def build_settings(tmp_path, **overrides) -> Settings:
    return Settings(
        meeting_history_db_path=str(tmp_path / "meeting_history.sqlite3"),
        raw_audio_dir=str(tmp_path / "raw_audio"),
        upload_queue_dir=str(tmp_path / "upload_queue"),
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
    meeting_analysis_service=None,
    translation_service=None,
    realtime_diarization_service=None,
    glossary_store_service=None,
    observability_service=None,
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
        realtime_diarization_service=realtime_diarization_service or StubRealtimeDiarizationService(),
        summary_service=summary_service or StubSummaryService(),
        meeting_analysis_service=meeting_analysis_service or StubMeetingAnalysisService(),
        translation_service=translation_service or StubTranslationService(),
        meeting_history_service=MeetingHistoryService(settings.resolved_meeting_history_db_path),
        glossary_service=GlossaryService(settings, glossary_store_service),
        observability_service=observability_service,
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
    meeting_analysis_service=None,
    translation_service=None,
    glossary_store_service=None,
    embedded_worker_enabled: bool = True,
    upload_queue_max_attempts: int = 1,
    upload_queue_retry_base_seconds: float = 0,
    upload_queue_retry_max_seconds: float = 0,
    upload_queue_processing_timeout_seconds: float = 1800,
    observability_service=None,
) -> tuple[Settings, MeetingHistoryService, UploadMeetingService]:
    settings = build_settings(
        tmp_path,
        default_asr_provider=default_asr_provider,
        diarization_mode=diarization_mode,
        upload_queue_max_attempts=upload_queue_max_attempts,
        upload_queue_retry_base_seconds=upload_queue_retry_base_seconds,
        upload_queue_retry_max_seconds=upload_queue_retry_max_seconds,
        upload_queue_processing_timeout_seconds=upload_queue_processing_timeout_seconds,
    )
    meeting_history_service = MeetingHistoryService(settings.resolved_meeting_history_db_path)
    upload_queue_store = UploadQueueStore(
        db_path=settings.resolved_meeting_history_db_path,
        queue_dir=settings.resolved_upload_queue_dir,
        max_attempts=settings.upload_queue_max_attempts,
        retry_base_seconds=settings.upload_queue_retry_base_seconds,
        retry_max_seconds=settings.upload_queue_retry_max_seconds,
    )
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
        meeting_analysis_service=meeting_analysis_service or StubMeetingAnalysisService(),
        translation_service=translation_service or StubTranslationService(),
        meeting_history_service=meeting_history_service,
        glossary_service=GlossaryService(settings, glossary_store_service),
        raw_audio_retention_service=RawAudioRetentionService(settings),
        upload_queue_store=upload_queue_store,
        embedded_worker_enabled=embedded_worker_enabled,
        upload_queue_processing_timeout_seconds=settings.upload_queue_processing_timeout_seconds,
        observability_service=observability_service,
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


class StubProviderStatusService:
    def provider_statuses(self):
        return [{"provider": "demo", "configured": True}]


def test_observability_middleware_generates_and_reuses_request_id(tmp_path) -> None:
    app = FastAPI()
    app.middleware("http")(observability_middleware)
    app.state.observability_service = ObservabilityService()

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    with TestClient(app) as client:
        generated_response = client.get("/ping")
        supplied_response = client.get("/ping", headers={"X-Request-ID": "manual-request-id"})

    assert generated_response.status_code == 200
    assert generated_response.headers["X-Request-ID"]
    assert supplied_response.headers["X-Request-ID"] == "manual-request-id"
    snapshot = app.state.observability_service.snapshot(
        service_name="test",
        service_version="0",
        demo_mode=True,
        provider_statuses=[],
        upload_queue={},
    )
    assert snapshot["requests"]["total"] == 2
    assert snapshot["requests"]["byStatus"]["200"] == 2


def test_diagnostics_returns_runtime_counters_and_queue_summary_without_paths(tmp_path) -> None:
    settings = build_settings(tmp_path, demo_mode=True)
    observability_service = ObservabilityService()
    observability_service.record_provider_operation(
        operation="upload_asr",
        provider="demo",
        latency_seconds=0.25,
        success=True,
    )
    upload_queue_store = UploadQueueStore(
        db_path=settings.resolved_meeting_history_db_path,
        queue_dir=settings.resolved_upload_queue_dir,
    )
    upload_queue_store.enqueue_upload(
        meeting_id="queued-meeting",
        audio_data=b"queued-audio",
        filename="meeting.wav",
        content_type="audio/wav",
        scene="general",
        target_lang=None,
        provider="demo",
        glossary_terms=[],
    )
    app = FastAPI()
    app.middleware("http")(observability_middleware)
    app.include_router(diagnostics_router)
    app.state.settings = settings
    app.state.observability_service = observability_service
    app.state.upload_queue_store = upload_queue_store
    app.state.asr_provider_service = StubProviderStatusService()

    with TestClient(app) as client:
        response = client.get("/api/diagnostics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service"]["name"] == settings.service_name
    assert payload["service"]["demoMode"] is True
    assert payload["providers"]["statuses"] == [{"provider": "demo", "configured": True}]
    assert payload["providers"]["operations"][0]["operation"] == "upload_asr"
    assert payload["uploadQueue"]["byStatus"]["queued"] == 1
    assert payload["uploadQueue"]["eligibleQueued"] == 1
    assert str(tmp_path) not in response.text


def test_audit_service_filters_meeting_and_global_events(tmp_path) -> None:
    audit_service = AuditLogService(tmp_path / "meeting_history.sqlite3")
    audit_service.record_event(
        scope=AuditLogService.SCOPE_MEETING,
        meeting_id="meeting-1",
        entity_type="meeting",
        entity_id="meeting-1",
        action="update",
        field_path="title",
        before="Old",
        after="New",
    )
    audit_service.record_event(
        scope=AuditLogService.SCOPE_GLOBAL,
        entity_type="glossary_term",
        entity_id="term-1",
        action="create",
        after={"term": "Qwen"},
    )

    meeting_events = audit_service.list_meeting_events("meeting-1")
    global_events = audit_service.list_events(scope=AuditLogService.SCOPE_GLOBAL, entity_type="glossary_term")

    assert len(meeting_events) == 1
    assert meeting_events[0].meeting_id == "meeting-1"
    assert meeting_events[0].before == "Old"
    assert meeting_events[0].after == "New"
    assert len(global_events) == 1
    assert global_events[0].scope == "global"


def test_meeting_edit_endpoints_write_audit_events(tmp_path) -> None:
    meeting_history_service = MeetingHistoryService(tmp_path / "meeting_history.sqlite3")
    audit_service = AuditLogService(tmp_path / "meeting_history.sqlite3")
    meeting_history_service.create_meeting(
        meeting_id="meeting-audit",
        scene="general",
        target_lang=None,
        provider="dashscope",
    )
    meeting_history_service.upsert_transcript(
        "meeting-audit",
        TranscriptItem(
            transcript_index=0,
            speaker="Speaker 1",
            speaker_is_final=True,
            transcript_is_final=True,
            text="I will send the update today",
            start=0,
            end=1,
        ),
    )
    meeting_history_service.upsert_transcript(
        "meeting-audit",
        TranscriptItem(
            transcript_index=1,
            speaker="Speaker 2",
            speaker_is_final=True,
            transcript_is_final=True,
            text="Thanks",
            start=1,
            end=2,
        ),
    )
    meeting_history_service.update_summary(
        "meeting-audit",
        MeetingSummary(
            title="Original title",
            overview="Original overview",
            key_topics=["Planning"],
            action_items=[
                {
                    "task": "Send the update",
                    "assignee": "Speaker 1",
                    "deadline": "today",
                    "status": "pending",
                    "source_excerpt": "I will send the update today",
                    "transcript_index": 0,
                    "is_actionable": True,
                    "confidence": 0.9,
                    "owner_explicit": True,
                    "deadline_explicit": True,
                }
            ],
            decisions=[],
            risks=[],
        ),
    )
    app = FastAPI()
    app.include_router(meetings_router)
    app.include_router(audit_router)
    app.state.meeting_history_service = meeting_history_service
    app.state.audit_log_service = audit_service

    with TestClient(app) as client:
        title_response = client.patch("/api/meetings/meeting-audit/title", json={"title": "Renamed meeting"})
        summary_response = client.patch(
            "/api/meetings/meeting-audit/summary",
            json={
                "overview": "Edited overview",
                "key_topics": ["Planning", "Launch"],
                "action_items": title_response.json()["summary"]["action_items"],
                "decisions": ["Ship"],
                "risks": [],
            },
        )
        action_response = client.patch(
            "/api/meetings/meeting-audit/action-items/0",
            json={"status": "completed"},
        )
        speaker_response = client.patch(
            "/api/meetings/meeting-audit/speakers",
            json={"speaker_updates": [{"from": "Speaker 1", "to": "Alice"}]},
        )
        metadata_response = client.patch(
            "/api/meetings/meeting-audit/metadata",
            json={"favorite": True, "archived": False, "tags": ["Launch", "Launch", "Q2"]},
        )
        audit_response = client.get("/api/meetings/meeting-audit/audit-events")
        missing_response = client.patch("/api/meetings/missing/title", json={"title": "Nope"})

    assert title_response.status_code == 200
    assert summary_response.status_code == 200
    assert action_response.status_code == 200
    assert speaker_response.status_code == 200
    assert metadata_response.status_code == 200
    assert missing_response.status_code == 404
    assert audit_response.status_code == 200
    events = audit_response.json()
    assert {event["entity_type"] for event in events} == {"speaker", "action_item", "summary", "meeting"}
    title_event = next(event for event in events if event["field_path"] == "title")
    assert title_event["before"] == "Original title"
    assert title_event["after"] == "Renamed meeting"
    speaker_event = next(event for event in events if event["entity_type"] == "speaker")
    assert speaker_event["metadata"]["affected_transcript_count"] == 1
    metadata_event = next(event for event in events if event["field_path"] == "metadata")
    assert metadata_event["before"] == {"favorite": False, "archived": False, "tags": []}
    assert metadata_event["after"] == {"favorite": True, "archived": False, "tags": ["Launch", "Q2"]}
    assert metadata_event["metadata"]["updated_fields"] == ["archived", "favorite", "tags"]
    assert len(audit_service.list_events(meeting_id="missing")) == 0


def test_delete_meeting_writes_compact_audit_event(tmp_path) -> None:
    meeting_history_service = MeetingHistoryService(tmp_path / "meeting_history.sqlite3")
    audit_service = AuditLogService(tmp_path / "meeting_history.sqlite3")
    meeting_history_service.create_meeting(
        meeting_id="meeting-delete",
        scene="general",
        target_lang=None,
        provider="dashscope",
    )
    meeting_history_service.upsert_transcript(
        "meeting-delete",
        TranscriptItem(
            transcript_index=0,
            speaker="Speaker 1",
            speaker_is_final=True,
            transcript_is_final=True,
            text="We can delete this test meeting.",
            start=0,
            end=1,
        ),
    )
    meeting_history_service.update_title("meeting-delete", "Delete audit check")

    app = FastAPI()
    app.include_router(meetings_router)
    app.include_router(audit_router)
    app.state.meeting_history_service = meeting_history_service
    app.state.audit_log_service = audit_service

    with TestClient(app) as client:
        delete_response = client.delete("/api/meetings/meeting-delete")
        audit_response = client.get("/api/audit-events?meeting_id=meeting-delete")

    assert delete_response.status_code == 204
    assert audit_response.status_code == 200
    events = audit_response.json()
    assert len(events) == 1
    delete_event = events[0]
    assert delete_event["action"] == "delete"
    assert delete_event["entity_type"] == "meeting"
    assert delete_event["before"] == {
        "title": "Delete audit check",
        "status": "draft",
        "source_type": "live",
        "transcript_count": 1,
        "raw_audio_retained": False,
    }
    assert delete_event["after"] is None
    assert delete_event["metadata"] == {"manual": True}


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
    assert detail_payload["title"] == "Meeting plan follow-up"
    assert detail_payload["transcript_count"] == 2
    assert detail_payload["summary"]["overview"].startswith("The team reviewed")
    assert [item["speaker"] for item in detail_payload["transcripts"]] == ["Speaker 1", "Speaker 2"]


def test_live_asr_fallback_records_provider_operation_metrics(tmp_path) -> None:
    speaker_service = SpeakerService()
    dashscope_client = StubASRClient("dashscope", build_segments())
    volcengine_client = FailingStartASRClient("volcengine", build_segments())
    diarization_service = StubDiarizationService(
        speaker_service,
        DiarizationResult(succeeded=False, turns=[]),
    )
    observability_service = ObservabilityService()
    app = FastAPI()
    app.include_router(websocket_router)
    _, session_manager = build_session_manager(
        tmp_path,
        speaker_service=speaker_service,
        dashscope_client=dashscope_client,
        volcengine_client=volcengine_client,
        diarization_service=diarization_service,
        default_asr_provider="volcengine",
        diarization_mode="disabled",
        observability_service=observability_service,
    )
    app.state.session_manager = session_manager

    with TestClient(app) as client:
        with client.websocket_connect("/ws/meeting?scene=general&provider=volcengine") as websocket:
            websocket.receive_json()
            websocket.send_bytes(b"\x00\x00" * 160)
            receive_until(websocket, lambda messages: any(message["type"] == "transcript" for message in messages))
            websocket.send_json({"type": "finalize"})

    snapshot = observability_service.snapshot(
        service_name="test",
        service_version="0",
        demo_mode=False,
        provider_statuses=[],
        upload_queue={},
    )
    metrics = {
        (item["operation"], item["provider"]): item
        for item in snapshot["providers"]["operations"]
    }
    assert metrics[("live_asr_start", "volcengine")]["error_count"] == 1
    assert metrics[("live_asr_fallback", "dashscope")]["count"] == 1


def test_websocket_hybrid_emits_realtime_speaker_updates_before_final_pyannote(tmp_path) -> None:
    speaker_service = SpeakerService()
    dashscope_client = StubASRClient("dashscope", build_segments())
    volcengine_client = StubASRClient("volcengine", build_segments(), is_configured=False)
    realtime_diarization_service = StubRealtimeDiarizationService(
        [
            [DiarizationTurn(start=0.0, end=1.0, speaker_label="REALTIME_A")],
            [DiarizationTurn(start=1.2, end=2.4, speaker_label="REALTIME_B")],
        ]
    )
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
        realtime_diarization_service=realtime_diarization_service,
        default_asr_provider="dashscope",
        diarization_mode="hybrid",
    )
    app.state.session_manager = session_manager
    app.state.meeting_history_service = session_manager._meeting_history_service

    with TestClient(app) as client:
        with client.websocket_connect("/ws/meeting?scene=general&provider=dashscope") as websocket:
            session_started = websocket.receive_json()
            websocket.send_bytes(b"\x00\x00" * 160)
            websocket.send_bytes(b"\x00\x00" * 160)
            realtime_messages = receive_until(
                websocket,
                lambda messages: sum(
                    1
                    for message in messages
                    if message["type"] == "speaker_update"
                    and message["data"]["speaker_is_final"] is False
                )
                == 2,
            )

            websocket.send_json({"type": "finalize"})
            final_messages = receive_until(
                websocket,
                lambda messages: sum(
                    1
                    for message in messages
                    if message["type"] == "speaker_update"
                    and message["data"]["speaker_is_final"] is True
                )
                == 2
                and any(message["type"] == "summary" for message in messages),
            )

        detail_response = client.get(f"/api/meetings/{session_started['data']['meeting_id']}")

    assert len(realtime_diarization_service.created_sessions) == 1
    realtime_updates = [
        message["data"]
        for message in realtime_messages
        if message["type"] == "speaker_update"
        and message["data"]["speaker_is_final"] is False
    ]
    assert [item["speaker"] for item in realtime_updates] == ["Speaker 1", "Speaker 2"]
    final_updates = [
        message["data"]
        for message in final_messages
        if message["type"] == "speaker_update"
        and message["data"]["speaker_is_final"] is True
    ]
    assert [item["speaker"] for item in final_updates] == ["Speaker 1", "Speaker 2"]
    assert detail_response.status_code == 200
    assert all(item["speaker_is_final"] is True for item in detail_response.json()["transcripts"])


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
        meeting_analysis_service=IncrementingMeetingAnalysisService(),
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
    assert list_response.json()[0]["title"] == "Meeting plan follow-up"
    assert list_response.json()[0]["preview_text"].startswith("The team reviewed")
    assert delete_response.status_code == 204
    assert missing_detail_response.status_code == 404


def test_live_rolling_summary_emits_without_persisting_until_finalize(tmp_path) -> None:
    speaker_service = SpeakerService()
    dashscope_client = StubASRClient("dashscope", build_three_segments())
    volcengine_client = StubASRClient("volcengine", build_three_segments(), is_configured=False)
    summary_service = CountingSummaryService()
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
        summary_service=summary_service,
    )
    app.state.session_manager = session_manager
    app.state.meeting_history_service = session_manager._meeting_history_service

    with TestClient(app) as client:
        with client.websocket_connect("/ws/meeting?scene=general&provider=dashscope") as websocket:
            session_started = websocket.receive_json()
            websocket.send_bytes(b"\x00\x00" * 160)
            websocket.send_bytes(b"\x00\x00" * 160)
            websocket.send_bytes(b"\x00\x00" * 160)

            live_messages = receive_until(
                websocket,
                lambda messages: (
                    sum(1 for message in messages if message["type"] == "transcript") == 3
                    and any(message["type"] == "rolling_summary" for message in messages)
                ),
            )
            draft_detail_response = client.get(f"/api/meetings/{session_started['data']['meeting_id']}")

            websocket.send_json({"type": "finalize"})
            final_messages = receive_until(
                websocket,
                lambda messages: any(message["type"] == "summary" for message in messages),
            )

        finalized_detail_response = client.get(f"/api/meetings/{session_started['data']['meeting_id']}")

    rolling_summary = next(message for message in live_messages if message["type"] == "rolling_summary")
    final_summary = next(message for message in final_messages if message["type"] == "summary")
    assert rolling_summary["data"]["overview"] == "Summary #1 over 3 transcripts."
    assert final_summary["data"]["overview"] == "Summary #2 over 3 transcripts."
    assert summary_service.transcript_counts == [3, 3]

    assert draft_detail_response.status_code == 200
    draft_payload = draft_detail_response.json()
    assert draft_payload["status"] == "draft"
    assert draft_payload["summary"] is None

    assert finalized_detail_response.status_code == 200
    finalized_payload = finalized_detail_response.json()
    assert finalized_payload["status"] == "finalized"
    assert finalized_payload["summary"]["overview"] == "Summary #2 over 3 transcripts."


def test_live_rolling_summary_requires_three_new_transcripts_and_sixty_seconds(tmp_path, monkeypatch) -> None:
    clock = {"now": 100.0}

    speaker_service = SpeakerService()
    dashscope_client = StubASRClient("dashscope", build_six_segments())
    volcengine_client = StubASRClient("volcengine", build_six_segments(), is_configured=False)
    summary_service = CountingSummaryService()
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
        summary_service=summary_service,
    )
    app.state.session_manager = session_manager
    app.state.meeting_history_service = session_manager._meeting_history_service
    monkeypatch.setattr(session_manager, "_monotonic", lambda: clock["now"])

    with TestClient(app) as client:
        with client.websocket_connect("/ws/meeting?scene=general&provider=dashscope") as websocket:
            websocket.receive_json()
            for _ in range(3):
                websocket.send_bytes(b"\x00\x00" * 160)
            receive_until(
                websocket,
                lambda messages: any(message["type"] == "rolling_summary" for message in messages),
            )

            for _ in range(3):
                websocket.send_bytes(b"\x00\x00" * 160)
            messages_before_sixty_seconds = receive_until(
                websocket,
                lambda messages: sum(1 for message in messages if message["type"] == "transcript") == 3,
            )

            websocket.send_json({"type": "finalize"})
            receive_until(websocket, lambda messages: any(message["type"] == "summary" for message in messages))

    assert not any(message["type"] == "rolling_summary" for message in messages_before_sixty_seconds)
    assert summary_service.transcript_counts == [3, 6]


def test_live_rolling_summary_allows_next_window_after_sixty_seconds(tmp_path, monkeypatch) -> None:
    clock = {"now": 100.0}

    speaker_service = SpeakerService()
    dashscope_client = StubASRClient("dashscope", build_six_segments())
    volcengine_client = StubASRClient("volcengine", build_six_segments(), is_configured=False)
    summary_service = CountingSummaryService()
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
        summary_service=summary_service,
    )
    app.state.session_manager = session_manager
    app.state.meeting_history_service = session_manager._meeting_history_service
    monkeypatch.setattr(session_manager, "_monotonic", lambda: clock["now"])

    with TestClient(app) as client:
        with client.websocket_connect("/ws/meeting?scene=general&provider=dashscope") as websocket:
            websocket.receive_json()
            for _ in range(3):
                websocket.send_bytes(b"\x00\x00" * 160)
            first_window_messages = receive_until(
                websocket,
                lambda messages: any(message["type"] == "rolling_summary" for message in messages),
            )

            clock["now"] = 161.0
            for _ in range(3):
                websocket.send_bytes(b"\x00\x00" * 160)
            second_window_messages = receive_until(
                websocket,
                lambda messages: any(message["type"] == "rolling_summary" for message in messages),
            )

            websocket.send_json({"type": "finalize"})
            final_messages = receive_until(
                websocket,
                lambda messages: any(message["type"] == "summary" for message in messages),
            )

    first_rolling = next(message for message in first_window_messages if message["type"] == "rolling_summary")
    second_rolling = next(message for message in second_window_messages if message["type"] == "rolling_summary")
    final_summary = next(message for message in final_messages if message["type"] == "summary")
    assert first_rolling["data"]["overview"] == "Summary #1 over 3 transcripts."
    assert second_rolling["data"]["overview"] == "Summary #2 over 6 transcripts."
    assert final_summary["data"]["overview"] == "Summary #3 over 6 transcripts."
    assert summary_service.transcript_counts == [3, 6, 6]


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
        meeting_analysis_service=IncrementingMeetingAnalysisService(),
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
    assert finalized_payload["title"] == "Meeting plan follow-up"
    assert finalized_payload["processing_stage"] is None
    assert finalized_payload["error_message"] is None
    assert finalized_payload["transcript_count"] == 3
    assert finalized_payload["summary"]["overview"].startswith("The team reviewed")
    assert finalized_payload["analysis"]["engagement_summary"] == "Analysis #1"
    assert finalized_payload["transcripts"][0]["translated_text"] == "[ja] Hello team"
    assert finalized_payload["transcripts"][0]["translated_target_lang"] == "ja"
    assert list_response.status_code == 200
    assert list_response.json()[0]["source_type"] == "upload"
    assert list_response.json()[0]["title"] == "Meeting plan follow-up"


def test_upload_can_retain_raw_audio_and_apply_glossary(tmp_path) -> None:
    speaker_service = SpeakerService()
    dashscope_client = StubASRClient(
        "dashscope",
        [
            TranscriptSegment(text="queue wen roadmap is ready", start=0.0, end=1.0),
            TranscriptSegment(text="I agree with the launch plan", start=1.2, end=2.2),
        ],
    )
    volcengine_client = StubASRClient("volcengine", [], is_configured=False)
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
        meeting_analysis_service=MeetingAnalysisService(type(
            "UnconfiguredDashScope",
            (),
            {"is_configured": False},
        )()),
    )
    app.state.meeting_history_service = meeting_history_service
    app.state.upload_meeting_service = upload_meeting_service

    with TestClient(app) as client:
        response = client.post(
            "/api/meetings/upload",
            data={
                "scene": "general",
                "provider": "dashscope",
                "retain_raw_audio": "true",
                "glossary_terms": "queue wen=>Qwen",
            },
            files={"file": ("meeting.wav", b"raw-audio", "audio/wav")},
        )
        assert response.status_code == 202
        meeting_id = response.json()["meeting_id"]
        finalized_payload = wait_for_meeting_status(client, meeting_id, "finalized")
        delete_response = client.delete(f"/api/meetings/{meeting_id}")

    retained_path = tmp_path / "raw_audio" / meeting_id / "meeting.wav"
    assert finalized_payload["raw_audio_retained"] is True
    assert finalized_payload["raw_audio_filename"] == "meeting.wav"
    assert finalized_payload["raw_audio_size_bytes"] == len(b"raw-audio")
    assert finalized_payload["glossary_terms"][0]["term"] == "queue wen"
    assert finalized_payload["glossary_terms"][0]["replacement"] == "Qwen"
    assert finalized_payload["transcripts"][0]["text"] == "Qwen roadmap is ready"
    assert finalized_payload["analysis"]["participants"][0]["speaker"] == "Unknown"
    assert retained_path.exists() is False
    assert delete_response.status_code == 204


def test_upload_uses_persisted_global_glossary_terms(tmp_path) -> None:
    speaker_service = SpeakerService()
    glossary_store_service = GlossaryStoreService(tmp_path / "meeting_history.sqlite3")
    glossary_store_service.create_term(GlossaryTermCreate(term="queue wen", replacement="Qwen"))
    dashscope_client = StubASRClient(
        "dashscope",
        [TranscriptSegment(text="queue wen roadmap is ready", start=0.0, end=1.0)],
    )
    volcengine_client = StubASRClient("volcengine", [], is_configured=False)
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
        glossary_store_service=glossary_store_service,
    )
    app.state.meeting_history_service = meeting_history_service
    app.state.upload_meeting_service = upload_meeting_service

    with TestClient(app) as client:
        response = client.post(
            "/api/meetings/upload",
            data={"scene": "general", "provider": "dashscope"},
            files={"file": ("meeting.wav", b"raw-audio", "audio/wav")},
        )
        assert response.status_code == 202
        finalized_payload = wait_for_meeting_status(client, response.json()["meeting_id"], "finalized")

    assert finalized_payload["glossary_terms"][0]["term"] == "queue wen"
    assert finalized_payload["transcripts"][0]["text"] == "Qwen roadmap is ready"


def test_live_session_uses_persisted_global_glossary_terms(tmp_path) -> None:
    speaker_service = SpeakerService()
    glossary_store_service = GlossaryStoreService(tmp_path / "meeting_history.sqlite3")
    glossary_store_service.create_term(GlossaryTermCreate(term="queue wen", replacement="Qwen"))
    dashscope_client = StubASRClient(
        "dashscope",
        [TranscriptSegment(text="queue wen roadmap is ready", start=0.0, end=1.0)],
    )
    volcengine_client = StubASRClient("volcengine", [], is_configured=False)
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
        glossary_store_service=glossary_store_service,
    )
    app = FastAPI()
    app.include_router(websocket_router)
    app.include_router(meetings_router)
    app.state.session_manager = session_manager
    app.state.meeting_history_service = session_manager._meeting_history_service

    with TestClient(app) as client:
        with client.websocket_connect("/ws/meeting?scene=general&provider=dashscope") as websocket:
            session_started = websocket.receive_json()
            websocket.send_bytes(b"audio")
            messages = receive_until(
                websocket,
                lambda items: any(
                    item["type"] == "transcript_update"
                    and item["data"]["text"] == "Qwen roadmap is ready"
                    for item in items
                ),
            )
            websocket.send_json({"type": "finalize"})
            receive_until(websocket, lambda items: any(item["type"] == "summary" for item in items))

        detail_response = client.get(f"/api/meetings/{session_started['data']['meeting_id']}")

    assert any(item["type"] == "transcript_update" for item in messages)
    assert detail_response.status_code == 200
    assert detail_response.json()["glossary_terms"][0]["term"] == "queue wen"
    assert detail_response.json()["transcripts"][0]["text"] == "Qwen roadmap is ready"


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
        meeting_analysis_service=SlowMeetingAnalysisService(),
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


def test_upload_transient_asr_runtime_error_retries_and_finalizes(tmp_path) -> None:
    speaker_service = SpeakerService()
    dashscope_client = FlakyASRClient("dashscope", build_segments())
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
        finalized_payload = wait_for_meeting_status(client, response.json()["meeting_id"], "finalized")

    assert dashscope_client.call_count == 2
    assert finalized_payload["summary"]["overview"].startswith("The team reviewed")


def test_upload_transient_analysis_and_summary_errors_retry_and_finalize(tmp_path) -> None:
    speaker_service = SpeakerService()
    dashscope_client = StubASRClient("dashscope", build_segments())
    volcengine_client = StubASRClient("volcengine", build_segments(), is_configured=False)
    analysis_service = FlakyMeetingAnalysisService()
    summary_service = FlakySummaryService()
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
        meeting_analysis_service=analysis_service,
        summary_service=summary_service,
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
        finalized_payload = wait_for_meeting_status(client, response.json()["meeting_id"], "finalized")

    assert analysis_service.call_count == 2
    assert summary_service.call_count == 2
    assert finalized_payload["status"] == "finalized"
    assert finalized_payload["summary"]["title"] == "Meeting plan follow-up"


def test_upload_runtime_error_marks_failed_after_retry_limit(tmp_path) -> None:
    speaker_service = SpeakerService()
    dashscope_client = StubASRClient("dashscope", build_segments())
    volcengine_client = StubASRClient("volcengine", build_segments(), is_configured=False)
    summary_service = FlakySummaryService(failures_before_success=2)
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
        summary_service=summary_service,
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

    assert summary_service.call_count == 2
    assert failed_payload["summary"] is None
    assert failed_payload["error_message"] == "Transient summary failure in test"


def test_upload_audio_conversion_failure_is_not_retried(tmp_path) -> None:
    speaker_service = SpeakerService()
    dashscope_client = StubASRClient("dashscope", build_segments())
    volcengine_client = StubASRClient("volcengine", build_segments(), is_configured=False)
    audio_codec_service = CountingFailingAudioCodecService()
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
        audio_codec_service=audio_codec_service,
    )
    app.state.meeting_history_service = meeting_history_service
    app.state.upload_meeting_service = upload_meeting_service

    with TestClient(app) as client:
        response = client.post(
            "/api/meetings/upload",
            files={
                "file": ("meeting.mp3", b"fake-audio", "audio/mpeg"),
                "scene": (None, "general"),
                "target_lang": (None, "en"),
                "provider": (None, "dashscope"),
            },
        )

        assert response.status_code == 202
        failed_payload = wait_for_meeting_status(client, response.json()["meeting_id"], "failed")

    assert audio_codec_service.call_count == 1
    assert failed_payload["error_message"] == "Audio conversion failed in test"


def test_upload_endpoint_enqueues_persistent_job_when_embedded_worker_is_disabled(tmp_path) -> None:
    speaker_service = SpeakerService()
    dashscope_client = StubASRClient("dashscope", build_segments())
    volcengine_client = StubASRClient("volcengine", [], is_configured=False)
    app = FastAPI()
    app.include_router(meetings_router)
    settings, meeting_history_service, upload_meeting_service = build_upload_service(
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
        embedded_worker_enabled=False,
    )
    app.state.meeting_history_service = meeting_history_service
    app.state.upload_meeting_service = upload_meeting_service

    with TestClient(app) as client:
        response = client.post(
            "/api/meetings/upload",
            data={"scene": "general", "provider": "dashscope"},
            files={"file": ("meeting.wav", b"queued-audio", "audio/wav")},
        )
        assert response.status_code == 202
        payload = response.json()

    store = UploadQueueStore(
        db_path=settings.resolved_meeting_history_db_path,
        queue_dir=settings.resolved_upload_queue_dir,
    )
    job = store.get_job(payload["meeting_id"])
    assert job is not None
    assert job.status == UploadJobStatus.QUEUED
    assert job.payload_path.read_bytes() == b"queued-audio"
    meeting = meeting_history_service.get_meeting(payload["meeting_id"])
    assert meeting is not None
    assert meeting.status == MeetingHistoryStatus.PROCESSING


def test_upload_worker_processes_persistent_job_and_cleans_queue_payload(tmp_path) -> None:
    speaker_service = SpeakerService()
    dashscope_client = StubASRClient("dashscope", build_segments())
    volcengine_client = StubASRClient("volcengine", [], is_configured=False)
    app = FastAPI()
    app.include_router(meetings_router)
    settings, meeting_history_service, upload_meeting_service = build_upload_service(
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
        embedded_worker_enabled=False,
    )
    app.state.meeting_history_service = meeting_history_service
    app.state.upload_meeting_service = upload_meeting_service

    with TestClient(app) as client:
        response = client.post(
            "/api/meetings/upload",
            data={"scene": "general", "provider": "dashscope", "retain_raw_audio": "true"},
            files={"file": ("meeting.wav", b"queued-audio", "audio/wav")},
        )
        assert response.status_code == 202
        payload = response.json()

    store = UploadQueueStore(
        db_path=settings.resolved_meeting_history_db_path,
        queue_dir=settings.resolved_upload_queue_dir,
    )
    queued_job = store.get_job(payload["meeting_id"])
    assert queued_job is not None
    assert queued_job.payload_path.exists()

    processed_count = asyncio.run(upload_meeting_service.process_available_jobs())

    assert processed_count == 1
    completed_job = store.get_job(payload["meeting_id"])
    assert completed_job is not None
    assert completed_job.status == UploadJobStatus.COMPLETED
    assert not queued_job.payload_path.exists()
    assert (tmp_path / "raw_audio" / payload["meeting_id"] / "meeting.wav").exists()
    finalized_meeting = meeting_history_service.get_meeting(payload["meeting_id"])
    assert finalized_meeting is not None
    assert finalized_meeting.status == MeetingHistoryStatus.FINALIZED


def test_upload_worker_records_provider_operation_metrics(tmp_path) -> None:
    speaker_service = SpeakerService()
    dashscope_client = StubASRClient("dashscope", build_segments())
    volcengine_client = StubASRClient("volcengine", [], is_configured=False)
    observability_service = ObservabilityService()
    settings, meeting_history_service, upload_meeting_service = build_upload_service(
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
        embedded_worker_enabled=False,
        observability_service=observability_service,
    )
    queued_meeting = asyncio.run(
        upload_meeting_service.start_upload(
            audio_data=b"queued-audio",
            filename="meeting.wav",
            content_type="audio/wav",
            scene="general",
            target_lang=None,
            preferred_provider="dashscope",
            retain_raw_audio=False,
        )
    )

    processed_count = asyncio.run(upload_meeting_service.process_available_jobs())

    assert processed_count == 1
    finalized_meeting = meeting_history_service.get_meeting(queued_meeting.meeting_id)
    assert finalized_meeting is not None
    assert finalized_meeting.status == MeetingHistoryStatus.FINALIZED
    snapshot = observability_service.snapshot(
        service_name=settings.service_name,
        service_version=settings.service_version,
        demo_mode=settings.demo_mode,
        provider_statuses=[],
        upload_queue={},
    )
    metrics = {
        (item["operation"], item["provider"]): item
        for item in snapshot["providers"]["operations"]
    }
    assert metrics[("upload_asr", "dashscope")]["count"] == 1
    assert metrics[("upload_analysis", "dashscope")]["count"] == 1
    assert metrics[("upload_summary", "dashscope")]["count"] == 1


def test_upload_queue_claim_next_does_not_claim_same_job_twice(tmp_path) -> None:
    store = UploadQueueStore(
        db_path=tmp_path / "meeting_history.sqlite3",
        queue_dir=tmp_path / "upload_queue",
    )
    store.enqueue_upload(
        meeting_id="meeting-1",
        audio_data=b"queued-audio",
        filename="meeting.wav",
        content_type="audio/wav",
        scene="general",
        target_lang=None,
        provider="dashscope",
        glossary_terms=[],
    )

    first_claim = store.claim_next()
    second_claim = store.claim_next()

    assert first_claim is not None
    assert first_claim.meeting_id == "meeting-1"
    assert first_claim.status == UploadJobStatus.PROCESSING
    assert second_claim is None


def test_upload_queue_migrates_legacy_schema_and_sets_retry_defaults(tmp_path) -> None:
    db_path = tmp_path / "meeting_history.sqlite3"
    queue_dir = tmp_path / "upload_queue"
    payload_dir = queue_dir / "legacy-meeting"
    payload_dir.mkdir(parents=True)
    payload_path = payload_dir / "source.wav"
    payload_path.write_bytes(b"legacy-audio")
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE upload_jobs (
                meeting_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                payload_path TEXT NOT NULL,
                filename TEXT,
                content_type TEXT,
                scene TEXT NOT NULL,
                target_lang TEXT,
                provider TEXT NOT NULL,
                glossary_terms_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                claimed_at TEXT,
                completed_at TEXT,
                error_message TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO upload_jobs (
                meeting_id, status, payload_path, filename, content_type, scene,
                target_lang, provider, glossary_terms_json, created_at, updated_at,
                claimed_at, completed_at, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
            """,
            (
                "legacy-meeting",
                UploadJobStatus.QUEUED,
                str(payload_path),
                "source.wav",
                "audio/wav",
                "general",
                None,
                "dashscope",
                None,
                timestamp,
                timestamp,
            ),
        )

    store = UploadQueueStore(db_path=db_path, queue_dir=queue_dir)
    job = store.get_job("legacy-meeting")

    assert job is not None
    assert job.attempt_count == 0
    assert job.max_attempts == 3
    assert job.next_run_at is None
    assert job.last_error is None
    assert job.last_attempted_at is None
    assert job.claimed_by is None


def test_upload_queue_claim_next_skips_jobs_until_next_run_at(tmp_path) -> None:
    db_path = tmp_path / "meeting_history.sqlite3"
    store = UploadQueueStore(
        db_path=db_path,
        queue_dir=tmp_path / "upload_queue",
    )
    store.enqueue_upload(
        meeting_id="delayed-meeting",
        audio_data=b"queued-audio",
        filename="meeting.wav",
        content_type="audio/wav",
        scene="general",
        target_lang=None,
        provider="dashscope",
        glossary_terms=[],
    )
    future_timestamp = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE upload_jobs SET next_run_at = ? WHERE meeting_id = ?",
            (future_timestamp, "delayed-meeting"),
        )

    assert store.claim_next() is None
    delayed_job = store.get_job("delayed-meeting")
    assert delayed_job is not None
    assert delayed_job.status == UploadJobStatus.QUEUED
    assert delayed_job.attempt_count == 0


def test_upload_queue_claim_next_records_attempt_metadata(tmp_path) -> None:
    store = UploadQueueStore(
        db_path=tmp_path / "meeting_history.sqlite3",
        queue_dir=tmp_path / "upload_queue",
    )
    store.enqueue_upload(
        meeting_id="meeting-1",
        audio_data=b"queued-audio",
        filename="meeting.wav",
        content_type="audio/wav",
        scene="general",
        target_lang=None,
        provider="dashscope",
        glossary_terms=[],
    )

    claimed_job = store.claim_next(claimed_by="test-worker")

    assert claimed_job is not None
    assert claimed_job.status == UploadJobStatus.PROCESSING
    assert claimed_job.attempt_count == 1
    assert claimed_job.claimed_by == "test-worker"
    assert claimed_job.claimed_at is not None
    assert claimed_job.last_attempted_at is not None


def test_upload_worker_requeues_retryable_failure_and_preserves_payload(tmp_path) -> None:
    store = UploadQueueStore(
        db_path=tmp_path / "meeting_history.sqlite3",
        queue_dir=tmp_path / "upload_queue",
        max_attempts=2,
        retry_base_seconds=60,
    )
    store.enqueue_upload(
        meeting_id="retry-meeting",
        audio_data=b"queued-audio",
        filename="meeting.wav",
        content_type="audio/wav",
        scene="general",
        target_lang=None,
        provider="dashscope",
        glossary_terms=[],
    )
    terminal_failures: list[str] = []

    async def fail_once(job):
        return "provider unavailable"

    worker = UploadQueueWorker(
        name="test-worker",
        store=store,
        handler=fail_once,
        on_terminal_failure=lambda job, error: terminal_failures.append(error),
    )

    processed_count = asyncio.run(worker.process_available_jobs())

    assert processed_count == 1
    job = store.get_job("retry-meeting")
    assert job is not None
    assert job.status == UploadJobStatus.QUEUED
    assert job.attempt_count == 1
    assert job.last_error == "provider unavailable"
    assert job.error_message is None
    assert job.next_run_at is not None
    assert job.payload_path.exists()
    assert terminal_failures == []


def test_upload_worker_marks_terminal_failed_after_attempts_exhausted(tmp_path) -> None:
    store = UploadQueueStore(
        db_path=tmp_path / "meeting_history.sqlite3",
        queue_dir=tmp_path / "upload_queue",
        max_attempts=1,
    )
    queued_job = store.enqueue_upload(
        meeting_id="failed-meeting",
        audio_data=b"queued-audio",
        filename="meeting.wav",
        content_type="audio/wav",
        scene="general",
        target_lang=None,
        provider="dashscope",
        glossary_terms=[],
    )
    terminal_failures: list[tuple[str, str]] = []

    async def always_fail(job):
        return "provider unavailable"

    worker = UploadQueueWorker(
        name="test-worker",
        store=store,
        handler=always_fail,
        on_terminal_failure=lambda job, error: terminal_failures.append((job.meeting_id, error)),
    )

    processed_count = asyncio.run(worker.process_available_jobs())

    assert processed_count == 1
    job = store.get_job("failed-meeting")
    assert job is not None
    assert job.status == UploadJobStatus.FAILED
    assert job.attempt_count == 1
    assert job.error_message == "provider unavailable"
    assert terminal_failures == [("failed-meeting", "provider unavailable")]
    assert not queued_job.payload_path.exists()


def test_upload_worker_retry_succeeds_and_cleans_payload(tmp_path) -> None:
    store = UploadQueueStore(
        db_path=tmp_path / "meeting_history.sqlite3",
        queue_dir=tmp_path / "upload_queue",
        max_attempts=2,
        retry_base_seconds=0,
    )
    queued_job = store.enqueue_upload(
        meeting_id="eventual-success",
        audio_data=b"queued-audio",
        filename="meeting.wav",
        content_type="audio/wav",
        scene="general",
        target_lang=None,
        provider="dashscope",
        glossary_terms=[],
    )
    call_count = 0

    async def flaky_handler(job):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return "temporary provider failure"
        return None

    worker = UploadQueueWorker(name="test-worker", store=store, handler=flaky_handler)

    processed_count = asyncio.run(worker.process_available_jobs())

    assert processed_count == 2
    job = store.get_job("eventual-success")
    assert job is not None
    assert job.status == UploadJobStatus.COMPLETED
    assert job.attempt_count == 2
    assert job.last_error is None
    assert not queued_job.payload_path.exists()


def test_upload_queue_releases_only_stale_processing_jobs(tmp_path) -> None:
    db_path = tmp_path / "meeting_history.sqlite3"
    store = UploadQueueStore(
        db_path=db_path,
        queue_dir=tmp_path / "upload_queue",
    )
    for meeting_id in ("fresh-processing", "stale-processing"):
        store.enqueue_upload(
            meeting_id=meeting_id,
            audio_data=b"queued-audio",
            filename="meeting.wav",
            content_type="audio/wav",
            scene="general",
            target_lang=None,
            provider="dashscope",
            glossary_terms=[],
        )
        assert store.claim_next(claimed_by=f"{meeting_id}-worker") is not None
    stale_timestamp = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE upload_jobs SET claimed_at = ? WHERE meeting_id = ?",
            (stale_timestamp, "stale-processing"),
        )

    released_count = store.release_stale_processing_jobs(timeout_seconds=1800)

    fresh_job = store.get_job("fresh-processing")
    stale_job = store.get_job("stale-processing")
    assert released_count == 1
    assert fresh_job is not None
    assert fresh_job.status == UploadJobStatus.PROCESSING
    assert stale_job is not None
    assert stale_job.status == UploadJobStatus.QUEUED


def test_upload_worker_missing_payload_marks_terminal_failed(tmp_path) -> None:
    store = UploadQueueStore(
        db_path=tmp_path / "meeting_history.sqlite3",
        queue_dir=tmp_path / "upload_queue",
    )
    queued_job = store.enqueue_upload(
        meeting_id="missing-payload",
        audio_data=b"queued-audio",
        filename="meeting.wav",
        content_type="audio/wav",
        scene="general",
        target_lang=None,
        provider="dashscope",
        glossary_terms=[],
    )
    queued_job.payload_path.unlink()
    terminal_failures: list[str] = []

    async def handler(job):
        raise AssertionError("Handler should not run when payload is missing.")

    worker = UploadQueueWorker(
        name="test-worker",
        store=store,
        handler=handler,
        on_terminal_failure=lambda job, error: terminal_failures.append(error),
    )

    processed_count = asyncio.run(worker.process_available_jobs())

    job = store.get_job("missing-payload")
    assert processed_count == 1
    assert job is not None
    assert job.status == UploadJobStatus.FAILED
    assert job.error_message == UploadQueueStore.MISSING_PAYLOAD_ERROR
    assert terminal_failures == [UploadQueueStore.MISSING_PAYLOAD_ERROR]


def test_upload_queue_reconcile_requeues_processing_jobs_and_marks_orphans_failed(tmp_path) -> None:
    settings = build_settings(tmp_path)
    meeting_history_service = MeetingHistoryService(settings.resolved_meeting_history_db_path)
    store = UploadQueueStore(
        db_path=settings.resolved_meeting_history_db_path,
        queue_dir=settings.resolved_upload_queue_dir,
    )
    for meeting_id in ("with-job", "orphan"):
        meeting_history_service.create_meeting(
            meeting_id=meeting_id,
            scene="general",
            target_lang=None,
            provider="dashscope",
            status=MeetingHistoryStatus.PROCESSING,
            source_type=MeetingSourceType.UPLOAD,
            processing_stage=MeetingProcessingStage.TRANSCRIBING,
        )
    store.enqueue_upload(
        meeting_id="with-job",
        audio_data=b"queued-audio",
        filename="meeting.wav",
        content_type="audio/wav",
        scene="general",
        target_lang=None,
        provider="dashscope",
        glossary_terms=[],
    )
    claimed_job = store.claim_next()
    assert claimed_job is not None
    assert claimed_job.status == UploadJobStatus.PROCESSING

    store.release_processing_jobs()
    meeting_history_service.reconcile_processing_uploads(store.active_job_meeting_ids())

    requeued_job = store.get_job("with-job")
    meeting_with_job = meeting_history_service.get_meeting("with-job")
    orphan_meeting = meeting_history_service.get_meeting("orphan")
    assert requeued_job is not None
    assert requeued_job.status == UploadJobStatus.QUEUED
    assert meeting_with_job is not None
    assert meeting_with_job.status == MeetingHistoryStatus.PROCESSING
    assert orphan_meeting is not None
    assert orphan_meeting.status == MeetingHistoryStatus.FAILED
    assert orphan_meeting.error_message == MeetingHistoryService.INTERRUPTED_UPLOAD_ERROR


def test_upload_worker_cli_once_processes_queued_demo_job(tmp_path, monkeypatch) -> None:
    from tools import run_upload_worker

    settings = build_settings(
        tmp_path,
        demo_mode=True,
        default_asr_provider="demo",
        diarization_mode="disabled",
        upload_queue_embedded_worker_enabled=False,
    )
    demo_asr_client = DemoASRClient(settings)
    demo_llm_client = DemoDashScopeClient(settings)
    speaker_service = SpeakerService()
    meeting_history_service = MeetingHistoryService(settings.resolved_meeting_history_db_path)
    queue_store = UploadQueueStore(
        db_path=settings.resolved_meeting_history_db_path,
        queue_dir=settings.resolved_upload_queue_dir,
    )
    upload_meeting_service = UploadMeetingService(
        asr_provider_service=ASRProviderService(
            settings=settings,
            dashscope_client=StubASRClient("dashscope", [], is_configured=False),
            volcengine_client=StubASRClient("volcengine", [], is_configured=False),
            demo_client=demo_asr_client,
        ),
        audio_codec_service=FailingAudioCodecService(),
        speaker_service=speaker_service,
        diarization_service=StubDiarizationService(speaker_service, DiarizationResult(succeeded=True, turns=[])),
        summary_service=SummaryService(demo_llm_client),
        meeting_analysis_service=MeetingAnalysisService(demo_llm_client),
        translation_service=TranslationService(demo_llm_client),
        meeting_history_service=meeting_history_service,
        glossary_service=GlossaryService(settings),
        raw_audio_retention_service=RawAudioRetentionService(settings),
        upload_queue_store=queue_store,
        embedded_worker_enabled=False,
    )
    queued_meeting = asyncio.run(
        upload_meeting_service.start_upload(
            audio_data=b"demo-audio",
            filename="demo.wav",
            content_type="audio/wav",
            scene="general",
            target_lang="es",
            preferred_provider="demo",
            retain_raw_audio=False,
        )
    )
    monkeypatch.setattr(run_upload_worker, "settings", settings)

    exit_code = asyncio.run(run_upload_worker.run_worker(once=True))

    assert exit_code == 0
    finalized_meeting = meeting_history_service.get_meeting(queued_meeting.meeting_id)
    assert finalized_meeting is not None
    assert finalized_meeting.status == MeetingHistoryStatus.FINALIZED
    job = queue_store.get_job(queued_meeting.meeting_id)
    assert job is not None
    assert job.status == UploadJobStatus.COMPLETED


def test_meeting_action_item_status_update_is_persisted(tmp_path) -> None:
    history_service = MeetingHistoryService(tmp_path / "meeting_history.sqlite3")
    history_service.create_meeting(
        meeting_id="meeting-with-actions",
        scene="general",
        target_lang="en",
        provider="dashscope",
    )
    history_service.update_summary(
        "meeting-with-actions",
        MeetingSummary(
            title="Follow-up review",
            overview="Follow-up review.",
            action_items=[
                {
                    "task": "Send the recap",
                    "assignee": "Speaker 1",
                    "deadline": "Today",
                    "status": "pending",
                    "source_excerpt": "I will send the recap today.",
                    "transcript_index": 0,
                    "is_actionable": True,
                    "confidence": 0.9,
                    "owner_explicit": True,
                    "deadline_explicit": True,
                }
            ],
        ),
    )

    app = FastAPI()
    app.include_router(meetings_router)
    app.state.meeting_history_service = history_service

    with TestClient(app) as client:
        response = client.patch(
            "/api/meetings/meeting-with-actions/action-items/0",
            json={"status": "completed"},
        )
        detail_response = client.get("/api/meetings/meeting-with-actions")
        missing_action_response = client.patch(
            "/api/meetings/meeting-with-actions/action-items/2",
            json={"status": "completed"},
        )

    assert response.status_code == 200
    assert response.json()["summary"]["action_items"][0]["status"] == "completed"
    assert detail_response.status_code == 200
    assert detail_response.json()["summary"]["action_items"][0]["status"] == "completed"
    assert missing_action_response.status_code == 404


def test_meeting_title_update_is_manual_and_not_overwritten_by_summary(tmp_path) -> None:
    history_service = MeetingHistoryService(tmp_path / "meeting_history.sqlite3")
    history_service.create_meeting(
        meeting_id="meeting-with-title",
        scene="general",
        target_lang="en",
        provider="dashscope",
    )
    history_service.update_summary(
        "meeting-with-title",
        MeetingSummary(
            title="Generated title",
            overview="The first generated summary.",
            key_topics=["Generated topic"],
        ),
    )

    app = FastAPI()
    app.include_router(meetings_router)
    app.state.meeting_history_service = history_service

    with TestClient(app) as client:
        rename_response = client.patch(
            "/api/meetings/meeting-with-title/title",
            json={"title": "Manual project review"},
        )
        blank_title_response = client.patch(
            "/api/meetings/meeting-with-title/title",
            json={"title": "   "},
        )

    history_service.update_summary(
        "meeting-with-title",
        MeetingSummary(
            title="Regenerated title",
            overview="The second generated summary.",
            key_topics=["Regenerated topic"],
        ),
    )
    meeting = history_service.get_meeting("meeting-with-title")

    assert rename_response.status_code == 200
    assert rename_response.json()["title"] == "Manual project review"
    assert rename_response.json()["title_manually_edited"] is True
    assert blank_title_response.status_code == 400
    assert meeting is not None
    assert meeting.title == "Manual project review"
    assert meeting.title_manually_edited is True
    assert meeting.preview_text == "The second generated summary."


def test_meeting_summary_update_is_persisted_and_marks_manual(tmp_path) -> None:
    history_service = MeetingHistoryService(tmp_path / "meeting_history.sqlite3")
    history_service.create_meeting(
        meeting_id="meeting-with-summary",
        scene="general",
        target_lang="en",
        provider="dashscope",
    )
    history_service.update_summary(
        "meeting-with-summary",
        MeetingSummary(
            title="Generated title",
            overview="Generated overview.",
            key_topics=["Generated topic"],
            action_items=[
                {
                    "task": "Generated action",
                    "assignee": "Speaker 1",
                    "deadline": "Today",
                    "status": "pending",
                    "source_excerpt": "I will send it today.",
                    "transcript_index": 0,
                    "is_actionable": True,
                    "confidence": 0.8,
                    "owner_explicit": True,
                    "deadline_explicit": True,
                }
            ],
            decisions=["Generated decision"],
            risks=[],
        ),
    )

    app = FastAPI()
    app.include_router(meetings_router)
    app.state.meeting_history_service = history_service

    with TestClient(app) as client:
        update_response = client.patch(
            "/api/meetings/meeting-with-summary/summary",
            json={
                "overview": "Edited overview.",
                "key_topics": ["Edited topic", "  "],
                "decisions": ["Edited decision"],
                "risks": ["Edited risk"],
                "action_items": [
                    {
                        "task": "Edited action",
                        "assignee": "Speaker 2",
                        "deadline": "Tomorrow",
                        "status": "completed",
                        "source_excerpt": "Edited source.",
                        "transcript_index": None,
                        "is_actionable": True,
                        "confidence": 0.7,
                        "owner_explicit": False,
                        "deadline_explicit": False,
                    }
                ],
            },
        )
        detail_response = client.get("/api/meetings/meeting-with-summary")
        status_response = client.patch(
            "/api/meetings/meeting-with-summary/action-items/0",
            json={"status": "pending"},
        )
        missing_response = client.patch(
            "/api/meetings/missing-meeting/summary",
            json={
                "overview": "Missing",
                "key_topics": [],
                "decisions": [],
                "risks": [],
                "action_items": [],
            },
        )

    assert update_response.status_code == 200
    payload = update_response.json()
    assert payload["title"] == "Generated title"
    assert payload["summary_manually_edited"] is True
    assert payload["preview_text"] == "Edited overview."
    assert payload["summary"]["overview"] == "Edited overview."
    assert payload["summary"]["key_topics"] == ["Edited topic"]
    assert payload["summary"]["action_items"][0]["status"] == "completed"
    assert detail_response.status_code == 200
    assert detail_response.json()["summary_manually_edited"] is True
    assert detail_response.json()["summary"]["risks"] == ["Edited risk"]
    assert status_response.status_code == 200
    assert status_response.json()["summary"]["action_items"][0]["status"] == "pending"
    assert missing_response.status_code == 404


def test_meeting_summary_update_requires_existing_summary(tmp_path) -> None:
    history_service = MeetingHistoryService(tmp_path / "meeting_history.sqlite3")
    history_service.create_meeting(
        meeting_id="meeting-without-summary",
        scene="general",
        target_lang="en",
        provider="dashscope",
    )

    app = FastAPI()
    app.include_router(meetings_router)
    app.state.meeting_history_service = history_service

    with TestClient(app) as client:
        response = client.patch(
            "/api/meetings/meeting-without-summary/summary",
            json={
                "overview": "Edited overview.",
                "key_topics": [],
                "decisions": [],
                "risks": [],
                "action_items": [],
            },
        )

    assert response.status_code == 409


def test_meeting_speaker_update_renames_and_merges_saved_references(tmp_path) -> None:
    history_service = MeetingHistoryService(tmp_path / "meeting_history.sqlite3")
    history_service.create_meeting(
        meeting_id="meeting-with-speakers",
        scene="general",
        target_lang="en",
        provider="dashscope",
    )
    history_service.upsert_transcript(
        "meeting-with-speakers",
        TranscriptItem(
            transcript_index=0,
            speaker="Speaker 1",
            speaker_is_final=True,
            transcript_is_final=True,
            text="I agree with the launch plan.",
            start=0.0,
            end=3.0,
        ),
    )
    history_service.upsert_transcript(
        "meeting-with-speakers",
        TranscriptItem(
            transcript_index=1,
            speaker="Speaker 2",
            speaker_is_final=True,
            transcript_is_final=True,
            text="I will send the checklist.",
            start=3.0,
            end=7.0,
        ),
    )
    history_service.upsert_transcript(
        "meeting-with-speakers",
        TranscriptItem(
            transcript_index=2,
            speaker="Speaker 3",
            speaker_is_final=True,
            transcript_is_final=True,
            text="I also agree.",
            start=7.0,
            end=9.0,
        ),
    )
    history_service.update_summary(
        "meeting-with-speakers",
        MeetingSummary(
            title="Launch plan",
            overview="The team reviewed launch planning.",
            action_items=[
                {
                    "task": "Send checklist",
                    "assignee": "Speaker 2",
                    "deadline": "Today",
                    "status": "pending",
                    "source_excerpt": "I will send the checklist.",
                    "transcript_index": 1,
                    "is_actionable": True,
                    "confidence": 0.9,
                    "owner_explicit": True,
                    "deadline_explicit": False,
                }
            ],
        ),
    )
    history_service.update_analysis(
        "meeting-with-speakers",
        MeetingAnalysis(
            overall_sentiment="positive",
            engagement_level="medium",
            engagement_summary="The meeting had agreement.",
            signal_counts=MeetingSignalCounts(agreement=2),
            highlights=[
                MeetingAnalysisHighlight(
                    transcript_index=0,
                    signal="agreement",
                    severity="medium",
                    reason="Speaker agrees.",
                ),
                MeetingAnalysisHighlight(
                    transcript_index=2,
                    signal="agreement",
                    severity="low",
                    reason="Speaker also agrees.",
                ),
            ],
            participants=[
                ParticipantAnalysis(speaker="Speaker 1", transcript_count=1),
                ParticipantAnalysis(speaker="Speaker 2", transcript_count=1),
                ParticipantAnalysis(speaker="Speaker 3", transcript_count=1),
            ],
        ),
    )

    app = FastAPI()
    app.include_router(meetings_router)
    app.state.meeting_history_service = history_service

    with TestClient(app) as client:
        response = client.patch(
            "/api/meetings/meeting-with-speakers/speakers",
            json={
                "speaker_updates": [
                    {"from": "Speaker 1", "to": "Alice"},
                    {"from": "Speaker 3", "to": "Alice"},
                    {"from": "Speaker 2", "to": "Bob"},
                ]
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert [item["speaker"] for item in payload["transcripts"]] == ["Alice", "Bob", "Alice"]
    assert payload["summary"]["action_items"][0]["assignee"] == "Bob"
    assert [item["speaker"] for item in payload["analysis"]["participants"]] == ["Alice", "Bob"]
    alice = payload["analysis"]["participants"][0]
    assert alice["transcript_count"] == 2
    assert alice["speaking_time_seconds"] == 5.0
    assert alice["signal_counts"]["agreement"] == 2


def test_meeting_speaker_update_requires_saved_terminal_meeting(tmp_path) -> None:
    history_service = MeetingHistoryService(tmp_path / "meeting_history.sqlite3")
    history_service.create_meeting(
        meeting_id="draft-meeting",
        scene="general",
        target_lang="en",
        provider="dashscope",
    )
    history_service.create_meeting(
        meeting_id="processing-upload",
        scene="general",
        target_lang="en",
        provider="dashscope",
        status=MeetingHistoryStatus.PROCESSING,
        source_type=MeetingSourceType.UPLOAD,
    )

    app = FastAPI()
    app.include_router(meetings_router)
    app.state.meeting_history_service = history_service

    with TestClient(app) as client:
        draft_response = client.patch(
            "/api/meetings/draft-meeting/speakers",
            json={"speaker_updates": [{"from": "Speaker 1", "to": "Alice"}]},
        )
        processing_response = client.patch(
            "/api/meetings/processing-upload/speakers",
            json={"speaker_updates": [{"from": "Speaker 1", "to": "Alice"}]},
        )
        missing_response = client.patch(
            "/api/meetings/missing/speakers",
            json={"speaker_updates": [{"from": "Speaker 1", "to": "Alice"}]},
        )

    assert draft_response.status_code == 409
    assert processing_response.status_code == 409
    assert missing_response.status_code == 404


def test_meeting_speaker_update_requires_matching_labels(tmp_path) -> None:
    history_service = MeetingHistoryService(tmp_path / "meeting_history.sqlite3")
    history_service.create_meeting(
        meeting_id="final-meeting",
        scene="general",
        target_lang="en",
        provider="dashscope",
    )
    history_service.upsert_transcript(
        "final-meeting",
        TranscriptItem(
            transcript_index=0,
            speaker="Speaker 1",
            speaker_is_final=True,
            transcript_is_final=True,
            text="Hello.",
            start=0.0,
            end=1.0,
        ),
    )
    history_service.mark_finalized("final-meeting")

    app = FastAPI()
    app.include_router(meetings_router)
    app.state.meeting_history_service = history_service

    with TestClient(app) as client:
        response = client.patch(
            "/api/meetings/final-meeting/speakers",
            json={"speaker_updates": [{"from": "Speaker 2", "to": "Alice"}]},
        )

    assert response.status_code == 409


def test_meeting_speaker_update_applies_mapping_without_cascading(tmp_path) -> None:
    history_service = MeetingHistoryService(tmp_path / "meeting_history.sqlite3")
    history_service.create_meeting(
        meeting_id="chain-meeting",
        scene="general",
        target_lang="en",
        provider="dashscope",
    )
    history_service.upsert_transcript(
        "chain-meeting",
        TranscriptItem(
            transcript_index=0,
            speaker="Speaker 1",
            speaker_is_final=True,
            transcript_is_final=True,
            text="First speaker.",
            start=0.0,
            end=1.0,
        ),
    )
    history_service.upsert_transcript(
        "chain-meeting",
        TranscriptItem(
            transcript_index=1,
            speaker="Speaker 2",
            speaker_is_final=True,
            transcript_is_final=True,
            text="Second speaker.",
            start=1.0,
            end=2.0,
        ),
    )
    history_service.mark_finalized("chain-meeting")

    app = FastAPI()
    app.include_router(meetings_router)
    app.state.meeting_history_service = history_service

    with TestClient(app) as client:
        response = client.patch(
            "/api/meetings/chain-meeting/speakers",
            json={
                "speaker_updates": [
                    {"from": "Speaker 1", "to": "Speaker 2"},
                    {"from": "Speaker 2", "to": "Bob"},
                ]
            },
        )

    assert response.status_code == 200
    assert [item["speaker"] for item in response.json()["transcripts"]] == ["Speaker 2", "Bob"]


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
    service.reconcile_processing_uploads()
    meeting = service.get_meeting("legacy-upload")
    assert meeting is not None
    assert meeting.status.value == "failed"
    assert meeting.source_type.value == "upload"
    assert meeting.processing_stage is None
    assert meeting.error_message == MeetingHistoryService.INTERRUPTED_UPLOAD_ERROR

    migrated_connection = service._connect()
    migrated_columns = service._get_table_columns(migrated_connection, "meetings")
    migrated_connection.close()
    assert {
        "source_type",
        "processing_stage",
        "error_message",
        "source_name",
        "title",
        "title_manually_edited",
        "summary_manually_edited",
        "raw_audio_retained",
        "raw_audio_path",
        "raw_audio_filename",
        "raw_audio_content_type",
        "raw_audio_size_bytes",
        "glossary_terms_json",
    }.issubset(migrated_columns)


def build_demo_services(tmp_path):
    settings = build_settings(
        tmp_path,
        demo_mode=True,
        default_asr_provider="demo",
    )
    speaker_service = SpeakerService()
    demo_asr_client = DemoASRClient(settings)
    demo_llm_client = DemoDashScopeClient(settings)
    meeting_history_service = MeetingHistoryService(settings.resolved_meeting_history_db_path)
    asr_provider_service = ASRProviderService(
        settings=settings,
        dashscope_client=StubASRClient("dashscope", [], is_configured=False),
        volcengine_client=StubASRClient("volcengine", [], is_configured=False),
        demo_client=demo_asr_client,
    )
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


def test_health_reports_demo_mode_and_available_provider(tmp_path) -> None:
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


def test_demo_provider_websocket_generates_meeting_outputs(tmp_path) -> None:
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
        audio_codec_service=StubAudioCodecService(),
        speaker_service=speaker_service,
        diarization_service=StubDiarizationService(speaker_service, DiarizationResult(succeeded=True, turns=[])),
        realtime_diarization_service=StubRealtimeDiarizationService(),
        summary_service=summary_service,
        meeting_analysis_service=meeting_analysis_service,
        translation_service=translation_service,
        meeting_history_service=meeting_history_service,
        glossary_service=GlossaryService(settings),
    )
    app.state.meeting_history_service = meeting_history_service

    with TestClient(app) as client:
        with client.websocket_connect("/ws/meeting?scene=general&target_lang=ja&provider=demo") as websocket:
            session_started = websocket.receive_json()
            websocket.send_bytes(b"demo-audio-1")
            websocket.send_bytes(b"demo-audio-2")
            websocket.send_bytes(b"demo-audio-3")
            messages = receive_until(
                websocket,
                lambda items: (
                    sum(1 for item in items if item["type"] == "transcript") == 3
                    and any(item["type"] == "translation" for item in items)
                ),
            )
            websocket.send_json({"type": "finalize"})
            finalized_messages = receive_until(
                websocket,
                lambda items: (
                    any(item["type"] == "analysis" for item in items)
                    and any(item["type"] == "summary" for item in items)
                ),
            )

        detail_response = client.get(f"/api/meetings/{session_started['data']['meeting_id']}")

    assert session_started["type"] == "session_started"
    assert session_started["data"]["provider"] == "demo"
    assert any(message["type"] == "translation" for message in messages)
    assert any(message["type"] == "analysis" for message in finalized_messages)
    assert any(message["type"] == "summary" for message in finalized_messages)
    detail_payload = detail_response.json()
    assert detail_payload["provider"] == "demo"
    assert detail_payload["transcript_count"] == 3
    assert detail_payload["analysis"]["engagement_summary"].startswith("The demo meeting")
    assert detail_payload["summary"]["title"] == "Demo Launch Checklist Review"


def test_demo_upload_finalizes_without_audio_conversion_or_external_keys(tmp_path) -> None:
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
        diarization_service=StubDiarizationService(speaker_service, DiarizationResult(succeeded=True, turns=[])),
        summary_service=summary_service,
        meeting_analysis_service=meeting_analysis_service,
        translation_service=translation_service,
        meeting_history_service=meeting_history_service,
        glossary_service=GlossaryService(settings),
        raw_audio_retention_service=RawAudioRetentionService(settings),
        upload_queue_store=UploadQueueStore(
            db_path=settings.resolved_meeting_history_db_path,
            queue_dir=settings.resolved_upload_queue_dir,
        ),
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
    assert finalized_payload["transcript_count"] == 3
    assert finalized_payload["transcripts"][0]["translated_target_lang"] == "es"
    assert finalized_payload["summary"]["title"] == "Demo Launch Checklist Review"
    assert finalized_payload["analysis"]["overall_sentiment"] == "mixed"


def test_demo_provider_disabled_does_not_silently_fallback_to_real_provider(tmp_path) -> None:
    settings = build_settings(tmp_path, demo_mode=False, default_asr_provider="volcengine")
    provider_service = ASRProviderService(
        settings=settings,
        dashscope_client=StubASRClient("dashscope", build_segments(), is_configured=True),
        volcengine_client=StubASRClient("volcengine", build_segments(), is_configured=True),
        demo_client=DemoASRClient(settings),
    )

    selection = provider_service.resolve_provider("demo")

    assert selection.provider_name == "demo"
    assert selection.client.is_configured is False
