from __future__ import annotations

from app.clients.dashscope_client import DashScopeClient


class TranslationService:
    SUPPORTED_TARGET_LANGUAGES = {
        "en": "English",
        "es": "Spanish",
        "fr": "French",
        "de": "German",
        "zh": "Chinese",
        "ja": "Japanese",
        "ko": "Korean",
        "pt": "Portuguese",
        "ar": "Arabic",
        "hi": "Hindi",
    }

    def __init__(self, dashscope_client: DashScopeClient) -> None:
        self._dashscope_client = dashscope_client

    @property
    def is_configured(self) -> bool:
        return self._dashscope_client.is_configured

    def normalize_target_lang(self, target_lang: str | None) -> str | None:
        if target_lang is None:
            return None
        normalized = target_lang.strip().lower()
        if not normalized:
            return None
        if normalized not in self.SUPPORTED_TARGET_LANGUAGES:
            return None
        return normalized

    async def translate_text(self, *, text: str, target_lang: str) -> str:
        normalized = self.normalize_target_lang(target_lang)
        if normalized is None:
            raise ValueError(f"Unsupported translation target language: {target_lang}")
        if not text.strip():
            return ""
        return await self._dashscope_client.translate_text(
            text=text,
            source_lang="auto",
            target_lang=self.SUPPORTED_TARGET_LANGUAGES[normalized],
        )
