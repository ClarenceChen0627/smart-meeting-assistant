from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class TranscriptTranslation(BaseModel):
    transcript_index: int
    target_lang: Literal["en", "ja", "ko"]
    text: str
