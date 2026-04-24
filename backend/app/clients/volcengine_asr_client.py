from __future__ import annotations

import asyncio
import gzip
import json
import logging
import struct
from typing import Any
from uuid import uuid4

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, WebSocketException

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

logger = logging.getLogger(__name__)


class VolcengineTranscriptSegment(TranscriptSegment):
    speaker: str | None = None
    speaker_is_final: bool = True
    transcript_is_final: bool = True


def _format_exception_message(exc: Exception) -> str:
    return str(exc).strip() or exc.__class__.__name__


class VolcengineASRStream(ASRStream):
    _PROTOCOL_VERSION = 0x1
    _HEADER_SIZE = 0x1
    _MESSAGE_TYPE_FULL_CLIENT_REQUEST = 0x1
    _MESSAGE_TYPE_AUDIO_ONLY_REQUEST = 0x2
    _MESSAGE_TYPE_FULL_SERVER_RESPONSE = 0x9
    _MESSAGE_TYPE_ERROR = 0xF
    _SERIALIZATION_NONE = 0x0
    _SERIALIZATION_JSON = 0x1
    _COMPRESSION_NONE = 0x0
    _COMPRESSION_GZIP = 0x1
    _FLAGS_NONE = 0x0
    _FLAGS_FINAL = 0x2

    def __init__(
        self,
        *,
        settings: Settings,
        websocket_url: str,
        audio_format: str,
        on_segment: SegmentHandler = noop_segment_handler,
        on_error: ErrorHandler = noop_error_handler,
    ) -> None:
        self._settings = settings
        self._websocket_url = websocket_url
        self._audio_format = audio_format
        self._on_segment = on_segment
        self._on_error = on_error
        self._connection: ClientConnection | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._started = asyncio.Event()
        self._finished = asyncio.Event()
        self._send_lock = asyncio.Lock()
        self._segments: list[TranscriptSegment] = []
        self._seen_segments: set[tuple[float, float, str, str | None]] = set()
        self._latest_partial_key: tuple[float, float, str, str | None] | None = None
        self._error_message: str | None = None
        self._finish_requested = False
        self._closed_by_client = False
        self._request_id = uuid4().hex
        self._connect_id = uuid4().hex

    async def start(self) -> None:
        if not self._settings.volcengine_asr_configured:
            raise RuntimeError(
                "Volcengine ASR is not configured. Set VOLCENGINE_ASR_APP_KEY and VOLCENGINE_ASR_ACCESS_KEY."
            )

        headers = {
            "X-Api-App-Key": self._settings.volcengine_asr_app_key,
            "X-Api-Access-Key": self._settings.volcengine_asr_access_key,
            "X-Api-Resource-Id": self._settings.volcengine_asr_resource_id,
            "X-Api-Connect-Id": self._connect_id,
            "User-Agent": "smart-meeting-assistant/2.0.0",
        }

        try:
            self._connection = await connect(
                self._websocket_url,
                additional_headers=headers,
                open_timeout=10,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=10,
                max_size=2**22,
            )
        except Exception as exc:  # pragma: no cover - network dependent
            raise RuntimeError(
                f"Volcengine ASR WebSocket connection failed: {_format_exception_message(exc)}"
            ) from exc

        self._reader_task = asyncio.create_task(self._read_events())
        await self._send_full_client_request()
        try:
            await asyncio.wait_for(self._started.wait(), timeout=10)
        except asyncio.TimeoutError as exc:
            await self.aclose()
            raise RuntimeError("Volcengine ASR did not acknowledge startup in time.") from exc

        if self._error_message:
            raise RuntimeError(self._error_message)

    async def send_audio(self, audio_chunk: bytes) -> None:
        if not audio_chunk:
            return
        if self._error_message:
            raise RuntimeError(self._error_message)
        if self._connection is None:
            raise RuntimeError("Volcengine ASR stream is not started.")
        await self._started.wait()
        await self._send_audio_request(audio_chunk, is_final=False)

    async def finish(self) -> list[TranscriptSegment]:
        if self._connection is None:
            return list(self._segments)

        self._finish_requested = True
        await self._send_audio_request(b"", is_final=True)
        try:
            await asyncio.wait_for(self._finished.wait(), timeout=30)
        except asyncio.TimeoutError as exc:
            raise RuntimeError("Volcengine ASR did not finish in time.") from exc

        if self._connection is not None:
            self._closed_by_client = True
            await self._connection.close()
            self._connection = None
        if self._reader_task is not None:
            await self._reader_task

        if self._error_message:
            raise RuntimeError(self._error_message)
        return list(self._segments)

    async def aclose(self) -> None:
        if self._connection is not None:
            self._closed_by_client = True
            await self._connection.close()
            self._connection = None
        if self._reader_task is not None and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

    async def _send_full_client_request(self) -> None:
        payload = {
            "user": {"uid": self._request_id},
            "audio": {
                "format": self._audio_format,
                "rate": self._settings.sample_rate,
                "bits": 16,
                "channel": self._settings.audio_channels,
            },
            "request": {
                "model_name": "bigmodel",
                "enable_itn": True,
                "enable_punc": True,
                "enable_ddc": False,
                "show_utterances": True,
                "result_type": "single",
                "enable_nonstream": True,
                "enable_speaker_info": True,
                "ssd_version": self._settings.volcengine_asr_ssd_version,
            },
        }
        await self._send_frame(
            message_type=self._MESSAGE_TYPE_FULL_CLIENT_REQUEST,
            flags=self._FLAGS_NONE,
            serialization=self._SERIALIZATION_JSON,
            compression=self._COMPRESSION_GZIP,
            payload=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )

    async def _send_audio_request(self, audio_chunk: bytes, *, is_final: bool) -> None:
        await self._send_frame(
            message_type=self._MESSAGE_TYPE_AUDIO_ONLY_REQUEST,
            flags=self._FLAGS_FINAL if is_final else self._FLAGS_NONE,
            serialization=self._SERIALIZATION_NONE,
            compression=self._COMPRESSION_GZIP,
            payload=audio_chunk,
        )

    async def _send_frame(
        self,
        *,
        message_type: int,
        flags: int,
        serialization: int,
        compression: int,
        payload: bytes,
    ) -> None:
        if self._connection is None:
            raise RuntimeError("Volcengine ASR stream is not connected.")
        header = bytes(
            [
                (self._PROTOCOL_VERSION << 4) | self._HEADER_SIZE,
                (message_type << 4) | flags,
                (serialization << 4) | compression,
                0x00,
            ]
        )
        payload_bytes = gzip.compress(payload) if compression == self._COMPRESSION_GZIP else payload
        frame = header + struct.pack(">I", len(payload_bytes)) + payload_bytes
        async with self._send_lock:
            await self._connection.send(frame)

    async def _read_events(self) -> None:
        if self._connection is None:
            return

        try:
            async for raw_message in self._connection:
                if not isinstance(raw_message, bytes):
                    continue
                await self._handle_frame(raw_message)
        except ConnectionClosed as exc:
            if (
                not self._finished.is_set()
                and not self._error_message
                and not self._finish_requested
                and not self._closed_by_client
            ):
                self._error_message = f"Volcengine ASR connection closed unexpectedly: {exc}"
                await self._on_error(self._error_message)
            else:
                logger.info("Volcengine ASR connection closed for %s: %s", self._connect_id, exc)
        except WebSocketException as exc:
            if not self._error_message:
                self._error_message = f"Volcengine ASR WebSocket failed: {_format_exception_message(exc)}"
                await self._on_error(self._error_message)
        finally:
            self._finished.set()

    async def _handle_frame(self, frame: bytes) -> None:
        if len(frame) < 8:
            return
        message_type = frame[1] >> 4
        flags = frame[1] & 0x0F
        serialization = frame[2] >> 4
        compression = frame[2] & 0x0F

        if message_type == self._MESSAGE_TYPE_ERROR:
            if len(frame) < 12:
                self._error_message = "Volcengine ASR returned a truncated error frame."
                self._finished.set()
                await self._on_error(self._error_message)
                return
            error_code = struct.unpack(">I", frame[4:8])[0]
            payload_size = struct.unpack(">I", frame[8:12])[0]
            payload = frame[12 : 12 + payload_size]
            if compression == self._COMPRESSION_GZIP:
                payload = gzip.decompress(payload)
            if serialization == self._SERIALIZATION_JSON:
                try:
                    payload_json = json.loads(payload.decode("utf-8"))
                    message = str(
                        payload_json.get("error")
                        or payload_json.get("message")
                        or payload_json
                    ).strip()
                except json.JSONDecodeError:
                    message = payload.decode("utf-8", errors="ignore").strip()
            else:
                message = payload.decode("utf-8", errors="ignore").strip()
            message = message or "Unknown Volcengine ASR error."
            self._error_message = f"{error_code}: {message}"
            self._finished.set()
            await self._on_error(self._error_message)
            return

        if message_type != self._MESSAGE_TYPE_FULL_SERVER_RESPONSE:
            return

        offset = 4
        if flags in (0x1, 0x3):
            if len(frame) < offset + 4:
                return
            sequence = struct.unpack(">i", frame[offset : offset + 4])[0]
            offset += 4
        else:
            sequence = 0

        if len(frame) < offset + 4:
            return
        payload_size = struct.unpack(">I", frame[offset : offset + 4])[0]
        offset += 4
        payload = frame[offset : offset + payload_size]
        if compression == self._COMPRESSION_GZIP:
            payload = gzip.decompress(payload)

        if serialization == self._SERIALIZATION_JSON:
            try:
                message = json.loads(payload.decode("utf-8"))
            except json.JSONDecodeError:
                logger.warning("Volcengine ASR returned non-JSON payload: %r", payload[:200])
                return
        else:
            return

        if not self._started.is_set():
            self._started.set()

        code = message.get("code")
        if code not in (None, 1000, 20000000):
            error_message = str(message.get("message", "")).strip() or "Volcengine ASR request failed."
            self._error_message = f"{code}: {error_message}"
            self._finished.set()
            await self._on_error(self._error_message)
            return

        await self._emit_segments(message)

        if sequence < 0 or flags in (0x2, 0x3):
            self._finished.set()

    async def _emit_segments(self, message: dict[str, Any]) -> None:
        results = self._normalize_results(message.get("result"))
        for item in results:
            utterances = item.get("utterances") or []
            for utterance in utterances:
                text = str(utterance.get("text", "")).strip()
                if not text:
                    continue
                is_definite = bool(utterance.get("definite", False))
                start_time = float(utterance.get("start_time", 0)) / 1000.0
                end_time = float(utterance.get("end_time", 0)) / 1000.0
                speaker = self._extract_speaker(utterance)
                if not is_definite:
                    partial_key = (start_time, end_time, text, speaker)
                    if partial_key == self._latest_partial_key:
                        continue
                    self._latest_partial_key = partial_key
                    await self._on_segment(
                        VolcengineTranscriptSegment(
                            text=text,
                            start=start_time,
                            end=end_time,
                            speaker=speaker,
                            speaker_is_final=False,
                            transcript_is_final=False,
                        )
                    )
                    continue

                self._latest_partial_key = None
                segment_key = (start_time, end_time, text, speaker)
                if segment_key in self._seen_segments:
                    continue
                self._seen_segments.add(segment_key)
                segment = VolcengineTranscriptSegment(
                    text=text,
                    start=start_time,
                    end=end_time,
                    speaker=speaker,
                    speaker_is_final=True,
                    transcript_is_final=True,
                )
                self._segments.append(segment)
                await self._on_segment(segment)

    def _normalize_results(self, result: Any) -> list[dict[str, Any]]:
        if result is None:
            return []
        if isinstance(result, dict):
            return [result]
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
        logger.debug("Volcengine ASR returned unsupported result payload: %r", result)
        return []

    def _extract_speaker(self, utterance: dict[str, Any]) -> str | None:
        speaker = utterance.get("speaker")
        if speaker:
            return self._normalize_speaker(speaker)

        for container_key in ("additions", "attribute"):
            container = utterance.get(container_key)
            if isinstance(container, dict):
                if container.get("speaker") is not None:
                    return self._normalize_speaker(container["speaker"])
                if container.get("speaker_id") is not None:
                    return self._normalize_speaker(container["speaker_id"])

        words = utterance.get("words") or []
        for word in words:
            if not isinstance(word, dict):
                continue
            if word.get("speaker") is not None:
                return self._normalize_speaker(word["speaker"])
            if word.get("speaker_id") is not None:
                return self._normalize_speaker(word["speaker_id"])
            for container_key in ("additions", "attribute"):
                container = word.get(container_key)
                if isinstance(container, dict):
                    if container.get("speaker") is not None:
                        return self._normalize_speaker(container["speaker"])
                    if container.get("speaker_id") is not None:
                        return self._normalize_speaker(container["speaker_id"])
        return None

    def _normalize_speaker(self, raw_speaker: Any) -> str:
        raw = str(raw_speaker).strip()
        if raw.isdigit():
            return f"Speaker {int(raw) + 1}"
        return raw or "Unknown"


