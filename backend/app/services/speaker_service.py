from __future__ import annotations

from app.schemas.transcript import TranscriptItem, TranscriptSegment


class SpeakerService:
    UNKNOWN_SPEAKER = "Unknown"

    def assign_speaker(
        self,
        segment: TranscriptSegment,
        *,
        transcript_index: int,
        speaker: str | None = None,
        speaker_is_final: bool = False,
        transcript_is_final: bool = True,
    ) -> TranscriptItem:
        return TranscriptItem(
            transcript_index=transcript_index,
            speaker=self._normalize_speaker(speaker),
            speaker_is_final=speaker_is_final,
            transcript_is_final=transcript_is_final,
            text=segment.text,
            start=segment.start,
            end=segment.end,
        )

    def create_empty_transcript(self) -> TranscriptItem:
        return TranscriptItem(
            transcript_index=0,
            speaker=self.UNKNOWN_SPEAKER,
            speaker_is_final=False,
            transcript_is_final=True,
            text="",
            start=0.0,
            end=0.0,
        )

    def update_speaker(
        self,
        transcript: TranscriptItem,
        *,
        speaker: str,
        speaker_is_final: bool,
    ) -> TranscriptItem:
        return transcript.model_copy(
            update={
                "speaker": self._normalize_speaker(speaker),
                "speaker_is_final": speaker_is_final,
            }
        )

    def update_transcript(
        self,
        transcript: TranscriptItem,
        *,
        text: str,
        start: float,
        end: float,
        speaker: str,
        speaker_is_final: bool,
        transcript_is_final: bool,
    ) -> TranscriptItem:
        return transcript.model_copy(
            update={
                "text": text,
                "start": start,
                "end": end,
                "speaker": self._normalize_speaker(speaker),
                "speaker_is_final": speaker_is_final,
                "transcript_is_final": transcript_is_final,
            }
        )

    def _normalize_speaker(self, speaker: str | None) -> str:
        normalized = (speaker or "").strip()
        return normalized or self.UNKNOWN_SPEAKER
