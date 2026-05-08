from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class GlossaryTerm(BaseModel):
    term: str = Field(min_length=1, max_length=80)
    replacement: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=160)

    @field_validator("term", "replacement", "note", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        normalized = " ".join(value.split()).strip()
        return normalized or None
