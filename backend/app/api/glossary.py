from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.schemas.glossary import GlossaryTermCreate, GlossaryTermRecord, GlossaryTermUpdate
from app.services.glossary_store_service import GlossaryTermAlreadyExists, GlossaryTermNotFound

router = APIRouter()


@router.get("/api/glossary/terms", response_model=list[GlossaryTermRecord])
async def list_glossary_terms(request: Request) -> list[GlossaryTermRecord]:
    return request.app.state.glossary_store_service.list_terms()


@router.post("/api/glossary/terms", response_model=GlossaryTermRecord, status_code=status.HTTP_201_CREATED)
async def create_glossary_term(
    request: Request,
    payload: GlossaryTermCreate,
) -> GlossaryTermRecord:
    try:
        return request.app.state.glossary_store_service.create_term(payload)
    except GlossaryTermAlreadyExists as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch("/api/glossary/terms/{term_id}", response_model=GlossaryTermRecord)
async def update_glossary_term(
    request: Request,
    term_id: str,
    payload: GlossaryTermUpdate,
) -> GlossaryTermRecord:
    try:
        return request.app.state.glossary_store_service.update_term(term_id, payload)
    except GlossaryTermNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GlossaryTermAlreadyExists as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/glossary/terms/{term_id}", status_code=204)
async def delete_glossary_term(request: Request, term_id: str) -> Response:
    deleted = request.app.state.glossary_store_service.delete_term(term_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Glossary term not found.")
    return Response(status_code=204)
