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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    provider = request.query_params.get("provider")
    asr_provider_service = request.app.state.asr_provider_service
    selection = asr_provider_service.resolve_provider(provider)
    try:
        segments = await selection.client.transcribe_wav(wav_audio)
    except RuntimeError as exc:
        fallback = asr_provider_service.resolve_fallback(selection.provider_name)
        if fallback is None:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        segments = await fallback.client.transcribe_wav(wav_audio)
        selection = fallback

    transcripts = [
        request.app.state.speaker_service.assign_speaker(
            segment,
            transcript_index=index,
            speaker=getattr(segment, "speaker", None),
            speaker_is_final=getattr(segment, "speaker_is_final", selection.provider_name == "volcengine"),
        )
        for index, segment in enumerate(segments)
    ]
    if selection.should_run_diarization:
        diarization_result = await request.app.state.diarization_service.diarize_audio_bytes(wav_audio)
        transcripts = request.app.state.diarization_service.assign_speakers(
            transcripts,
            diarization_result.turns,
            speaker_is_final=diarization_result.succeeded,
        )
    return transcripts


@router.post("/api/transcribe", response_model=TranscriptItem)
async def transcribe(request: Request, file: UploadFile = File(...)) -> TranscriptItem:
    transcripts = await _transcribe_upload(request, file)
    if transcripts:
        return transcripts[0]
    return request.app.state.speaker_service.create_empty_transcript()


@router.post("/api/transcribe/batch", response_model=list[TranscriptItem])
async def transcribe_batch(
    request: Request,
    file: UploadFile = File(...),
) -> list[TranscriptItem]:
    return await _transcribe_upload(request, file)
