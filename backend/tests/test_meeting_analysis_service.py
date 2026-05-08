from __future__ import annotations

import asyncio

from app.schemas.transcript import TranscriptItem
from app.services.meeting_analysis_service import MeetingAnalysisService


class StubDashScopeClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.is_configured = True

    async def create_chat_completion(self, *, system_prompt: str, user_prompt: str) -> str:
        return self.response


def transcript(index: int, text: str) -> TranscriptItem:
    return TranscriptItem(
        transcript_index=index,
        speaker=f"Speaker {index + 1}",
        speaker_is_final=True,
        transcript_is_final=True,
        text=text,
        start=float(index),
        end=float(index + 1),
    )


def test_analysis_drops_request_sentence_misclassified_as_agreement() -> None:
    service = MeetingAnalysisService(
        StubDashScopeClient(
            """
            {
              "overall_sentiment": "neutral",
              "engagement_level": "medium",
              "engagement_summary": "The meeting is logistical.",
              "signal_counts": {"agreement": 1, "disagreement": 0, "tension": 0, "hesitation": 0},
              "highlights": [
                {
                  "transcript_index": 0,
                  "signal": "agreement",
                  "severity": "low",
                  "reason": "The speaker asks for help, implying cooperation."
                }
              ]
            }
            """
        )
    )

    analysis = asyncio.run(
        service.analyze_meeting(
            [transcript(0, "Will you help me set that up later?")],
            "general",
        )
    )

    assert analysis.highlights == []
    assert analysis.signal_counts.agreement == 0


def test_analysis_supplements_real_agreement_after_dropping_wrong_index() -> None:
    service = MeetingAnalysisService(
        StubDashScopeClient(
            """
            {
              "overall_sentiment": "neutral",
              "engagement_level": "medium",
              "engagement_summary": "The meeting is logistical.",
              "signal_counts": {"agreement": 1, "disagreement": 0, "tension": 0, "hesitation": 0},
              "highlights": [
                {
                  "transcript_index": 0,
                  "signal": "agreement",
                  "severity": "low",
                  "reason": "The speaker asks for help, implying cooperation."
                }
              ]
            }
            """
        )
    )

    analysis = asyncio.run(
        service.analyze_meeting(
            [
                transcript(0, "Will you help me set that up later?"),
                transcript(1, "I would rather get an alert. Yeah, of course."),
            ],
            "general",
        )
    )

    assert len(analysis.highlights) == 1
    assert analysis.highlights[0].transcript_index == 1
    assert analysis.highlights[0].signal.value == "agreement"
    assert analysis.signal_counts.agreement == 1


def test_analysis_recalculates_signal_counts_from_final_highlights() -> None:
    service = MeetingAnalysisService(
        StubDashScopeClient(
            """
            {
              "overall_sentiment": "mixed",
              "engagement_level": "high",
              "engagement_summary": "The meeting has several signals.",
              "signal_counts": {"agreement": 4, "disagreement": 2, "tension": 3, "hesitation": 1},
              "highlights": [
                {
                  "transcript_index": 0,
                  "signal": "disagreement",
                  "severity": "medium",
                  "reason": "Explicit disagreement."
                },
                {
                  "transcript_index": 1,
                  "signal": "agreement",
                  "severity": "low",
                  "reason": "Request incorrectly treated as agreement."
                },
                {
                  "transcript_index": 2,
                  "signal": "tension",
                  "severity": "high",
                  "reason": "Explicit risk."
                }
              ]
            }
            """
        )
    )

    analysis = asyncio.run(
        service.analyze_meeting(
            [
                transcript(0, "I disagree with that approach."),
                transcript(1, "Can you help me set that up?"),
                transcript(2, "The risk is high if we launch today."),
            ],
            "general",
        )
    )

    assert [(item.transcript_index, item.signal.value) for item in analysis.highlights] == [
        (0, "disagreement"),
        (2, "tension"),
    ]
    assert analysis.signal_counts.agreement == 0
    assert analysis.signal_counts.disagreement == 1
    assert analysis.signal_counts.tension == 1
    assert analysis.signal_counts.hesitation == 0


def test_analysis_adds_participant_rollups_from_highlights() -> None:
    service = MeetingAnalysisService(
        StubDashScopeClient(
            """
            {
              "overall_sentiment": "mixed",
              "engagement_level": "high",
              "engagement_summary": "The meeting has several signals.",
              "signal_counts": {"agreement": 1, "disagreement": 1, "tension": 0, "hesitation": 0},
              "highlights": [
                {
                  "transcript_index": 0,
                  "signal": "agreement",
                  "severity": "medium",
                  "reason": "Explicit agreement."
                },
                {
                  "transcript_index": 1,
                  "signal": "disagreement",
                  "severity": "medium",
                  "reason": "Explicit disagreement."
                }
              ]
            }
            """
        )
    )

    analysis = asyncio.run(
        service.analyze_meeting(
            [
                transcript(0, "I agree with the proposal."),
                transcript(1, "I disagree with the launch date."),
                transcript(2, "I will send the notes."),
            ],
            "general",
        )
    )

    assert [participant.speaker for participant in analysis.participants] == [
        "Speaker 1",
        "Speaker 2",
        "Speaker 3",
    ]
    assert analysis.participants[0].signal_counts.agreement == 1
    assert analysis.participants[1].signal_counts.disagreement == 1
    assert analysis.participants[2].signal_counts.agreement == 0