class VolcengineASRClient(ASRClient):
    provider_name = "volcengine"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def is_configured(self) -> bool:
        return self._settings.volcengine_asr_configured

    async def aclose(self) -> None:
        return

    def create_pcm_stream(
        self,
        *,
        on_segment: SegmentHandler = noop_segment_handler,
        on_error: ErrorHandler = noop_error_handler,
    ) -> VolcengineASRStream:
        return VolcengineASRStream(
            settings=self._settings,
            websocket_url=self._settings.volcengine_asr_ws_url,
            audio_format="pcm",
            on_segment=on_segment,
            on_error=on_error,
        )

    async def transcribe_wav(self, audio_data: bytes) -> list[TranscriptSegment]:
        collected_segments: list[TranscriptSegment] = []
        error_messages: list[str] = []

        async def on_segment(segment: TranscriptSegment) -> None:
            collected_segments.append(segment)

        async def on_error(message: str) -> None:
            error_messages.append(message)

        stream = VolcengineASRStream(
            settings=self._settings,
            websocket_url=self._settings.volcengine_asr_nostream_ws_url,
            audio_format="wav",
            on_segment=on_segment,
            on_error=on_error,
        )
        try:
            await stream.start()
            for start_index in range(0, len(audio_data), 8192):
                await stream.send_audio(audio_data[start_index : start_index + 8192])
            segments = await stream.finish()
        finally:
            await stream.aclose()

        if error_messages:
            raise RuntimeError(error_messages[-1])
        return segments
