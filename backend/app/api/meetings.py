from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile, status

from app.schemas.meeting_history import MeetingHistoryListItem, MeetingRecord, MeetingTitleUpdate
from app.schemas.summary import ActionItemStatusUpdate, SummaryUpdate

router = APIRouter()


@router.post("/api/meetings/upload", response_model=MeetingRecord, status_code=status.HTTP_202_ACCEPTED)
async def upload_meeting(
    request: Request,
    file: UploadFile = File(...),
    scene: str = Form("general"),
    target_lang: str | None = Form(None),
    provider: str | None = Form(None),
) -> MeetingRecord:
    audio_data = await file.read()
    try:
        return await request.app.state.upload_meeting_service.start_upload(
            audio_data=audio_data,
            filename=file.filename,
            content_type=file.content_type,
            scene=scene,
            target_lang=target_lang,
            preferred_provider=provider,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/meetings", response_model=list[MeetingHistoryListItem])
async def list_meetings(request: Request) -> list[MeetingHistoryListItem]:
    return request.app.state.meeting_history_service.list_meetings()


@router.get("/api/meetings/{meeting_id}", response_model=MeetingRecord)
async def get_meeting(request: Request, meeting_id: str) -> MeetingRecord:
    meeting = request.app.state.meeting_history_service.get_meeting(meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting record not found.")
    return meeting


@router.patch("/api/meetings/{meeting_id}/title", response_model=MeetingRecord)
async def update_meeting_title(
    request: Request,
    meeting_id: str,
    payload: MeetingTitleUpdate,
) -> MeetingRecord:
    try:
        meeting = request.app.state.meeting_history_service.update_title(
            meeting_id,
            payload.title,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting record not found.")
    return meeting


@router.patch("/api/meetings/{meeting_id}/summary", response_model=MeetingRecord)
async def update_meeting_summary(
    request: Request,
    meeting_id: str,
    payload: SummaryUpdate,
) -> MeetingRecord:
    try:
        meeting = request.app.state.meeting_history_service.update_summary_fields(
            meeting_id,
            payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting record not found.")
    return meeting


@router.patch("/api/meetings/{meeting_id}/action-items/{action_item_index}", response_model=MeetingRecord)
async def update_action_item_status(
    request: Request,
    meeting_id: str,
    action_item_index: int,
    payload: ActionItemStatusUpdate,
) -> MeetingRecord:
    try:
        meeting = request.app.state.meeting_history_service.update_action_item_status(
            meeting_id,
            action_item_index,
            payload.status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IndexError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting record not found.")
    return meeting


@router.delete("/api/meetings/{meeting_id}", status_code=204)
async def delete_meeting(request: Request, meeting_id: str) -> Response:
    deleted = request.app.state.meeting_history_service.delete_meeting(meeting_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Meeting record not found.")
    return Response(status_code=204)
