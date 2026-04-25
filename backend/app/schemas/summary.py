from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ActionItem(BaseModel):
    task: str
    assignee: str = "Unassigned"
    deadline: str = "Not specified"
    status: Literal["pending", "completed"] = "pending"
    source_excerpt: str = ""
    transcript_index: int | None = None
    is_actionable: bool = True
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    owner_explicit: bool = False
    deadline_explicit: bool = False


class MeetingSummary(BaseModel):
    overview: str = ""
    key_topics: list[str] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)

    @classmethod
    def empty(cls) -> "MeetingSummary":
        return cls()
