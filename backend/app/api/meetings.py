from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from app.schemas.meeting_history import MeetingHistoryListItem, MeetingRecord

router = APIRouter()


@router.get("/api/meetings", response_model=list[MeetingHistoryListItem])
async def list_meetings(request: Request) -> list[MeetingHistoryListItem]:
    return request.app.state.meeting_history_service.list_meetings()


@router.get("/api/meetings/{meeting_id}", response_model=MeetingRecord)
async def get_meeting(request: Request, meeting_id: str) -> MeetingRecord:
    meeting = request.app.state.meeting_history_service.get_meeting(meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting record not found.")
    return meeting


@router.delete("/api/meetings/{meeting_id}", status_code=204)
async def delete_meeting(request: Request, meeting_id: str) -> Response:
    deleted = request.app.state.meeting_history_service.delete_meeting(meeting_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Meeting record not found.")
    return Response(status_code=204)
