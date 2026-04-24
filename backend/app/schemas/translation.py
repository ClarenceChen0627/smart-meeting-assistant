from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class TranscriptTranslation(BaseModel):
    transcript_index: int
    target_lang: Literal["en", "es", "fr", "de", "zh", "ja", "ko", "pt", "ar", "hi"]
    text: str
