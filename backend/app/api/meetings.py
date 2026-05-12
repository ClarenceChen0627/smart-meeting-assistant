from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, Response, UploadFile, status

from app.api.upload_validation import read_validated_upload
from app.core.config import settings as default_settings
from app.schemas.meeting_history import (
    MeetingHistoryListItem,
    MeetingMetadataUpdate,
    MeetingRecord,
    MeetingSpeakerUpdate,
    MeetingTitleUpdate,
)
from app.schemas.summary import ActionItemStatusUpdate, SummaryUpdate
from app.services.audit_log_service import AuditLogService

router = APIRouter()


def _audit_log_service(request: Request):
    return getattr(request.app.state, "audit_log_service", None)


@router.post("/api/meetings/upload", response_model=MeetingRecord, status_code=status.HTTP_202_ACCEPTED)
async def upload_meeting(
    request: Request,
    file: UploadFile = File(...),
    scene: str = Form("general"),
    target_lang: str | None = Form(None),
    provider: str | None = Form(None),
    retain_raw_audio: bool = Form(False),
    glossary_terms: str | None = Form(None),
) -> MeetingRecord:
    runtime_settings = getattr(request.app.state, "settings", default_settings)
    audio_data = await read_validated_upload(file, runtime_settings)
    try:
        return await request.app.state.upload_meeting_service.start_upload(
            audio_data=audio_data,
            filename=file.filename,
            content_type=file.content_type,
            scene=scene,
            target_lang=target_lang,
            preferred_provider=provider,
            retain_raw_audio=retain_raw_audio,
            glossary_terms=glossary_terms,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/meetings", response_model=list[MeetingHistoryListItem])
async def list_meetings(
    request: Request,
    q: str | None = Query(None),
    status: str | None = Query(None),
    source_type: str | None = Query(None),
    provider: str | None = Query(None),
    scene: str | None = Query(None),
    favorite: bool | None = Query(None),
    archived: bool | None = Query(False),
    tag: str | None = Query(None),
) -> list[MeetingHistoryListItem]:
    return request.app.state.meeting_history_service.list_meetings(
        q=q,
        status=status,
        source_type=source_type,
        provider=provider,
        scene=scene,
        favorite=favorite,
        archived=archived,
        tag=tag,
    )


@router.get("/api/meetings/{meeting_id}", response_model=MeetingRecord)
async def get_meeting(request: Request, meeting_id: str) -> MeetingRecord:
    meeting = request.app.state.meeting_history_service.get_meeting(meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting record not found.")
    return meeting


@router.patch("/api/meetings/{meeting_id}/metadata", response_model=MeetingRecord)
async def update_meeting_metadata(
    request: Request,
    meeting_id: str,
    payload: MeetingMetadataUpdate,
) -> MeetingRecord:
    before_meeting = request.app.state.meeting_history_service.get_meeting(meeting_id)
    try:
        meeting = request.app.state.meeting_history_service.update_metadata(meeting_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting record not found.")
    audit_log_service = _audit_log_service(request)
    if audit_log_service is not None:
        audit_log_service.record_event(
            scope=AuditLogService.SCOPE_MEETING,
            meeting_id=meeting_id,
            entity_type="meeting",
            entity_id=meeting_id,
            action="update",
            field_path="metadata",
            before={
                "favorite": before_meeting.favorite if before_meeting else None,
                "archived": before_meeting.archived if before_meeting else None,
                "tags": before_meeting.tags if before_meeting else None,
            },
            after={
                "favorite": meeting.favorite,
                "archived": meeting.archived,
                "tags": meeting.tags,
            },
            metadata={"manual": True, "updated_fields": sorted(payload.model_fields_set)},
        )
    return meeting


@router.patch("/api/meetings/{meeting_id}/title", response_model=MeetingRecord)
async def update_meeting_title(
    request: Request,
    meeting_id: str,
    payload: MeetingTitleUpdate,
) -> MeetingRecord:
    before_meeting = request.app.state.meeting_history_service.get_meeting(meeting_id)
    try:
        meeting = request.app.state.meeting_history_service.update_title(
            meeting_id,
            payload.title,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting record not found.")
    audit_log_service = _audit_log_service(request)
    if audit_log_service is not None:
        audit_log_service.record_event(
            scope=AuditLogService.SCOPE_MEETING,
            meeting_id=meeting_id,
            entity_type="meeting",
            entity_id=meeting_id,
            action="update",
            field_path="title",
            before=before_meeting.title if before_meeting else None,
            after=meeting.title,
            metadata={"manual": True},
        )
    return meeting


@router.patch("/api/meetings/{meeting_id}/summary", response_model=MeetingRecord)
async def update_meeting_summary(
    request: Request,
    meeting_id: str,
    payload: SummaryUpdate,
) -> MeetingRecord:
    before_meeting = request.app.state.meeting_history_service.get_meeting(meeting_id)
    try:
        meeting = request.app.state.meeting_history_service.update_summary_fields(
            meeting_id,
            payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting record not found.")
    audit_log_service = _audit_log_service(request)
    if audit_log_service is not None:
        audit_log_service.record_event(
            scope=AuditLogService.SCOPE_MEETING,
            meeting_id=meeting_id,
            entity_type="summary",
            entity_id=meeting_id,
            action="update",
            field_path="summary",
            before=before_meeting.summary.model_dump() if before_meeting and before_meeting.summary else None,
            after=meeting.summary.model_dump() if meeting.summary else None,
            metadata={"manual": True},
        )
    return meeting


@router.patch("/api/meetings/{meeting_id}/speakers", response_model=MeetingRecord)
async def update_meeting_speakers(
    request: Request,
    meeting_id: str,
    payload: MeetingSpeakerUpdate,
) -> MeetingRecord:
    before_meeting = request.app.state.meeting_history_service.get_meeting(meeting_id)
    try:
        meeting = request.app.state.meeting_history_service.update_speakers(
            meeting_id,
            payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting record not found.")
    before_labels = [item.speaker for item in before_meeting.transcripts] if before_meeting else []
    after_labels = [item.speaker for item in meeting.transcripts]
    affected_count = sum(
        1
        for index, before_label in enumerate(before_labels)
        if index < len(after_labels) and before_label != after_labels[index]
    )
    audit_log_service = _audit_log_service(request)
    if audit_log_service is not None:
        audit_log_service.record_event(
            scope=AuditLogService.SCOPE_MEETING,
            meeting_id=meeting_id,
            entity_type="speaker",
            entity_id=meeting_id,
            action="update",
            field_path="transcripts.speaker",
            before={"speakers": sorted(set(before_labels))},
            after={"speakers": sorted(set(after_labels))},
            metadata={
                "speaker_updates": [update.model_dump(by_alias=True) for update in payload.speaker_updates],
                "affected_transcript_count": affected_count,
                "merge_count": len(payload.speaker_updates) - len({update.to for update in payload.speaker_updates}),
            },
        )
    return meeting


@router.patch("/api/meetings/{meeting_id}/action-items/{action_item_index}", response_model=MeetingRecord)
async def update_action_item_status(
    request: Request,
    meeting_id: str,
    action_item_index: int,
    payload: ActionItemStatusUpdate,
) -> MeetingRecord:
    before_meeting = request.app.state.meeting_history_service.get_meeting(meeting_id)
    before_item = (
        before_meeting.summary.action_items[action_item_index].model_dump()
        if before_meeting
        and before_meeting.summary
        and 0 <= action_item_index < len(before_meeting.summary.action_items)
        else None
    )
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
    after_item = (
        meeting.summary.action_items[action_item_index].model_dump()
        if meeting.summary and 0 <= action_item_index < len(meeting.summary.action_items)
        else None
    )
    audit_log_service = _audit_log_service(request)
    if audit_log_service is not None:
        audit_log_service.record_event(
            scope=AuditLogService.SCOPE_MEETING,
            meeting_id=meeting_id,
            entity_type="action_item",
            entity_id=str(action_item_index),
            action="update",
            field_path=f"summary.action_items[{action_item_index}].status",
            before=before_item,
            after=after_item,
            metadata={"action_item_index": action_item_index},
        )
    return meeting


@router.delete("/api/meetings/{meeting_id}", status_code=204)
async def delete_meeting(request: Request, meeting_id: str) -> Response:
    before_meeting = request.app.state.meeting_history_service.get_meeting(meeting_id)
    deleted = request.app.state.meeting_history_service.delete_meeting(meeting_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Meeting record not found.")
    audit_log_service = _audit_log_service(request)
    if audit_log_service is not None:
        audit_log_service.record_event(
            scope=AuditLogService.SCOPE_MEETING,
            meeting_id=meeting_id,
            entity_type="meeting",
            entity_id=meeting_id,
            action="delete",
            field_path=None,
            before={
                "title": before_meeting.title if before_meeting else None,
                "status": before_meeting.status if before_meeting else None,
                "source_type": before_meeting.source_type if before_meeting else None,
                "transcript_count": before_meeting.transcript_count if before_meeting else None,
                "raw_audio_retained": before_meeting.raw_audio_retained if before_meeting else None,
            },
            after=None,
            metadata={"manual": True},
        )
    return Response(status_code=204)
