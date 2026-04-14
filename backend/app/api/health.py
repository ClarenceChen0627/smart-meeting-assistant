from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/api/health")
async def health(request: Request) -> dict:
    settings = request.app.state.settings
    return {
        "status": "UP",
        "service": settings.service_name,
        "version": settings.service_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "providers": {
            "asrConfigured": settings.asr_configured,
            "llmConfigured": settings.llm_configured,
        },
    }
