from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel


class WebSocketMessageType(str, Enum):
    TRANSCRIPT = "transcript"
    TRANSLATION = "translation"
    SUMMARY = "summary"
    ERROR = "error"


class WebSocketMessage(BaseModel):
    type: WebSocketMessageType
    data: Any


class FinalizeControlMessage(BaseModel):
    type: Literal["finalize"]
