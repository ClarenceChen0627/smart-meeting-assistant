from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from app.schemas.transcript import TranscriptSegment

SegmentHandler = Callable[[TranscriptSegment], Awaitable[None]]
ErrorHandler = Callable[[str], Awaitable[None]]


async def noop_segment_handler(_: TranscriptSegment) -> None:
    return


async def noop_error_handler(_: str) -> None:
    return


class ASRStream(Protocol):
    async def start(self) -> None: ...

    async def send_audio(self, audio_chunk: bytes) -> None: ...

    async def finish(self) -> list[TranscriptSegment]: ...

    async def aclose(self) -> None: ...


class ASRClient(Protocol):
    provider_name: str

    @property
    def is_configured(self) -> bool: ...

    async def aclose(self) -> None: ...

    def create_pcm_stream(
        self,
        *,
        on_segment: SegmentHandler = noop_segment_handler,
        on_error: ErrorHandler = noop_error_handler,
    ) -> ASRStream: ...

    async def transcribe_wav(self, audio_data: bytes) -> list[TranscriptSegment]: ...
