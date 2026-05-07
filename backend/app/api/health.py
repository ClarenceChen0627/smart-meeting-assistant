from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/api/health")
async def health(request: Request) -> dict:
    settings = request.app.state.settings
    asr_provider_service = getattr(request.app.state, "asr_provider_service", None)
    return {
        "status": "UP",
        "service": settings.service_name,
        "version": settings.service_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "demoMode": settings.demo_mode,
        "providers": {
            "asrConfigured": settings.asr_configured,
            "llmConfigured": settings.llm_configured,
            "availableAsrProviders": (
                asr_provider_service.available_provider_names()
                if asr_provider_service is not None
                else []
            ),
            "asrProviderStatuses": (
                asr_provider_service.provider_statuses()
                if asr_provider_service is not None
                else []
            ),
        },
    }
