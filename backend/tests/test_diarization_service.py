from __future__ import annotations

import asyncio

from app.core.config import Settings
from app.schemas.transcript import TranscriptSegment
from app.services.diarization_service import DiarizationService, DiarizationTurn
from app.services.speaker_service import SpeakerService


def build_service(**overrides: object) -> tuple[DiarizationService, SpeakerService]:
    settings = Settings(**overrides)
    speaker_service = SpeakerService()
    return DiarizationService(settings, speaker_service), speaker_service


def test_assign_speakers_normalizes_labels_in_first_appearance_order() -> None:
    diarization_service, speaker_service = build_service()
    transcripts = [
        speaker_service.assign_speaker(
            TranscriptSegment(text="alpha", start=0.0, end=1.0),
            transcript_index=0,
        ),
        speaker_service.assign_speaker(
            TranscriptSegment(text="beta", start=1.0, end=2.0),
            transcript_index=1,
        ),
        speaker_service.assign_speaker(
            TranscriptSegment(text="gamma", start=2.0, end=3.0),
            transcript_index=2,
        ),
    ]
    turns = [
        DiarizationTurn(start=0.0, end=1.0, speaker_label="SPEAKER_09"),
        DiarizationTurn(start=1.0, end=3.0, speaker_label="SPEAKER_03"),
    ]

    assigned = diarization_service.assign_speakers(transcripts, turns, speaker_is_final=True)

    assert [item.speaker for item in assigned] == ["Speaker 1", "Speaker 2", "Speaker 2"]
    assert all(item.speaker_is_final for item in assigned)


def test_assign_speakers_prefers_largest_overlap_then_earlier_turn() -> None:
    diarization_service, speaker_service = build_service()
    transcript = speaker_service.assign_speaker(
        TranscriptSegment(text="shared", start=1.0, end=3.0),
        transcript_index=0,
    )

    stronger_overlap = diarization_service.assign_speakers(
        [transcript],
        [
            DiarizationTurn(start=1.0, end=1.4, speaker_label="SPEAKER_00"),
            DiarizationTurn(start=1.2, end=2.8, speaker_label="SPEAKER_01"),
        ],
        speaker_is_final=True,
    )
    tie_break = diarization_service.assign_speakers(
        [transcript],
        [
            DiarizationTurn(start=1.0, end=2.0, speaker_label="SPEAKER_00"),
            DiarizationTurn(start=2.0, end=3.0, speaker_label="SPEAKER_01"),
        ],
        speaker_is_final=True,
    )

    assert stronger_overlap[0].speaker == "Speaker 1"
    assert tie_break[0].speaker == "Speaker 1"


def test_diarization_falls_back_when_disabled_or_missing_token() -> None:
    disabled_service, _ = build_service(diarization_mode="disabled")
    missing_token_service, _ = build_service(diarization_mode="offline", huggingface_token="")

    disabled_result = asyncio.run(disabled_service.diarize_audio_bytes(b"not-used"))
    missing_token_result = asyncio.run(missing_token_service.diarize_audio_bytes(b"not-used"))

    assert disabled_result.succeeded is False
    assert disabled_result.turns == []
    assert missing_token_result.succeeded is False
    assert missing_token_result.turns == []
