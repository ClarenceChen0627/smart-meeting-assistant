from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.analysis import MeetingAnalysis
from app.schemas.summary import MeetingSummary
from app.schemas.transcript import TranscriptItem


class MeetingHistoryStatus(str, Enum):
    DRAFT = "draft"
    PROCESSING = "processing"
    FAILED = "failed"
    FINALIZED = "finalized"


class MeetingSourceType(str, Enum):
    LIVE = "live"
    UPLOAD = "upload"


class MeetingProcessingStage(str, Enum):
    TRANSCRIBING = "transcribing"
    TRANSLATING = "translating"
    ANALYZING = "analyzing"
    SUMMARIZING = "summarizing"


class SessionStarted(BaseModel):
    meeting_id: str
    status: MeetingHistoryStatus
    created_at: str
    scene: str
    target_lang: str | None = None
    provider: str
    source_type: MeetingSourceType = MeetingSourceType.LIVE


class MeetingHistoryListItem(BaseModel):
    meeting_id: str
    status: MeetingHistoryStatus
    source_type: MeetingSourceType = MeetingSourceType.LIVE
    scene: str
    target_lang: str | None = None
    provider: str
    created_at: str
    updated_at: str
    title: str = ""
    title_manually_edited: bool = False
    summary_manually_edited: bool = False
    transcript_count: int = 0
    preview_text: str = ""
    processing_stage: MeetingProcessingStage | None = None
    error_message: str | None = None
    source_name: str | None = None


class MeetingHistoryTranscriptItem(TranscriptItem):
    translated_text: str | None = None
    translated_target_lang: str | None = None


class MeetingRecord(BaseModel):
    meeting_id: str
    status: MeetingHistoryStatus
    source_type: MeetingSourceType = MeetingSourceType.LIVE
    scene: str
    target_lang: str | None = None
    provider: str
    created_at: str
    updated_at: str
    title: str = ""
    title_manually_edited: bool = False
    summary_manually_edited: bool = False
    transcript_count: int = 0
    preview_text: str = ""
    processing_stage: MeetingProcessingStage | None = None
    error_message: str | None = None
    source_name: str | None = None
    transcripts: list[MeetingHistoryTranscriptItem] = Field(default_factory=list)
    summary: MeetingSummary | None = None
    analysis: MeetingAnalysis | None = None


class MeetingTitleUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=80)
