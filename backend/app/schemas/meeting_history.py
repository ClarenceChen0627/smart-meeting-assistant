from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.analysis import MeetingAnalysis
from app.schemas.summary import MeetingSummary
from app.schemas.transcript import TranscriptItem


class MeetingHistoryStatus(str, Enum):
    DRAFT = "draft"
    FINALIZED = "finalized"


class SessionStarted(BaseModel):
    meeting_id: str
    status: MeetingHistoryStatus
    created_at: str
    scene: str
    target_lang: str | None = None
    provider: str


class MeetingHistoryListItem(BaseModel):
    meeting_id: str
    status: MeetingHistoryStatus
    scene: str
    target_lang: str | None = None
    provider: str
    created_at: str
    updated_at: str
    transcript_count: int = 0
    preview_text: str = ""


class MeetingHistoryTranscriptItem(TranscriptItem):
    translated_text: str | None = None
    translated_target_lang: str | None = None


class MeetingRecord(BaseModel):
    meeting_id: str
    status: MeetingHistoryStatus
    scene: str
    target_lang: str | None = None
    provider: str
    created_at: str
    updated_at: str
    transcript_count: int = 0
    preview_text: str = ""
    transcripts: list[MeetingHistoryTranscriptItem] = Field(default_factory=list)
    summary: MeetingSummary | None = None
    analysis: MeetingAnalysis | None = None
