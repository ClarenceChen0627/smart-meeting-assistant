from __future__ import annotations

from pydantic import BaseModel, Field


class MeetingSummary(BaseModel):
    todos: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)

    @classmethod
    def empty(cls) -> "MeetingSummary":
        return cls()
