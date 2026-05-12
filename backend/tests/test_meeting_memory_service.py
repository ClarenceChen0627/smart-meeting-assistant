from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.memory import router as memory_router
from app.schemas.meeting_history import MeetingMetadataUpdate, MeetingSourceType
from app.schemas.summary import MeetingSummary
from app.schemas.transcript import TranscriptItem
from app.services.meeting_history_service import MeetingHistoryService
from app.services.meeting_memory_service import MeetingMemoryService


def _seed_memory_meetings(history_service: MeetingHistoryService) -> None:
    history_service.create_meeting(
        meeting_id="launch-1",
        scene="general",
        target_lang="en",
        provider="demo",
        source_type=MeetingSourceType.LIVE,
    )
    history_service.update_metadata("launch-1", MeetingMetadataUpdate(tags=["Launch"]))
    history_service.upsert_transcript(
        "launch-1",
        TranscriptItem(
            transcript_index=0,
            speaker="Speaker 1",
            speaker_is_final=True,
            transcript_is_final=True,
            text="We decided to keep the launch date, but who owns support coverage?",
            start=0,
            end=8,
        ),
    )
    history_service.upsert_transcript(
        "launch-1",
        TranscriptItem(
            transcript_index=1,
            speaker="Speaker 2",
            speaker_is_final=True,
            transcript_is_final=True,
            text="I will send the launch checklist by Friday.",
            start=8,
            end=12,
        ),
    )
    history_service.update_summary(
        "launch-1",
        MeetingSummary(
            title="Launch Readiness",
            overview="The team reviewed launch readiness.",
            key_topics=["Launch readiness"],
            decisions=["Keep the launch date"],
            action_items=[
                {
                    "task": "Send the launch checklist",
                    "assignee": "Speaker 2",
                    "deadline": "Friday",
                    "status": "pending",
                    "source_excerpt": "I will send the launch checklist by Friday.",
                    "transcript_index": 1,
                    "is_actionable": True,
                    "confidence": 0.92,
                    "owner_explicit": True,
                    "deadline_explicit": True,
                }
            ],
            risks=["Who owns support coverage?", "Integration risk needs mitigation"],
        ),
    )

    history_service.create_meeting(
        meeting_id="launch-2",
        scene="finance",
        target_lang="en",
        provider="demo",
        source_type=MeetingSourceType.UPLOAD,
    )
    history_service.update_metadata("launch-2", MeetingMetadataUpdate(tags=["Launch", "Budget"]))
    history_service.update_summary(
        "launch-2",
        MeetingSummary(
            title="Launch Budget",
            overview="Budget readiness was reviewed.",
            key_topics=["Budget"],
            decisions=["Approve launch budget"],
            action_items=[
                {
                    "task": "Share the updated budget",
                    "assignee": "Speaker 1",
                    "deadline": "Today",
                    "status": "completed",
                    "source_excerpt": "I will share the updated budget today.",
                    "transcript_index": None,
                    "is_actionable": True,
                    "confidence": 0.9,
                    "owner_explicit": True,
                    "deadline_explicit": True,
                }
            ],
            risks=[],
        ),
    )

    history_service.create_meeting(
        meeting_id="hiring-1",
        scene="hr",
        target_lang="en",
        provider="demo",
    )
    history_service.update_metadata("hiring-1", MeetingMetadataUpdate(tags=["Hiring"]))
    history_service.update_summary(
        "hiring-1",
        MeetingSummary(
            title="Hiring Loop",
            overview="The team discussed interview feedback.",
            key_topics=["Hiring"],
            decisions=["Schedule final interview"],
            action_items=[],
            risks=[],
        ),
    )


def test_memory_overview_groups_meetings_and_tracks_cross_meeting_artifacts(tmp_path) -> None:
    history_service = MeetingHistoryService(tmp_path / "meeting_history.sqlite3")
    _seed_memory_meetings(history_service)

    overview = MeetingMemoryService(history_service).get_overview(collection_id="tag:Launch")

    assert overview.collection_id == "tag:Launch"
    assert {collection.collection_id for collection in overview.collections} >= {
        "all",
        "tag:Launch",
        "tag:Budget",
        "tag:Hiring",
        "scene:general",
        "scene:finance",
        "scene:hr",
    }
    assert overview.stats.meeting_count == 2
    assert overview.stats.open_action_count == 1
    assert overview.stats.completed_action_count == 1
    assert overview.stats.decision_count == 2
    assert overview.stats.risk_count == 2
    assert overview.stats.open_question_count == 1
    assert [item.task for item in overview.action_items] == [
        "Send the launch checklist",
        "Share the updated budget",
    ]
    assert overview.decisions[0].source.meeting_id in {"launch-1", "launch-2"}
    assert overview.open_questions[0].question == "Who owns support coverage?"
    assert "pending action items" in overview.next_meeting_brief.recap
    assert any("Confirm progress" in item for item in overview.next_meeting_brief.agenda)


def test_memory_api_returns_selected_collection(tmp_path) -> None:
    history_service = MeetingHistoryService(tmp_path / "meeting_history.sqlite3")
    _seed_memory_meetings(history_service)

    app = FastAPI()
    app.include_router(memory_router)
    app.state.meeting_memory_service = MeetingMemoryService(history_service)

    with TestClient(app) as client:
        response = client.get("/api/memory?collection_id=tag%3ALaunch")
        missing_response = client.get("/api/memory?collection_id=tag%3AMissing")

    assert response.status_code == 200
    payload = response.json()
    assert payload["collection_id"] == "tag:Launch"
    assert payload["stats"]["meeting_count"] == 2
    assert payload["action_items"][0]["source"]["meeting_id"] == "launch-1"
    assert missing_response.status_code == 404
