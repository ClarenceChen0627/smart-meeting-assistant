from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.schemas.memory import MeetingMemoryOverview

router = APIRouter()


@router.get("/api/memory", response_model=MeetingMemoryOverview)
async def get_meeting_memory(
    request: Request,
    collection_id: str | None = Query(None),
    archived: bool | None = Query(False),
) -> MeetingMemoryOverview:
    try:
        return request.app.state.meeting_memory_service.get_overview(
            collection_id=collection_id,
            archived=archived,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
