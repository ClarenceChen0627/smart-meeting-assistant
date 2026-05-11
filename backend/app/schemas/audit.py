from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AuditEventRecord(BaseModel):
    id: str
    scope: str
    meeting_id: str | None = None
    entity_type: str
    entity_id: str | None = None
    action: str
    field_path: str | None = None
    before: Any = None
    after: Any = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
