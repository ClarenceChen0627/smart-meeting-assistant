from __future__ import annotations

from fastapi import HTTPException, UploadFile

from app.core.config import Settings


def _normalize_content_type(content_type: str | None) -> str:
    return (content_type or "application/octet-stream").split(";", 1)[0].strip().lower()


async def read_validated_upload(file: UploadFile, settings: Settings) -> bytes:
    content_type = _normalize_content_type(file.content_type)
    allowed_types = {item.lower() for item in settings.allowed_upload_content_types}
    if allowed_types and "*" not in allowed_types and content_type not in allowed_types:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported upload content type: {content_type}.",
        )

    audio_data = await file.read()
    if not audio_data:
        raise HTTPException(status_code=400, detail="Audio upload is empty.")
    if len(audio_data) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Audio upload exceeds the configured limit of {settings.max_upload_bytes} bytes.",
        )
    return audio_data
