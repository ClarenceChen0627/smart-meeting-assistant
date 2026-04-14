from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from app.schemas.transcript import TranscriptItem

router = APIRouter()


async def _transcribe_upload(request: Request, file: UploadFile) -> list[TranscriptItem]:
    audio_data = await file.read()
    if not audio_data:
        raise HTTPException(status_code=400, detail="Audio upload is empty.")

    try:
        wav_audio = await request.app.state.audio_codec_service.convert_upload_to_wav(
            audio_data,
            filename=file.filename,
            content_type=file.content_type,
        )
        segments = await request.app.state.asr_client.transcribe_wav(wav_audio)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    transcripts = [
        request.app.state.speaker_service.assign_speaker(segment, transcript_index=index)
        for index, segment in enumerate(segments)
    ]
    return transcripts


@router.post("/api/transcribe", response_model=TranscriptItem)
async def transcribe(request: Request, file: UploadFile = File(...)) -> TranscriptItem:
    transcripts = await _transcribe_upload(request, file)
    if transcripts:
        return transcripts[0]
    return TranscriptItem(speaker="Speaker_A", text="", start=0.0, end=0.0)


@router.post("/api/transcribe/batch", response_model=list[TranscriptItem])
async def transcribe_batch(
    request: Request,
    file: UploadFile = File(...),
) -> list[TranscriptItem]:
    return await _transcribe_upload(request, file)
