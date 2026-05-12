from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.meeting_history import MeetingSourceType
from app.schemas.summary import ActionItemStatus


MemoryCollectionType = Literal["all", "tag", "scene"]


class MemoryMeetingReference(BaseModel):
    meeting_id: str
    title: str
    created_at: str
    updated_at: str
    scene: str
    source_type: MeetingSourceType
    tags: list[str] = Field(default_factory=list)


class MemorySourceReference(MemoryMeetingReference):
    transcript_index: int | None = None
    source_excerpt: str = ""


class MemoryCollection(BaseModel):
    collection_id: str
    collection_type: MemoryCollectionType
    name: str
    meeting_count: int = 0
    finalized_count: int = 0
    open_action_count: int = 0
    completed_action_count: int = 0
    decision_count: int = 0
    risk_count: int = 0
    open_question_count: int = 0
    updated_at: str | None = None


class MemoryStats(BaseModel):
    meeting_count: int = 0
    finalized_count: int = 0
    action_count: int = 0
    open_action_count: int = 0
    completed_action_count: int = 0
    decision_count: int = 0
    risk_count: int = 0
    open_question_count: int = 0


class MemoryActionItem(BaseModel):
    id: str
    action_item_index: int
    task: str
    assignee: str
    deadline: str
    status: ActionItemStatus
    source_excerpt: str = ""
    confidence: float = 0.5
    owner_explicit: bool = False
    deadline_explicit: bool = False
    source: MemorySourceReference


class MemoryDecisionItem(BaseModel):
    id: str
    decision: str
    source: MemorySourceReference


class MemoryRiskItem(BaseModel):
    id: str
    risk: str
    source: MemorySourceReference


class MemoryOpenQuestionItem(BaseModel):
    id: str
    question: str
    source: MemorySourceReference


class NextMeetingBrief(BaseModel):
    collection_id: str
    collection_name: str
    generated_at: str
    recap: str
    agenda: list[str] = Field(default_factory=list)
    suggested_focus: list[str] = Field(default_factory=list)
    recent_meetings: list[MemoryMeetingReference] = Field(default_factory=list)


class MeetingMemoryOverview(BaseModel):
    collection_id: str
    generated_at: str
    collections: list[MemoryCollection] = Field(default_factory=list)
    stats: MemoryStats = Field(default_factory=MemoryStats)
    action_items: list[MemoryActionItem] = Field(default_factory=list)
    decisions: list[MemoryDecisionItem] = Field(default_factory=list)
    risks: list[MemoryRiskItem] = Field(default_factory=list)
    open_questions: list[MemoryOpenQuestionItem] = Field(default_factory=list)
    next_meeting_brief: NextMeetingBrief
