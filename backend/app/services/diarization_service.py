from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import Any

from app.core.config import Settings
from app.schemas.transcript import TranscriptItem
from app.services.speaker_service import SpeakerService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiarizationTurn:
    start: float
    end: float
    speaker_label: str


@dataclass(frozen=True)
class DiarizationResult:
    succeeded: bool
    turns: list[DiarizationTurn]


class DiarizationService:
    def __init__(self, settings: Settings, speaker_service: SpeakerService) -> None:
        self._settings = settings
        self._speaker_service = speaker_service
        self._pipeline: Any | None = None
        self._load_failed = False
        self._load_lock = asyncio.Lock()

    @property
    def is_enabled(self) -> bool:
        return self._settings.diarization_mode == "offline"

    async def diarize_audio_file(self, audio_path: Path) -> DiarizationResult:
        if not self.is_enabled:
            return DiarizationResult(succeeded=False, turns=[])

        pipeline = await self._get_pipeline()
        if pipeline is None:
            return DiarizationResult(succeeded=False, turns=[])

        try:
            turns = await asyncio.to_thread(self._run_pipeline, pipeline, audio_path)
        except Exception as exc:  # pragma: no cover - model/runtime dependent
            logger.warning("Speaker diarization failed for %s: %s", audio_path, exc)
            return DiarizationResult(succeeded=False, turns=[])

        return DiarizationResult(succeeded=True, turns=turns)

    async def diarize_audio_bytes(
        self,
        audio_data: bytes,
        *,
        suffix: str = ".wav",
    ) -> DiarizationResult:
        if not audio_data:
            return DiarizationResult(succeeded=False, turns=[])

        temp_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        temp_path = Path(temp_file.name)
        try:
            temp_file.write(audio_data)
            temp_file.flush()
            temp_file.close()
            return await self.diarize_audio_file(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)

    def assign_speakers(
        self,
        transcripts: list[TranscriptItem],
        turns: list[DiarizationTurn],
        *,
        speaker_is_final: bool,
    ) -> list[TranscriptItem]:
        normalized_speakers: dict[str, str] = {}
        updated: list[TranscriptItem] = []

        for transcript in transcripts:
            matched_label = self._match_turn_label(transcript, turns)
            if matched_label is None:
                updated.append(
                    self._speaker_service.update_speaker(
                        transcript,
                        speaker=self._speaker_service.UNKNOWN_SPEAKER,
                        speaker_is_final=speaker_is_final,
                    )
                )
                continue

            normalized = normalized_speakers.get(matched_label)
            if normalized is None:
                normalized = f"Speaker {len(normalized_speakers) + 1}"
                normalized_speakers[matched_label] = normalized

            updated.append(
                self._speaker_service.update_speaker(
                    transcript,
                    speaker=normalized,
                    speaker_is_final=speaker_is_final,
                )
            )

        return updated

    async def _get_pipeline(self) -> Any | None:
        if self._pipeline is not None:
            return self._pipeline
        if self._load_failed:
            return None
        if not self._settings.huggingface_token.strip():
            logger.warning(
                "Speaker diarization is enabled but HUGGINGFACE_TOKEN is missing; falling back to Unknown speakers."
            )
            self._load_failed = True
            return None

        async with self._load_lock:
            if self._pipeline is not None:
                return self._pipeline
            if self._load_failed:
                return None

            try:
                self._pipeline = await asyncio.to_thread(self._load_pipeline)
            except Exception as exc:  # pragma: no cover - environment dependent
                logger.warning(
                    "Failed to initialize speaker diarization pipeline; falling back to Unknown speakers: %s",
                    exc,
                )
                self._load_failed = True
                return None

        return self._pipeline

    def _load_pipeline(self) -> Any:
        import torch
        from pyannote.audio import Pipeline

        pipeline = Pipeline.from_pretrained(
            self._settings.diarization_model,
            token=self._settings.huggingface_token,
        )
        device_name = "cuda" if torch.cuda.is_available() else "cpu"
        pipeline.to(torch.device(device_name))
        return pipeline

    def _run_pipeline(self, pipeline: Any, audio_path: Path) -> list[DiarizationTurn]:
        output = pipeline(str(audio_path))
        speaker_diarization = getattr(output, "speaker_diarization", output)

        turns: list[DiarizationTurn] = []
        if hasattr(speaker_diarization, "itertracks"):
            for turn, _, speaker_label in speaker_diarization.itertracks(yield_label=True):
                turns.append(
                    DiarizationTurn(
                        start=float(turn.start),
                        end=float(turn.end),
                        speaker_label=str(speaker_label),
                    )
                )
            return turns

        for item in speaker_diarization:
            if len(item) == 2:
                turn, speaker_label = item
            else:
                turn, _, speaker_label = item
            turns.append(
                DiarizationTurn(
                    start=float(turn.start),
                    end=float(turn.end),
                    speaker_label=str(speaker_label),
                )
            )
        return turns

    def _match_turn_label(
        self,
        transcript: TranscriptItem,
        turns: list[DiarizationTurn],
    ) -> str | None:
        best_turn: DiarizationTurn | None = None
        best_overlap = 0.0

        for turn in turns:
            overlap = min(transcript.end, turn.end) - max(transcript.start, turn.start)
            if overlap <= 0:
                continue
            if overlap > best_overlap:
                best_overlap = overlap
                best_turn = turn
                continue
            if best_turn is not None and overlap == best_overlap and turn.start < best_turn.start:
                best_turn = turn

        return best_turn.speaker_label if best_turn is not None else None
