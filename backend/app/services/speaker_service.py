from __future__ import annotations

from app.schemas.transcript import TranscriptItem, TranscriptSegment


class SpeakerService:
    def assign_speaker(
        self,
        segment: TranscriptSegment,
        *,
        transcript_index: int,
    ) -> TranscriptItem:
        return TranscriptItem(
            speaker=self._resolve_speaker(segment.start, transcript_index),
            text=segment.text,
            start=segment.start,
            end=segment.end,
        )

    def _resolve_speaker(self, begin_time: float, transcript_index: int) -> str:
        if begin_time < 10:
            return "Speaker_A"
        if begin_time < 20:
            return "Speaker_B"
        if begin_time < 30:
            return "Speaker_A"
        return "Speaker_A" if transcript_index % 2 == 0 else "Speaker_B"
