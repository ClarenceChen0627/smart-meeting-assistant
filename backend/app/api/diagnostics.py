from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/api/diagnostics")
async def diagnostics(request: Request) -> dict:
    settings = request.app.state.settings
    observability_service = request.app.state.observability_service
    upload_queue_store = request.app.state.upload_queue_store
    asr_provider_service = getattr(request.app.state, "asr_provider_service", None)
    return observability_service.snapshot(
        service_name=settings.service_name,
        service_version=settings.service_version,
        demo_mode=settings.demo_mode,
        provider_statuses=(
            asr_provider_service.provider_statuses()
            if asr_provider_service is not None
            else []
        ),
        upload_queue=upload_queue_store.diagnostics_snapshot(
            processing_timeout_seconds=settings.upload_queue_processing_timeout_seconds
        ),
    )
