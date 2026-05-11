from __future__ import annotations

from time import perf_counter
from uuid import uuid4

from fastapi import Request

from app.core.logging import reset_request_id, set_request_id
from app.services.observability_service import ObservabilityService


REQUEST_ID_HEADER = "X-Request-ID"


async def observability_middleware(request: Request, call_next):
    request_id = request.headers.get(REQUEST_ID_HEADER) or uuid4().hex
    token = set_request_id(request_id)
    started_at = perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
    finally:
        latency_seconds = perf_counter() - started_at
        observability_service: ObservabilityService | None = getattr(
            request.app.state,
            "observability_service",
            None,
        )
        if observability_service is not None:
            observability_service.record_request(
                status_code=status_code,
                latency_seconds=latency_seconds,
            )
        reset_request_id(token)
