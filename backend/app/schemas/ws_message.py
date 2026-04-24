from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel


class WebSocketMessageType(str, Enum):
    TRANSCRIPT = "transcript"
    TRANSCRIPT_UPDATE = "transcript_update"
    SPEAKER_UPDATE = "speaker_update"
    TRANSLATION = "translation"
    ANALYSIS = "analysis"
    SUMMARY = "summary"
    ERROR = "error"


class WebSocketMessage(BaseModel):
    type: WebSocketMessageType
    data: Any


class FinalizeControlMessage(BaseModel):
    type: Literal["finalize"]


class SpeakerUpdate(BaseModel):
    transcript_index: int
    speaker: str
    speaker_is_final: bool = True
