from __future__ import annotations

from pydantic import BaseModel


class TranscriptSegment(BaseModel):
    text: str
    start: float
    end: float


class TranscriptItem(TranscriptSegment):
    transcript_index: int
    speaker: str
    speaker_is_final: bool = False
    transcript_is_final: bool = True
