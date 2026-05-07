from __future__ import annotations

import asyncio

from app.clients.asr_base import (
    ASRClient,
    ASRStream,
    ErrorHandler,
    SegmentHandler,
    noop_error_handler,
    noop_segment_handler,
)
from app.core.config import Settings
from app.schemas.transcript import TranscriptSegment


class DemoTranscriptSegment(TranscriptSegment):
    speaker: str | None = None
    speaker_is_final: bool = True
    transcript_is_final: bool = True


DEMO_TRANSCRIPT_SEGMENTS = (
    DemoTranscriptSegment(
        text="Welcome everyone. Today we need to confirm the launch checklist.",
        start=0.0,
        end=3.2,
        speaker="Speaker 1",
    ),
    DemoTranscriptSegment(
        text="I agree with the plan, but we should call out the integration risk.",
        start=3.4,
        end=7.1,
        speaker="Speaker 2",
    ),
    DemoTranscriptSegment(
        text="I will send the final checklist by Friday and follow up with engineering.",
        start=7.4,
        end=11.2,
        speaker="Speaker 1",
    ),
)


class DemoASRStream(ASRStream):
    def __init__(
        self,
        *,
        settings: Settings,
        on_segment: SegmentHandler,
        on_error: ErrorHandler,
    ) -> None:
        self._settings = settings
        self._on_segment = on_segment
        self._on_error = on_error
        self._sent_count = 0
        self._closed = False

    async def start(self) -> None:
        if not self._settings.demo_mode:
            await self._on_error("Demo ASR is disabled. Set DEMO_MODE=1 to use provider=demo.")
            raise RuntimeError("Demo ASR is disabled.")

    async def send_audio(self, audio_chunk: bytes) -> None:
        if self._closed or not audio_chunk:
            return
        if self._sent_count >= len(DEMO_TRANSCRIPT_SEGMENTS):
            return
        segment = DEMO_TRANSCRIPT_SEGMENTS[self._sent_count]
        self._sent_count += 1
        await asyncio.sleep(0)
        await self._on_segment(segment)

    async def finish(self) -> list[TranscriptSegment]:
        return list(DEMO_TRANSCRIPT_SEGMENTS[: self._sent_count])

    async def aclose(self) -> None:
        self._closed = True


class DemoASRClient(ASRClient):
    provider_name = "demo"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def is_configured(self) -> bool:
        return self._settings.demo_mode

    async def aclose(self) -> None:
        return

    def create_pcm_stream(
        self,
        *,
        on_segment: SegmentHandler = noop_segment_handler,
        on_error: ErrorHandler = noop_error_handler,
    ) -> ASRStream:
        return DemoASRStream(
            settings=self._settings,
            on_segment=on_segment,
            on_error=on_error,
        )

    async def transcribe_wav(self, audio_data: bytes) -> list[TranscriptSegment]:
        if not self.is_configured:
            raise RuntimeError("Demo ASR is disabled. Set DEMO_MODE=1 to use provider=demo.")
        await asyncio.sleep(0)
        return list(DEMO_TRANSCRIPT_SEGMENTS)
