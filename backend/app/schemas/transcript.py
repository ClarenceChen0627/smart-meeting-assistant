from __future__ import annotations

from pydantic import BaseModel


class TranscriptSegment(BaseModel):
    text: str
    start: float
    end: float


class TranscriptItem(TranscriptSegment):
    speaker: str
