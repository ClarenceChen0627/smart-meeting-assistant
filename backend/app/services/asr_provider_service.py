from __future__ import annotations

import logging
from dataclasses import dataclass

from app.clients.asr_base import ASRClient
from app.core.config import Settings

logger = logging.getLogger(__name__)

ASR_PROVIDER_DASHSCOPE = "dashscope"
ASR_PROVIDER_VOLCENGINE = "volcengine"
ASR_PROVIDER_DEMO = "demo"
SUPPORTED_ASR_PROVIDERS = {
    ASR_PROVIDER_DASHSCOPE,
    ASR_PROVIDER_VOLCENGINE,
    ASR_PROVIDER_DEMO,
}


@dataclass(frozen=True)
class ASRProviderSelection:
    provider_name: str
    client: ASRClient
    should_run_diarization: bool
    should_run_realtime_diarization: bool


class ASRProviderService:
    def __init__(
        self,
        *,
        settings: Settings,
        dashscope_client: ASRClient,
        volcengine_client: ASRClient,
        demo_client: ASRClient | None = None,
    ) -> None:
        self._settings = settings
        self._clients: dict[str, ASRClient] = {
            ASR_PROVIDER_DASHSCOPE: dashscope_client,
            ASR_PROVIDER_VOLCENGINE: volcengine_client,
        }
        if demo_client is not None:
            self._clients[ASR_PROVIDER_DEMO] = demo_client

    def resolve_provider(self, preferred_provider: str | None) -> ASRProviderSelection:
        preferred = self.normalize_provider(preferred_provider) or self._settings.default_asr_provider
        if preferred == ASR_PROVIDER_DEMO and ASR_PROVIDER_DEMO in self._clients:
            return self._build_selection(ASR_PROVIDER_DEMO)

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

    def provider_statuses(self) -> list[dict[str, str | bool]]:
        return [
            {
                "provider": provider_name,
                "configured": client.is_configured,
            }
            for provider_name, client in self._clients.items()
        ]

    def available_provider_names(self) -> list[str]:
        return [
            provider_name
            for provider_name, client in self._clients.items()
            if client.is_configured
        ]

    def _build_selection(self, provider_name: str) -> ASRProviderSelection:
        client = self._clients[provider_name]
        is_dashscope = provider_name == ASR_PROVIDER_DASHSCOPE
        is_paraformer_realtime = self._settings.dashscope_asr_model.strip().lower() == "paraformer-realtime-v1"
        return ASRProviderSelection(
            provider_name=provider_name,
            client=client,
            should_run_diarization=is_dashscope and self._settings.diarization_enabled,
            should_run_realtime_diarization=(
                is_dashscope
                and is_paraformer_realtime
                and self._settings.realtime_diarization_enabled
            ),
        )

    def _candidate_order(self, preferred: str) -> list[str]:
        ordered = [preferred]
        if ASR_PROVIDER_DASHSCOPE not in ordered:
            ordered.append(ASR_PROVIDER_DASHSCOPE)
        if ASR_PROVIDER_VOLCENGINE not in ordered:
            ordered.append(ASR_PROVIDER_VOLCENGINE)
        if self._settings.demo_mode and ASR_PROVIDER_DEMO in self._clients and ASR_PROVIDER_DEMO not in ordered:
            ordered.append(ASR_PROVIDER_DEMO)
        return ordered
