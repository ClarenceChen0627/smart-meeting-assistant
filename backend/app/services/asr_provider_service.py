from __future__ import annotations

import logging
from dataclasses import dataclass

from app.clients.asr_base import ASRClient
from app.core.config import Settings

logger = logging.getLogger(__name__)

ASR_PROVIDER_DASHSCOPE = "dashscope"
ASR_PROVIDER_VOLCENGINE = "volcengine"
SUPPORTED_ASR_PROVIDERS = {
    ASR_PROVIDER_DASHSCOPE,
    ASR_PROVIDER_VOLCENGINE,
}


@dataclass(frozen=True)
class ASRProviderSelection:
    provider_name: str
    client: ASRClient
    should_run_diarization: bool


class ASRProviderService:
    def __init__(
        self,
        *,
        settings: Settings,
        dashscope_client: ASRClient,
        volcengine_client: ASRClient,
    ) -> None:
        self._settings = settings
        self._clients: dict[str, ASRClient] = {
            ASR_PROVIDER_DASHSCOPE: dashscope_client,
            ASR_PROVIDER_VOLCENGINE: volcengine_client,
        }

    def resolve_provider(self, preferred_provider: str | None) -> ASRProviderSelection:
        preferred = self.normalize_provider(preferred_provider) or self._settings.default_asr_provider
        for provider_name in self._candidate_order(preferred):
            client = self._clients.get(provider_name)
            if client is None:
                continue
            if client.is_configured:
                return self._build_selection(provider_name)

        fallback_provider = preferred if preferred in self._clients else ASR_PROVIDER_DASHSCOPE
        return self._build_selection(fallback_provider)

    def resolve_fallback(self, current_provider: str) -> ASRProviderSelection | None:
        if current_provider != ASR_PROVIDER_DASHSCOPE:
            dashscope = self._clients.get(ASR_PROVIDER_DASHSCOPE)
            if dashscope is not None and dashscope.is_configured:
                logger.warning("Falling back to DashScope ASR after provider %s failed.", current_provider)
                return self._build_selection(ASR_PROVIDER_DASHSCOPE)
        return None

    def normalize_provider(self, provider: str | None) -> str | None:
        if provider is None:
            return None
        normalized = provider.strip().lower()
        if normalized in SUPPORTED_ASR_PROVIDERS:
            return normalized
        return None

    def _build_selection(self, provider_name: str) -> ASRProviderSelection:
        client = self._clients[provider_name]
        return ASRProviderSelection(
            provider_name=provider_name,
            client=client,
            should_run_diarization=provider_name == ASR_PROVIDER_DASHSCOPE and self._settings.diarization_enabled,
        )

    def _candidate_order(self, preferred: str) -> list[str]:
        ordered = [preferred]
        if ASR_PROVIDER_DASHSCOPE not in ordered:
            ordered.append(ASR_PROVIDER_DASHSCOPE)
        if ASR_PROVIDER_VOLCENGINE not in ordered:
            ordered.append(ASR_PROVIDER_VOLCENGINE)
        return ordered
