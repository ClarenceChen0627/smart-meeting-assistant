from __future__ import annotations

from pydantic import BaseModel, Field, model_validator, field_validator


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


class GlossaryTermCreate(GlossaryTerm):
    pass


class GlossaryTermUpdate(BaseModel):
    term: str | None = Field(default=None, min_length=1, max_length=80)
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

    @model_validator(mode="after")
    def require_one_field(self) -> "GlossaryTermUpdate":
        fields_set = self.model_fields_set
        if not fields_set:
            raise ValueError("At least one glossary field must be provided.")
        return self


class GlossaryTermRecord(GlossaryTerm):
    id: str
    created_at: str
    updated_at: str
