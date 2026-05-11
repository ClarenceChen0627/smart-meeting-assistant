from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.schemas.glossary import GlossaryTermCreate, GlossaryTermRecord, GlossaryTermUpdate
from app.services.audit_log_service import AuditLogService
from app.services.glossary_store_service import GlossaryTermAlreadyExists, GlossaryTermNotFound

router = APIRouter()


def _audit_log_service(request: Request):
    return getattr(request.app.state, "audit_log_service", None)


@router.get("/api/glossary/terms", response_model=list[GlossaryTermRecord])
async def list_glossary_terms(request: Request) -> list[GlossaryTermRecord]:
    return request.app.state.glossary_store_service.list_terms()


@router.post("/api/glossary/terms", response_model=GlossaryTermRecord, status_code=status.HTTP_201_CREATED)
async def create_glossary_term(
    request: Request,
    payload: GlossaryTermCreate,
) -> GlossaryTermRecord:
    try:
        term = request.app.state.glossary_store_service.create_term(payload)
    except GlossaryTermAlreadyExists as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit_log_service = _audit_log_service(request)
    if audit_log_service is not None:
        audit_log_service.record_event(
            scope=AuditLogService.SCOPE_GLOBAL,
            entity_type="glossary_term",
            entity_id=term.id,
            action="create",
            field_path="glossary_terms",
            before=None,
            after=term.model_dump(),
            metadata={"manual": True},
        )
    return term


@router.patch("/api/glossary/terms/{term_id}", response_model=GlossaryTermRecord)
async def update_glossary_term(
    request: Request,
    term_id: str,
    payload: GlossaryTermUpdate,
) -> GlossaryTermRecord:
    before = request.app.state.glossary_store_service.get_term(term_id)
    try:
        term = request.app.state.glossary_store_service.update_term(term_id, payload)
    except GlossaryTermNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GlossaryTermAlreadyExists as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_log_service = _audit_log_service(request)
    if audit_log_service is not None:
        audit_log_service.record_event(
            scope=AuditLogService.SCOPE_GLOBAL,
            entity_type="glossary_term",
            entity_id=term.id,
            action="update",
            field_path="glossary_terms",
            before=before.model_dump() if before else None,
            after=term.model_dump(),
            metadata={"manual": True, "updated_fields": sorted(payload.model_fields_set)},
        )
    return term


@router.delete("/api/glossary/terms/{term_id}", status_code=204)
async def delete_glossary_term(request: Request, term_id: str) -> Response:
    before = request.app.state.glossary_store_service.get_term(term_id)
    deleted = request.app.state.glossary_store_service.delete_term(term_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Glossary term not found.")
    audit_log_service = _audit_log_service(request)
    if audit_log_service is not None:
        audit_log_service.record_event(
            scope=AuditLogService.SCOPE_GLOBAL,
            entity_type="glossary_term",
            entity_id=term_id,
            action="delete",
            field_path="glossary_terms",
            before=before.model_dump() if before else None,
            after=None,
            metadata={"manual": True},
        )
    return Response(status_code=204)
