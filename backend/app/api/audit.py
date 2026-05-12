from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.schemas.audit import AuditEventRecord

router = APIRouter()


@router.get("/api/meetings/{meeting_id}/audit-events", response_model=list[AuditEventRecord])
async def list_meeting_audit_events(
    request: Request,
    meeting_id: str,
    limit: int = Query(100, ge=1, le=500),
) -> list[AuditEventRecord]:
    return request.app.state.audit_log_service.list_meeting_events(meeting_id, limit=limit)


@router.get("/api/audit-events", response_model=list[AuditEventRecord])
async def list_audit_events(
    request: Request,
    scope: str | None = Query(None),
    meeting_id: str | None = Query(None),
    entity_type: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> list[AuditEventRecord]:
    return request.app.state.audit_log_service.list_events(
        scope=scope,
        meeting_id=meeting_id,
        entity_type=entity_type,
        limit=limit,
    )
