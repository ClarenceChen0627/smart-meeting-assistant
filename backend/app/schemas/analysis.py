from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class MeetingSignalType(str, Enum):
    AGREEMENT = "agreement"
    DISAGREEMENT = "disagreement"
    TENSION = "tension"
    HESITATION = "hesitation"


class MeetingSentimentLevel(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    MIXED = "mixed"


class MeetingEngagementLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class MeetingSignalCounts(BaseModel):
    agreement: int = 0
    disagreement: int = 0
    tension: int = 0
    hesitation: int = 0


class MeetingAnalysisHighlight(BaseModel):
    transcript_index: int
    signal: MeetingSignalType
    severity: str
    reason: str


class MeetingAnalysis(BaseModel):
    overall_sentiment: MeetingSentimentLevel = MeetingSentimentLevel.NEUTRAL
    engagement_level: MeetingEngagementLevel = MeetingEngagementLevel.LOW
    engagement_summary: str = ""
    signal_counts: MeetingSignalCounts = Field(default_factory=MeetingSignalCounts)
    highlights: list[MeetingAnalysisHighlight] = Field(default_factory=list)

    @classmethod
    def empty(cls) -> "MeetingAnalysis":
        return cls(
            overall_sentiment=MeetingSentimentLevel.NEUTRAL,
            engagement_level=MeetingEngagementLevel.LOW,
            engagement_summary="Analysis pending.",
        )
